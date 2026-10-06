"""Standard manufacturing lines, used as reference test cases and examples.

Every builder returns a :class:`Line` (the model plus its elements by name). Delays
accept any sampler specification (number, ``"Exponential~0.8"``, scipy distribution,
label expression...). Element names follow one convention:

    Source / Source_<product>, Q<i> (buffer before station i), M<i> (station i), Sink

Example::

    line = serial_line(arrival=1.0, stages=[Stage(0.5), Stage(0.8, buffer=2)], seed=1)
    result = line.run(until=1000, warmup=100)
    result["throughput"], result["elements"]["M2"]["utilization"]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .Elements.combiner import Combiner
from .Elements.element import Element
from .Elements.interArrivalSource import InterArrivalSource
from .Elements.itemsQueue import ItemsQueue
from .Elements.multiAssembler import MultiAssembler
from .Elements.multiServer import MultiServer
from .Elements.scheduleSource import ScheduleSource
from .Elements.sink import Sink
from .Items.item import Item
from .Link.outputStrategy import FirstAvailableStrategy, LabelBasedStrategy, OutputStrategy
from .downtime import MtbfMttrDowntime, ShiftDowntime
from .model import Model

INFINITE = float("inf")


@dataclass
class Stage:
    """One station of a line: ``buffer`` places before it, ``servers`` in parallel.

    Optional: ``setup`` (changeover time when the item type changes, see ``MultiServer``),
    ``ttf``/``ttr`` (time to failure / to repair: random breakdowns, ``basis`` "calendar" or
    "busy") and ``shifts`` (weekly shift pattern text, uses the model calendar)."""
    service: Any
    buffer: float = INFINITE
    servers: int = 1
    setup: Any = None
    ttf: Any = None
    ttr: Any = None
    basis: str = "calendar"
    shifts: Optional[str] = None


class Line:
    """A model and its elements, with a uniform way to run it and read results."""

    def __init__(self, name: str, model: Model):
        self.name = name
        self.model = model
        self.elements: Dict[str, Element] = {}

    def add(self, element: Element) -> Element:
        self.elements[element.name] = element
        return element

    def __getitem__(self, name: str) -> Element:
        return self.elements[name]

    @property
    def sinks(self) -> List[Sink]:
        return [e for e in self.elements.values() if isinstance(e, Sink)]

    def run(self, until: float, *, warmup: Optional[float] = None) -> dict:
        self.model.initialize()
        self.model.run(until, warmup=warmup)
        return self.summary()

    def summary(self) -> dict:
        """Throughput and per-element statistics since the last statistics reset."""
        elapsed = self.model.now - self.model.stats_reset_time
        completed = sum(s.get_stats_collector().get_var_input_value() for s in self.sinks)
        elements = {}
        for name, element in self.elements.items():
            sc = element.get_stats_collector()
            info = {
                "input": sc.get_var_input_value(),
                "output": sc.get_var_output_value(),
                "wip_average": sc.get_var_content_average(),
                "wip_max": sc.get_var_content_max(),
                "staytime_average": sc.get_var_staytime_average(),
            }
            if isinstance(element, MultiServer):
                info["utilization"] = info["wip_average"] / element.num_servers
                info["states"] = element.state_ratios()
            elements[name] = info
        return {
            "line": self.name,
            "time": self.model.now,
            "observed": elapsed,
            "completed": completed,
            "throughput": completed / elapsed if elapsed > 0 else 0.0,
            "elements": elements,
        }


def _model(model: Optional[Model], seed: Optional[int], name: str) -> Model:
    return model if model is not None else Model(seed=seed, name=name)


def _stations(line: Line, upstream: Element, stages: Sequence[Stage], first: int = 1) -> Element:
    for i, stage in enumerate(stages, start=first):
        queue = line.add(ItemsQueue(stage.buffer, f"Q{i}", line.model))
        station = line.add(MultiServer(stage.servers, stage.service, f"M{i}", line.model, setup_time=stage.setup))
        if stage.ttf is not None:
            if stage.ttr is None:
                raise ValueError(f"E_INVALID_STAGE: stage {i} has ttf but no ttr")
            MtbfMttrDowntime(station, stage.ttf, stage.ttr, basis=stage.basis)
        if stage.shifts:
            ShiftDowntime(station, stage.shifts)
        upstream.connect([queue])
        queue.connect([station])
        upstream = station
    return upstream


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def single_station(*, arrival: Any, service: Any, servers: int = 1, buffer: float = INFINITE,
                   model: Optional[Model] = None, seed: Optional[int] = None) -> Line:
    """Source -> Q1 -> M1 (``servers`` in parallel) -> Sink. M/M/1, M/M/c, M/D/1..."""
    return serial_line(arrival=arrival, stages=[Stage(service, buffer, servers)],
                       model=model, seed=seed, name="single_station")


def serial_line(*, arrival: Any, stages: Sequence[Stage], model: Optional[Model] = None,
                seed: Optional[int] = None, name: str = "serial_line") -> Line:
    """Source -> Q1 -> M1 -> Q2 -> M2 ... -> Sink. Finite buffers block upstream stations."""
    line = Line(name, _model(model, seed, name))
    source = line.add(InterArrivalSource("Source", line.model, arrival))
    last = _stations(line, source, stages)
    last.connect([line.add(Sink("Sink", line.model))])
    return line


def parallel_machines(*, arrival: Any, services: Sequence[Any], buffer: float = INFINITE,
                      strategy: Optional[OutputStrategy] = None, model: Optional[Model] = None,
                      seed: Optional[int] = None) -> Line:
    """Source -> Q1 -> {M1 ... Mn} (one server each, possibly different speeds) -> Sink.
    ``strategy`` decides which free machine takes the next item (default FirstAvailable)."""
    line = Line("parallel_machines", _model(model, seed, "parallel_machines"))
    source = line.add(InterArrivalSource("Source", line.model, arrival))
    queue = line.add(ItemsQueue(buffer, "Q1", line.model))
    machines = [line.add(MultiServer(1, s, f"M{i}", line.model)) for i, s in enumerate(services, start=1)]
    sink = line.add(Sink("Sink", line.model))
    source.connect([queue])
    queue.connect(machines, strategy=strategy or FirstAvailableStrategy())
    for machine in machines:
        machine.connect([sink])
    return line


def assembly_line(*, main_arrival: Any, component_arrival: Any, components_per_unit: int,
                  assembly_time: Any, final_stages: Sequence[Stage] = (), buffer: float = INFINITE,
                  batch_mode: bool = True, model: Optional[Model] = None,
                  seed: Optional[int] = None) -> Line:
    """Main parts and components arrive on separate feeders and meet in a Combiner
    (``components_per_unit`` components per main part), then optional final stations.

        Source_main -> Q_main -> Assembly -> [Q2 -> M2 ...] -> Sink
        Source_comp -> Q_comp -> Assembly.Input0
    """
    line = Line("assembly_line", _model(model, seed, "assembly_line"))
    m = line.model
    main = line.add(InterArrivalSource("Source_main", m, main_arrival))
    comp = line.add(InterArrivalSource("Source_comp", m, component_arrival))
    q_main = line.add(ItemsQueue(buffer, "Q_main", m))
    q_comp = line.add(ItemsQueue(buffer, "Q_comp", m))
    assembly = line.add(Combiner([components_per_unit], assembly_time, "Assembly", m, batch_mode=batch_mode))
    main.connect([q_main])
    comp.connect([q_comp])
    q_main.connect([assembly])
    q_comp.connect([assembly.get_component_input(0)])
    last = _stations(line, assembly, final_stages, first=2)
    last.connect([line.add(Sink("Sink", m))])
    return line


def kit_assembly(*, arrivals: Sequence[Any], requirements: Sequence[int], assembly_time: Any,
                 assemblers: int = 1, buffer: float = INFINITE, batch_mode: bool = True,
                 model: Optional[Model] = None, seed: Optional[int] = None) -> Line:
    """``len(arrivals)`` component feeders -> MultiAssembler (``requirements[i]`` of each)
    -> Sink. The assembler creates a new item per kit."""
    if len(arrivals) != len(requirements):
        raise ValueError("arrivals and requirements must have the same length")
    line = Line("kit_assembly", _model(model, seed, "kit_assembly"))
    m = line.model
    assembler = line.add(MultiAssembler(assemblers, list(requirements), assembly_time, "Assembly", m,
                                        batch_mode=batch_mode))
    for i, arrival in enumerate(arrivals):
        source = line.add(InterArrivalSource(f"Source_{i}", m, arrival))
        queue = line.add(ItemsQueue(buffer, f"Q_{i}", m))
        source.connect([queue])
        queue.connect([assembler.get_component_input(i)])
    assembler.connect([line.add(Sink("Sink", m))])
    return line


def multi_product_flow_shop(*, products: Dict[str, dict], stations: int, buffer: float = INFINITE,
                            model: Optional[Model] = None, seed: Optional[int] = None) -> Line:
    """Several products share the same sequence of stations; processing times come from
    item labels ``PT1, PT2, ...``.

    ``products = {"A": {"arrival": 10, "PT1": 2, "PT2": 3}, ...}``

        Source_A ┐
        Source_B ┼-> Q1 -> M1 (PT1) -> Q2 -> M2 (PT2) ... -> Sink
        Source_C ┘
    """
    line = Line("multi_product_flow_shop", _model(model, seed, "multi_product_flow_shop"))
    m = line.model
    queue1 = line.add(ItemsQueue(buffer, "Q1", m))
    for product, spec in products.items():
        labels = {k: v for k, v in spec.items() if k != "arrival"}
        template = Item(0, item_type=product, labels=labels)
        source = line.add(InterArrivalSource(f"Source_{product}", m, spec["arrival"], model_item=template))
        source.connect([queue1])
    station = line.add(MultiServer(1, "PT1", "M1", m))
    queue1.connect([station])
    last = _stations(line, station, [Stage(f"PT{i}", buffer) for i in range(2, stations + 1)], first=2)
    last.connect([line.add(Sink("Sink", m))])
    return line


def product_routing(*, products: Dict[str, dict], buffer: float = INFINITE,
                    model: Optional[Model] = None, seed: Optional[int] = None) -> Line:
    """Each product is routed to its own dedicated machine by the label ``route``
    (0-based machine index), then all products leave through one Sink.

    ``products = {"A": {"arrival": 5, "route": 0, "PT": 4}, "B": {...}}``
    """
    line = Line("product_routing", _model(model, seed, "product_routing"))
    m = line.model
    n_machines = max(int(spec["route"]) for spec in products.values()) + 1
    queue = line.add(ItemsQueue(buffer, "Q1", m))
    for product, spec in products.items():
        labels = {k: v for k, v in spec.items() if k != "arrival"}
        template = Item(0, item_type=product, labels=labels)
        line.add(InterArrivalSource(f"Source_{product}", m, spec["arrival"], model_item=template)).connect([queue])
    machines = [line.add(MultiServer(1, "PT", f"M{i + 1}", m)) for i in range(n_machines)]
    queue.connect(machines, strategy=LabelBasedStrategy("route"))
    sink = line.add(Sink("Sink", m))
    for machine in machines:
        machine.connect([sink])
    return line


def order_release_line(*, orders: Dict[str, List[Any]], stages: Sequence[Stage],
                       model: Optional[Model] = None, seed: Optional[int] = None) -> Line:
    """Orders released from a table (``ScheduleSource``) into a serial line.

    ``orders`` has the columns ``Time, Name, Q`` (release time, product, quantity) and
    optional label columns, e.g. ``{"Time": [0, 5], "Name": ["A", "B"], "Q": [2, 1], "PT": [3, 4]}``.
    """
    line = Line("order_release_line", _model(model, seed, "order_release_line"))
    source = line.add(ScheduleSource("Source", line.model, data_dict=orders))
    last = _stations(line, source, stages)
    last.connect([line.add(Sink("Sink", line.model))])
    return line


__all__ = [
    "Stage", "Line", "single_station", "serial_line", "parallel_machines", "assembly_line",
    "kit_assembly", "multi_product_flow_shop", "product_routing", "order_release_line",
]
