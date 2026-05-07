# Implementation Brief: PyFlow MCP Server (Proof of Concept)

## Mission

Build a Python **MCP (Model Context Protocol) server** that exposes the PyFlow discrete-event simulation library to AI agents. The agent should be able to construct simulation models from JSON, connect elements, run simulations, and read statistics — all through MCP tool calls. The target client is **Langflow** (acting as MCP client).

This is a **proof of concept**. Keep the surface small, the code clean, and the failure modes loud and informative.

---

## What "PyFlow" is (1-paragraph context)

PyFlow is a Python discrete-event simulation library. You build a model by instantiating **Elements** (Source, Queue, Server, Sink) and connecting them with `element.connect([downstream])`. A singleton **SimClock** drives event-by-event simulation. Items flow through the network. Each Element has an `ElementStatsCollector` (accessed via `element.get_stats_collector()`) that auto-tracks input count, output count, content level, and stay time. The full library reference is in `DOCUMENTATION.md` at the project root — **read it before coding**, especially section 13 (Simulation Pipeline) and section 15 (Important Rules and Constraints).

**Critical PyFlow quirks you MUST handle correctly:**

1. `SimClock` is a singleton. To run a fresh simulation, you must do `SimClock._instance = None` and create a new one. `clock.reset()` is NOT enough — old elements stay registered and `Item.ITEM_NUMBER` keeps climbing.
2. All `connect()` calls must happen **before** `clock.initialize()`. Calling `connect()` after init is undefined behaviour.
3. `Item.ITEM_NUMBER` is a class-level global counter. Reset it to 0 between runs or item IDs become meaningless.
4. Sources cannot receive items. Sinks cannot unblock. (You won't expose these methods, but be aware.)

---

## Scope: what's IN, what's OUT

### IN scope (this proof of concept)

**Elements (4 total):**
- `InterArrivalSource` — generates items with inter-arrival times from a distribution.
- `ItemsQueue` — finite-capacity FIFO buffer.
- `MultiServer` — N parallel processing slots, service time from a distribution.
- `Sink` — terminal element, counts arrivals.

**Distributions (4 total):**
- `expon(scale)` — exponential, scipy.stats.expon
- `uniform(loc, scale)` — uniform on [loc, loc+scale]; use `scale=0` for deterministic
- `norm(loc, scale)` — normal, scipy.stats.norm
- `triang(c, loc, scale)` — triangular, scipy.stats.triang

**Output strategies for connections:**
- `FirstAvailable` (default) — try destinations in order
- `RoundRobin` — cycle through destinations

**Run mode:** synchronous only, with chunked progress and a wall-clock timeout safeguard.

### OUT of scope (do NOT implement)

- Combiner, MultiAssembler, InfiniteSource, InterArrivalBufferingSource, ScheduleSource
- CombinerInput / ConstrainedInput ports
- Expression-string delays (`"item.get_label_value(...)"`)
- Custom output strategies (LabelBased, QueueSize)
- Async/background runs, MCP Tasks, run cancellation
- Item labels / model items
- Saving and loading models to disk

If the agent asks for any of the above, the relevant tool should reject with a clear "not supported in this version" error.

---

## Tech stack

- **Python 3.11+**
- **`mcp` package** (official Python SDK) — use `FastMCP` from `mcp.server.fastmcp`
- **`pydantic` v2** — for spec validation and JSON schema generation
- **`scipy.stats`** — already a PyFlow dependency
- **`PyFlow`** — the existing library, imported as a package

Install: `pip install mcp pydantic scipy` (PyFlow is local).

Project layout (create alongside the existing `PyFlow/` package):

```
pyflow_mcp/
├── __init__.py
├── server.py                # FastMCP entry point, all @mcp.tool definitions
├── session.py               # SimulationSession + state machine
├── schemas.py               # Pydantic models for every spec type
├── factories.py             # element_factory, distribution_factory, strategy_factory
├── runner.py                # run_chunked_simulation with wall-clock budget
├── inspection.py            # list_elements, describe_element, get_stats helpers
└── examples/
    └── mm1_smoke_test.py    # Standalone script: runs an M/M/1 via the session, no MCP
tests/
└── test_mcp_server.py       # Pytest suite (see "Tests required" below)
```

---

## Component-by-component spec

### 1. `schemas.py` — Pydantic models

Use Pydantic v2 with **discriminated unions** so `mcp.tool` auto-generates clean JSON schemas the agent can read.

```python
from typing import Literal, Annotated, Union
from pydantic import BaseModel, Field

# --- Distributions ---

class ExponDist(BaseModel):
    type: Literal["expon"]
    scale: float = Field(gt=0, description="Mean of the exponential distribution")

class UniformDist(BaseModel):
    type: Literal["uniform"]
    loc: float = Field(description="Lower bound")
    scale: float = Field(ge=0, description="Width (use 0 for deterministic value=loc)")

class NormDist(BaseModel):
    type: Literal["norm"]
    loc: float = Field(description="Mean")
    scale: float = Field(gt=0, description="Standard deviation")

class TriangDist(BaseModel):
    type: Literal["triang"]
    c: float = Field(ge=0, le=1, description="Mode as fraction of [loc, loc+scale]")
    loc: float = Field(description="Lower bound")
    scale: float = Field(gt=0, description="Width")

DistributionSpec = Annotated[
    Union[ExponDist, UniformDist, NormDist, TriangDist],
    Field(discriminator="type"),
]

# --- Elements ---

class InterArrivalSourceSpec(BaseModel):
    type: Literal["InterArrivalSource"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    name: str
    interarrival: DistributionSpec

class ItemsQueueSpec(BaseModel):
    type: Literal["ItemsQueue"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    name: str
    capacity: int = Field(gt=0)

class MultiServerSpec(BaseModel):
    type: Literal["MultiServer"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    name: str
    num_servers: int = Field(gt=0)
    service_time: DistributionSpec

class SinkSpec(BaseModel):
    type: Literal["Sink"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    name: str

ElementSpec = Annotated[
    Union[InterArrivalSourceSpec, ItemsQueueSpec, MultiServerSpec, SinkSpec],
    Field(discriminator="type"),
]

# --- Connections ---

class ConnectionSpec(BaseModel):
    """A connection from one origin element to one or more destinations.
    
    All destinations sharing the same origin should be passed in a single
    spec, since PyFlow's connect() takes a list — this preserves strategy
    semantics (e.g. RoundRobin across the whole destination set).
    """
    origin: str = Field(description="Element id of the origin")
    destinations: list[str] = Field(min_length=1)
    strategy: Literal["FirstAvailable", "RoundRobin"] = "FirstAvailable"
```

### 2. `factories.py` — Spec → PyFlow object

Each factory takes a validated Pydantic model and returns the live PyFlow object.

```python
from scipy import stats
from PyFlow import (
    InterArrivalSource, ItemsQueue, MultiServer, Sink, SimClock,
)
from PyFlow.Link.outputStrategy import FirstAvailableStrategy, RoundRobinStrategy

def build_distribution(spec):
    if spec.type == "expon":
        return stats.expon(scale=spec.scale)
    if spec.type == "uniform":
        return stats.uniform(loc=spec.loc, scale=spec.scale)
    if spec.type == "norm":
        return stats.norm(loc=spec.loc, scale=spec.scale)
    if spec.type == "triang":
        return stats.triang(c=spec.c, loc=spec.loc, scale=spec.scale)
    raise ValueError(f"Unknown distribution type: {spec.type}")

def build_element(spec, clock):
    if spec.type == "InterArrivalSource":
        return InterArrivalSource(spec.name, clock, build_distribution(spec.interarrival))
    if spec.type == "ItemsQueue":
        return ItemsQueue(spec.capacity, spec.name, clock)
    if spec.type == "MultiServer":
        return MultiServer(spec.num_servers, build_distribution(spec.service_time), spec.name, clock)
    if spec.type == "Sink":
        return Sink(spec.name, clock)
    raise ValueError(f"Unknown element type: {spec.type}")

def build_strategy(name: str):
    if name == "FirstAvailable":
        return FirstAvailableStrategy()
    if name == "RoundRobin":
        return RoundRobinStrategy()
    raise ValueError(f"Unknown strategy: {name}")
```

### 3. `session.py` — The state-managed model holder

```python
from enum import Enum
from typing import Any
from .factories import build_element, build_strategy
from .schemas import ElementSpec, ConnectionSpec

class SessionState(str, Enum):
    BUILDING = "building"
    READY = "ready"
    COMPLETED = "completed"

class SessionStateError(Exception):
    """Raised when a tool is called in the wrong session state."""

class SimulationSession:
    """Holds the current model. One instance per server (singleton-ish via lifespan)."""
    
    def __init__(self):
        self.state: SessionState = SessionState.BUILDING
        self.elements: dict[str, Any] = {}        # id -> PyFlow element
        self.element_specs: dict[str, dict] = {}  # id -> original spec dict (for inspection)
        self.connections: list[ConnectionSpec] = []
        self.clock = None
        self.last_run_info: dict | None = None
        self.reset()
    
    def reset(self) -> None:
        """Full reset — handles SimClock singleton + Item counter correctly."""
        # Drop references first so GC can clean up
        self.elements.clear()
        self.element_specs.clear()
        self.connections.clear()
        
        # Reset PyFlow globals
        from PyFlow import SimClock, Item
        SimClock._instance = None
        Item.ITEM_NUMBER = 0
        self.clock = SimClock.get_instance()
        
        self.state = SessionState.BUILDING
        self.last_run_info = None
    
    def require_state(self, *allowed: SessionState) -> None:
        if self.state not in allowed:
            raise SessionStateError(
                f"Operation not allowed in state '{self.state.value}'. "
                f"Allowed states: {[s.value for s in allowed]}. "
                f"Hint: call new_model to start over."
            )
    
    def add_element(self, spec: ElementSpec) -> None:
        self.require_state(SessionState.BUILDING)
        if spec.id in self.elements:
            raise ValueError(f"Element id '{spec.id}' already exists")
        element = build_element(spec, self.clock)
        self.elements[spec.id] = element
        self.element_specs[spec.id] = spec.model_dump()
    
    def add_connection(self, conn: ConnectionSpec) -> None:
        self.require_state(SessionState.BUILDING)
        if conn.origin not in self.elements:
            raise ValueError(f"Origin element '{conn.origin}' does not exist")
        for dst in conn.destinations:
            if dst not in self.elements:
                raise ValueError(f"Destination element '{dst}' does not exist")
        origin = self.elements[conn.origin]
        destinations = [self.elements[d] for d in conn.destinations]
        origin.connect(destinations, strategy=build_strategy(conn.strategy))
        self.connections.append(conn)
    
    def initialize(self) -> None:
        self.require_state(SessionState.BUILDING)
        if not self.elements:
            raise ValueError("Cannot initialize: model has no elements")
        # Light validation: at least one source and one sink
        types = {spec["type"] for spec in self.element_specs.values()}
        if "InterArrivalSource" not in types:
            raise ValueError("Model must contain at least one InterArrivalSource")
        if "Sink" not in types:
            raise ValueError("Model must contain at least one Sink")
        self.clock.initialize()
        self.state = SessionState.READY
    
    def snapshot(self) -> dict:
        """JSON-serializable view of the current model. Safe to call in any state."""
        return {
            "state": self.state.value,
            "elements": list(self.element_specs.values()),
            "connections": [c.model_dump() for c in self.connections],
            "last_run_info": self.last_run_info,
        }
```

### 4. `runner.py` — Chunked simulation with wall-clock budget

```python
import time
from .session import SimulationSession, SessionState

async def run_chunked(
    session: SimulationSession,
    stop_time: float,
    chunk_count: int,
    max_wall_seconds: float,
    ctx,  # FastMCP Context
) -> dict:
    """Advance the SimClock in chunks. Stop early if wall-clock budget is exceeded.
    
    Returns a dict describing the outcome. NEVER raises on timeout —
    timeouts are a structured return value, not an exception.
    """
    if session.state != SessionState.READY:
        raise RuntimeError(
            f"Cannot run: session is in state '{session.state.value}', expected 'ready'. "
            f"Call initialize_model first."
        )
    
    chunk_size = stop_time / chunk_count
    sim_time = 0.0
    wall_start = time.monotonic()
    chunks_done = 0
    network_idle = False
    timed_out = False
    
    await ctx.report_progress(0, stop_time, "Starting simulation")
    
    for i in range(chunk_count):
        # Check wall-clock budget BEFORE running the chunk
        elapsed = time.monotonic() - wall_start
        if elapsed >= max_wall_seconds:
            timed_out = True
            break
        
        # Run the chunk in a worker thread so the asyncio loop stays responsive
        next_t = min((i + 1) * chunk_size, stop_time)
        import asyncio
        has_more = await asyncio.to_thread(session.clock.advance_clock, next_t)
        sim_time = next_t
        chunks_done += 1
        
        await ctx.report_progress(
            sim_time, stop_time,
            f"t={sim_time:.2f} (chunk {chunks_done}/{chunk_count})"
        )
        
        if not has_more:
            network_idle = True
            break
    
    wall_elapsed = time.monotonic() - wall_start
    
    if timed_out:
        status = "wall_clock_timeout"
    elif network_idle:
        status = "network_idle"
    else:
        status = "completed"
    
    info = {
        "status": status,
        "sim_time_reached": sim_time,
        "stop_time_requested": stop_time,
        "wall_seconds_elapsed": round(wall_elapsed, 3),
        "wall_seconds_budget": max_wall_seconds,
        "chunks_completed": chunks_done,
        "chunks_total": chunk_count,
    }
    session.last_run_info = info
    session.state = SessionState.COMPLETED
    return info
```

### 5. `inspection.py` — Stats extraction

PyFlow exposes stats via `element.get_stats_collector()`. Pull the useful ones into a clean JSON dict:

```python
def stats_for_element(element_id: str, element, spec: dict) -> dict:
    sc = element.get_stats_collector()
    return {
        "id": element_id,
        "type": spec["type"],
        "name": spec["name"],
        "input_count": sc.get_var_input_value(),
        "output_count": sc.get_var_output_value(),
        "content_current": sc.get_var_content_value(),
        "content_average": sc.get_var_content_average(),
        "content_max": sc.get_var_content_max(),
        "staytime_current": sc.get_var_staytime_value(),
        "staytime_average": sc.get_var_staytime_average(),
        "staytime_max": sc.get_var_staytime_max(),
        "staytime_min": sc.get_var_staytime_min(),
    }
```

### 6. `server.py` — FastMCP tools

This is the user-facing surface. Every tool docstring is what the agent reads to understand what it does — write them clearly, with examples in the docstring.

Tools to expose:

#### `new_model() -> dict`
Resets everything. Returns `{"state": "building", "message": "..."}`. Always succeeds.

#### `create_elements_batch(elements: list[ElementSpec]) -> dict`
Creates multiple elements in one call. Sequential processing. On first failure, stops and returns the structured partial-failure response below. Token-efficient — agent sends 5 elements in one message.

Return shape:
```json
{
  "status": "success" | "partial_success",
  "created_ids": ["src1", "queue1", "server1"],
  "failed_at": null | {
    "phase": "elements",
    "index": 2,
    "spec": {...the spec that failed...},
    "error_type": "ValidationError",
    "error_message": "..."
  },
  "remaining": [...specs not yet processed...],
  "current_model": {...session.snapshot()...}
}
```

#### `connect_batch(connections: list[ConnectionSpec]) -> dict`
Same partial-failure semantics as `create_elements_batch` but for connections.

#### `initialize_model() -> dict`
Calls `session.initialize()`. Transitions BUILDING → READY. Returns the model snapshot. Validates that the model has at least one source and one sink.

#### `run_experiment(stop_time: float, chunk_count: int = 20, max_wall_seconds: float = 25.0, ctx: Context) -> dict`
Synchronous chunked run with wall-clock guard. Requires READY state. Returns:
```json
{
  "run_info": {
    "status": "completed" | "wall_clock_timeout" | "network_idle",
    "sim_time_reached": 1000.0,
    "stop_time_requested": 1000.0,
    "wall_seconds_elapsed": 4.2,
    "wall_seconds_budget": 25.0,
    "chunks_completed": 20,
    "chunks_total": 20
  },
  "stats": [...stats per element...]
}
```

#### `get_stats() -> dict`
Read-only. Returns stats for all elements. Works in READY or COMPLETED state (in READY, all stats are 0).

#### `list_elements() -> list[dict]`
Returns the list of element specs currently in the model.

#### `list_connections() -> list[dict]`
Returns the list of connections currently in the model.

#### `describe_model() -> dict`
Returns `session.snapshot()` — full state, elements, connections, last run info.

#### `get_supported_types() -> dict`
Static reference data: lists supported element types, distribution types, strategies, with their JSON schemas. Agent can call this once to learn the API. Implementation: extract from the Pydantic models via `model_json_schema()`.

### Server bootstrap pattern

Use FastMCP's lifespan to manage the single `SimulationSession`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP, Context
from .session import SimulationSession

@dataclass
class AppContext:
    session: SimulationSession

@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    yield AppContext(session=SimulationSession())

mcp = FastMCP("PyFlow Simulator", lifespan=lifespan)

# Helper to grab the session inside a tool:
def _session(ctx: Context) -> SimulationSession:
    return ctx.request_context.lifespan_context.session
```

Run the server with stdio transport for now (Langflow supports both stdio and HTTP):

```python
if __name__ == "__main__":
    mcp.run()  # defaults to stdio
```

---

## State machine — explicit transitions

```
            new_model
       ┌──────────────┐
       ▼              │
  ┌─────────┐    ┌────┴────┐    ┌───────────┐
  │BUILDING │───▶│ READY   │───▶│ COMPLETED │
  └─────────┘    └─────────┘    └───────────┘
   (mutate ok)   (run ok)        (read-only)
```

Tool → state requirement table:

| Tool | Allowed states |
|---|---|
| `new_model` | any |
| `create_elements_batch` | BUILDING |
| `connect_batch` | BUILDING |
| `initialize_model` | BUILDING |
| `run_experiment` | READY |
| `get_stats` | READY, COMPLETED |
| `list_elements`, `list_connections`, `describe_model`, `get_supported_types` | any |

Wrong-state errors must include the current state and a hint to call `new_model`.

---

## Tests required (`tests/test_mcp_server.py`)

Use `pytest` with the FastMCP in-memory client (`from mcp.client.session import ClientSession` + `from mcp.shared.memory import create_connected_server_and_client_session`). Each test must be independent.

1. **`test_double_run_isolation`** — The footgun test. Build an M/M/1, run it, call `new_model`, build another M/M/1, run it. Item counts in the second run must be reasonable (not contaminated by the first run). Specifically: `Sink.input_count` should not exceed what the second simulation could have produced.

2. **`test_state_machine_blocks_mutation_after_init`** — Build a model, call `initialize_model`, then try `create_elements_batch`. Must return a state-error response, not silently corrupt the model.

3. **`test_batch_partial_failure`** — Submit 5 elements, where #3 has invalid params (e.g. `num_servers=0`). Must return `partial_success` with `created_ids = [#1, #2]`, `failed_at.index == 2`, `remaining` containing #4 and #5.

4. **`test_wall_clock_timeout`** — Build a model with a fast source and a fast server (so simulation runs forever generating items). Call `run_experiment(stop_time=1e9, max_wall_seconds=2.0)`. Must return within ~3 seconds (allow some overhead) with `status="wall_clock_timeout"` and `sim_time_reached < 1e9`.

5. **`test_network_idle_early_stop`** — Use a `uniform(loc=10, scale=0)` arrival source (deterministic, slow). Call `run_experiment(stop_time=5.0)` so no items arrive at all. Must return `status="network_idle"` (or completed with sim_time at 5.0, depending on PyFlow's behaviour for empty calendars — verify and assert correct case).

6. **`test_mm1_throughput_sane`** — Classic M/M/1: arrival rate λ=1/2, service rate μ=1/3. Run for sim_time=10000. Sink throughput should be roughly λ × stop_time = 5000 items, within ±10%. This validates that the wiring actually works end-to-end.

7. **`test_get_supported_types_schema`** — Call `get_supported_types`, assert the response includes all 4 element types and 4 distributions, and that each entry has a JSON schema with the expected fields.

8. **`test_initialize_requires_source_and_sink`** — Build a model with only a queue. `initialize_model` must reject with a clear error message.

9. **`test_unknown_element_id_in_connection`** — Try to connect from a non-existent element id. Must return a clear error including the bad id.

---

## Smoke test (`pyflow_mcp/examples/mm1_smoke_test.py`)

Standalone script — no MCP, just exercises `SimulationSession` directly. Builds an M/M/1, runs it for 1000 time units, prints stats. Lets you debug the core pipeline before MCP wiring. Should be runnable via `python -m pyflow_mcp.examples.mm1_smoke_test` and complete in under 5 seconds.

---

## Acceptance criteria

The proof of concept is done when:

1. All 9 tests pass.
2. The smoke test prints sensible stats for an M/M/1 (~500 items through the sink for stop_time=1000 with λ=1/2).
3. Running `mcp dev pyflow_mcp/server.py` opens the MCP Inspector and you can manually click through: `new_model` → `create_elements_batch` → `connect_batch` → `initialize_model` → `run_experiment` → `get_stats`.
4. The server never crashes on bad input — every error is a structured tool response.
5. Running `new_model` followed by another full build-and-run sequence gives correct results (the singleton issue is properly handled).

---

## Style and quality bar

- **Docstrings on every public tool** — these are what the agent reads. Include at least one example call in JSON in each docstring.
- **Type hints everywhere.** FastMCP uses them for schema generation.
- **No `print()` statements** in production code. Use the `logging` module if you need diagnostics.
- **Errors are data, not exceptions** — at the MCP tool boundary, catch exceptions and convert to structured `{"error": {...}}` responses where it makes sense (especially for batch operations). Let truly unexpected exceptions bubble up so MCP returns a proper error response.
- **No `eval`, no `exec`, no dynamic imports.** This server runs untrusted-ish input; keep the attack surface flat.
- **Keep `server.py` thin.** Tools should be 5–15 lines each, delegating to `session.py`, `runner.py`, and `inspection.py`.

---

## Deliverables checklist

- [ ] `pyflow_mcp/` package with all 7 modules listed above
- [ ] `tests/test_mcp_server.py` with all 9 tests passing
- [ ] `pyflow_mcp/examples/mm1_smoke_test.py` runnable and producing sensible output
- [ ] `README.md` in `pyflow_mcp/` covering: installation, how to run with `mcp dev`, how to configure in Langflow (stdio command), and a worked example of the JSON the agent should send to build an M/M/1
- [ ] `requirements.txt` or update to existing `pyproject.toml` listing `mcp`, `pydantic>=2`, `scipy`

---

## What to read first

1. `DOCUMENTATION.md` sections 6, 7.4, 7.7, 7.8, 7.11, 13, 15.
2. The MCP Python SDK README progress-reporting example.
3. The existing PyFlow tests (if any) to understand how the library is normally exercised.

Ask before deviating from this brief. If something is ambiguous, choose the simpler option and document the choice in code comments.