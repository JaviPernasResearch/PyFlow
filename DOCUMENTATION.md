# PyFlow — Discrete Event Simulation Framework

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Package Structure](#3-package-structure)
4. [Core Concepts](#4-core-concepts)
5. [SimClock — Simulation Engine](#5-simclock--simulation-engine)
6. [Items — Flowing Entities](#6-items--flowing-entities)
7. [Elements — Building Blocks](#7-elements--building-blocks)
   - 7.1 [Base Element](#71-base-element)
   - 7.2 [Source (abstract base)](#72-source-abstract-base)
   - 7.3 [InfiniteSource](#73-infinitesource)
   - 7.4 [InterArrivalSource](#74-interarrivalsource)
   - 7.5 [InterArrivalBufferingSource](#75-interarrivalbufferingsource)
   - 7.6 [ScheduleSource](#76-schedulesource)
   - 7.7 [ItemsQueue](#77-itemsqueue)
   - 7.8 [MultiServer](#78-multiserver)
   - 7.9 [Combiner](#79-combiner)
   - 7.10 [MultiAssembler](#710-multiassembler)
   - 7.11 [Sink](#711-sink)
   - 7.12 [CombinerInput](#712-combinerinput)
   - 7.13 [ConstrainedInput](#713-constrainedinput)
   - 7.14 [ServerProcess](#714-serverprocess)
8. [Links — Connectivity Layer](#8-links--connectivity-layer)
   - 8.1 [GeneralLink](#81-generallink)
   - 8.2 [Output Strategies](#82-output-strategies)
9. [Samplers](#9-samplers-service-and-inter-arrival-times)
10. [Input Strategies](#10-input-strategies)
11. [Statistics Collection](#11-statistics-collection)
13. [Simulation Pipeline](#13-simulation-pipeline)
14. [Complete Examples](#14-complete-examples)
    - 14b. [States, Stops, Downtime and Shifts](#14b-states-stops-downtime-and-shifts)
    - 14c. [Model Specification (JSON / YAML)](#14c-model-specification-json--yaml)
    - 14d. [Shared Resources](#14d-shared-resources-operators-robots-tools)
    - 14e. [Queries and Model Lists](#14e-queries-and-model-lists-flexsim-style)
    - 14f. [Task Executers](#14f-task-executers-operators-vehicles)
15. [Important Rules and Constraints](#15-important-rules-and-constraints)

---

## 1. Overview

PyFlow is a Python-based discrete event simulation (DES) framework. It models systems as a network of interconnected **Elements** through which **Items** (entities) flow. Time advances event-by-event using a central **SimClock**, making it memory- and time-efficient even for very large simulations.

Typical use cases:
- Manufacturing and production line simulation
- Queuing network analysis (M/M/1, M/D/1, etc.)
- Assembly and disassembly processes
- Scheduled arrival and demand modelling
- Sequence optimisation experiments (DOE)

---

## 2. Architecture

```
Model ─ SimClock (one calendar per model)
   │  schedules & fires Events
   │
   └── Elements (nodes in the network)
          │  connected by
          └── Links (edges)
                 │  route Items through
                 └── Items (entities flowing through the network)
```

The central pattern:
1. **Items** are created by **Sources** and consumed by **Sinks**.
2. Elements are connected with `element.connect([downstream_element, ...])`.
3. A `Link` arbitrates routing using an **OutputStrategy**.
4. When an element is busy and cannot receive, the upstream `Link` queues a *pending request*.
5. When capacity frees up, the element calls `link.notify_available()`, which triggers `unblock()` on pending origins.
6. **Statistics** are collected automatically on every entry/exit event.

---

## 3. Package Structure

```
PyFlow/
├── __init__.py               # Re-exports the public classes
├── model.py                  # Model: clock, registry, item ids, random streams, initialize/run
├── sampling.py               # Samplers ("Exponential~0.5", scipy, expressions)
├── expressions.py            # Safe expression evaluator (no eval)
├── query.py                  # FlexSim-style WHERE / ORDER BY queries
├── states.py / stops.py / work.py   # Element states, stops, pausable work
├── downtime.py / simcalendar.py     # Downtime generators, calendar and shifts
├── resources.py              # Shared resources (ResourcePool, requirements, manager)
├── lists.py                  # ModelList (push / pull / back-orders)
├── reporting.py              # JSON-ready statistics summaries
├── standard_lines.py         # Builders of typical manufacturing lines
├── Elements/
│   ├── element.py            # Abstract base Element
│   ├── source.py             # Abstract base Source
│   ├── infiniteSource.py / interArrivalSource.py / interArrivalBufferingSource.py / scheduleSource.py
│   ├── itemsQueue.py         # FIFO buffer with finite capacity
│   ├── multiServer.py        # Parallel servers (setup, resources)
│   ├── combiner.py           # Main item + component ports
│   ├── multiAssembler.py     # Parallel assembler, creates new items
│   ├── sink.py               # Terminal element
│   ├── combinerInput.py / constrainedInput.py   # Component ports
│   ├── serverProcess.py      # One service slot
│   ├── inputStrategy.py      # Input strategies
│   └── arrivalListener.py    # Interface of the component ports' owners
├── Items/item.py             # Item entity with labels and sub-items
├── Link/
│   ├── link.py               # Abstract Link interface
│   ├── generalLink.py        # Element-to-element link
│   ├── listLinks.py          # Push to / pull from lists
│   └── outputStrategy.py     # Routing strategies
├── SimClock/
│   ├── simClock.py           # Event calendar (heapq, cancellable handles)
│   └── event.py              # Event protocol
├── Statistics/               # Per-element statistics (counts, time-weighted WIP, stay times)
└── spec/                     # ModelSpec (JSON/YAML), element registry, validation, builder
```

---

## 4. Core Concepts

| Concept | Description |
|---|---|
| **Item** | An entity (job, part, customer) that flows through the network. Carries metadata labels. |
| **Element** | A processing node (source, queue, server, sink). Receives and sends Items. |
| **Link** | A directed connection between elements that routes items using an OutputStrategy. |
| **Event** | A scheduled callable executed at a specific simulation time. |
| **SimClock** | Event calendar of one `Model`: schedules events and advances simulation time. |
| **Delay Strategy** | Determines how long a server processes an item (distribution or expression). |
| **Input Strategy** | Determines whether a CombinerInput port accepts a given item (label filtering). |
| **Output Strategy** | Determines which downstream element receives an item from a Link. |
| **Statistics Collector** | Automatically records flow counts, current content, and stay-times per element. |

---

## 5. Model and SimClock — Simulation Engine

**Location:** `PyFlow/model.py`, `PyFlow/SimClock/simClock.py`

A `Model` is the simulation context: it owns its `SimClock`, its element registry, its
item-id counter, its random streams (seeded) and a `parameters` dict. Nothing is global,
so several models can run in the same process.

```python
from PyFlow import Model

model = Model(seed=42)                 # same seed => identical results
src = InterArrivalSource("Source", model, "Exponential~0.5")   # elements take the model
...
model.initialize()                     # t=0, empty calendar, fresh streams, stats reset, start()
model.run(10_000, warmup=1_000)        # statistics are reset at t=1000
```

Elements need the `Model` (passing anything else raises `E_INVALID_MODEL`).

### Key Methods

| Method | Signature | Description |
|---|---|---|
| `Model.initialize` | `() -> None` | t = 0, empty calendar, item ids and random streams reset, statistics reset, `start()` on every element. Events scheduled before it are discarded (with a warning). |
| `Model.run` | `(until, *, warmup=None) -> bool` | Advances to `until`; with `warmup`, calls `reset_stats()` at that time. |
| `Model.reset_stats` | `() -> None` | Discards statistics collected so far. |
| `Model.schedule` / `schedule_at` | `(target, delay) / (target, time) -> EventHandle` | `target` is an object with `execute()` or a callable. |
| `Model.bind_sampler` | `(spec, key) -> Sampler` | Sampler with its own stream derived from `(seed, key)`. |
| `SimClock.schedule_event` | `(event, delay) -> EventHandle` | Relative delay; negative delays raise `E_NEGATIVE_DELAY`. |
| `SimClock.advance_clock` | `(time) -> bool` | Fires every event with time `<= time` and leaves the clock **exactly** at `time`. Returns `True` if events remain. |
| `SimClock.last_event_time` | attribute | Time of the last fired event (e.g. makespan). |
| `EventHandle.cancel` | `() -> bool` | Cancels a pending event. |

### Event Calendar

`heapq` ordered by `(time, seq)`: simultaneous events fire in scheduling order (FIFO).
Cancelled events are removed lazily.

### Randomness

Each sampler gets its own `numpy.random.Generator` derived from the model seed and a stable
key (`"<element name>.<purpose>"`), so adding an element does not change the random numbers of
the others (common random numbers between scenarios). See section 9 for the accepted
sampler specifications.

### Typical Run Loop

```python
model.initialize()          # Reset time, start all elements
model.run(10000)            # Run until sim time 10000
```

Or, for incremental reporting:

```python
model.initialize()
sim_time = 0
step = 100
while sim_time < max_sim_time:
    model.advance_clock(sim_time + step)
    # collect stats here
    sim_time += step
```

---

## 6. Items — Flowing Entities

**Location:** `PyFlow/Items/item.py`

`Item` represents an entity (job, part, customer) that flows through the network.

### Constructor

```python
Item(
    creation_time: float,
    name: Optional[str] = None,
    item_type: Optional[str] = None,
    labels: Optional[dict] = None,
    model_item: bool = False
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `creation_time` | `float` | — | Simulation time when the item was created. |
| `name` | `str` | `"Item{N}"` | Human-readable name. Auto-generated if omitted. |
| `item_type` | `str` | `"Default"` | Type classifier for routing and filtering. |
| `labels` | `dict` | `{}` | Arbitrary key-value metadata attached to the item. |
| `model_item` | `bool` | `False` | If `True`, the item acts as a template and does **not** increment the global counter. |

### Key Methods

| Method | Signature | Description |
|---|---|---|
| `copy_model` | `(creation_time, name=None) -> Item` | Creates a new Item cloning type and labels from this template. Used by Sources. |
| `set_label_value` | `(label_name: str, value) -> None` | Adds or updates a label. |
| `get_label_value` | `(label_name: str) -> Any` | Returns a label value, or `None`. |
| `get_all_labels` | `() -> dict` | Returns all labels. |
| `add_label` | `(label_name, value) -> None` | Alias for `set_label_value`. |
| `remove_label` | `(label_name) -> None` | Removes a label if present. |
| `get_creation_time` | `() -> float` | Returns creation timestamp. |
| `get_type` | `() -> str` | Returns item type. |
| `set_type` | `(type) -> None` | Sets item type. |
| `set_constrained_input` | `(input_id: int) -> None` | Tags which CombinerInput port this item entered (used internally). |
| `get_input_id` | `() -> int` | Returns the tagged input port id. |

### Model Items (Templates)

A model item is used to stamp-out copies at each arrival, preserving type and labels:

```python
model = Item(0, item_type="PartA", labels={"ProcessTime": 3.5})
source = InterArrivalSource("Source", model, dist, model_item=model)
```

Every generated item will have `type="PartA"` and `labels={"ProcessTime": 3.5}` with its own `creation_time`.

---

## 7. Elements — Building Blocks

All elements share these characteristics:
- Registered automatically with the `SimClock` upon creation.
- Linked to neighbours via `element.connect([list_of_successors])`.
- Have an `ElementStatsCollector` accessible via `element.get_stats_collector()`.

### 7.1 Base Element

**Location:** `PyFlow/Elements/element.py`

Abstract class that all elements inherit. Defines the interface:

| Method | Description |
|---|---|
| `start()` | Called by `model.initialize()`. Resets internal state. |
| `receive(item) -> bool` | Called by a Link when an item arrives. Returns `True` if accepted. |
| `unblock() -> bool` | Called by a Link when downstream capacity freed. Resumes sending if blocked. |
| `check_availability(item) -> bool` | Returns `True` if the element can immediately accept `item`. |
| `connect(successors: list, **kwargs)` | Creates a `GeneralLink` from this element to all listed successors. |
| `connect_multiple(predecessors, successors, **kwargs)` | Class-level helper for fan-in/fan-out wiring. |
| `get_stats_collector()` | Returns the `ElementStatsCollector` for this element. |
| `set_input(link)` / `get_input()` | Set/get the upstream link. |
| `set_output(link)` / `get_output()` | Set/get the downstream link. |

#### `connect()` Behaviour

```python
element_a.connect([element_b, element_c], strategy=RoundRobinStrategy())
```

- If `element_a` already has an output link, the new destinations are merged into it.
- If `element_b` already has an input link, the new origin is merged into it.
- The optional `strategy` keyword argument selects an `OutputStrategy` (default: `FirstAvailableStrategy`).

---

### 7.2 Source (abstract base)

**Location:** `PyFlow/Elements/source.py`

Abstract base for all source types. Adds:

| Attribute / Method | Description |
|---|---|
| `model_item` | Optional template `Item` used to stamp copies. |
| `create_item(name=None) -> Item` | Returns a new Item; if `model_item` is set, calls `copy_model()`. |
| `number_items` | Count of items generated so far (reset on `start()`). |

---

### 7.3 InfiniteSource

**Location:** `PyFlow/Elements/infiniteSource.py`

**Behaviour:** Generates items as fast as the downstream network can accept them. Immediately after the simulation starts it pushes items until the first blocked element, then waits to be unblocked.

```python
InfiniteSource(name: str, model: Model, model_item: Optional[Item] = None)
```

| Parameter | Description |
|---|---|
| `name` | Element name. |
| `clock` | SimClock instance. |
| `model_item` | Optional template Item. |

**Flow logic:**
- On `start()`: schedules an immediate event (`time=0`) to begin sending.
- On `execute()`: creates and sends items in a tight loop until `send()` returns `False` (downstream blocked).
- On `unblock()`: resumes by sending one item and then re-entering the tight loop.

**Use case:** Model an infinite supply upstream of a bottleneck (e.g., studying a server's throughput capacity).

---

### 7.4 InterArrivalSource

**Location:** `PyFlow/Elements/interArrivalSource.py`

**Behaviour:** Generates items with inter-arrival times drawn from a distribution (or expression). The next arrival is scheduled **after** the previous item is successfully sent — mirroring FlexSim's Source behaviour (inter-departure time, not purely inter-arrival time).

```python
InterArrivalSource(
    name: str,
    model: Model,
    interarrival_dist: Union[stats.rv_continuous, stats.rv_discrete, str],
    model_item: Optional[Item] = None
)
```

| Parameter | Description |
|---|---|
| `name` | Element name. |
| `clock` | SimClock instance. |
| `interarrival_dist` | A `scipy.stats` distribution **or** a Python expression string. |
| `model_item` | Optional template Item. |

**Distribution examples:**

```python
# Exponential arrivals with mean 2
stats.expon(scale=2)

# Deterministic arrivals every 5 time units
stats.uniform(loc=5, scale=0)

# Expression string (no item context needed here, use "None")
"5.0"
```

**Flow logic:**
- Schedules the first arrival at `start()`.
- On `execute()`: creates one item, attempts to send it. If successful, schedules the next arrival. If blocked, stores the item and waits.
- On `unblock()`: sends the stored item and then schedules the next arrival.

---

### 7.5 InterArrivalBufferingSource

**Location:** `PyFlow/Elements/interArrivalBufferingSource.py`

**Behaviour:** Like `InterArrivalSource`, but uses true inter-arrival spacing (the next arrival is always scheduled from the moment of creation, regardless of downstream availability). Items blocked during a blockage are buffered internally and sent as soon as the downstream unblocks.

```python
InterArrivalBufferingSource(
    name: str,
    model: Model,
    interarrival_dist: Union[stats.rv_continuous, stats.rv_discrete, str],
    model_item: Optional[Item] = None
)
```

**Use case:** When arrival times are independent of processing (e.g., customers arriving at a physical counter, who wait in-place rather than being lost).

---

### 7.6 ScheduleSource

**Location:** `PyFlow/Elements/scheduleSource.py`

**Behaviour:** Reads a schedule from a file or dictionary and generates items at the exact times specified. Supports Excel (`.xlsx`), CSV (`.csv`), whitespace-delimited (`.data`), and Python `dict`.

```python
ScheduleSource(
    name: str,
    model: Model,
    file_name: Optional[str] = None,
    data_dict: Optional[Dict[str, List[Any]]] = None,
    model_item: Optional[Item] = None,
    sheet_name: Optional[str] = None
)
```

#### Schedule File Format

The file/dict must have at minimum a `Time` column. Optional columns:

| Column | Type | Description |
|---|---|---|
| `Time` | float | Absolute simulation time at which the arrival occurs. |
| `Name` | str | Name assigned to the generated item. |
| `Q` | int | Number of items to generate at this time step (batch size, default 1). |
| *any other column* | any | Loaded as an item label with the column header as the key. |

**Example CSV:**

```
Time,Name,Q,ProcessTime
0,JobA,1,3.5
5,JobB,2,2.0
10,JobC,1,5.0
```

**Example dict usage:**

```python
schedule = {
    "Time": [0, 5, 10],
    "Name": ["JobA", "JobB", "JobC"],
    "Q":    [1, 2, 1]
}
source = ScheduleSource("Source", model, data_dict=schedule, model_item=model)
```

**Flow logic:**
- Reads rows one by one and schedules an event at the time specified in each row.
- If blocked, items are queued internally (`blocked_items`) and flushed on `unblock()`.

---

### 7.7 ItemsQueue

**Location:** `PyFlow/Elements/itemsQueue.py`

**Behaviour:** A finite-capacity FIFO buffer. Immediately forwards items downstream; if downstream is blocked, holds them internally until capacity is available.

```python
ItemsQueue(capacity: int, name: str, model: Model)
```

| Parameter | Description |
|---|---|
| `capacity` | Maximum number of items the queue can hold simultaneously. |
| `name` | Element name. |
| `clock` | SimClock instance. |

**Flow logic:**
- `receive(item)`: If the queue has space, it immediately tries to send downstream. If blocked, it stores the item. Returns `False` if full.
- `unblock()`: Pops the front item and sends downstream; notifies upstream on success.
- `check_availability(item)`: Returns `True` if `current_items < capacity`.

**Use case:** Acts as a waiting room or buffer between two stages (e.g., between a source and a server).

---

### 7.8 MultiServer

**Location:** `PyFlow/Elements/multiServer.py`

**Behaviour:** A workstation with `num_servers` parallel processing slots. Each slot holds one item at a time for a delay sampled from `delay_strategy`. Items are processed in FIFO order.

```python
MultiServer(
    num_servers: int,
    delay_strategy: Union[stats.rv_continuous, stats.rv_discrete, str],
    name: str,
    model: Model
)
```

| Parameter | Description |
|---|---|
| `num_servers` | Number of parallel processing slots. |
| `delay_strategy` | Scipy distribution **or** Python expression string for service time. |
| `name` | Element name. |
| `clock` | SimClock instance. |

**States per slot:**
- `IDLE` — slot is free.
- `BUSY` — item is being processed; a completion event is scheduled.
- (Implicitly) `BLOCKED` — item has completed but downstream cannot accept it; item sits in `completed` deque.

**Flow logic:**
- `receive(item)`: Takes an idle slot, schedules a completion event.
- On completion: tries `send()` downstream; if blocked, stores in `completed`.
- `unblock()`: Sends from `completed` and recycles the slot.
- `check_availability(item)`: Returns `True` if `current_items < num_servers`.

**Example — Single server, exponential service time:**

```python
processor = MultiServer(1, stats.expon(scale=3), "Processor", model)
```

**Example — Label-driven service time:**

```python
# Item must have a label "ServiceTime"
processor = MultiServer(1, "item.get_label_value('ServiceTime')", "Processor", model)
```

---

### 7.9 Combiner

**Location:** `PyFlow/Elements/combiner.py`

**Behaviour:** Assembles components onto a **main item**. Has exactly **1 main input port** (via the element's normal input link) and **N component input ports** (`CombinerInput` objects). After the main item arrives, it waits until each component port has accumulated the required quantity, then starts processing for a delay, then sends the combined main item downstream.

```python
Combiner(
    requirements: List[int],
    delay_strategy: Union[stats.rv_continuous, stats.rv_discrete, str],
    name: str,
    model: Model,
    **kwargs
)
```

| Parameter | Description |
|---|---|
| `requirements` | List of required item counts per component input. `[2, 1]` means port 0 needs 2 components, port 1 needs 1. |
| `delay_strategy` | Processing time distribution or expression. |
| `name` | Element name. |
| `model` | the Model. |

**Keyword arguments (`kwargs`):**

| Kwarg | Type | Default | Description |
|---|---|---|---|
| `batch_mode` | `bool` | `False` | If `True`, component items are nested inside the main item (accessible via `the_item` sub-items). |
| `pull_mode` | `InputStrategy` | `DefaultStrategy()` | Strategy that filters which items are accepted by the component ports. |
| `update_requirements` | `bool` | `False` | If `True`, requirements are updated from label values of the arriving main item. |
| `update_labels` | `List[str]` | `None` | Label names (one per component port) whose values override the `requirements` for that port. |

**Accessing component input ports:**

```python
combiner.get_component_input(i)  # Returns CombinerInput for port index i
combiner.get_inputs_count()      # Returns number of component ports
```

**Wiring the Combiner:**

```python
# Main item flow → Combiner's main input
buffer_main.connect([combiner])

# Component flows → individual component input ports
buffer_comp0.connect([combiner.get_component_input(0)])
buffer_comp1.connect([combiner.get_component_input(1)])

# Output
combiner.connect([sink])
```

**State machine:**
1. `IDLE` → Main item arrives → `RECEIVING`
2. `RECEIVING` → Combiner pulls components from all ports
3. All requirements met → `BUSY` (processing event scheduled)
4. Processing completes → tries to send → `IDLE` (success) or `BLOCKED` (downstream full)

**Dynamic requirements example (label-driven):**

```python
# The main item has labels "Req0" and "Req1" specifying component quantities
combiner = Combiner(
    requirements=[1, 1],
    delay_strategy=stats.expon(scale=2),
    name="Combiner",
    model=model,
    update_requirements=True,
    update_labels=["Req0", "Req1"]
)
```

---

### 7.10 MultiAssembler

**Location:** `PyFlow/Elements/multiAssembler.py`

**Behaviour:** Similar to `Combiner` but creates a **new output item** rather than annotating an existing main item. Operates as a parallel assembler with `num_servers` slots. Does **not** have a main item input port — it listens to all component ports equally and starts processing once requirements are satisfied.

```python
MultiAssembler(
    num_servers: int,
    requirements: List[int],
    delay_strategy: Union[stats.rv_continuous, stats.rv_discrete, str],
    name: str,
    model: Model,
    batch_mode: bool = False
)
```

| Parameter | Description |
|---|---|
| `num_servers` | Number of parallel assembly slots. |
| `requirements` | Required item count per constrained input port. |
| `delay_strategy` | Processing time. |
| `name` | Element name. |
| `model` | the Model. |
| `batch_mode` | If `True`, source items are embedded in the new output item. |

**Accessing component input ports:**

```python
assembler.get_component_input(i)   # Returns ConstrainedInput for port i
assembler.get_inputs_count()       # Number of component ports
```

**Wiring:**

```python
buffer1.connect([assembler.get_component_input(0)])
buffer2.connect([assembler.get_component_input(1)])
assembler.connect([sink])
```

**Key difference from Combiner:** The MultiAssembler does not require a main item; it creates a brand-new `Item` each time requirements are fulfilled across all ports. It can serve multiple assembly jobs concurrently (up to `num_servers`).

---

### 7.11 Sink

**Location:** `PyFlow/Elements/sink.py`

**Behaviour:** Terminal element. Accepts any item, increments its internal counter, and discards the item. Always returns `True` from `check_availability()`.

```python
Sink(name: str, model: Model)
```

**Use:** Acts as the endpoint of the network. All statistics (throughput, etc.) are typically read from the sink's `ElementStatsCollector`.

```python
sink.get_stats_collector().get_var_input_value()    # Total items received
```

---

### 7.12 CombinerInput

**Location:** `PyFlow/Elements/combinerInput.py`

An internal element representing one component input port of a `Combiner`. Created automatically by `Combiner.__init__` — **do not instantiate directly**.

**Behaviour:**
- Acts as a bounded queue for incoming components.
- Only accepts items when the parent `Combiner` is in `RECEIVING` state.
- Applies the `InputStrategy` to filter items (e.g., label matching).
- Notifies the `Combiner` via `component_received()` when a new item arrives.

**Key method:**

```python
combiner_input.set_capacity(n: int)   # Dynamically change buffer capacity
```

**Capacity = -1** means unlimited (accept as many components as come in while the Combiner is receiving).

---

### 7.13 ConstrainedInput

**Location:** `PyFlow/Elements/constrainedInput.py`

Analogous to `CombinerInput` but used by `MultiAssembler`. Created automatically — **do not instantiate directly**.

**Difference from CombinerInput:** `ConstrainedInput` always reports `is_main_receiving() = True`, meaning it accepts items at any time (not gated by a main item arrival).

---

### 7.14 ServerProcess

**Location:** `PyFlow/Elements/serverProcess.py`

Represents one processing slot within a `MultiServer` or `Combiner`. Holds a reference to the item being processed and fires a completion event when the delay expires.

- Created automatically inside `MultiServer.start()` — **do not instantiate directly**.
- `execute()` calls `my_server.complete_server_process(self)`.

---

## 8. Links — Connectivity Layer

**Location:** `PyFlow/Link/generalLink.py`, `PyFlow/Link/outputStrategy.py`, `PyFlow/Elements/inputStrategy.py`

`element.connect([successors], strategy=...)` creates the links; `Element.connect_multiple(preds, succs,
strategy=...)` connects many origins (each origin gets its own copy of the strategy). Every element
has an **output strategy** (`element.output_strategy`, default first available) and an **input
strategy** (`element.input_strategy`, default accept all; `element.set_input_strategy(...)`).

`GeneralLink.send(item)`:
1. refused if the origin is stopped (output blocked);
2. the origin's output strategy picks a destination among those with
   `can_accept(item, origin)` = not stopped + `check_availability` + input strategy;
3. statistics are recorded only if `receive()` accepts the item (otherwise rolled back).

Refused origins wait in a FIFO and get priority when `notify_available()` is called.

### Output strategies

| Strategy | Behaviour |
|---|---|
| `FirstAvailableStrategy()` | First destination that can accept. |
| `RoundRobinStrategy()` | Rotates, skipping destinations that cannot accept. |
| `QueueSizeStrategy()` / `ShortestQueueStrategy()` | Fewest items (`get_queue_length()`); ties to the lowest index. |
| `MostAvailableCapacityStrategy()` | Most free capacity (`get_free_capacity()`). |
| `LabelBasedStrategy(label)` | The label value is the destination index. |
| `LabelRoutingStrategy(label, {"A": 0, "B": 1}, default_index=-1)` | Value → index; waits if that destination is full (no fallback). |
| `PriorityRoutingStrategy()` | `item.priority > 0` → first available, else shortest queue. |
| `ParameterizedRoutingStrategy(key, default)` | `model.parameters[key]` = `"first_available" \| "round_robin" \| "shortest_queue" \| "most_capacity"` or an index (experiments). |
| `DelegateOutputStrategy(fn)` | `fn(outputs, item, source) -> index`. |

Custom strategies subclass `OutputStrategy` and implement `select_output(outputs, item, context)`
(`context.source`, `context.model`, `context.parameters`, `context.now`), testing destinations with
`self.accepts(output, item, context)`. The old two-argument signature still works.

### Input strategies

| Strategy | Accepts |
|---|---|
| `DefaultStrategy()` | everything |
| `SingleLabelStrategy(label, value)` | items whose label equals the value (updated by the Combiner main item) |
| `MultiLabelStrategy({label: [values]})` | items with any of the values |
| `OriginNameInputStrategy(names)` / `OriginTypeInputStrategy(class_names)` | items sent by those elements / element classes |
| `MaxQueueInputStrategy(n)` | while the element holds fewer than `n` items |
| `CompositeAndInputStrategy(*s)` / `CompositeOrInputStrategy(*s)` | all / any |

Every element reports `get_queue_length()` and `get_free_capacity()`.

---

## 9. Samplers (service and inter-arrival times)

**Location:** `PyFlow/sampling.py`

Every time argument (`delay_strategy`, `interarrival_dist`, setup times, downtime `ttf`/`ttr`)
accepts a sampler specification. Each element binds it to its own random stream (keyed by
element name and purpose), so the same seed gives the same results.

| Spec | Example | Meaning |
|---|---|---|
| number | `5` | constant |
| scipy frozen distribution | `stats.expon(scale=2)` | drawn with the element's own seeded stream |
| SimuLean `SamplerSpec` | `"Exponential~0.5"`, `"Triangular~3~5~8"` | same syntax as SimuLean (`Exponential` takes a **rate**; `ExponentialMean` a mean). Types: Constant, Uniform, Normal, Exponential, ExponentialMean, Triangular, Gamma, Weibull, LogNormal, Beta, ChiSquare, StudentT, FDistribution, Poisson, Binomial, DiscreteUniform, LabelExpression. Unknown types or wrong parameter counts raise `E_INVALID_DIST`. |
| expression | `"tSoldadura + tInspeccion * inspeccionOn"` | see below |
| `Sampler` | `ConstantSampler(3)` | used as is |

Negative samples raise `E_NEGATIVE_SAMPLE` unless the sampler is built with
`negative="truncate"`. `Normal~` and `StudentT~` specs truncate at 0, as in SimuLean.

**Expressions** are evaluated safely (`PyFlow/expressions.py`: `ast` whitelist, no `eval`). Item
labels are available by name, and `item` is the current item (`item.get_label_value('PT')`,
`item.type`...). Functions: `min, max, abs, round, int, float`.

```python
processor = MultiServer(1, "ServiceTime * 1.2", "Proc", model)
```

---|---|---|
| number | `5` | constant |
| scipy frozen distribution | `stats.expon(scale=2)` | drawn with the element's own seeded stream |
| SimuLean `SamplerSpec` | `"Exponential~0.5"`, `"Triangular~3~5~8"` | same syntax as SimuLean (`Exponential` takes a **rate**; `ExponentialMean` a mean). Types: Constant, Uniform, Normal, Exponential, ExponentialMean, Triangular, Gamma, Weibull, LogNormal, Beta, ChiSquare, StudentT, FDistribution, Poisson, Binomial, DiscreteUniform, LabelExpression. Unknown types or wrong parameter counts raise `E_INVALID_DIST`. |
| expression | `"tSoldadura + tInspeccion * inspeccionOn"` | see below |
| `Sampler` | `ConstantSampler(3)` | used as is |

Negative samples raise `E_NEGATIVE_SAMPLE` unless the sampler is built with
`negative="truncate"`. `Normal~` and `StudentT~` specs truncate at 0, as in SimuLean.

### ExpressionDelayStrategy

Evaluates an arithmetic expression safely (`PyFlow/expressions.py`: `ast` whitelist, no `eval`). Item labels are available
by name, and `item` refers to the current `Item` (public methods only). Functions: `min, max,
abs, round, int, float`.

```python
# Read delay from an item label
"item.get_label_value('ServiceTime')"

# Arithmetic on labels
"float(item.get_label_value('Weight')) * 0.5 + 1.0"
```

The expression string is passed directly as `delay_strategy`:

```python
processor = MultiServer(1, "item.get_label_value('ServiceTime')", "Proc", model)
```

---

## 10. Input Strategies

**Location:** `PyFlow/Elements/inputStrategy.py`

Input strategies are used by `CombinerInput` ports to filter which items they accept. Passed as `pull_mode` to `Combiner`.

| Strategy | Class | Constructor | Behaviour |
|---|---|---|---|
| Default | `DefaultStrategy` | `DefaultStrategy()` | Accepts every item. |
| Single Label | `SingleLabelStrategy` | `SingleLabelStrategy(label_name, value=None)` | Accepts items whose `label_name` equals a stored value. The stored value is updated each time a new **main item** arrives (via `update_strategy`). |
| Multi Label | `MultiLabelStrategy` | `MultiLabelStrategy(accepted_labels: dict)` | Accepts items that match any label/value pair in `accepted_labels`. |

**SingleLabelStrategy example** — components must share the same `OrderID` as the main item:

```python
strategy = SingleLabelStrategy("OrderID")
combiner = Combiner([1], stats.expon(scale=2), "Combiner", model, pull_mode=strategy)
```

When the main item arrives (e.g., `OrderID=42`), `update_strategy` sets `required_label_value=42`, so only components with `OrderID=42` are accepted at the component port.

---

## 11. Statistics Collection

Every `Element` has an `ElementStatsCollector` automatically attached at construction time, accessible via:

```python
element.get_stats_collector()
```

### Tracked Variables

| Variable | Type | Description |
|---|---|---|
| `var_input` | `StatLevelVariable` | Cumulative count of items **entered** this element. |
| `var_output` | `StatLevelVariable` | Cumulative count of items **exited** this element. |
| `var_content` | `StatLevelVariable` | Current number of items **inside** this element (in-queue + in-service). |
| `var_staytime` | `StatTimeVariable` | Time each item spent inside this element (from entry to exit). |

### Accessor Methods

All methods below are called on `element.get_stats_collector()`:

```python
sc = element.get_stats_collector()
```

#### Current Values

| Method | Description |
|---|---|
| `get_var_input_value() -> float` | Total items that entered (running sum). |
| `get_var_output_value() -> float` | Total items that exited (running sum). |
| `get_var_content_value() -> float` | Items currently inside the element. |
| `get_var_staytime_value() -> float` | Most recent stay-time recorded. |

#### Averages

| Method | Description |
|---|---|
| `get_var_input_average() -> float` | Running average of input increments. |
| `get_var_output_average() -> float` | Running average of output increments. |
| `get_var_content_average() -> float` | Running average of content level. |
| `get_var_staytime_average() -> float` | Average stay-time across all items. |

#### Min / Max

| Method | Description |
|---|---|
| `get_var_input_max() / _min()` | Max/min observed input value. |
| `get_var_output_max() / _min()` | Max/min observed output value. |
| `get_var_content_max() / _min()` | Max/min observed content level. |
| `get_var_staytime_max() / _min()` | Max/min stay-time. |

#### Full Stats Dict

```python
sc.get_var_staytime_stats()
# Returns: {'max': ..., 'min': ..., 'average': ..., 'count': ..., 'current': ...}
```

### StatLevelVariable vs StatTimeVariable

- **`StatLevelVariable`**: Tracks a cumulative counter. `update(delta)` adds `delta` to `value`. Useful for counts (input, output) and queue length (content).
- **`StatTimeVariable`**: Tracks time-series measurements. `update(value)` sets `value` directly and computes a running average. Used for stay-times.

---

## 13. Simulation Pipeline

Follow these steps in order for every simulation:

### Step 1 — Import

```python
from PyFlow import (
    SimClock,
    InfiniteSource, InterArrivalSource, ScheduleSource,
    ItemsQueue,
    MultiServer, Combiner, MultiAssembler,
    Sink,
    Item
)
from scipy import stats
```

### Step 2 — Create the Model

```python
model = Model(seed=1)
```

Create a new `Model` for every independent run.

### Step 3 — Instantiate Elements

Create all elements in the **same model**. The order does not matter for correctness, but a top-down order from source to sink improves readability.

```python
source    = InterArrivalSource("Source", model, stats.expon(scale=2))
buffer    = ItemsQueue(1000, "Buffer", model)
processor = MultiServer(2, stats.expon(scale=3), "Processor", model)
sink      = Sink("Sink", model)
```

### Step 4 — Connect Elements

```python
source.connect([buffer])
buffer.connect([processor])
processor.connect([sink])
```

For multi-path or multi-input networks:

```python
# Fan-out with round-robin
source.connect([processor_a, processor_b], strategy=RoundRobinStrategy())

# Combiner: main flow + component flow
source_main.connect([buffer_main])
source_comp.connect([buffer_comp])
buffer_main.connect([combiner])
buffer_comp.connect([combiner.get_component_input(0)])
combiner.connect([sink])
```

### Step 5 — Initialize

```python
model.initialize()
```

This resets simulation time to 0 and calls `start()` on every registered element.

### Step 6 — Run

```python
# Run to a fixed end time
model.advance_clock(max_sim_time)

# Or run step by step
sim_time = 0
step = 1000
while sim_time < max_sim_time:
    model.advance_clock(sim_time + step)
    sim_time += step
```

`advance_clock(t)` returns `False` when the event calendar is empty (simulation has no more events — network is idle). Use this to detect early termination:

```python
while model.advance_clock(sim_time + step):
    sim_time += step
    if sim_time >= max_sim_time:
        break
```

### Step 7 — Collect Results

```python
sc = sink.get_stats_collector()
print(f"Throughput:        {sc.get_var_input_value()}")

sc_buf = buffer.get_stats_collector()
print(f"Avg queue length:  {sc_buf.get_var_content_average()}")
print(f"Avg waiting time:  {sc_buf.get_var_staytime_average()}")
print(f"Max queue length:  {sc_buf.get_var_content_max()}")
```

---

## 14. Complete Examples

### Example 1 — M/M/1 Queue

Classic single-server queue with exponential arrivals and exponential service times.

```python
from PyFlow import Model, InterArrivalSource, ItemsQueue, MultiServer, Sink
from scipy import stats

model = Model(seed=1)

source    = InterArrivalSource("Source", model, stats.expon(scale=2))
buffer    = ItemsQueue(1_000_000, "Queue", model)
processor = MultiServer(1, stats.expon(scale=2), "Server", model)
sink      = Sink("Sink", model)

source.connect([buffer])
buffer.connect([processor])
processor.connect([sink])

model.initialize()
model.advance_clock(100_000)

print(f"Items processed:      {sink.get_stats_collector().get_var_input_value()}")
print(f"Avg queue length:     {buffer.get_stats_collector().get_var_content_average()}")
print(f"Avg waiting time:     {buffer.get_stats_collector().get_var_staytime_average()}")
```

---

### Example 2 — Serial Production Line

A line of N machines, each with a queue, driven by an infinite source.

```python
from PyFlow import Model, InfiniteSource, ItemsQueue, MultiServer, Sink
from scipy import stats

model = Model(seed=1)

n_machines = 3
mean_service = 4.0
queue_cap = 100

elements = [InfiniteSource("Source", model)]

for i in range(n_machines):
    elements.append(MultiServer(1, stats.expon(scale=mean_service), f"M{i+1}", model))
    if i < n_machines - 1:
        elements.append(ItemsQueue(queue_cap, f"Q{i+1}", model))

sink = Sink("Sink", model)
elements.append(sink)

for i in range(len(elements) - 1):
    elements[i].connect([elements[i + 1]])

model.initialize()
model.advance_clock(10_000)

print(f"Throughput: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 3 — Combiner (Assembly)

One main item assembled with 2 components from separate feeds.

```python
from PyFlow import (SimClock, InterArrivalSource, ItemsQueue, Combiner, Sink)
from scipy import stats

model = Model(seed=1)

src_main = InterArrivalSource("Main",  clock, stats.uniform(loc=2, scale=0))
src_comp = InterArrivalSource("Comp",  clock, stats.uniform(loc=1, scale=0))
buf_main = ItemsQueue(100, "BufMain", model)
buf_comp = ItemsQueue(100, "BufComp", model)
sink     = Sink("Sink", model)

combiner = Combiner(
    requirements=[2],                         # 2 components needed per main item
    delay_strategy=stats.uniform(loc=3, scale=0),
    name="Combiner",
    model=model
)

src_main.connect([buf_main])
src_comp.connect([buf_comp])
buf_main.connect([combiner])                         # Main item feed
buf_comp.connect([combiner.get_component_input(0)])  # Component feed → port 0
combiner.connect([sink])

model.initialize()
model.advance_clock(1000)

print(f"Assembled items: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 4 — MultiAssembler (Parallel Assembly)

Two component streams, 2 parallel assembly slots, new items created.

```python
from PyFlow import (SimClock, InterArrivalSource, ItemsQueue, MultiAssembler, Sink)
from scipy import stats

model = Model(seed=1)

src1 = InterArrivalSource("S1", model, stats.uniform(loc=4, scale=0))
src2 = InterArrivalSource("S2", model, stats.uniform(loc=4, scale=0))
buf1 = ItemsQueue(100, "Q1", model)
buf2 = ItemsQueue(100, "Q2", model)
sink = Sink("Sink", model)

assembler = MultiAssembler(
    num_servers=2,
    requirements=[1, 1],
    delay_strategy=stats.expon(scale=4),
    name="Assembler",
    model=model
)

src1.connect([buf1])
src2.connect([buf2])
buf1.connect([assembler.get_component_input(0)])
buf2.connect([assembler.get_component_input(1)])
assembler.connect([sink])

model.initialize()
model.advance_clock(1000)

print(f"Assembled items: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 5 — ScheduleSource with Labels

Items arrive at scheduled times carrying custom labels for expression-driven delays.

```python
from PyFlow import Model, ScheduleSource, MultiServer, Sink, Item
from scipy import stats

model = Model(seed=1)

schedule = {
    "Time": [0, 5, 12, 20],
    "Name": ["JobA", "JobB", "JobC", "JobD"],
    "Q":    [1, 1, 2, 1],
    "ServiceTime": [3.0, 1.5, 2.0, 4.0]
}
model = Item(0)
source    = ScheduleSource("Source", model, data_dict=schedule, model_item=model)
processor = MultiServer(1, "item.get_label_value('ServiceTime')", "Proc", model)
sink      = Sink("Sink", model)

source.connect([processor])
processor.connect([sink])

model.initialize()
model.advance_clock(100)

print(f"Items completed: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 6 — Multiple Output Routing (Label-Based)

Route items to one of two sinks based on an item label.

```python
from PyFlow import (SimClock, InterArrivalSource, MultiServer, Sink, Item)
from PyFlow.Link.outputStrategy import LabelBasedStrategy
from scipy import stats

model = Model(seed=1)

# Items alternate between type 0 and type 1
def make_item(model):
    # For illustration – in practice set labels in model_item or ScheduleSource
    pass

model_a = Item(0, labels={"Route": 0})
model_b = Item(0, labels={"Route": 1})

src_a = InterArrivalSource("SrcA", model, stats.expon(scale=3), model_item=model_a)
src_b = InterArrivalSource("SrcB", model, stats.expon(scale=3), model_item=model_b)
proc  = MultiServer(2, stats.expon(scale=2), "Proc", model)
sink0 = Sink("Sink0", model)
sink1 = Sink("Sink1", model)

src_a.connect([proc])
src_b.connect([proc])
proc.connect([sink0, sink1], strategy=LabelBasedStrategy("Route"))

model.initialize()
model.advance_clock(1000)

print(f"Sink0: {sink0.get_stats_collector().get_var_input_value()}")
print(f"Sink1: {sink1.get_stats_collector().get_var_input_value()}")
```

---

### Example 7 — Design of Experiments (Multiple Runs)

```python
from PyFlow import Model, InterArrivalSource, ItemsQueue, MultiServer, Sink
from scipy import stats

def run_simulation(mean_service, sim_time=10_000):
    SimClock._instance = None          # Reset singleton for each independent run
    model = Model(seed=1)

    source    = InterArrivalSource("Source", model, stats.expon(scale=2))
    buffer    = ItemsQueue(10_000, "Queue", model)
    processor = MultiServer(1, stats.expon(scale=mean_service), "Server", model)
    sink      = Sink("Sink", model)

    source.connect([buffer])
    buffer.connect([processor])
    processor.connect([sink])

    model.initialize()
    model.advance_clock(sim_time)

    return {
        "throughput":   sink.get_stats_collector().get_var_input_value(),
        "avg_wip":      buffer.get_stats_collector().get_var_content_average(),
        "avg_waittime": buffer.get_stats_collector().get_var_staytime_average(),
    }

scenarios = [1.5, 2.0, 2.5, 3.0]
for ms in scenarios:
    result = run_simulation(ms)
    print(f"mean_service={ms}: {result}")
```

---

## 14b. States, Stops, Downtime and Shifts

**Location:** `PyFlow/states.py`, `PyFlow/stops.py`, `PyFlow/work.py`, `PyFlow/downtime.py`, `PyFlow/simcalendar.py`

### States

Every element has a visible state (`element.state`): `IDLE`, `PROCESSING`, `BLOCKED`, `RECEIVING`,
`SETUP`, ... and, while a stop is effective, the stop state (`BREAKDOWN`, `OFF_SHIFT`,
`SCHEDULED_DOWN`, `STOPPED` or any custom string). States are strings, so models can add their own.

| Method | Description |
|---|---|
| `element.time_in_state(s)` / `state_ratio(s)` | Time / fraction since the last statistics reset (warm-up aware). |
| `element.state_breakdown()` / `state_ratios()` | All states visited. |
| `element.state_log` | `[(t, state entered), ...]` for the run. |
| `element.underlying_state` | The element's own state while a stop is shown. |

Servers: `PROCESSING` if any server works, else `SETUP`, else `BLOCKED` (finished items waiting),
else `IDLE`. Queues: `BLOCKED` while items wait, else `IDLE`. Sources: `BLOCKED` while holding items.

### Stops

```python
token = machine.stop("BREAKDOWN")                    # immediate: work pauses, input/output blocked
machine.resume(token)                                # work continues where it stopped
token = machine.stop("OFF_SHIFT", "after_current")   # finish the current job, accept no more
machine.stop("STOPPED", block_input=False, block_output=True)
```

Stops overlap (blocks are counted; the most recent effective stop is shown). On resume the
element retries sending and pulls from upstream. Custom elements should schedule timed work with
`self.schedule_work(fn, delay)` so that stops pause it.

### Setup times

`MultiServer(..., setup_time=2)` applies a changeover when a server starts an item whose `type`
differs from the previous one; `setup_time={("A", "B"): 3, "B": 1}` gives a matrix (by
`(from, to)` or by `to`).

### Downtime generators

| Generator | Use |
|---|---|
| `TimetableDowntime(m, [DowntimeInterval(start, duration, state, mode, code)], overlap="allow"\|"serialize"\|"merge")` | Planned stops. |
| `MtbfMttrDowntime(m, ttf, ttr, basis="calendar"\|"busy", busy_states={"PROCESSING"})` | Random failures; `busy` counts only productive time. |
| `ShiftDowntime(m, "Mon-Fri 06:00-22:00")` | `OFF_SHIFT` (after_current) outside the shifts, using `model.calendar`. |
| `downtimes_from_table(rows_or_dataframe, DowntimeTableMapping(...), calendar)` | `{target: [DowntimeInterval]}` from a table (numbers or dates). |

Generators register with the model and start after the elements on `model.initialize()`.

### Calendar and shifts

`Model(calendar=SimCalendar("2026-01-05 06:00", seconds_per_unit=60))` maps simulation time to
dates (`model.to_datetime(t)`, `model.to_sim_time(date)`). `WeeklyShiftPattern.parse` accepts
`"Mon-Fri 06:00-14:00,14:00-22:00; Sat 06:00-14:00"` (day ranges wrap, `22:00-06:00` crosses
midnight, `00:00-24:00` is a whole day) and `holidays=[...]` (windows starting on a holiday are skipped).

---

## 14c. Model Specification (JSON / YAML)

A whole model can be written as data and loaded with `PyFlow.spec`. The same format is used by
the MCP server (`load_model_spec` / `export_model_spec`), so a model built by an agent can be
saved, versioned and run again from Python.

```python
from PyFlow.spec import ModelSpec

spec = ModelSpec.from_file("examples/models/assembly_line.json")
for issue in spec.validate_model():          # errors and warnings, nothing is built
    print(issue)
built = spec.build(seed=7)                   # seed overrides the file (replications)
results = built.run(until=10_000, warmup=1_000)
results["elements"]["m1"]["state_ratios"]    # {"PROCESSING": 0.71, "IDLE": 0.2, ...}
built["m1"]                                  # the MultiServer object, by id
spec.to_file("copy.json")                    # round trip; .yaml/.yml need PyYAML
```

Command line: `python examples/run_spec.py examples/models/assembly_line.json [--seed 7] [--json]`.

### Structure

```json
{
  "spec_version": 1,
  "name": "Line", "seed": 42,
  "calendar":   {"start": "2026-01-05 00:00", "seconds_per_unit": 60},
  "parameters": {"route": "shortest_queue"},
  "resources":   [{"id": "welders", "kind": "operator", "capacity": 2}],
  "elements":    [{"type": "MultiServer", "id": "m1", "num_servers": 2, "service_time": "Triangular~3~4~6",
                   "resources": ["welders"]}],
  "connections": [{"origin": "q", "destinations": ["m1", "m2"], "strategy": "RoundRobin"}],
  "downtimes":   [{"type": "Shift", "targets": ["m1"], "pattern": "Mon-Fri 06:00-14:00"}],
  "run": {"until": 7200, "warmup": 1440}
}
```

Only `elements` and `connections` are needed in practice. Unknown fields are rejected (typos are
reported instead of being ignored).

| Field | Meaning |
|---|---|
| `seed` | Model seed. Random streams are keyed by element **name** and purpose, so the same seed gives the same results and adding an element does not change the numbers of the others. |
| `calendar` | `start` date of t = 0 and `seconds_per_unit` (60 = the model works in minutes). Needed by `Shift` downtimes and dated intervals. |
| `parameters` | Model parameters (`Parameterized` routing, experiments). |
| `resources` | Shared resource pools: `{id, kind, capacity}` or `{id, kind, units: [{name, skills, attributes}]}`, optional `unit_order` (§14d, §14e). |
| `resource_rules` | `{request_order, discipline}` of the resource manager (§14e). |
| `run` | Defaults for `BuiltModel.run()`. |

### Elements

Every element has `type`, `id` (`^[A-Za-z][A-Za-z0-9_]*$`), optional `name` (default: the id) and
optional `input_strategy`.

| `type` | Fields |
|---|---|
| `InterArrivalSource` | `interarrival`; `item_type`, `labels`, `priority` |
| `InterArrivalBufferingSource` | as above (arrivals keep coming while blocked) |
| `InfiniteSource` | `item_type`, `labels`, `priority` |
| `ScheduleSource` | `jobs: [{time, name, qty, labels}]` **or** `file` (+ `sheet`) |
| `ItemsQueue` | `capacity` |
| `MultiServer` | `num_servers`, `service_time`, `setup_time` (a sampler, or `{by_type: {B: 2}, changes: [{from_type, to_type, time}]}`), `resources`, `resource_release` |
| `Combiner` | `requirements`, `service_time`, `batch_mode`, `pull_mode` (input strategy), `update_requirements`, `update_labels`, `resources`, `resource_release` |
| `MultiAssembler` | `num_servers`, `requirements`, `service_time`, `batch_mode`, `resources`, `resource_release` |

`resources`: a list of pool ids (`"welders"` = 1 unit during the whole service) or
`{pool, quantity, during: setup|processing|both, skill, where}`; `resource_release`: `on_finish` | `on_exit` (§14d).
| `Sink` | `keep_items` |

**Time fields** (`interarrival`, `service_time`, `ttf`, ...) accept a number, a SimuLean spec
string (`"Exponential~0.5"` is a *rate*, `"ExponentialMean~2"`, `"Triangular~3~5~8"`, ...), a
or a label expression (`"PT1 * 60"`). Strings are
checked when the spec is validated.

### Connections

`{"origin": id, "destinations": [...], "strategy": ...}`. Put every destination of an origin in
one connection. `"asm:0"` is component port 0 of a `Combiner` / `MultiAssembler` (a
`MultiAssembler` only receives through its ports).

Strategies: `"FirstAvailable"` (default), `"RoundRobin"`, `"ShortestQueue"`,
`"MostAvailableCapacity"`, `"PriorityRouting"`, or
`{"type": "LabelRouting", "label": "family", "mapping": {"A": 0, "1": 1}, "default_index": -1}`
(numeric labels match their text key), `{"type": "LabelBased", "label": "dest"}`,
`{"type": "Parameterized", "parameter": "route", "default": "FirstAvailable"}`.

Input strategies: `{"type": "Default" | "SingleLabel" (label, value) | "MultiLabel" (labels:
{label: [values]}) | "OriginName" (origins: element ids) | "OriginType" (types) | "MaxQueue"
(max_queue) | "And" | "Or" (strategies)}`.

### Downtimes

One generator per target. Common fields: `state`, `mode` (`immediate` | `after_current`),
`block_input`, `block_output`.

| `type` | Fields |
|---|---|
| `MtbfMttr` | `ttf`, `ttr`, `first_failure`, `basis` (`calendar` \| `busy`), `busy_states`, `code`, `repair_resources` (pool ids or `{pool, quantity, skill}`), `repair_priority`, `repair_wait_state` |
| `Timetable` | `intervals: [{start, duration \| end, state, mode, code, reason}]` (start/end may be dates), `overlap` (`allow` \| `serialize` \| `merge`) |
| `Shift` | `pattern` (`"Mon-Fri 06:00-14:00,14:00-22:00; Sat 06:00-14:00"`), `holidays` |

### Validation

`spec.validate_model()` (or `validate_spec(spec)`) returns `Issue(severity, code, message, path)`.
`build()` raises `SpecError` (a `ValueError` with `.issues`) on errors; warnings do not block
unless `strict_warnings=True`.

| Errors | Warnings |
|---|---|
| `E_DUPLICATE_ID`, `E_UNKNOWN_ELEMENT`, `E_SINK_AS_ORIGIN`, `E_SOURCE_AS_DESTINATION`, `E_SELF_LOOP`, `E_INVALID_PORT`, `E_PORT_REQUIRED`, `E_ROUTING_INDEX`, `E_UNKNOWN_RESOURCE`, `E_RESOURCE_INSUFFICIENT` | `W_UNCONNECTED_OUTPUT`, `W_NO_INPUT`, `W_UNFED_PORT`, `W_SPLIT_CONNECTION`, `W_MISSING_PARAMETER`, `W_DEFAULT_CALENDAR`, `W_DUPLICATE_NAME`, `W_NO_SOURCE`, `W_NO_SINK`, `W_UNUSED_RESOURCE` |

### Results

`BuiltModel.run()` / `results()` return JSON-ready dicts (`PyFlow.reporting.element_summary`):
`input_count`, `output_count`, `content_current/average/max` (time-weighted WIP), `staytime_*`
(`null` while nothing has left the element), `state`, `state_ratios`, and `blockage_count`
(servers), `type_counts` (sinks), `items_created` (sources). `results["resources"]` has the
statistics of every pool by id with its `units` (state, state ratios, utilization, completed
task sequences of each unit, §14d), `results["lists"]` the lists and `results["downtimes"]` every
downtime generator (`stop_count`, `total_downtime`; failures with `repair_resources` also
`repairs` and `repair_wait_*`). For models built by code, `PyFlow.reporting.model_summary(model)`
returns the same sections (plus `executers` outside pools); the MCP `run_experiment` and
`get_stats` return `stats`, `resources`, `lists` and `downtimes`.

### Adding an element type

```python
from typing import Literal
from pydantic import ConfigDict, Field
from PyFlow.spec import ElementSpecBase, register_element
from PyFlow.spec.bindings import Binding

class ConveyorSpec(ElementSpecBase):
    """Accumulating conveyor."""          # first paragraph = description shown to agents
    type: Literal["Conveyor"]
    model_config = ConfigDict(json_schema_extra={"examples": [{"type": "Conveyor", "id": "c1", "length": 12}]})
    length: float = Field(gt=0)
    speed: float = 1.0                    # same default as Conveyor.__init__

@register_element(ConveyorSpec, role="flow",          # role: source | flow | sink; ports=...
                  binding=Binding(Conveyor))          # engine class + field correspondence
def _build_conveyor(spec, ctx):
    return Conveyor(spec.length, spec.name, ctx.model, speed=spec.speed)
```

The new type is then accepted by `ModelSpec`, validated, listed by the MCP
`get_supported_types` and included in `ModelSpec.json_schema()`. Built-in types are also added to
`BUILTIN_ELEMENT_SPECS` (typed schema of the MCP tools), to the table above and to the
`create_elements_batch` docstring.

### Keeping the specification in sync (`tests/unit/test_spec_sync.py`)

Each spec class declares, with a `Binding`, the engine class it builds and how its fields map
to the constructor (`field_map` for renamed fields, `not_exposed` / `spec_only` with a reason,
`converted` for values transformed on the way). The sync test inspects the real constructor
signatures and fails when:

* a constructor gains, renames or loses a parameter that the spec does not reflect;
* a default value differs between the spec and the constructor;
* a new concrete element, output/input strategy or downtime generator class appears in the
  engine without a spec (or an explicit exclusion: `INTERNAL_ELEMENT_CLASSES`,
  `NOT_SERIALIZABLE_OUTPUT_STRATEGIES`);
* a registered type has no example, its example does not build, or it is missing from this
  document or from the MCP tool docstring;
* a sampler type is missing from the sampler description shown to agents.

The failure message says which field to add or which entry to update.

---

## 14d. Shared Resources (operators, robots, tools...)

`PyFlow/resources.py`. A `ResourcePool` is a set of units that elements need while they work:
operators, robots, tools, fixtures, inspectors... (`kind` is a free label for reports). Every
element with active service time accepts `resources` and `resource_release`: today
`MultiServer`, `Combiner` and `MultiAssembler`. New elements get the same behaviour through
the `ResourceUser` mixin.

```python
from PyFlow import Model, MultiServer, ResourcePool, ResourceRequirement

model = Model(seed=1)
welders = ResourcePool("Welders", model, capacity=2, kind="operator")
robots = ResourcePool("Robots", model, kind="robot",
                      units=[{"name": "R1", "skills": ["weld", "paint"]}, {"name": "R2", "skills": ["paint"]}])
tech = ResourcePool("Tech", model, capacity=1)

weld = MultiServer(2, "Triangular~3~4~6", "Weld", model, setup_time={"B": 5},
                   resources=[welders,                                               # 1 unit, whole service
                              ResourceRequirement(robots, skill="weld", during="processing"),
                              ResourceRequirement(tech, during="setup")],
                   resource_release="on_finish")
```

| Requirement field | Meaning |
|---|---|
| `pool` | the `ResourcePool` (a pool alone = 1 unit, `during="both"`) |
| `quantity` | units needed at once (default 1) |
| `during` | `"both"` (default: from the start of the setup to the end of the processing), `"setup"`, `"processing"` |
| `skill` | only units with this skill |
| `where` | query filter over the unit fields (and `item`, `element`), e.g. `"level >= item.complexity"` |

Rules (defaults; request order, discipline, unit choice and unit filters are configurable
with queries, see §14e "Resource rules"):

* **All or nothing.** A phase starts only when all its requirements are granted together; a
  waiting element holds nothing, so two elements cannot deadlock each other.
* **Order.** Waiting requests are served by item `priority` (higher first), then in request
  order. On each release the queue is scanned in that order and every request that can be fully
  served is granted, so a big request does not block smaller ones behind it (it can starve if
  small requests keep the units busy).
* **Unit choice.** Default `unit_order` = `"skills_count ASC, index ASC"`: among the idle units
  with the skill, the one with the fewest skills (then declaration order), so versatile units
  stay free for the tasks only they can do. Without `index`, ties follow the list order (the
  unit idle for longest first).
* **Release.** `"on_exit"` (default, as SimuLean) keeps the units while the finished item is
  blocked; `"on_finish"` frees them when the processing ends.
* **Units are task executers** (`Operator` by default, §14f) with their own states and
  statistics; idle units are published in `pool.list`. A grant reserves the units at once; a
  request that had to wait is told in a dt = 0 event (like list back-orders).
* **Stops.** Units stay held while the element is stopped; units granted during a stop wait
  for the resume (the work is paused).
* **Impossible requests** (more units, or units with a skill, than the pool has) are rejected
  when the element is created (`E_RESOURCE_INSUFFICIENT`).

### Repairs that need resources

`MtbfMttrDowntime(..., repair_resources=[techs], repair_priority=10)`: after a failure the
element shows `WAITING_FOR_REPAIR` until every repair resource is granted, then `BREAKDOWN`
for `ttr` (sampled when the repair starts); the units are released when the repair ends. It is
one stop (`restate_stop` changes its state), so `stop_count` and `total_downtime` count it once.
`repair_priority` orders the repair against other requests on the same pools (production
requests use the item priority, 0 by default). With `basis="calendar"` the next time to failure
counts from the end of the repair. The generator keeps `repairs`, `repair_wait_total` and
`repair_wait_max` (a repair's wait is measured from its failure, also when it started before the
warm-up reset).

```python
techs = ResourcePool("Techs", model, kind="technician",
                     units=[{"name": "T1", "skills": ["electric"]}, {"name": "T2", "skills": ["mechanic"]}])
MtbfMttrDowntime(press, "ExponentialMean~480", "ExponentialMean~30", basis="busy",
                 repair_resources=[ResourceRequirement(techs, skill="electric")], repair_priority=10)
```

### Statistics

While a slot waits, the element shows `WAITING_FOR_RESOURCE` (if no other slot is processing or
in setup). Pool statistics since the last reset (`PyFlow.reporting.resource_summary`, the
`resources` part of `BuiltModel.results()` and of the MCP results): `utilization` (time-weighted
busy units / capacity), `busy_*`, `queue_*` (waiting requests), `requests`, `grants`,
`wait_average`, `wait_max` and `unit_utilization` per unit. Waits are measured per request: a
joint request (operator + robot) counts its whole wait for both pools, because they are granted
together — a free robot can show waiting time caused by the operators.

---

## 14e. Queries and Model Lists (FlexSim-style)

### Queries (`PyFlow/query.py`)

Lists and resource rules use the same query language, the one of FlexSim lists:

```text
WHERE type == puller.type AND due - now < 60 ORDER BY priority DESC, age DESC
```

* Both parts are optional; a string without the keywords is an `ORDER BY` clause
  (`"utilization ASC"`). Each term is an expression followed by `ASC` (default) or `DESC`;
  ties keep the original order; `None` sorts last in ascending order.
* Expressions are the safe expressions of §9 (no `eval`) plus SQL spellings: `AND`, `OR`,
  `NOT`, `=` (equality), `<>`.
* `x.field` works on objects that expose fields: items (`type`, `name`, `priority`,
  `creation_time`, `item_number` and any label), elements (`name`, `class`, `state`,
  `queue_length`, `free_capacity`), resource units, list entries and requests.
* From Python, `where` / `order_by` may also be functions of the scope.

### Model lists (`PyFlow/lists.py`)

A `ModelList` is the rendezvous of SimuLean's `ModelList` and FlexSim's lists: producers
`push` values, consumers `pull` them with a query, and a pull that cannot be served waits as a
**back-order** until a push satisfies it.

```python
from PyFlow.lists import ModelList

orders = ModelList("Orders", model, fields={"slack": "due - now"}, backorder_order="priority DESC")
orders.push(item)                                         # or push(value, **data)
orders.pull("WHERE type == puller.type ORDER BY slack", puller=machine,
            on_fulfilled=lambda values: machine_start(values[0]))   # now or later (back-order)
orders.pull("ORDER BY age DESC", quantity=2)              # now only: list of values or []
orders.peek("WHERE slack < 0", quantity=None)             # look without taking
```

| Topic | Rule |
|---|---|
| Names in queries | list `fields` (expressions or `fn(entry, puller)`), then `value`, `puller`, `origin` (element that pushed it, or `None`), `age` (time in the list), `push_time`, `now`, then the `push(**data)` values, then the value's own fields (`type`, labels...). A field of `None` is `None` (SQL NULL) |
| Default order | first in, first out |
| `quantity` | all or nothing: a pull takes `quantity` values or none |
| Back-orders | re-evaluated on every push in `backorder_order` (default: oldest first; fields `priority`, `age`, `time`, `quantity`, `puller` and the puller's own fields); every back-order that can be fully served is served (first-fit) |
| Delivery | values reserved at once, callback in a dt = 0 event (`deliver="event"`), or inside the push (`"immediate"`); it may push or pull again |
| Unique values | by default a value already in the list is not added twice (`unique=False` to allow it) |
| Statistics | `summary()`: content (current, time-weighted average, max), back-orders (current, average, max), pushes, pulls, stay time and back-order wait (average, max); reset at the warm-up, cleared by `initialize()` |

Lists belong to the model (`model.lists[name]`). Back-orders are delivered in a separate event
at the same time (dt = 0, `deliver="event"`, the default): the values are reserved at once
(`contains()` stays true) and handed over in that event, like the re-entrance protection of
links. `deliver="immediate"` runs the callback inside the push (SimuLean's `ModelList`).

### Flow through lists (push to list / pull from list)

As in FlexSim, **sending to a list does not move the item**: it is announced. The item stays in
its origin (which keeps it as when its output is full: capacity, blocking and statistics as
usual) and the list holds an entry pointing to it (`origin`). A queue announces *every* item it
holds, so one list over several queues is a global priority queue. When a puller's query
matches, the item goes directly from its origin to the puller.

```python
jobs = ModelList("Jobs", model)
q1.connect([jobs])                                     # or q1.connect_to_list(jobs)
q2.connect([jobs])
m1.pull_from_list(jobs, "WHERE type == 'A' ORDER BY priority DESC, age DESC")
m2.pull_from_list(jobs, "ORDER BY age DESC", priority=1)
```

* **Pull.** An element pulling from a list asks for one item whenever it has space (free
  capacity and input not stopped); the pull waits as a back-order when nothing matches. Its
  query is combined with its input strategy (`can_accept(item, origin)`) and skips items of
  stopped origins (they become available again when the origin is resumed).
* **Transfer.** `ListInputLink` moves the item and records the statistics (exit of the origin,
  entry of the puller), like `GeneralLink`. If, at delivery, the origin no longer holds the
  item or the puller can no longer take it, the entry goes back to the list.
* **Origins.** Elements that can send to a list implement `holds_item(item)` and
  `release_item(item)`: queues, servers (`MultiServer`, `Combiner`, `MultiAssembler`: their
  finished items) and sources. An element has one input: either connections from elements or
  one list.
* **Values that are not items** (orders, tokens, messages) are pushed and pulled from code with
  callbacks.

In a specification: `"lists": [{"id": "jobs", "fields": {...}, "backorder_order": ...}]`; a
connection whose only destination is a list id pushes, and a connection whose origin is a list
id pulls (`"query"`, `"priority"`). Results have `results["lists"][id]` (`ModelList.summary()`).
Validation: `E_MIXED_LIST_DESTINATION`, `E_LIST_NOT_SUPPORTED`, `E_QUERY_NOT_ALLOWED`,
`E_STRATEGY_NOT_ALLOWED`, `E_LIST_TO_LIST`, `E_MIXED_INPUT`, `W_LIST_WITHOUT_PULLERS`,
`W_LIST_WITHOUT_PUSHERS`, `W_UNUSED_LIST`. MCP: `create_lists_batch`.

### Resource rules

The resource manager (§14d) ranks waiting requests and chooses units with the same queries:

```python
model.resources.configure(request_order="kind == 'repair' DESC, item.due_date ASC", discipline="strict")
techs = ResourcePool("Techs", model, unit_order="utilization ASC",
                     units=[{"name": "T1", "attributes": {"level": 1}}, {"name": "T2", "attributes": {"level": 3}}])
MultiServer(1, 5, "Press", model, resources=[ResourceRequirement(techs, where="level >= item.complexity")])
```

| Rule | Where | Fields |
|---|---|---|
| `request_order` (default `"priority DESC"`) | `model.resources.configure`, spec `resource_rules` | `priority`, `time`, `age`, `seq`, `quantity`, `kind` (`work`/`repair`), `element` (name), `item` |
| `discipline` (`first_fit` default, `strict`) | same | strict: nobody overtakes the first waiting request |
| `unit_order` (default `"skills_count ASC"`) | per pool | `name`, `index`, `skills`, `skills_count`, `busy_time`, `utilization`, `idle_since`, `idle_time`, `kind`, unit `attributes` |
| `where` | per requirement | the unit fields plus `item` and `element` of the request |

---

## 14f. Task Executers (operators, vehicles...)

`PyFlow/executers.py`. A `TaskExecuter` is a resource with identity: an element of the engine
(states, statistics, stops and shifts like any element) with `skills`, `attributes`, `speed`,
`location` and cargo `capacity`. It executes `TaskSequence`s, one task after another:

```python
from PyFlow.executers import TaskExecuter, TaskSequence, Travel, Load, Unload, Utilize, Wait, Callback

truck = TaskExecuter("Truck", model, speed=2, capacity=1)
truck.execute(TaskSequence([Travel("A", distance=10), Load(item, time=1), Travel("B", time=3),
                            Unload(time=1, on_done=lambda ex, task: deliver(task.item)),
                            Utilize(2), Wait(), Callback(log)], priority=2))
truck.release()        # ends an open Utilize / Wait (no time)
```

| Task | State shown | Effect |
|---|---|---|
| `Travel(to, time= \| distance=)` | `TRAVEL_EMPTY` / `TRAVEL_LOADED` | time, or distance / speed; updates `location`, `distance_travelled` |
| `Load(item, time=)` | `LOADING` | item into the cargo (`E_CARGO_FULL` beyond `capacity`) |
| `Unload(item=None, time=)` | `UNLOADING` | item (default the first) out of the cargo; `on_done` hands it over |
| `Utilize(time=None)` | `WORKING` | work for a time, or until `release()` |
| `Wait(time=None)` | `WAITING` | same, shown as waiting |
| `Callback(fn)` | — | `fn(executer)`, instant |

Timed tasks are pausable work: a breakdown pauses them, an `after_current` stop (shifts) lets
the current sequence finish. Statistics: time in each state, `busy` (time executing a
sequence), `sequences_completed`, `tasks_completed`, `distance_travelled` (`summary()`).

Work reaches executers through lists, in both directions:

* **The resource waits for work.** `executer.serve(task_list, "WHERE skill in puller.skills
  ORDER BY priority DESC")`: whenever it is available, the executer pulls a task sequence pushed
  to that `ModelList` (back-order while there is none). Task sequences expose `priority`,
  `name` and their `labels` to queries.
* **The work waits for a resource.** A `ResourcePool` is a team of executers (`Operator` by
  default) and publishes its idle units in `pool.list` (`"<pool>.available"`). Stations take
  units through the resource manager (§14d): with all-or-nothing grants across pools, request
  order, discipline, `unit_order` and `where` queries. A held unit runs an open `Utilize`
  (`WORKING`) until the station frees it.

A unit can do both (serve a task list when no station holds it). An executer that is stopped
(breakdown, shift) leaves the list and comes back when resumed. In a specification, a downtime
whose `targets` include a pool id applies to every unit of the pool (operator shifts and
breakdowns). Known limit: a breakdown of a unit held by a station does not pause the station's
work.

---

## 15. Important Rules and Constraints

### One Model per Simulation

- Create a new `Model(seed=...)` for every independent run; models never share state.

### Connection Order

- All `connect()` calls must be made **before** `model.initialize()`.
- Calling `connect()` after `initialize()` is undefined behaviour.

### Combiner Wiring

- The **main item flow** is always connected to the Combiner element directly:
  ```python
  buffer_main.connect([combiner])
  ```
- **Component flows** are connected to explicit ports:
  ```python
  buffer_comp.connect([combiner.get_component_input(i)])
  ```
- The Combiner will only accept a new main item when it is `IDLE`. It will not accept a second main item while processing.

### MultiAssembler vs Combiner

| Aspect | Combiner | MultiAssembler |
|---|---|---|
| Main item | Required (arrives first) | Not needed |
| Output item | The arriving main item (modified) | New `Item` created |
| Parallel capacity | Always 1 | Configurable (`num_servers`) |
| Input strategy filtering | Yes (via `pull_mode`) | No |

### Time Units

PyFlow is time-unit agnostic. Use whatever unit is consistent (minutes, seconds, days). All delays and arrival times use the same unit as the clock.

### Item Ids

Items created by elements get an id that is unique within their model (`item.item_number`),
starting at 1 on every `initialize()`. Items created by hand (templates, tests) have id 0 unless
`item_id` is given.

### Sources Cannot Receive

All source types raise `NotImplementedError` if `receive()` is called. Sources are strictly one-directional (generate only).

### Sink Cannot Unblock

`Sink.unblock()` raises `NotImplementedError`. The sink is always available (`check_availability` always returns `True`) and never propagates availability notifications.

### Empty Event Calendar

`advance_clock(t)` returns `False` when no events remain, but the clock still moves to `t`
(idle time counts for time-weighted statistics). Use `clock.last_event_time` for the time of
the last event (makespan).

### Statistics and Warm-up

Statistics are reset by `initialize()`. `model.run(until, warmup=w)` (or `model.reset_stats()`)
discards what was collected before `w`. Content (WIP) averages are **time-weighted** since the
last reset; for a single server the content average is its utilisation.
