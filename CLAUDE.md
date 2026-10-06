# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Setup (once):**
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

**Run all tests:** `python -m pytest`  (configured in `pyproject.toml`, collects `tests/`)

**Run one file / test:** `python -m pytest tests/unit/test_clock.py -k fifo`

**Run the examples:** `python examples/standard_lines.py`

**Run a model file:** `python examples/run_spec.py examples/models/assembly_line.json [--seed 7] [--json]`

**Tests layout:** `tests/unit` (one file per feature, exact values; `test_spec.py` = model specification), `tests/standard` (standard manufacturing lines from `PyFlow/standard_lines.py`: deterministic cases computed by hand + queueing-theory checks with 99 % CIs), `tests/properties` (seeded random topologies, invariants), `tests/test_mcp_server.py` (session level), `tests/test_mcp_tools.py` (real in-memory MCP client). Harness: `tests/harness.py` (`Feeder`, `Collector`, `at`).

**Dependencies:** keep the existing ones (numpy, scipy, pandas, openpyxl, pydantic; `mcp>=1.20,<2` for the server — it uses the 1.x `FastMCP` API, renamed in mcp 2). For new features prefer the stdlib or in-house code over adding packages.

---

## Architecture

PyFlow is a **discrete-event simulation (DES) engine** for manufacturing and queuing models. Items (entities) flow through a directed network of Elements, with time advancing event-by-event. Everything belongs to a `Model` (no global state).

```
Model (seed, element registry, item ids, random streams, parameters)
  └─ SimClock (heapq calendar, (t, seq) FIFO tie-break, cancellable EventHandle)
  └─ fires Events → Elements (sources, queues, servers, sinks)
       └─ connected via Links (directed edges with OutputStrategy)
            └─ route Items through the network
```

### Core modules

| Module | Purpose |
|---|---|
| `PyFlow/model.py` | `Model`: clock, element registry, per-model item ids, seeded random streams (`rng(key)`, `bind_sampler`), `initialize()`, `run(until, warmup=)` |
| `PyFlow/SimClock/simClock.py` | Event calendar; `advance_clock(t)` fires events `<= t`, leaves `now == t`, returns `True` if events remain |
| `PyFlow/sampling.py` | `Sampler`s and `as_sampler`: numbers, scipy frozen dists, SimuLean `"Type~p1~p2"` specs, safe label expressions (`PyFlow/expressions.py`, own `ast` whitelist) |
| `PyFlow/states.py`, `PyFlow/stops.py`, `PyFlow/work.py` | Element states (`ElementState`, `StateTracker`: log, time/ratio since last reset), `element.schedule_work` (pausable `WorkHandle`), `element.stop(state, mode, block_input, block_output)` / `resume(token)` (overlapping, immediate/after_current), events `element.on("state_changed" \| "item_entered" \| "item_exited" \| "stopped" \| "resumed", fn)` |
| `PyFlow/downtime.py` | `TimetableDowntime` (overlap allow/serialize/merge), `MtbfMttrDowntime` (calendar or busy basis; `repair_resources` from pools: `WAITING_FOR_REPAIR` then `BREAKDOWN`, `repair_priority`), `ShiftDowntime`, `downtimes_from_table`; generators start after elements in `Model.initialize` |
| `PyFlow/simcalendar.py` | `SimCalendar` (sim time <-> date, `Model(calendar=...)`), `WeeklyShiftPattern.parse("Mon-Fri 06:00-14:00,14:00-22:00; Sat 06:00-14:00")` with holidays |
| `PyFlow/spec/` | Models as data: element type **registry** (`register_element(SpecClass, role=, ports=)`), `ModelSpec` (JSON round trip, YAML with PyYAML), `validate_spec` (`Issue` codes `E_*`/`W_*`), `ModelBuilder` (incremental, used by the MCP session), `BuiltModel.run()/results()`. New element types must be registered here (and added to `BUILTIN_ELEMENT_SPECS`) so the MCP and the files support them |
| `PyFlow/resources.py` | Shared resources: `ResourcePool` (units with optional skills; operators, robots, tools...), `ResourceRequirement(pool, quantity, during=setup\|processing\|both, skill)`, `ResourceManager` (`model.resources`: all-or-nothing grants; `configure(request_order=, discipline=first_fit|strict)`; pools have `unit_order`, requirements `where`), `ResourceUser` mixin used by `MultiServer`/`Combiner`/`MultiAssembler` (`resources=`, `resource_release=on_finish\|on_exit`; state `WAITING_FOR_RESOURCE`) |
| `PyFlow/query.py` | FlexSim-style queries `"WHERE ... ORDER BY ... ASC\|DESC"` (SQL spellings accepted) over the safe expressions; objects expose fields with `expression_field(name)` (items, elements, resource units, list entries, requests) |
| `PyFlow/lists.py` | `ModelList` (SimuLean ModelList / FlexSim lists): `push(value, origin=)`, `pull(query, puller, quantity, on_fulfilled)` with back-orders served on push (`backorder_order`, first-fit, delivered in a dt = 0 event), calculated `fields`, `peek`, `restore`, stats; `model.lists` |
| `PyFlow/Link/listLinks.py` | Flow through lists: `element.connect_to_list(lst)` / `connect([lst])` announces items (they stay in the origin), `element.pull_from_list(lst, query)` takes them when there is space; `ListInputLink` transfers and records stats. Origins implement `holds_item` / `release_item` |
| `PyFlow/reporting.py` | `element_summary(element)`: JSON-ready stats (counts, time-weighted WIP, stay times, state ratios, extras) shared by `BuiltModel` and the MCP |
| `PyFlow/standard_lines.py` | Builders for typical lines (single station, serial line, parallel machines, assembly, kit assembly, multi-product flow shop, routing by label, order release) returning a `Line` with `run()`/`summary()` |
| `PyFlow/Elements/element.py` | Abstract base for all elements; registers itself with its Model on init; owns an `ElementStatsCollector` |
| `PyFlow/Elements/interArrivalSource.py` | Generates items on a random schedule; cannot receive items |
| `PyFlow/Elements/itemsQueue.py` | FIFO buffer with finite capacity |
| `PyFlow/Elements/multiServer.py` | N parallel servers with configurable service-time distribution |
| `PyFlow/Elements/sink.py` | Terminal absorber; cannot unblock |
| `PyFlow/Link/generalLink.py` | Default link implementation; carries an `OutputStrategy` |
| `PyFlow/Link/outputStrategy.py` | Output strategies with `OutputContext` (FirstAvailable, RoundRobin, QueueSize/ShortestQueue, MostAvailableCapacity, LabelBased, LabelRouting, PriorityRouting, ParameterizedRouting, Delegate); every element owns `output_strategy` |
| `PyFlow/Elements/inputStrategy.py` | Input strategies for any element (`input_strategy`): Default, SingleLabel, MultiLabel, OriginName, OriginType, MaxQueue, CompositeAnd/Or; links use `can_accept(item, origin)` |
| `PyFlow/Items/item.py` | Entity class; ids come from the Model (0 for templates and hand-made items); `sub_items` for batch mode; `expression_field` for queries |
| `PyFlow/Statistics/elementStatsCollector.py` | Input/output counts, time-weighted content (WIP), stay time; `reset(t)` |

