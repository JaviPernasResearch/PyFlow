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

**Tests layout:** `tests/unit` (one file per feature, exact values), `tests/standard` (standard manufacturing lines from `PyFlow/standard_lines.py`: deterministic cases computed by hand + queueing-theory checks with 99 % CIs), `tests/properties` (seeded random topologies, invariants), `tests/test_mcp_server.py`. Harness: `tests/harness.py` (`Feeder`, `Collector`, `at`).

**Dependencies:** keep the existing ones (numpy, scipy, pandas, openpyxl; mcp/pydantic for the server). For new features prefer the stdlib or in-house code over adding packages.

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
| `PyFlow/SimClock/simClock.py` | Event calendar; `advance_clock(t)` fires events `<= t`, leaves `now == t`, returns `True` if events remain; `get_instance()` is a deprecated shim |
| `PyFlow/sampling.py` | `Sampler`s and `as_sampler`: numbers, scipy frozen dists, SimuLean `"Type~p1~p2"` specs, safe label expressions (`PyFlow/expressions.py`, own `ast` whitelist) |
| `PyFlow/states.py`, `PyFlow/stops.py`, `PyFlow/work.py` | Element states (`ElementState`, `StateTracker`: log, time/ratio since last reset), `element.schedule_work` (pausable `WorkHandle`), `element.stop(state, mode, block_input, block_output)` / `resume(token)` (overlapping, immediate/after_current), events `element.on("state_changed" \| "item_entered" \| "item_exited" \| "stopped" \| "resumed", fn)` |
| `PyFlow/downtime.py` | `TimetableDowntime` (overlap allow/serialize/merge), `MtbfMttrDowntime` (calendar or busy basis), `ShiftDowntime`, `downtimes_from_table`; generators start after elements in `Model.initialize` |
| `PyFlow/simcalendar.py` | `SimCalendar` (sim time <-> date, `Model(calendar=...)`), `WeeklyShiftPattern.parse("Mon-Fri 06:00-14:00,14:00-22:00; Sat 06:00-14:00")` with holidays |
| `PyFlow/standard_lines.py` | Builders for typical lines (single station, serial line, parallel machines, assembly, kit assembly, multi-product flow shop, routing by label, order release) returning a `Line` with `run()`/`summary()` |
| `PyFlow/Elements/element.py` | Abstract base for all elements; registers itself with its Model on init; owns an `ElementStatsCollector` |
| `PyFlow/Elements/interArrivalSource.py` | Generates items on a random schedule; cannot receive items |
| `PyFlow/Elements/itemsQueue.py` | FIFO buffer with finite capacity |
| `PyFlow/Elements/multiServer.py` | N parallel servers with configurable service-time distribution |
| `PyFlow/Elements/sink.py` | Terminal absorber; cannot unblock |
| `PyFlow/Link/generalLink.py` | Default link implementation; carries an `OutputStrategy` |
| `PyFlow/Link/outputStrategy.py` | Output strategies with `OutputContext` (FirstAvailable, RoundRobin, QueueSize/ShortestQueue, MostAvailableCapacity, LabelBased, LabelRouting, PriorityRouting, ParameterizedRouting, Delegate); every element owns `output_strategy` |
| `PyFlow/Elements/inputStrategy.py` | Input strategies for any element (`input_strategy`): Default, SingleLabel, MultiLabel, OriginName, OriginType, MaxQueue, CompositeAnd/Or; links use `can_accept(item, origin)` |
| `PyFlow/Items/item.py` | Entity class; ids come from the Model (`Item.ITEM_NUMBER` only for hand-made items); `sub_items` for batch mode |
| `PyFlow/Statistics/elementStatsCollector.py` | Input/output counts, time-weighted content (WIP), stay time; `reset(t)` |

### Constructor signatures

```python
# `model` may be a Model or (legacy) its SimClock; delays accept any sampler spec
InterArrivalSource(name: str, model, interarrival_dist)
ItemsQueue(capacity: int, name: str, model)
MultiServer(num_servers: int, delay_strategy, name: str, model)
Sink(name: str, model)
```

`element.connect(successors: list, strategy=FirstAvailableStrategy())` — keyword arg `strategy` accepted.

### Stats API

Access via `element.get_stats_collector()`. Key methods:
- `get_var_input_value()` / `get_var_output_value()`
- `get_var_content_value()` / `get_var_content_average()` / `get_var_content_max()`
- `get_var_staytime_value()` / `get_var_staytime_average()` / `get_var_staytime_max()` / `get_var_staytime_min()`

### Critical constraints

1. **One `Model` per independent run.** No global state; do not use `SimClock.get_instance()` in new code.
2. **`initialize()` empties the calendar.** Schedule interventions (`model.schedule_at`) after it.
3. **All `connect()` calls must happen before `initialize()`.** Wiring after init is undefined behaviour.
4. **`Sources` cannot receive items; `Sinks` cannot unblock** — both raise `NotImplementedError`.

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

`docs/propuesta-paridad-simulean.md` is the plan for SimuLean 2.1 parity; its §7 tracks status. Done: Phase 0 (core clean-up) and Phase 1 (states, stops, downtime, calendar, input/output strategies, setup times). Next: Phase 5.1–5.3 (type registry + `ModelSpec`), then Phase 2 elements (OperatorPool, GateQueue, ReleaseSource…). `docs/informe-bugs-simulean.md` lists SimuLean bugs found during the port (do not replicate them).

### MCP server

`todo.md` at the repo root specifies a **PyFlow MCP server** (`pyflow_mcp/` package) that exposes simulation construction and execution to AI agents via FastMCP tool calls. The full spec is in `todo.md`; `DOCUMENTATION.md` is the library reference.
