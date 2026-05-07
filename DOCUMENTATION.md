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
9. [Delay Strategies](#9-delay-strategies)
10. [Input Strategies](#10-input-strategies)
11. [Statistics Collection](#11-statistics-collection)
12. [Optimization Utilities](#12-optimization-utilities)
13. [Simulation Pipeline](#13-simulation-pipeline)
14. [Complete Examples](#14-complete-examples)
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
SimClock (Singleton)
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
├── __init__.py               # Re-exports all public classes
├── Elements/
│   ├── element.py            # Abstract base Element
│   ├── source.py             # Abstract base Source
│   ├── infiniteSource.py     # Generates items as fast as downstream allows
│   ├── interArrivalSource.py # Time-scheduled arrivals (inter-arrival gaps)
│   ├── interArrivalBufferingSource.py  # Like above, but buffers blocked items
│   ├── scheduleSource.py     # Arrivals driven by a file/dict schedule
│   ├── itemsQueue.py         # FIFO buffer with finite capacity
│   ├── multiServer.py        # Parallel server workstation
│   ├── combiner.py           # Assembles one main item + N component inputs
│   ├── multiAssembler.py     # Parallel assembler, creates new output items
│   ├── sink.py               # Terminal element (destroys items)
│   ├── combinerInput.py      # Port that feeds components into a Combiner
│   ├── constrainedInput.py   # Port that feeds components into a MultiAssembler
│   ├── serverProcess.py      # Internal process handle for a server slot
│   ├── delayStrategy.py      # RandomDelayStrategy / ExpressionDelayStrategy
│   ├── inputStrategy.py      # DefaultStrategy / SingleLabelStrategy / MultiLabelStrategy
│   ├── arrivalListener.py    # Abstract interface for assembly notification
│   ├── state.py              # Enum: IDLE, RECEIVING, BUSY, BLOCKED
│   └── workStation.py        # Abstract workstation interface
├── Items/
│   └── item.py               # Item entity with labels
├── Link/
│   ├── link.py               # Abstract Link interface
│   ├── generalLink.py        # Default link implementation
│   └── outputStrategy.py     # Routing strategies
├── SimClock/
│   ├── simClock.py           # Simulation clock (event scheduler)
│   ├── event.py              # Event protocol
│   └── doubleMinBinaryHeat.py # Min-heap event queue
├── Statistics/
│   ├── statsCollector.py     # Base statistics collector
│   ├── elementStatsCollector.py  # Per-element stats (input, output, content, stay-time)
│   ├── statVariable.py       # Abstract stat variable
│   ├── statLevelVariable.py  # Running counter (cumulative)
│   └── statTimeVariable.py   # Time-series average
└── Optimization/
    └── seqOptTools.py        # Excel/dict helpers for DOE / sequence optimisation
```

---

## 4. Core Concepts

| Concept | Description |
|---|---|
| **Item** | An entity (job, part, customer) that flows through the network. Carries metadata labels. |
| **Element** | A processing node (source, queue, server, sink). Receives and sends Items. |
| **Link** | A directed connection between elements that routes items using an OutputStrategy. |
| **Event** | A scheduled callable executed at a specific simulation time. |
| **SimClock** | Singleton that manages the event calendar and advances simulation time. |
| **Delay Strategy** | Determines how long a server processes an item (distribution or expression). |
| **Input Strategy** | Determines whether a CombinerInput port accepts a given item (label filtering). |
| **Output Strategy** | Determines which downstream element receives an item from a Link. |
| **Statistics Collector** | Automatically records flow counts, current content, and stay-times per element. |

---

## 5. SimClock — Simulation Engine

**Location:** `PyFlow/SimClock/simClock.py`

`SimClock` is a **singleton** — only one instance exists per simulation run.

### Instantiation

```python
from PyFlow import SimClock

clock = SimClock.get_instance()   # Returns existing or creates new singleton
```

> **Important:** To run multiple independent simulations (e.g., in tests), reset the singleton before each run:
> ```python
> SimClock._instance = None
> clock = SimClock.get_instance()
> ```

### Key Methods

| Method | Signature | Description |
|---|---|---|
| `get_instance` | `() -> SimClock` | Returns (or creates) the singleton clock. |
| `schedule_event` | `(event: Event, time: float) -> None` | Schedules `event` to fire `time` units from **now** (relative delay). |
| `initialize` | `() -> None` | Resets sim time to 0 and calls `start()` on every registered element. |
| `reset` | `() -> None` | Resets sim time and clears the event calendar without re-starting elements. |
| `advance_clock` | `(time: float) -> bool` | Processes all events up to absolute time `time`. Returns `False` if no more events remain. |
| `get_simulation_time` | `() -> float` | Returns the current simulation time. |
| `add_element` | `(element: Element) -> None` | Registers an element (called automatically in `Element.__init__`). |

### Event Calendar

Internally uses a **min-heap** (`DoubleMinBinaryHeat`) for O(log n) scheduling and retrieval.

### Typical Run Loop

```python
clock.initialize()          # Reset time, start all elements
clock.advance_clock(10000)  # Run until sim time 10000
```

Or, for incremental reporting:

```python
clock.initialize()
sim_time = 0
step = 100
while sim_time < max_sim_time:
    clock.advance_clock(sim_time + step)
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
model = Item(0, item_type="PartA", labels={"ProcessTime": 3.5}, model_item=True)
source = InterArrivalSource("Source", clock, dist, model_item=model)
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
| `start()` | Called by `clock.initialize()`. Resets internal state. |
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
InfiniteSource(name: str, clock: SimClock, model_item: Optional[Item] = None)
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
    clock: SimClock,
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
    clock: SimClock,
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
    clock: SimClock,
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
source = ScheduleSource("Source", clock, data_dict=schedule, model_item=model)
```

**Flow logic:**
- Reads rows one by one and schedules an event at the time specified in each row.
- If blocked, items are queued internally (`blocked_items`) and flushed on `unblock()`.

---

### 7.7 ItemsQueue

**Location:** `PyFlow/Elements/itemsQueue.py`

**Behaviour:** A finite-capacity FIFO buffer. Immediately forwards items downstream; if downstream is blocked, holds them internally until capacity is available.

```python
ItemsQueue(capacity: int, name: str, clock: SimClock)
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
    clock: SimClock
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
processor = MultiServer(1, stats.expon(scale=3), "Processor", clock)
```

**Example — Label-driven service time:**

```python
# Item must have a label "ServiceTime"
processor = MultiServer(1, "item.get_label_value('ServiceTime')", "Processor", clock)
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
    sim_clock: SimClock,
    **kwargs
)
```

| Parameter | Description |
|---|---|
| `requirements` | List of required item counts per component input. `[2, 1]` means port 0 needs 2 components, port 1 needs 1. |
| `delay_strategy` | Processing time distribution or expression. |
| `name` | Element name. |
| `sim_clock` | SimClock instance. |

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
    sim_clock=clock,
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
    sim_clock: SimClock,
    batch_mode: bool = False
)
```

| Parameter | Description |
|---|---|
| `num_servers` | Number of parallel assembly slots. |
| `requirements` | Required item count per constrained input port. |
| `delay_strategy` | Processing time. |
| `name` | Element name. |
| `sim_clock` | SimClock instance. |
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
Sink(name: str, clock: SimClock)
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

Links are created automatically by `element.connect()`. You generally **do not need to create or interact with links directly**, but understanding their behaviour is important for routing.

### 8.1 GeneralLink

**Location:** `PyFlow/Link/generalLink.py`

The default link type. Supports many-to-many wiring (multiple origins, multiple destinations).

```python
GeneralLink(
    origins: List[Element],
    destinations: List[Element],
    strategy: OutputStrategy = FirstAvailableStrategy()
)
```

**Key methods:**

| Method | Description |
|---|---|
| `send(item) -> bool` | Routes `item` to a destination selected by `strategy`. Returns `False` if all blocked; adds origin to `pending_requests`. |
| `notify_available() -> bool` | Called when a downstream element frees capacity. Iterates `pending_requests`, calls `unblock()` on each. Returns `True` if one successfully unblocked. |
| `get_origins() -> List[Element]` | Returns all upstream elements. |
| `get_destinations() -> List[Element]` | Returns all downstream elements. |

**`pending_requests`** is a class-level deque, shared across all `GeneralLink` instances. It tracks which elements need to retry sending.

---

### 8.2 Output Strategies

**Location:** `PyFlow/Link/outputStrategy.py`

All strategies implement:
```python
select_output(outputs: List[Element], the_item: Item) -> int
```
Returns the index of the chosen destination, or `-1` if none are available.

| Strategy | Class | Behaviour |
|---|---|---|
| First Available | `FirstAvailableStrategy` | Tries destinations in order; picks the first one that `check_availability()` returns `True`. **Default.** |
| Round Robin | `RoundRobinStrategy` | Cycles through destinations in order, skipping unavailable ones. |
| Minimum Queue | `QueueSizeStrategy` | Sends to the destination with the smallest current `content` stat. Falls back to `-1` if the chosen one is unavailable. |
| Label-Based | `LabelBasedStrategy(label_name)` | Reads `item.get_label_value(label_name)` as the destination index. |

**Usage:**

```python
from PyFlow import RoundRobinStrategy

server_a.connect([sink1, sink2], strategy=RoundRobinStrategy())
```

---

## 9. Delay Strategies

**Location:** `PyFlow/Elements/delayStrategy.py`

Delay strategies determine how long a `ServerProcess` holds an item. They are applied transparently — pass the strategy as the `delay_strategy` argument in `MultiServer`, `Combiner`, or `MultiAssembler`.

### RandomDelayStrategy

Wraps a `scipy.stats` distribution. Also accepts a plain `float` or `int` (converted to a degenerate uniform distribution).

```python
# Exponential service time, mean 3
stats.expon(scale=3)

# Deterministic delay of 5.0
stats.uniform(loc=5.0, scale=0)

# Triangular distribution
stats.triang(c=0.5, loc=2, scale=6)
```

### ExpressionDelayStrategy

Evaluates a Python expression string at runtime. The variable `item` refers to the current `Item` object.

```python
# Read delay from an item label
"item.get_label_value('ServiceTime')"

# Arithmetic on labels
"float(item.get_label_value('Weight')) * 0.5 + 1.0"
```

The expression string is passed directly as `delay_strategy`:

```python
processor = MultiServer(1, "item.get_label_value('ServiceTime')", "Proc", clock)
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
combiner = Combiner([1], stats.expon(scale=2), "Combiner", clock, pull_mode=strategy)
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

## 12. Optimization Utilities

**Location:** `PyFlow/Optimization/seqOptTools.py`

### SeqOptTools

A static helper class for building simulation scenarios from tabular data (Design of Experiments support).

| Method | Signature | Description |
|---|---|---|
| `read_excel_to_dict` | `(file_path, sheet_name=None) -> dict` | Reads an Excel file and returns a column-keyed dict of lists. |
| `transform_sequence` | `(data_dict, priorities) -> dict` | Reorders each column's values according to a 1-based priorities list. Used to enumerate job sequences. |
| `add_labels_to_dict` | `(data_dict, new_label_name, new_label_values) -> dict` | Adds or overwrites a label column in the dict. |

**Example — Loading and reordering a schedule:**

```python
from PyFlow.Optimization.seqOptTools import SeqOptTools

data = SeqOptTools.read_excel_to_dict("schedule.xlsx")
priorities = [3, 1, 2]  # New order: put row 3 first, row 1 second, row 2 third
reordered = SeqOptTools.transform_sequence(data, priorities)
source = ScheduleSource("Source", clock, data_dict=reordered)
```

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

### Step 2 — Create the Clock

```python
clock = SimClock.get_instance()
```

For unit tests or repeated runs, reset the singleton first:

```python
SimClock._instance = None
clock = SimClock.get_instance()
```

### Step 3 — Instantiate Elements

Create all elements with the **same clock instance**. The order does not matter for correctness, but a top-down order from source to sink improves readability.

```python
source    = InterArrivalSource("Source", clock, stats.expon(scale=2))
buffer    = ItemsQueue(1000, "Buffer", clock)
processor = MultiServer(2, stats.expon(scale=3), "Processor", clock)
sink      = Sink("Sink", clock)
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
clock.initialize()
```

This resets simulation time to 0 and calls `start()` on every registered element.

### Step 6 — Run

```python
# Run to a fixed end time
clock.advance_clock(max_sim_time)

# Or run step by step
sim_time = 0
step = 1000
while sim_time < max_sim_time:
    clock.advance_clock(sim_time + step)
    sim_time += step
```

`advance_clock(t)` returns `False` when the event calendar is empty (simulation has no more events — network is idle). Use this to detect early termination:

```python
while clock.advance_clock(sim_time + step):
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
from PyFlow import SimClock, InterArrivalSource, ItemsQueue, MultiServer, Sink
from scipy import stats

clock = SimClock.get_instance()

source    = InterArrivalSource("Source", clock, stats.expon(scale=2))
buffer    = ItemsQueue(1_000_000, "Queue", clock)
processor = MultiServer(1, stats.expon(scale=2), "Server", clock)
sink      = Sink("Sink", clock)

source.connect([buffer])
buffer.connect([processor])
processor.connect([sink])

clock.initialize()
clock.advance_clock(100_000)

print(f"Items processed:      {sink.get_stats_collector().get_var_input_value()}")
print(f"Avg queue length:     {buffer.get_stats_collector().get_var_content_average()}")
print(f"Avg waiting time:     {buffer.get_stats_collector().get_var_staytime_average()}")
```

---

### Example 2 — Serial Production Line

A line of N machines, each with a queue, driven by an infinite source.

```python
from PyFlow import SimClock, InfiniteSource, ItemsQueue, MultiServer, Sink
from scipy import stats

clock = SimClock.get_instance()

n_machines = 3
mean_service = 4.0
queue_cap = 100

elements = [InfiniteSource("Source", clock)]

for i in range(n_machines):
    elements.append(MultiServer(1, stats.expon(scale=mean_service), f"M{i+1}", clock))
    if i < n_machines - 1:
        elements.append(ItemsQueue(queue_cap, f"Q{i+1}", clock))

sink = Sink("Sink", clock)
elements.append(sink)

for i in range(len(elements) - 1):
    elements[i].connect([elements[i + 1]])

clock.initialize()
clock.advance_clock(10_000)

print(f"Throughput: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 3 — Combiner (Assembly)

One main item assembled with 2 components from separate feeds.

```python
from PyFlow import (SimClock, InterArrivalSource, ItemsQueue, Combiner, Sink)
from scipy import stats

clock = SimClock.get_instance()

src_main = InterArrivalSource("Main",  clock, stats.uniform(loc=2, scale=0))
src_comp = InterArrivalSource("Comp",  clock, stats.uniform(loc=1, scale=0))
buf_main = ItemsQueue(100, "BufMain", clock)
buf_comp = ItemsQueue(100, "BufComp", clock)
sink     = Sink("Sink", clock)

combiner = Combiner(
    requirements=[2],                         # 2 components needed per main item
    delay_strategy=stats.uniform(loc=3, scale=0),
    name="Combiner",
    sim_clock=clock
)

src_main.connect([buf_main])
src_comp.connect([buf_comp])
buf_main.connect([combiner])                         # Main item feed
buf_comp.connect([combiner.get_component_input(0)])  # Component feed → port 0
combiner.connect([sink])

clock.initialize()
clock.advance_clock(1000)

print(f"Assembled items: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 4 — MultiAssembler (Parallel Assembly)

Two component streams, 2 parallel assembly slots, new items created.

```python
from PyFlow import (SimClock, InterArrivalSource, ItemsQueue, MultiAssembler, Sink)
from scipy import stats

clock = SimClock.get_instance()

src1 = InterArrivalSource("S1", clock, stats.uniform(loc=4, scale=0))
src2 = InterArrivalSource("S2", clock, stats.uniform(loc=4, scale=0))
buf1 = ItemsQueue(100, "Q1", clock)
buf2 = ItemsQueue(100, "Q2", clock)
sink = Sink("Sink", clock)

assembler = MultiAssembler(
    num_servers=2,
    requirements=[1, 1],
    delay_strategy=stats.expon(scale=4),
    name="Assembler",
    sim_clock=clock
)

src1.connect([buf1])
src2.connect([buf2])
buf1.connect([assembler.get_component_input(0)])
buf2.connect([assembler.get_component_input(1)])
assembler.connect([sink])

clock.initialize()
clock.advance_clock(1000)

print(f"Assembled items: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 5 — ScheduleSource with Labels

Items arrive at scheduled times carrying custom labels for expression-driven delays.

```python
from PyFlow import SimClock, ScheduleSource, MultiServer, Sink, Item
from scipy import stats

clock = SimClock.get_instance()

schedule = {
    "Time": [0, 5, 12, 20],
    "Name": ["JobA", "JobB", "JobC", "JobD"],
    "Q":    [1, 1, 2, 1],
    "ServiceTime": [3.0, 1.5, 2.0, 4.0]
}
model = Item(0, model_item=True)
source    = ScheduleSource("Source", clock, data_dict=schedule, model_item=model)
processor = MultiServer(1, "item.get_label_value('ServiceTime')", "Proc", clock)
sink      = Sink("Sink", clock)

source.connect([processor])
processor.connect([sink])

clock.initialize()
clock.advance_clock(100)

print(f"Items completed: {sink.get_stats_collector().get_var_input_value()}")
```

---

### Example 6 — Multiple Output Routing (Label-Based)

Route items to one of two sinks based on an item label.

```python
from PyFlow import (SimClock, InterArrivalSource, MultiServer, Sink, Item)
from PyFlow.Link.outputStrategy import LabelBasedStrategy
from scipy import stats

clock = SimClock.get_instance()

# Items alternate between type 0 and type 1
def make_item(clock):
    # For illustration – in practice set labels in model_item or ScheduleSource
    pass

model_a = Item(0, labels={"Route": 0}, model_item=True)
model_b = Item(0, labels={"Route": 1}, model_item=True)

src_a = InterArrivalSource("SrcA", clock, stats.expon(scale=3), model_item=model_a)
src_b = InterArrivalSource("SrcB", clock, stats.expon(scale=3), model_item=model_b)
proc  = MultiServer(2, stats.expon(scale=2), "Proc", clock)
sink0 = Sink("Sink0", clock)
sink1 = Sink("Sink1", clock)

src_a.connect([proc])
src_b.connect([proc])
proc.connect([sink0, sink1], strategy=LabelBasedStrategy("Route"))

clock.initialize()
clock.advance_clock(1000)

print(f"Sink0: {sink0.get_stats_collector().get_var_input_value()}")
print(f"Sink1: {sink1.get_stats_collector().get_var_input_value()}")
```

---

### Example 7 — Design of Experiments (Multiple Runs)

```python
from PyFlow import SimClock, InterArrivalSource, ItemsQueue, MultiServer, Sink
from scipy import stats

def run_simulation(mean_service, sim_time=10_000):
    SimClock._instance = None          # Reset singleton for each independent run
    clock = SimClock.get_instance()

    source    = InterArrivalSource("Source", clock, stats.expon(scale=2))
    buffer    = ItemsQueue(10_000, "Queue", clock)
    processor = MultiServer(1, stats.expon(scale=mean_service), "Server", clock)
    sink      = Sink("Sink", clock)

    source.connect([buffer])
    buffer.connect([processor])
    processor.connect([sink])

    clock.initialize()
    clock.advance_clock(sim_time)

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

## 15. Important Rules and Constraints

### Clock Singleton

- There is **only one** `SimClock` per Python process (singleton pattern).
- When running multiple independent simulations (e.g., DOE or unit tests), reset before each:
  ```python
  SimClock._instance = None
  clock = SimClock.get_instance()
  ```
- All elements created before a reset are **not** automatically deregistered. Always re-create elements after resetting the singleton.

### Connection Order

- All `connect()` calls must be made **before** `clock.initialize()`.
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

### Item Counter

`Item.ITEM_NUMBER` is a class-level counter that increments globally. If you run multiple simulations in the same process, item numbers will keep increasing unless you reset:

```python
Item.ITEM_NUMBER = 0
```

### Sources Cannot Receive

All source types raise `NotImplementedError` if `receive()` is called. Sources are strictly one-directional (generate only).

### Sink Cannot Unblock

`Sink.unblock()` raises `NotImplementedError`. The sink is always available (`check_availability` always returns `True`) and never propagates availability notifications.

### Empty Event Calendar

`clock.advance_clock(t)` returns `False` when there are no more scheduled events. An empty calendar means the entire network is idle (no items in transit and no source scheduled to fire). This can happen before `t` is reached if the simulation has naturally exhausted its inputs (e.g., a `ScheduleSource` that has dispatched all rows).

### Statistics Start from Zero

All statistics counters start at zero on `clock.initialize()`. For warm-up period removal, run the simulation past the warm-up horizon, then manually read statistics (note: the current implementation resets counters on `initialize()` but **does not** support mid-run resets — plan your scenarios accordingly).
