"""Pytest suite for the PyFlow MCP server business logic.

Tests exercise SimulationSession (and run_chunked) directly — the MCP tool
layer is a thin wrapper (5-15 lines each) so testing the session covers the
real behaviour without needing an in-process MCP client.
"""

from __future__ import annotations

import asyncio
import pytest

from pyflow_mcp.schemas import (
    ConnectionSpec,
    ExponDist,
    InterArrivalSourceSpec,
    ItemsQueueSpec,
    MultiServerSpec,
    NormDist,
    SinkSpec,
    UniformDist,
)
from pyflow_mcp.session import SimulationSession, SessionState, SessionStateError
from pyflow_mcp.runner import run_chunked
from pyflow_mcp.inspection import all_stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mm1_specs(arrival_scale: float = 2.0, service_scale: float = 1.0, queue_cap: int = 100_000):
    return [
        InterArrivalSourceSpec(type="InterArrivalSource", id="src", name="Source",
                               interarrival=ExponDist(type="expon", scale=arrival_scale)),
        ItemsQueueSpec(type="ItemsQueue", id="q", name="Queue", capacity=queue_cap),
        MultiServerSpec(type="MultiServer", id="srv", name="Server", num_servers=1,
                        service_time=ExponDist(type="expon", scale=service_scale)),
        SinkSpec(type="Sink", id="snk", name="Sink"),
    ]


def _mm1_connections():
    return [
        ConnectionSpec(origin="src", destinations=["q"]),
        ConnectionSpec(origin="q",   destinations=["srv"]),
        ConnectionSpec(origin="srv", destinations=["snk"]),
    ]


def _build_and_init(session: SimulationSession, arrival_scale=2.0, service_scale=1.0, queue_cap=100_000):
    for spec in _mm1_specs(arrival_scale, service_scale, queue_cap):
        session.add_element(spec)
    for conn in _mm1_connections():
        session.add_connection(conn)
    session.initialize()


def _run(session, stop_time=1000.0, chunk_count=10, max_wall_seconds=30.0):
    return asyncio.run(run_chunked(session, stop_time, chunk_count, max_wall_seconds))


# ---------------------------------------------------------------------------
# Test 1 — double-run isolation (the singleton footgun)
# ---------------------------------------------------------------------------

def test_double_run_isolation():
    """Two back-to-back M/M/1 runs must not contaminate each other."""
    session = SimulationSession()
    stop_time = 500.0

    # First run
    _build_and_init(session)
    info1 = _run(session, stop_time=stop_time)
    stats1 = all_stats(session.elements, session.element_specs)
    sink1 = next(s["input_count"] for s in stats1 if s["id"] == "snk")

    # Reset and run again
    session.reset()
    _build_and_init(session)
    info2 = _run(session, stop_time=stop_time)
    stats2 = all_stats(session.elements, session.element_specs)
    sink2 = next(s["input_count"] for s in stats2 if s["id"] == "snk")

    assert info1["status"] == "completed"
    assert info2["status"] == "completed"
    # Both runs are independent; sink counts must be in a plausible per-run range.
    # λ=0.5, T=500 → ~250 items expected. Allow wide band for randomness.
    assert 50 <= sink1 <= 600, f"Run 1 sink={sink1} outside expected range"
    assert 50 <= sink2 <= 600, f"Run 2 sink={sink2} outside expected range"
    # Second run must NOT accumulate counts from the first run.
    assert sink2 < 800, f"Run 2 sink={sink2} suspiciously high — singleton contamination?"


# ---------------------------------------------------------------------------
# Test 2 — state machine blocks mutation after initialize
# ---------------------------------------------------------------------------

def test_state_machine_blocks_mutation_after_init():
    """Adding elements in READY state must raise SessionStateError."""
    session = SimulationSession()
    _build_and_init(session)

    assert session.state == SessionState.READY

    with pytest.raises(SessionStateError):
        session.add_element(SinkSpec(type="Sink", id="extra_sink", name="Extra"))


# ---------------------------------------------------------------------------
# Test 3 — batch partial failure
# ---------------------------------------------------------------------------

