"""FastMCP server — exposes PyFlow simulation to AI agents as MCP tool calls.

Run with:
    mcp dev pyflow_mcp/server.py          # MCP Inspector (stdio)
    python pyflow_mcp/server.py           # SSE/HTTP directly (Langflow, n8n, etc.)

Every tool docstring is what the agent reads; keep them precise and include a
JSON example so the agent knows the expected payload shape.
"""

from __future__ import annotations

import argparse
import logging
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from collections.abc import AsyncIterator
from typing import Any, List, Optional, Union

from pydantic import Field, TypeAdapter, create_model

from mcp.server.fastmcp import Context, FastMCP

from PyFlow.spec import (CalendarSpec, ConnectionSpec, DowntimeSpec, ElementSpec, ListSpec, ModelSpec,
                         ResourcePoolSpec, ResourceRulesSpec, SpecError)

from .inspection import all_stats, downtime_stats, list_stats, resource_stats
from .runner import run_chunked
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
    """One SimulationSession per connected client (keyed by its MCP session object)."""
    sessions: "weakref.WeakKeyDictionary[Any, SimulationSession]" = field(default_factory=weakref.WeakKeyDictionary)
    default: SimulationSession = field(default_factory=SimulationSession)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    yield AppContext()


mcp = FastMCP("PyFlow Simulator", lifespan=lifespan)


def _session(ctx: Context) -> SimulationSession:
    app: AppContext = ctx.request_context.lifespan_context
    client = getattr(ctx, "session", None)
    if client is None:
        return app.default
    try:
        session = app.sessions.get(client)
        if session is None:
            session = app.sessions[client] = SimulationSession()
        return session
    except TypeError:  # client object not weak-referenceable: share the default session
        return app.default


# ModelSpec with the element list typed as the built-in element union, so that the tool
# schema shows every element type (ModelSpec itself accepts any registered type).
ModelSpecInput = create_model("ModelSpecInput", __base__=ModelSpec,
                              elements=(List[ElementSpec], Field(default_factory=list)))


# ---------------------------------------------------------------------------
# Helper — structured error response
# ---------------------------------------------------------------------------

def _error(error_type: str, message: str, issues: Optional[list] = None) -> dict:
    error = {"type": error_type, "message": message}
    if issues:
        error["issues"] = issues
    return {"error": error}


def _exc_error(exc: Exception) -> dict:
    issues = [i.to_dict() for i in exc.issues] if isinstance(exc, SpecError) else None
    return _error(type(exc).__name__, str(exc), issues)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def new_model(ctx: Context, seed: Optional[int] = None, name: str = "Model",
              parameters: Optional[dict[str, Union[bool, int, float, str]]] = None,
              calendar: Optional[CalendarSpec] = None) -> dict:
    """Reset the simulator and start a fresh empty model.

    Can be called from any state (building, ready, or completed). Alternative: build the
    whole model in one call with load_model_spec.

    Args:
        seed:       Random seed. Same seed + same model => identical results. None: random.
        name:       Model name.
        parameters: Model parameters read by Parameterized routing strategies.
        calendar:   {"start": "2026-01-05 00:00", "seconds_per_unit": 60} maps simulation
                    time to dates (needed by Shift downtimes and dated intervals).

    Example response:
        {"state": "building", "seed": 42, "message": "Model reset. Ready to add elements."}
    """
    session = _session(ctx)
    try:
        session.reset(seed, name=name, parameters=parameters, calendar=calendar)
    except ValueError as exc:
        return _exc_error(exc)
    return {"state": "building", "seed": session.model.seed, "message": "Model reset. Ready to add elements."}


@mcp.tool()
def load_model_spec(spec: ModelSpecInput, ctx: Context) -> dict:
    """Replace the current model with a complete model specification (one call).

    The spec is the same JSON format as export_model_spec and the model files:
        {"name": "Line", "seed": 42,
         "calendar": {"start": "2026-01-05 00:00", "seconds_per_unit": 60},   (optional)
         "parameters": {"route": "round_robin"},                             (optional)
         "resources":   [ ...resource pools, as in create_resources_batch... ], (optional)
         "lists":       [ ...lists, as in create_lists_batch... ],             (optional)
         "resource_rules": {"request_order": "priority DESC", "discipline": "first_fit"}, (optional)
         "elements":    [ ...element specs, as in create_elements_batch... ],
         "connections": [ ...connection specs, as in connect_batch... ],
         "downtimes":   [ ...downtime specs, as in add_downtimes_batch... ],   (optional)
         "run": {"until": 10000, "warmup": 1000}}                            (optional)

    The whole spec is validated first. On errors nothing is built and the response lists
    every problem: {"error": {"type": "SpecError", "issues": [{"severity", "code",
    "message", "path"}, ...]}}. Warnings (e.g. an element without outgoing connection) do
    not prevent loading and are returned in "warnings".

    Leaves the session in BUILDING state: call initialize_model, then run_experiment
    (run.until / run.warmup are only defaults for the library; pass them explicitly).
    """
    session = _session(ctx)
    try:
        model_spec = ModelSpec.model_validate(spec.model_dump())
        built = session.load_spec(model_spec)
    except (ValueError, SessionStateError) as exc:
        return _exc_error(exc)
    return {"state": session.state.value, "seed": session.model.seed,
            "created_ids": list(built.elements), "warnings": [i.to_dict() for i in built.issues]}


