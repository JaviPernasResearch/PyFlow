# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run all tests:**
```bash
python -m unittest discover -s . -p "*_test.py" -v
```

**Run a single test file:**
```bash
python -m unittest test_BasicModels -v
```

**Run a single test case:**
```bash
python -m unittest test_BasicModels.TestBasicModels.test_MM1
```

**Run a simulation example:**
```bash
python Mains/TemplateModel.py
python Mains/MM1.py
```

**No build step or packaging** — PyFlow is a local package; run everything from the repo root so `from PyFlow import *` resolves correctly.

---

## Architecture

PyFlow is a **discrete-event simulation (DES) engine** for manufacturing and queuing models. Items (entities) flow through a directed network of Elements, with time advancing event-by-event via a singleton SimClock.

```
SimClock (Singleton, min-heap event calendar)
  └─ fires Events → Elements (sources, queues, servers, sinks)
       └─ connected via Links (directed edges with OutputStrategy)
            └─ route Items through the network
```

### Core modules

| Module | Purpose |
|---|---|
| `PyFlow/SimClock/simClock.py` | Singleton event scheduler; `advance_clock(t)` returns `True` if future events remain, `False` when calendar is empty |
| `PyFlow/Elements/element.py` | Abstract base for all elements; registers itself with SimClock on init; owns an `ElementStatsCollector` |
| `PyFlow/Elements/interArrivalSource.py` | Generates items on a random schedule; cannot receive items |
| `PyFlow/Elements/itemsQueue.py` | FIFO buffer with finite capacity |
| `PyFlow/Elements/multiServer.py` | N parallel servers with configurable service-time distribution |
| `PyFlow/Elements/sink.py` | Terminal absorber; cannot unblock |
| `PyFlow/Link/generalLink.py` | Default link implementation; carries an `OutputStrategy` |
| `PyFlow/Link/outputStrategy.py` | `FirstAvailableStrategy`, `RoundRobinStrategy`, `QueueSizeStrategy`, `LabelBasedStrategy` |
| `PyFlow/Items/item.py` | Entity class; `ITEM_NUMBER` is a **class-level global counter** |
| `PyFlow/Statistics/elementStatsCollector.py` | Auto-collects input/output count, content level, stay time per element |

### Constructor signatures

```python
InterArrivalSource(name: str, clock: SimClock, interarrival_dist)
ItemsQueue(capacity: int, name: str, clock: SimClock)
MultiServer(num_servers: int, delay_strategy, name: str, clock: SimClock)
Sink(name: str, clock: SimClock)
```

`element.connect(successors: list, strategy=FirstAvailableStrategy())` — keyword arg `strategy` accepted.

### Stats API

Access via `element.get_stats_collector()`. Key methods:
- `get_var_input_value()` / `get_var_output_value()`
- `get_var_content_value()` / `get_var_content_average()` / `get_var_content_max()`
- `get_var_staytime_value()` / `get_var_staytime_average()` / `get_var_staytime_max()` / `get_var_staytime_min()`

### Critical constraints

1. **SimClock is a singleton.** Reset between independent runs with `SimClock._instance = None`, then call `SimClock.get_instance()` to get a fresh instance. `clock.reset()` is NOT enough — it leaves old elements registered.
2. **`Item.ITEM_NUMBER` is a class-level global.** Reset with `Item.ITEM_NUMBER = 0` between runs.
3. **All `connect()` calls must happen before `clock.initialize()`.** Wiring after init is undefined behaviour.
4. **`Sources` cannot receive items; `Sinks` cannot unblock** — both raise `NotImplementedError`.

### Typical simulation lifecycle

```python
from PyFlow import *
from scipy import stats

clock = SimClock.get_instance()
source = InterArrivalSource("Source", clock, stats.expon(scale=2))
queue  = ItemsQueue(1000, "Queue", clock)
server = MultiServer(1, stats.expon(scale=2), "Server", clock)
sink   = Sink("Sink", clock)

source.connect([queue])
queue.connect([server])
server.connect([sink])

clock.initialize()          # starts all elements
clock.advance_clock(10000)  # run until t=10000 or event calendar empty
```

### Current work (branch `MCP-Server`)

`todo.md` at the repo root specifies a **PyFlow MCP server** (`pyflow_mcp/` package) that exposes simulation construction and execution to AI agents via FastMCP tool calls. The full spec is in `todo.md`; `DOCUMENTATION.md` is the library reference.