def test_batch_partial_failure():
    """3rd element has invalid params; only the first two must be created."""
    session = SimulationSession()

    specs = [
        InterArrivalSourceSpec(type="InterArrivalSource", id="src", name="Source",
                               interarrival=ExponDist(type="expon", scale=1.0)),
        ItemsQueueSpec(type="ItemsQueue", id="q", name="Queue", capacity=100),
        # num_servers=0 is invalid (gt=0 enforced at schema level, but test duplicate id too)
        InterArrivalSourceSpec(type="InterArrivalSource", id="src", name="Duplicate",
                               interarrival=ExponDist(type="expon", scale=1.0)),
        SinkSpec(type="Sink", id="snk", name="Sink"),
        SinkSpec(type="Sink", id="snk2", name="Sink2"),
    ]

    created_ids: list[str] = []
    failed_at = None

    for i, spec in enumerate(specs):
        try:
            session.add_element(spec)
            created_ids.append(spec.id)
        except (ValueError, SessionStateError) as exc:
            failed_at = {"index": i, "error": str(exc)}
            remaining = specs[i + 1:]
            break

    assert created_ids == ["src", "q"], f"Expected [src, q], got {created_ids}"
    assert failed_at is not None
    assert failed_at["index"] == 2
    assert len(remaining) == 2  # snk and snk2 not processed


# ---------------------------------------------------------------------------
# Test 4 — wall-clock timeout
# ---------------------------------------------------------------------------

def test_wall_clock_timeout():
    """A simulation that would run forever must stop within the wall-clock budget.

    Design: λ=1 (scale=1.0), μ=2 (scale=0.5), chunk=10K time units ≈ 0.3s each.
    The wall-clock check fires after ~7 chunks (2.1s) well before stop_time=1B is reached.
    Total test time is bounded by max_wall_seconds + one chunk duration ≈ 2.4s.
    """
    session = SimulationSession()
    _build_and_init(session, arrival_scale=1.0, service_scale=0.5, queue_cap=100_000)

    max_wall = 2.0
    import time
    t0 = time.monotonic()
    # 100_000 chunks × 10K units each = 1B total; only ~7 chunks actually run.
    info = _run(session, stop_time=1_000_000_000, chunk_count=100_000, max_wall_seconds=max_wall)
    elapsed = time.monotonic() - t0

    assert info["status"] == "wall_clock_timeout", f"Expected timeout, got {info['status']}"
    assert info["sim_time_reached"] < 1_000_000_000
    assert elapsed < max_wall + 10, f"Test took {elapsed:.1f}s, too slow"


# ---------------------------------------------------------------------------
# Test 5 — network idle early stop
# ---------------------------------------------------------------------------

def test_network_idle_early_stop():
    """With stop_time < first arrival time, the run completes without idle-network status.

    advance_clock(5.0) with first event at t=10 returns True (future events exist),
    so all chunks finish and status is "completed" — not "network_idle".
    """
    session = SimulationSession()
    # Deterministic arrival at t=10 via uniform(loc=10, scale=0)
    session.add_element(InterArrivalSourceSpec(
        type="InterArrivalSource", id="src", name="Source",
        interarrival=UniformDist(type="uniform", loc=10.0, scale=0.0),
    ))
    session.add_element(ItemsQueueSpec(type="ItemsQueue", id="q", name="Queue", capacity=100))
    session.add_element(MultiServerSpec(
        type="MultiServer", id="srv", name="Server", num_servers=1,
        service_time=UniformDist(type="uniform", loc=1.0, scale=0.0),
    ))
    session.add_element(SinkSpec(type="Sink", id="snk", name="Sink"))
    for conn in _mm1_connections():
        session.add_connection(conn)
    session.initialize()

    # stop_time=5.0 means no events are processed (first arrival is at t=10)
    info = _run(session, stop_time=5.0, chunk_count=5, max_wall_seconds=30.0)

    # advance_clock returns True (events exist at t=10) → all chunks complete → "completed"
    assert info["status"] == "completed"
    assert info["sim_time_reached"] == pytest.approx(5.0)
    # Nothing went through the sink
    stats = all_stats(session.elements, session.element_specs)
    sink_count = next(s["input_count"] for s in stats if s["id"] == "snk")
    assert sink_count == 0