@mcp.tool()
def export_model_spec(ctx: Context) -> dict:
    """Return the current model as a specification (JSON), whatever way it was built.

    Save it to reproduce the model later with load_model_spec (same seed => same results).
    """
    return {"spec": _session(ctx).export_spec().to_dict()}


@mcp.tool()
def validate_model(ctx: Context) -> dict:
    """Check the current model without running it.

    Returns {"valid": bool, "issues": [{"severity": "error"|"warning", "code", "message",
    "path"}]}. Typical warnings: W_UNCONNECTED_OUTPUT (items would pile up), W_NO_INPUT,
    W_UNFED_PORT (an assembly port nobody feeds), W_MISSING_PARAMETER, W_DEFAULT_CALENDAR.
    """
    issues = _session(ctx).validate()
    return {"valid": not any(i["severity"] == "error" for i in issues), "issues": issues}


@mcp.tool()
def create_resources_batch(resources: list[ResourcePoolSpec], ctx: Context) -> dict:
    """Create shared resource pools: operators, robots, tools, fixtures... Create them before
    the elements that use them.

    A pool has identical units ({"id": "welders", "kind": "operator", "capacity": 2}) or
    named units with skills and attributes ({"id": "robots", "kind": "robot", "units":
    [{"name": "R1", "skills": ["weld", "paint"], "attributes": {"level": 2}},
    {"name": "R2", "skills": ["paint"]}]}). "unit_order" chooses among idle units
    (ORDER BY, default "skills_count ASC"; e.g. "utilization ASC" to balance work).

    Elements with service time (MultiServer, Combiner, MultiAssembler) use them with
    "resources": ["welders"] (one unit during the whole service) or
    [{"pool": "robots", "quantity": 1, "during": "processing", "skill": "weld",
      "where": "level >= item.complexity"}], and
    "resource_release": "on_finish" (default) | "on_exit" (keep the units while the finished
    item is blocked). Waiting time shows as state WAITING_FOR_RESOURCE; pool statistics
    (utilization, queue, waits, per unit) come in the "resources" part of the results.

    Example response: {"status": "success", "created_ids": ["welders"], "failed_at": null}
    """
    session = _session(ctx)
    created: list[str] = []
    for i, spec in enumerate(resources):
        try:
            session.add_resource(spec)
            created.append(spec.id)
        except (ValueError, SessionStateError) as exc:
            return {"status": "partial_success", "created_ids": created,
                    "failed_at": {"index": i, "spec": spec.model_dump(mode="json", exclude_none=True),
                                  **_exc_error(exc)["error"]}}
    return {"status": "success", "created_ids": created, "failed_at": None}


@mcp.tool()
def create_lists_batch(lists: list[ListSpec], ctx: Context) -> dict:
    """Create FlexSim-style lists. A list decouples who has items from who needs them.

    Push: connect an element to a list id ({"origin": "q1", "destinations": ["jobs"]}). The
    items stay in the element (announced, the element stays blocked as when its output is full);
    a queue announces every item it holds, so a list over several queues is a global priority
    queue. Pull: connect a list to elements ({"origin": "jobs", "destinations": ["m1", "m2"],
    "query": "WHERE type == 'A' ORDER BY priority DESC, age DESC"}): each destination takes the
    best matching item whenever it has space, or waits (back-order) until one is pushed.

    Query names: the item's fields (type, name, priority, any label), origin (origin.name),
    age (time in the list), push_time, now, puller (puller.name) and the list "fields"
    (calculated: {"slack": "due - now"}). SQL spellings (AND, OR, =) are accepted.

    Example: [{"id": "jobs"}, {"id": "orders", "fields": {"slack": "due - now"},
              "backorder_order": "priority DESC"}]
    """
    session = _session(ctx)
    created: list[str] = []
    for i, spec in enumerate(lists):
        try:
            session.add_list(spec)
            created.append(spec.id)
        except (ValueError, SessionStateError) as exc:
            return {"status": "partial_success", "created_ids": created,
                    "failed_at": {"index": i, "spec": spec.model_dump(mode="json", exclude_none=True),
                                  **_exc_error(exc)["error"]}}
    return {"status": "success", "created_ids": created, "failed_at": None}