### Constructor signatures

```python
# elements need the Model; delays accept any sampler spec
InterArrivalSource(name: str, model: Model, interarrival_dist)
ItemsQueue(capacity: int, name: str, model: Model)
MultiServer(num_servers: int, delay_strategy, name: str, model: Model, *, setup_time=None, resources=None, resource_release="on_exit")
Sink(name: str, model: Model)
```

`element.connect(successors: list, strategy=FirstAvailableStrategy())` — keyword arg `strategy` accepted.

### Stats API

Access via `element.get_stats_collector()`. Key methods:
- `get_var_input_value()` / `get_var_output_value()`
- `get_var_content_value()` / `get_var_content_average()` / `get_var_content_max()`
- `get_var_staytime_value()` / `get_var_staytime_average()` / `get_var_staytime_max()` / `get_var_staytime_min()`

### Critical constraints

1. **One `Model` per independent run.** No global state.
2. **`initialize()` empties the calendar.** Schedule interventions (`model.schedule_at`) after it.
3. **All `connect()` calls must happen before `initialize()`.** Wiring after init is undefined behaviour.
4. **`Sources` cannot receive items; `Sinks` cannot unblock** — both raise `NotImplementedError`.
5. **Engine and specification change together.** When an element, strategy or downtime constructor changes (or a new class is added), update its Pydantic spec and `Binding` in `PyFlow/spec/` in the same change. `tests/unit/test_spec_sync.py` fails otherwise and says what to update (DOCUMENTATION.md §14c, "Keeping the specification in sync").

### Typical simulation lifecycle

```python
from PyFlow import *
from scipy import stats

model  = Model(seed=42)
source = InterArrivalSource("Source", model, "Exponential~0.5")   # rate 0.5
queue  = ItemsQueue(1000, "Queue", model)
server = MultiServer(1, stats.expon(scale=1.5), "Server", model)
sink   = Sink("Sink", model)

source.connect([queue])
queue.connect([server])
server.connect([sink])

model.initialize()                 # t=0, streams reseeded, stats reset, starts all elements
model.run(10000, warmup=1000)      # clock ends exactly at t=10000
```

### Roadmap

`docs/propuesta-paridad-simulean.md` is the plan for SimuLean 2.1 parity; its §7 tracks status. Done: Phase 0 (core clean-up), Phase 1 (states, stops, downtime, calendar, input/output strategies, setup times) and Phase 5.1–5.4 (registry, `ModelSpec`, validation, MCP). Phase 2 in progress: shared resources done (generic `ResourcePool`, replaces SimuLean's OperatorPool); next GateQueue, ReleaseSource, LengthLimitedQueue…, each with its spec class registered in `PyFlow/spec/elements.py`. `docs/informe-bugs-simulean.md` lists SimuLean bugs found during the port (do not replicate them).

### MCP server

`pyflow_mcp/` exposes the library to AI agents (FastMCP). Spec types come from `PyFlow.spec` and the session builds through `ModelBuilder`. One session per client. Tools: `new_model(seed, parameters, calendar)`, `create_resources_batch`, `set_resource_rules`, `create_lists_batch`, `load_model_spec`, `export_model_spec`, `validate_model`, `create_elements_batch`, `connect_batch`, `add_downtimes_batch`, `set_parameters`, `initialize_model`, `run_experiment(stop_time, warmup)` (re-runs from t = 0 in COMPLETED state), `get_stats`, `list_*`, `describe_model`, `get_supported_types` (from the registry). Start: `python -m pyflow_mcp.server --transport stdio` (Claude Code) or `--transport sse` (default; Langflow/n8n). `DOCUMENTATION.md` §14c documents the spec format.