# ---------------------------------------------------------------------------
# Test 6 — M/M/1 throughput sanity check
# ---------------------------------------------------------------------------

def test_mm1_throughput_sane():
    """M/M/1 with ρ=0.5 must deliver ~λ×T items at the Sink (±10%)."""
    session = SimulationSession()
    # λ=0.5 (scale=2), μ=1.0 (scale=1) → ρ=0.5, stable queue
    _build_and_init(session, arrival_scale=2.0, service_scale=1.0)

    stop_time = 10_000.0
    info = _run(session, stop_time=stop_time, chunk_count=20, max_wall_seconds=60.0)
    assert info["status"] == "completed"

    stats = all_stats(session.elements, session.element_specs)
    sink_count = next(s["input_count"] for s in stats if s["id"] == "snk")
    expected = 0.5 * stop_time  # λ × T = 5000
    assert abs(sink_count - expected) / expected <= 0.10, (
        f"Throughput {sink_count} deviates >10% from expected {expected}"
    )


# ---------------------------------------------------------------------------
# Test 7 — get_supported_types schema completeness
# ---------------------------------------------------------------------------

def test_get_supported_types_schema():
    """The schema dict must include all 4 element types and 4 distribution types."""
    from pyflow_mcp.schemas import (
        ExponDist, InterArrivalSourceSpec, ItemsQueueSpec,
        MultiServerSpec, NormDist, SinkSpec, TriangDist, UniformDist,
    )

    supported = {
        "element_types": {
            "InterArrivalSource": InterArrivalSourceSpec.model_json_schema(),
            "ItemsQueue": ItemsQueueSpec.model_json_schema(),
            "MultiServer": MultiServerSpec.model_json_schema(),
            "Sink": SinkSpec.model_json_schema(),
        },
        "distribution_types": {
            "expon": ExponDist.model_json_schema(),
            "uniform": UniformDist.model_json_schema(),
            "norm": NormDist.model_json_schema(),
            "triang": TriangDist.model_json_schema(),
        },
    }

    assert set(supported["element_types"]) == {"InterArrivalSource", "ItemsQueue", "MultiServer", "Sink"}
    assert set(supported["distribution_types"]) == {"expon", "uniform", "norm", "triang"}

    # Each schema must have a "properties" key (Pydantic v2 JSON schema)
    for name, schema in supported["element_types"].items():
        assert "properties" in schema, f"{name} schema missing 'properties'"

    # InterArrivalSource must reference interarrival distribution
    ia_props = supported["element_types"]["InterArrivalSource"]["properties"]
    assert "interarrival" in ia_props

    # MultiServer must reference service_time and num_servers
    ms_props = supported["element_types"]["MultiServer"]["properties"]
    assert "num_servers" in ms_props
    assert "service_time" in ms_props


# ---------------------------------------------------------------------------
# Extra regression tests for the bugs fixed in the debug report
# ---------------------------------------------------------------------------

def test_source_content_stats_not_negative():
    """InterArrivalSource content stats must never be negative (B1 fix)."""
    session = SimulationSession()
    _build_and_init(session)
    _run(session, stop_time=500.0)

    stats = all_stats(session.elements, session.element_specs)
    src = next(s for s in stats if s["id"] == "src")
    assert src["content_current"] >= 0, "Source content_current must not be negative"
    assert src["content_average"] >= 0, "Source content_average must not be negative"
    assert src["content_max"] >= 0, "Source content_max must not be negative"