@mcp.tool()
def set_resource_rules(rules: ResourceRulesSpec, ctx: Context) -> dict:
    """Set how waiting resource requests are served (model-wide). Takes effect at the next grant;
    can be changed between runs to compare dispatching rules.

    request_order: ORDER BY over the requests — priority (item priority or repair priority),
    time, age, seq, quantity, kind ('work' | 'repair'), element (name), item (item.due_date,
    item.type, any item label). Examples: "priority DESC" (default),
    "kind == 'repair' DESC, priority DESC" (repairs first), "item.due_date ASC" (EDD).
    discipline: "first_fit" (default: serve every request that fits, in that order) or
    "strict" (stop at the first one that cannot be served: nobody overtakes).

    Unit choice is per pool (resources[].unit_order, e.g. "utilization ASC") and unit filters
    per requirement ({"pool": "techs", "where": "level >= item.complexity"}).
    """
    session = _session(ctx)
    try:
        session.set_resource_rules(rules)
    except ValueError as exc:
        return _exc_error(exc)
    manager = session.model.resources
    return {"request_order": manager.request_order, "discipline": manager.discipline}


@mcp.tool()
def create_elements_batch(elements: list[ElementSpec], ctx: Context, verbose: bool = False) -> dict:
    """Add multiple elements to the model in one call.

    Processing is sequential. On the first failure the tool stops and returns a
    partial_success response so the agent can inspect the error and retry.

    Logical errors (duplicate IDs, wrong session state) are returned as
    structured JSON with a failed_at block. Schema-level errors (unknown type
    name, missing required field, constraint violation) are returned by the MCP
    protocol as tool errors — correct the element spec and retry.

    Supported element types (call get_supported_types for the full JSON schemas):
      InterArrivalSource          — random arrivals; no new arrivals while blocked downstream.
      InterArrivalBufferingSource — random arrivals that keep coming and wait inside the source.
      InfiniteSource              — saturates the line (an item whenever downstream accepts).
      ScheduleSource              — finite job list released at given times (jobs or file).
      ItemsQueue                  — finite-capacity FIFO buffer.
      MultiServer                 — N parallel servers; optional setup_time by item type.
      Combiner                    — main item + component ports ("<id>:<port>"), capacity 1.
      MultiAssembler              — N servers assembling a new item from component ports.
      Sink                        — terminal absorber; tracks per-type item counts.
    Every element accepts an optional input_strategy (Default, SingleLabel, MultiLabel,
    OriginName, OriginType, MaxQueue, And, Or). "name" is optional (default: the id).
    MultiServer, Combiner and MultiAssembler accept "resources" (pools created with
    create_resources_batch) and "resource_release".

    Time fields (interarrival, service_time, ...) accept a number (constant), a spec
    string such as "Exponential~0.5" (rate) / "ExponentialMean~2" / "Triangular~2~5~8",
    or a label expression such as "PT1 * 60".

    Args:
        elements: List of typed element specs.
        verbose:  If true, includes the full model snapshot in the response.
                  Default false (use describe_model to inspect the model separately).

    Example input (continuous sources with typed items + label-based server):
        [
          {"type": "InterArrivalSource", "id": "src1", "name": "Source1",
           "interarrival": 10,
           "item_type": "Type1", "labels": {"PT1": 10, "PT2": 5}},
          {"type": "ItemsQueue", "id": "buf1", "name": "Buffer1", "capacity": 10},
          {"type": "MultiServer", "id": "p1", "name": "Processor1", "num_servers": 1,
           "service_time": "PT1"},
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
           "service_time": "PT1"},
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
        except (ValueError, KeyError, SessionStateError) as exc:
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

    A destination "<id>:<port>" feeds a component port of a Combiner / MultiAssembler
    (e.g. "assembly:0"); "<id>" alone is the main input.

    Lists (create_lists_batch): a list id as the only destination = push to the list;
    a list id as origin = its destinations pull from it with "query" (and "priority").

    Strategies: "FirstAvailable" (default), "RoundRobin", "ShortestQueue",
    "MostAvailableCapacity", "PriorityRouting", or an object:
      {"type": "LabelRouting", "label": "family", "mapping": {"A": 0, "B": 1}, "default_index": -1}
      {"type": "LabelBased", "label": "dest"}            (label value = destination index)
      {"type": "Parameterized", "parameter": "route", "default": "FirstAvailable"}

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
def add_downtimes_batch(downtimes: list[DowntimeSpec], ctx: Context) -> dict:
    """Add downtime generators (failures, planned stops, shifts) to existing elements.

    One generator is created per target. Kinds:
      {"type": "MtbfMttr", "targets": ["m1"], "ttf": "ExponentialMean~3600",
       "ttr": "ExponentialMean~300", "basis": "calendar"|"busy",
       "repair_resources": ["techs"], "repair_priority": 10}       (repair_resources optional:
       pools from create_resources_batch; the element shows WAITING_FOR_REPAIR until they
       are granted, then BREAKDOWN during ttr)
      {"type": "Timetable", "targets": ["m1"], "intervals": [{"start": 480, "duration": 30}]}
      {"type": "Shift", "targets": ["m1", "m2"], "pattern": "Mon-Fri 06:00-14:00,14:00-22:00",
       "holidays": ["2026-12-25"]}                (needs a calendar, see new_model)
    Common fields: state, mode ("immediate" pauses the work in progress, "after_current"
    finishes it first), block_input, block_output.

    Example response: {"status": "success", "added": 2, "failed_at": null}
    """
    session = _session(ctx)
    for i, spec in enumerate(downtimes):
        try:
            session.add_downtime(spec)
        except (ValueError, SessionStateError) as exc:
            return {"status": "partial_success", "added": i,
                    "failed_at": {"index": i, "spec": spec.model_dump(mode="json", exclude_none=True),
                                  **_exc_error(exc)["error"]}}
    return {"status": "success", "added": len(downtimes), "failed_at": None}


@mcp.tool()
def set_parameters(parameters: dict[str, Union[bool, int, float, str]], ctx: Context) -> dict:
    """Set model parameters (read by Parameterized routing). Takes effect on the next run.

    Example: {"parameters": {"route": "shortest_queue"}}
    """
    session = _session(ctx)
    try:
        session.set_parameters(parameters)
    except SessionStateError as exc:
        return _exc_error(exc)
    return {"parameters": dict(session.model.parameters)}


@mcp.tool()
def initialize_model(ctx: Context) -> dict:
    """Freeze the model topology and start all elements and downtime generators.

    Must be called after building (create_elements_batch / connect_batch /
    add_downtimes_batch, or load_model_spec) and before run_experiment. Requires at least
    one source and one Sink. The response includes the validation warnings.

    Transitions state: BUILDING → READY.
    """
    session = _session(ctx)
    try:
        session.initialize()
    except (ValueError, SessionStateError) as exc:
        return _exc_error(exc)
    return {**session.snapshot(), "warnings": [i for i in session.validate() if i["severity"] == "warning"]}


@mcp.tool()
async def run_experiment(
    stop_time: float,
    ctx: Context,
    chunk_count: int = 20,
    max_wall_seconds: float = 25.0,
    warmup: Optional[float] = None,
) -> dict:
    """Run the simulation up to *stop_time* model-time units.

    The run is divided into *chunk_count* equal slices so progress can be
    reported and the wall-clock budget checked between slices. The wall-clock
    check also fires after each slice completes, so even a single slow slice
    cannot silently exceed the budget.

    Requires READY state (call initialize_model first). In COMPLETED state the model is
    re-initialized and run again from t = 0 (same seed => same results).

    With *warmup*, statistics are reset when the clock reaches that time, so the results
    describe [warmup, stop_time] only (steady-state analysis).

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
        warmup:           Optional warm-up time (0 <= warmup <= stop_time).

    Example call:
        {"stop_time": 10000, "chunk_count": 20, "max_wall_seconds": 25.0}

    Example response:
        {"run_info": {"status": "completed", "sim_time_reached": 10000.0,
                      "wall_seconds_elapsed": 1.23, "chunks_completed": 20, ...},
         "stats": [{"id": "src", "output_count": 4987, ...}, ...]}
    """
    session = _session(ctx)
    try:
        if session.state == SessionState.COMPLETED:
            session.rerun()
        run_info = await run_chunked(session, stop_time, chunk_count, max_wall_seconds, ctx, warmup=warmup)
    except (ValueError, SessionStateError) as exc:
        return _exc_error(exc)
    return {
        "run_info": run_info,
        "stats": all_stats(session.elements, session.element_specs),
        "resources": resource_stats(session.builder.resources),
        "lists": list_stats(session.builder.lists),
        "downtimes": downtime_stats(session.builder.generators),
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
      content_average            : time-weighted mean number of items held
                                   (for a single server: its utilisation).
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
    return {"stats": all_stats(session.elements, session.element_specs),
            "resources": resource_stats(session.builder.resources),
            "lists": list_stats(session.builder.lists),
            "downtimes": downtime_stats(session.builder.generators)}


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
    """Return the JSON schemas of every element type, sampler, strategy and downtime kind.

    Call this once before constructing a model to learn exactly which fields are
    required and their constraints. Element types come from the PyFlow registry
    (role: source | flow | sink; ports: number of component ports, reached with
    destination "<id>:<port>").

    State machine:
      building → ready     : initialize_model
      ready    → completed : run_experiment
      completed → completed: run_experiment (fresh run from t = 0)
      any → building       : new_model / load_model_spec
    """
    from PyFlow.spec import (OUTPUT_STRATEGY_DOCS, InputStrategySpec, OutputStrategySpec,
                             element_types)
    from PyFlow.spec.samplers import SAMPLER_DESCRIPTION

    elements = {}
    for name, etype in element_types().items():
        entry = {"role": etype.role, "description": etype.description, "schema": etype.spec.model_json_schema()}
        if etype.ports is not None:
            entry["component_ports"] = "one per entry of 'requirements' (destination '<id>:<port>')"
            entry["main_input"] = etype.main_input
        elements[name] = entry

    return {
        "element_types": elements,
        "samplers": SAMPLER_DESCRIPTION,
        "output_strategies": {"descriptions": OUTPUT_STRATEGY_DOCS,
                              "schema": TypeAdapter(OutputStrategySpec).json_schema()},
        "input_strategies": TypeAdapter(InputStrategySpec).json_schema(),
        "downtimes": TypeAdapter(DowntimeSpec).json_schema(),
        "resources": ResourcePoolSpec.model_json_schema(),
        "resource_rules": ResourceRulesSpec.model_json_schema(),
        "lists": ListSpec.model_json_schema(),
        "model_spec": "load_model_spec / export_model_spec use {name, seed, calendar, parameters, "
                      "resources, resource_rules, lists, elements, connections, downtimes, run}",
        "state_machine": {
            "states": ["building", "ready", "completed"],
            "transitions": {
                "building → ready": "initialize_model",
                "ready → completed": "run_experiment",
                "completed → completed": "run_experiment (re-initializes: fresh run from t = 0)",
                "any → building": "new_model, load_model_spec",
            },
            "run_experiment_status_values": [
                "completed        — ran to stop_time successfully",
                "wall_clock_timeout — real-world budget exceeded; partial results available",
                "network_idle     — event calendar empty before stop_time (sources blocked or schedule exhausted)",
            ],
        },
        "stats_fields": {
            "content_average": "time-weighted mean number of items held (single server: utilisation)",
            "state / state_ratios": "current state and fraction of time per state (IDLE, PROCESSING, "
                                    "BLOCKED, SETUP, BREAKDOWN, OFF_SHIFT, ...)",
            "blockage_count": "servers: times a finished item could not be sent downstream",
            "type_counts": "sinks: items absorbed per type",
            "items_created": "sources: items generated",
            "resources[]": "per pool: utilization, busy_*, queue_*, requests, grants, wait_average, "
                           "wait_max, unit_utilization, idle_units_average and units (state, "
                           "state_ratios, utilization, sequences_completed of every unit)",
            "lists[]": "content, back-orders, pushes, pulls, stay and back-order wait times",
            "downtimes[]": "stop_count, total_downtime; with repair_resources: repairs and repair_wait_*",
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description="PyFlow MCP server")
    parser.add_argument("--transport", choices=["sse", "stdio", "streamable-http"], default="sse",
                        help="stdio for Claude Code / Claude Desktop launching the server; "
                             "sse (default) or streamable-http for Langflow, n8n and other HTTP clients")
    args = parser.parse_args(argv)

    if args.transport != "stdio":  # stdout is the protocol channel in stdio mode
        host, port = mcp.settings.host, mcp.settings.port
        path = "/sse" if args.transport == "sse" else "/mcp"
        print("=" * 60)
        print("  PyFlow MCP Server")
        print("=" * 60)
        print(f"  Transport : {args.transport}")
        print(f"  URL       : http://{host}:{port}{path}")
        print()
        print("  Claude Code (stdio, no server to start):")
        print("    claude mcp add pyflow -- python -m pyflow_mcp.server --transport stdio")
        print()
        print("  Waiting for connections... (Ctrl+C to stop)")
        print("=" * 60)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
