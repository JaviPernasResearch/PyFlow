"""FastMCP server — exposes PyFlow simulation to AI agents as MCP tool calls.

Run with:
    mcp dev pyflow_mcp/server.py          # MCP Inspector (stdio)
    python pyflow_mcp/server.py           # SSE/HTTP directly (Langflow, n8n, etc.)

Every tool docstring is what the agent reads; keep them precise and include a
JSON example so the agent knows the expected payload shape.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import AsyncIterator

from pydantic import TypeAdapter, ValidationError as PydanticValidationError

from mcp.server.fastmcp import Context, FastMCP

from .experiments import capture_enabled, capture_model
from .inspection import all_stats
from .runner import run_chunked
from .schemas import ConnectionSpec, ElementSpec, ScheduleSourceSpec
from .session import SessionState, SessionStateError, SimulationSession

logger = logging.getLogger(__name__)

# Pre-built TypeAdapters — used only for per-item re-validation inside tools
# (the tool parameters themselves use the typed annotations for rich schema).
_ELEMENT_SPEC_ADAPTER = TypeAdapter(ElementSpec)
_CONNECTION_SPEC_ADAPTER = TypeAdapter(ConnectionSpec)


# ---------------------------------------------------------------------------
# Lifespan — one SimulationSession per server process
# ---------------------------------------------------------------------------

@dataclass
class AppContext:
    session: SimulationSession


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    yield AppContext(session=SimulationSession())


mcp = FastMCP("PyFlow Simulator", lifespan=lifespan)


def _session(ctx: Context) -> SimulationSession:
    return ctx.request_context.lifespan_context.session


# ---------------------------------------------------------------------------
# Helper — structured error response
# ---------------------------------------------------------------------------

def _error(error_type: str, message: str) -> dict:
    return {"error": {"type": error_type, "message": message}}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def new_model(ctx: Context) -> dict:
    """Reset the simulator and start a fresh empty model.

    Always succeeds. Call this before building a new model or after a run to
    reuse the server for another experiment. Can be called from any state
    (building, ready, or completed).

    Example response:
        {"state": "building", "message": "Model reset. Ready to add elements."}
    """
    _session(ctx).reset()
    return {"state": "building", "message": "Model reset. Ready to add elements."}


@mcp.tool()
def create_elements_batch(elements: list[ElementSpec], ctx: Context, verbose: bool = False) -> dict:
    """Add multiple elements to the model in one call.

    Processing is sequential. On the first failure the tool stops and returns a
    partial_success response so the agent can inspect the error and retry.

    Logical errors (duplicate IDs, wrong session state) are returned as
    structured JSON with a failed_at block. Schema-level errors (unknown type
    name, missing required field, constraint violation) are returned by the MCP
    protocol as tool errors — correct the element spec and retry.

    Supported element types:
      InterArrivalSource — continuous random arrivals; optional item_type + labels
                           stamp every generated item (use with label_expr servers).
      ScheduleSource     — finite job list released at specified times; each job
                           carries its own labels (use for known job sets).
      ItemsQueue         — finite-capacity FIFO buffer.
      MultiServer        — N parallel servers; service_time can be a distribution
                           OR a label_expr that reads the delay from an item label.
      Sink               — terminal absorber; always tracks per-type item counts.

    Supported distribution types: expon, uniform, norm, triang.
    Call get_supported_types for the full JSON schema of each type.

    Args:
        elements: List of typed element specs.
        verbose:  If true, includes the full model snapshot in the response.
                  Default false (use describe_model to inspect the model separately).

    Example input (continuous sources with typed items + label-based server):
        [
          {"type": "InterArrivalSource", "id": "src1", "name": "Source1",
           "interarrival": {"type": "uniform", "loc": 10, "scale": 0},
           "item_type": "Type1", "labels": {"PT1": "10", "PT2": "5"}},
          {"type": "ItemsQueue", "id": "buf1", "name": "Buffer1", "capacity": 10},
          {"type": "MultiServer", "id": "p1", "name": "Processor1", "num_servers": 1,
           "service_time": {"type": "label_expr", "expression": "item.get_label_value('PT1')"}},
          {"type": "Sink", "id": "snk", "name": "Sink"}
        ]

    Example input (schedule source — 8 jobs at t=0):
        [
          {"type": "ScheduleSource", "id": "src", "name": "Source",
           "jobs": [
             {"time": 0, "name": "J1", "qty": 1, "labels": {"PT1": 10, "PT2": 5}},
             {"time": 0, "name": "J2", "qty": 1, "labels": {"PT1": 5,  "PT2": 15}}
           ]},
          {"type": "ItemsQueue", "id": "buf", "name": "Buffer", "capacity": 20},
          {"type": "MultiServer", "id": "p1", "name": "Processor1", "num_servers": 1,
           "service_time": {"type": "label_expr", "expression": "item.get_label_value('PT1')"}},
          {"type": "Sink", "id": "snk", "name": "Sink"}
        ]

    Example response (success):
        {"status": "success", "created_ids": ["src", "buf", "p1", "snk"],
         "failed_at": null, "remaining": []}
    """
    session = _session(ctx)
    created_ids: list[str] = []

    for i, spec in enumerate(elements):
        try:
            session.add_element(spec)
            created_ids.append(spec.id)
        except (ValueError, SessionStateError) as exc:
            failed = {
                "status": "partial_success",
                "created_ids": created_ids,
                "failed_at": {
                    "phase": "elements",
                    "index": i,
                    "spec": spec.model_dump(),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                "remaining": [s.model_dump() for s in elements[i + 1:]],
            }
            if verbose:
                failed["current_model"] = session.snapshot()
            return failed

    result = {
        "status": "success",
        "created_ids": created_ids,
        "failed_at": None,
        "remaining": [],
    }
    if verbose:
        result["current_model"] = session.snapshot()
    return result


@mcp.tool()
def connect_batch(connections: list[ConnectionSpec], ctx: Context, verbose: bool = False) -> dict:
    """Wire elements together with directed connections.

    All destinations for a given origin must appear in a single ConnectionSpec
    so PyFlow receives the full destination list when calling connect(). This is
    required for strategies like RoundRobin to work across the whole destination
    set.

    When there is only one destination, FirstAvailable and RoundRobin are
    equivalent — the strategy only matters when routing to multiple destinations.

    Supported strategies: FirstAvailable (default), RoundRobin.

    Args:
        connections: List of connection specs.
        verbose:     If true, includes the full model snapshot in the response.

    Example input:
        [
          {"origin": "src",  "destinations": ["q"],   "strategy": "FirstAvailable"},
          {"origin": "q",    "destinations": ["srv"],  "strategy": "FirstAvailable"},
          {"origin": "srv",  "destinations": ["snk"],  "strategy": "FirstAvailable"}
        ]
    """
    session = _session(ctx)
    connected: list[dict] = []

    for i, conn in enumerate(connections):
        try:
            session.add_connection(conn)
            connected.append(conn.model_dump())
        except (ValueError, SessionStateError) as exc:
            failed = {
                "status": "partial_success",
                "connected": connected,
                "failed_at": {
                    "phase": "connections",
                    "index": i,
                    "spec": conn.model_dump(),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                "remaining": [c.model_dump() for c in connections[i + 1:]],
            }
            if verbose:
                failed["current_model"] = session.snapshot()
            return failed

    result = {
        "status": "success",
        "connected": connected,
        "failed_at": None,
        "remaining": [],
    }
    if verbose:
        result["current_model"] = session.snapshot()
    return result


@mcp.tool()
def initialize_model(ctx: Context) -> dict:
    """Freeze the model topology and start all elements.

    Must be called after all create_elements_batch and connect_batch calls and
    before run_experiment. Validates that the model has at least one
    InterArrivalSource and one Sink.

    Transitions state: BUILDING → READY.
    """
    session = _session(ctx)
    try:
        session.initialize()
    except (ValueError, SessionStateError) as exc:
        return _error(type(exc).__name__, str(exc))
    snapshot = session.snapshot()

    # Harness-only side effect: when experiment capture is enabled, persist the
    # frozen model to disk for later structural scoring. Never affects the tool
    # response and never raises into the agent.
    if capture_enabled():
        try:
            path = capture_model(snapshot)
            logger.info("Experiment capture: wrote model snapshot to %s", path)
        except Exception:  # pragma: no cover - capture must never break a run
            logger.exception("Experiment capture failed (ignored)")

    return snapshot


@mcp.tool()
async def run_experiment(
    stop_time: float,
    ctx: Context,
    chunk_count: int = 20,
    max_wall_seconds: float = 25.0,
) -> dict:
    """Run the simulation up to *stop_time* model-time units.

    The run is divided into *chunk_count* equal slices so progress can be
    reported and the wall-clock budget checked between slices. The wall-clock
    check also fires after each slice completes, so even a single slow slice
    cannot silently exceed the budget.

    Requires READY state (call initialize_model first).

    Possible values for run_info.status:
      "completed"          — all chunks ran to stop_time without issue.
      "wall_clock_timeout" — wall-clock budget exceeded; sim_time_reached < stop_time.
      "network_idle"       — the event calendar became empty before stop_time
                             (e.g. all sources blocked on a full queue).

    Args:
        stop_time:        Simulation end time in model time units.
        chunk_count:      Number of equal slices (default 20). Increase for longer
                          runs so progress is reported more often and the wall-clock
                          check fires more frequently.
        max_wall_seconds: Maximum real-world seconds before aborting (default 25.0).

    Example call:
        {"stop_time": 10000, "chunk_count": 20, "max_wall_seconds": 25.0}

    Example response:
        {"run_info": {"status": "completed", "sim_time_reached": 10000.0,
                      "wall_seconds_elapsed": 1.23, "chunks_completed": 20, ...},
         "stats": [{"id": "src", "output_count": 4987, ...}, ...]}
    """
    session = _session(ctx)
    try:
        run_info = await run_chunked(session, stop_time, chunk_count, max_wall_seconds, ctx)
    except (ValueError, SessionStateError) as exc:
        return _error(type(exc).__name__, str(exc))
    return {
        "run_info": run_info,
        "stats": all_stats(session.elements, session.element_specs),
    }


@mcp.tool()
def get_stats(ctx: Context) -> dict:
    """Return current statistics for all elements.

    Works in READY state (all counts will be 0 — no simulation has run yet) and
    COMPLETED state (counts reflect the completed run). Call this after
    run_experiment to read results without re-running the model.

    Stats fields per element:
      input_count / output_count : total items that entered / left this element.
      content_current            : items currently inside the element.
      content_average            : mean items held (arithmetic mean of level changes,
                                   meaningful for queues and servers).
      content_max                : peak items held simultaneously.
      staytime_current           : stay time of the last item that exited (seconds).
      staytime_average           : mean time items spend inside this element.
      staytime_max / staytime_min: extremes of the stay-time distribution.

    Additional fields (always present for the corresponding element types):
      blockage_count [MultiServer] : number of times a finished item was blocked
                                     from moving downstream (downstream full/busy).
      type_counts    [Sink]        : dict mapping item type → number of items of
                                     that type that completed. Example:
                                     {"Type1": 12, "Type2": 11, "Type3": 10}

    Note — InterArrivalSource / ScheduleSource: input_count is always 0 (items
    are generated, not received); output_count is the number of items dispatched.
    Content fields are always 0 (sources do not hold items).

    Note — Sink: output_count is always 0 (items are absorbed). content_current
    grows with each arrival. staytime_* fields are 0 (no exit event recorded).

    Example response:
        {"stats": [{"id": "snk", "type": "Sink", "input_count": 4987,
                    "type_counts": {"Type1": 1662, "Type2": 1663, "Type3": 1662}, ...}, ...]}
    """
    session = _session(ctx)
    try:
        session.require_state(SessionState.READY, SessionState.COMPLETED)
    except SessionStateError as exc:
        return _error("SessionStateError", str(exc))
    return {"stats": all_stats(session.elements, session.element_specs)}


@mcp.tool()
def list_elements(ctx: Context) -> dict:
    """Return the element specs currently in the model (any state).

    Returns a single JSON object with an "elements" array to ensure a consistent
    single-response format regardless of the number of elements.

    Example response:
        {"elements": [{"type": "InterArrivalSource", "id": "src", ...}, ...]}
    """
    return {"elements": list(_session(ctx).element_specs.values())}


@mcp.tool()
def list_connections(ctx: Context) -> dict:
    """Return the connection specs currently in the model (any state).

    Returns a single JSON object with a "connections" array.

    Example response:
        {"connections": [{"origin": "src", "destinations": ["q"], "strategy": "FirstAvailable"}, ...]}
    """
    return {"connections": [c.model_dump() for c in _session(ctx).connections]}


@mcp.tool()
def describe_model(ctx: Context) -> dict:
    """Return the full model snapshot: state, elements, connections, last run info.

    Useful after any operation to confirm the current model state. The
    last_run_info field is null until run_experiment has been called.
    """
    return _session(ctx).snapshot()


@mcp.tool()
def get_supported_types(ctx: Context) -> dict:
    """Return JSON schemas for all supported element types and distribution types.

    Call this once before constructing a model to learn exactly which fields are
    required and their constraints. Each entry contains the Pydantic-generated
    JSON schema.

    State machine:
      building → ready     : initialize_model
      ready    → completed : run_experiment
      building | ready | completed → building : new_model  (resets everything)
    """
    from .schemas import (
        ExponDist, InterArrivalSourceSpec, ItemsQueueSpec, JobSpec,
        LabelExprSpec, MultiServerSpec, NormDist, ScheduleSourceSpec,
        SinkSpec, TriangDist, UniformDist,
    )

    return {
        "element_types": {
            "InterArrivalSource": InterArrivalSourceSpec.model_json_schema(),
            "ScheduleSource": ScheduleSourceSpec.model_json_schema(),
            "ItemsQueue": ItemsQueueSpec.model_json_schema(),
            "MultiServer": MultiServerSpec.model_json_schema(),
            "Sink": SinkSpec.model_json_schema(),
        },
        "distribution_types": {
            "expon": ExponDist.model_json_schema(),
            "uniform": UniformDist.model_json_schema(),
            "norm": NormDist.model_json_schema(),
            "triang": TriangDist.model_json_schema(),
            "label_expr": LabelExprSpec.model_json_schema(),
        },
        "output_strategies": {
            "FirstAvailable": "Try destinations in order; send to the first that has space. "
                              "Equivalent to RoundRobin when there is only one destination.",
            "RoundRobin": "Cycle through destinations in order. "
                          "Equivalent to FirstAvailable when there is only one destination.",
        },
        "state_machine": {
            "states": ["building", "ready", "completed"],
            "transitions": {
                "building → ready": "initialize_model",
                "ready → completed": "run_experiment",
                "building | ready | completed → building": "new_model",
            },
            "run_experiment_status_values": [
                "completed        — ran to stop_time successfully",
                "wall_clock_timeout — real-world budget exceeded; partial results available",
                "network_idle     — event calendar empty before stop_time (sources blocked or schedule exhausted)",
            ],
        },
        "extra_stats_fields": {
            "MultiServer.blockage_count": (
                "Number of times a finished item could not be sent downstream "
                "(downstream element was full or busy). Always present in MultiServer stats."
            ),
            "Sink.type_counts": (
                "Dict mapping item type string → count of items of that type absorbed. "
                "Always present in Sink stats. Example: {\"Type1\": 12, \"J1\": 1}"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import socket

    host = mcp.settings.host  # default: 127.0.0.1
    port = mcp.settings.port  # default: 8000
    sse_url = f"http://{host}:{port}/sse"

    print("=" * 60)
    print("  PyFlow MCP Server")
    print("=" * 60)
    print(f"  Transport : SSE (HTTP)")
    print(f"  Address   : {host}")
    print(f"  Port      : {port}")
    print(f"  SSE URL   : {sse_url}")
    print()
    print("  -- Langflow / n8n / any SSE-capable MCP client --")
    print(f"  Add an MCP tool with SSE URL: {sse_url}")
    print()
    print("  -- Claude Desktop (claude_desktop_config.json) --")
    print('  {')
    print('    "mcpServers": {')
    print('      "pyflow": {')
    print(f'        "url": "{sse_url}"')
    print('      }')
    print('    }')
    print('  }')
    print()
    print("  -- VS Code (settings.json) --")
    print('  "mcp": { "servers": { "pyflow": {')
    print(f'    "type": "sse", "url": "{sse_url}" }} }}')
    print()
    print("  Waiting for connections... (Ctrl+C to stop)")
    print("=" * 60)

    mcp.run(transport="sse")