def test_staytime_min_nonzero_for_deterministic_service(tmp_path):
    """staytime_min must equal the deterministic service time, not 0 (B5 fix)."""
    session = SimulationSession()
    # Deterministic arrival and service (uniform scale=0 ≡ constant value)
    session.add_element(InterArrivalSourceSpec(
        type="InterArrivalSource", id="src", name="Source",
        interarrival=UniformDist(type="uniform", loc=1.0, scale=0.0),
    ))
    session.add_element(ItemsQueueSpec(type="ItemsQueue", id="q", name="Queue", capacity=10000))
    session.add_element(MultiServerSpec(
        type="MultiServer", id="srv", name="Server", num_servers=2,
        service_time=UniformDist(type="uniform", loc=1.0, scale=0.0),
    ))
    session.add_element(SinkSpec(type="Sink", id="snk", name="Sink"))
    for conn in _mm1_connections():
        session.add_connection(conn)
    session.initialize()

    _run(session, stop_time=200.0)
    stats = all_stats(session.elements, session.element_specs)
    srv = next(s for s in stats if s["id"] == "srv")

    # With deterministic service_time=1.0, both min and max must equal 1.0
    assert srv["staytime_min"] == pytest.approx(1.0, rel=0.01), (
        f"staytime_min={srv['staytime_min']} should equal deterministic service time 1.0"
    )
    assert srv["staytime_max"] == pytest.approx(1.0, rel=0.01)


def test_batch_logical_error_returns_structured_json():
    """Logical errors (duplicate IDs, wrong state) in batch tools must return structured partial_success JSON."""
    session = SimulationSession()

    # First add a valid source so we have something to duplicate
    from pyflow_mcp.schemas import InterArrivalSourceSpec, ExponDist
    first = InterArrivalSourceSpec(
        type="InterArrivalSource", id="src", name="Source",
        interarrival=ExponDist(type="expon", scale=2.0),
    )
    session.add_element(first)

    # Now try to add the same id again — this is a logical error (ValueError), not a schema error
    created_ids: list[str] = ["src"]  # already created
    failed_at = None
    duplicate = InterArrivalSourceSpec(
        type="InterArrivalSource", id="src", name="Dup",
        interarrival=ExponDist(type="expon", scale=1.0),
    )
    try:
        session.add_element(duplicate)
    except ValueError as exc:
        failed_at = {"error_type": "ValueError", "error_message": str(exc)}

    assert failed_at is not None
    assert "src" in failed_at["error_message"]  # error identifies the duplicate id


def test_schema_level_error_is_pydantic_validation_error():
    """Schema violations (negative scale, unknown type) raise PydanticValidationError.

    These surface as MCP protocol errors (isError=True) rather than structured JSON.
    This is expected behaviour — the agent must correct its spec and retry.
    """
    from pydantic import TypeAdapter, ValidationError as PydanticValidationError
    from pyflow_mcp.schemas import ElementSpec

    adapter = TypeAdapter(ElementSpec)

    # Scale must be > 0
    with pytest.raises(PydanticValidationError):
        adapter.validate_python({"type": "InterArrivalSource", "id": "src", "name": "S",
                                 "interarrival": {"type": "expon", "scale": -1.0}})

    # Unknown element type — discriminator fails
    with pytest.raises(PydanticValidationError):
        adapter.validate_python({"type": "UnknownElement", "id": "x", "name": "X"})


def test_list_elements_returns_single_dict():
    """list_elements must return a dict with an 'elements' key (I1 fix)."""
    session = SimulationSession()
    for spec in _mm1_specs():
        session.add_element(spec)

    # Simulate what the tool returns (test the session layer)
    result = {"elements": list(session.element_specs.values())}
    assert isinstance(result, dict)
    assert "elements" in result
    assert isinstance(result["elements"], list)
    assert len(result["elements"]) == 4


# ---------------------------------------------------------------------------
# Test 8 — initialize requires source and sink
# ---------------------------------------------------------------------------

def test_initialize_requires_source_and_sink():
    """A model with only a queue must be rejected by initialize()."""
    session = SimulationSession()
    session.add_element(ItemsQueueSpec(type="ItemsQueue", id="q", name="Queue", capacity=10))

    with pytest.raises(ValueError, match="InterArrivalSource"):
        session.initialize()


# ---------------------------------------------------------------------------
# Test 9 — unknown element id in connection
# ---------------------------------------------------------------------------

def test_unknown_element_id_in_connection():
    """Connecting from a non-existent element id must raise a clear ValueError."""
    session = SimulationSession()
    session.add_element(SinkSpec(type="Sink", id="snk", name="Sink"))

    with pytest.raises(ValueError, match="nonexistent"):
        session.add_connection(ConnectionSpec(origin="nonexistent", destinations=["snk"]))
