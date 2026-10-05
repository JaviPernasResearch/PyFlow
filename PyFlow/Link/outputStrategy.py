# FILE: PyFlow/Link/outputStrategy.py
"""Output strategies: which destination receives an item (SimuLean ``IOutputStrategy``).

``select_output(outputs, item, context)`` returns the index of the destination or -1 (the
item waits). ``context`` is an :class:`OutputContext` (source element, model, parameters).
Destinations must be tested with ``self.accepts(output, item, context)`` (= availability,
not stopped and the destination's input strategy). Strategies written for the old
two-argument signature ``select_output(outputs, item)`` keep working.
"""
import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..Elements.element import Element
from ..Items.item import Item


class OutputContext:
    """What a strategy may look at besides the candidates and the item."""
    __slots__ = ("source", "outputs")

    def __init__(self, source: Optional[Element], outputs: List[Element]):
        self.source = source
        self.outputs = outputs

    @property
    def model(self):
        return self.source.model if self.source is not None else None

    @property
    def parameters(self) -> Dict[str, Any]:
        return self.source.model.parameters if self.source is not None else {}

    @property
    def now(self) -> float:
        return self.source.clock.now if self.source is not None else 0.0


class OutputStrategy(ABC):
    _legacy_signature: Optional[bool] = None

    @abstractmethod
    def select_output(self, outputs: List[Element], the_item: Item, context: Optional[OutputContext] = None) -> int:
        pass

    def select(self, outputs: List[Element], the_item: Item, context: OutputContext) -> int:
        """Entry point used by links (supports legacy two-argument strategies)."""
        cls = type(self)
        legacy = cls.__dict__.get("_legacy_signature")
        if legacy is None:
            params = inspect.signature(self.select_output).parameters
            legacy = len(params) < 3 and not any(p.kind == p.VAR_POSITIONAL for p in params.values())
            cls._legacy_signature = legacy
        if legacy:
            return self.select_output(outputs, the_item)
        return self.select_output(outputs, the_item, context)

    @staticmethod
    def accepts(output: Element, the_item: Item, context: Optional[OutputContext] = None) -> bool:
        return output.can_accept(the_item, context.source if context is not None else None)


class FirstAvailableStrategy(OutputStrategy):
    def select_output(self, outputs, the_item, context=None) -> int:
        for i, output in enumerate(outputs):
            if self.accepts(output, the_item, context):
                return i
        return -1


class RoundRobinStrategy(OutputStrategy):
    """Cycles through the destinations, skipping those that cannot accept."""

    def __init__(self):
        self.index = 0

    def select_output(self, outputs, the_item, context=None) -> int:
        n = len(outputs)
        start = self.index % n if n else 0
        for k in range(n):
            i = (start + k) % n
            if self.accepts(outputs[i], the_item, context):
                self.index = (i + 1) % n
                return i
        return -1


class QueueSizeStrategy(OutputStrategy):
    """Available destination holding the fewest items; ties go to the lowest index."""

    def select_output(self, outputs, the_item, context=None) -> int:
        selected_index = -1
        min_queue_size = float('inf')
        for i, output in enumerate(outputs):
            queue_size = output.get_queue_length()
            if queue_size < min_queue_size and self.accepts(output, the_item, context):
                min_queue_size = queue_size
                selected_index = i
        return selected_index


ShortestQueueStrategy = QueueSizeStrategy  # SimuLean name


class MostAvailableCapacityStrategy(OutputStrategy):
    """Available destination with the most free capacity; ties go to the lowest index."""

    def select_output(self, outputs, the_item, context=None) -> int:
        selected_index = -1
        best = -1.0
        for i, output in enumerate(outputs):
            free = output.get_free_capacity()
            if free > best and self.accepts(output, the_item, context):
                best = free
                selected_index = i
        return selected_index


class LabelBasedStrategy(OutputStrategy):
    """The label value *is* the destination index (0-based)."""

    def __init__(self, label_name: str):
        self.label_name = label_name

    def select_output(self, outputs, the_item, context=None) -> int:
        try:
            index = int(the_item.get_label_value(self.label_name))
            if 0 <= index < len(outputs):
                if self.accepts(outputs[index], the_item, context):
                    return index
        except (TypeError, ValueError):
            pass
        return -1


class LabelRoutingStrategy(OutputStrategy):
    """Maps label values to destination indices: ``{"A": 0, "B": 1}``. Unmapped values (or a
    missing label) go to ``default_index`` (-1 = refuse). No fallback when the chosen
    destination is full: the item waits (deterministic routing)."""

    def __init__(self, label_name: str, mapping: Mapping[Any, int], default_index: int = -1):
        self.label_name = label_name
        self.mapping = dict(mapping)
        self.default_index = default_index

    def select_output(self, outputs, the_item, context=None) -> int:
        index = self.mapping.get(the_item.get_label_value(self.label_name), self.default_index)
        if not 0 <= index < len(outputs):
            return -1
        return index if self.accepts(outputs[index], the_item, context) else -1


class PriorityRoutingStrategy(OutputStrategy):
    """Items with ``priority > 0`` take the first available destination, the rest the
    shortest queue."""

    def __init__(self):
        self._first = FirstAvailableStrategy()
        self._shortest = QueueSizeStrategy()

    def select_output(self, outputs, the_item, context=None) -> int:
        if getattr(the_item, "priority", 0) > 0:
            return self._first.select_output(outputs, the_item, context)
        return self._shortest.select_output(outputs, the_item, context)


class ParameterizedRoutingStrategy(OutputStrategy):
    """Routing chosen by a model parameter (useful for experiments):
    ``model.parameters[key]`` = ``"first_available" | "round_robin" | "shortest_queue" |
    "most_capacity"`` or an integer destination index. Otherwise ``default``."""

    def __init__(self, parameter_key: str, default: Optional[OutputStrategy] = None):
        self.parameter_key = parameter_key
        self.default = default or FirstAvailableStrategy()
        # one instance per mode, so round robin keeps its position (SimuLean creates a new
        # RoundRobinStrategy on every call, which therefore never rotates)
        self._strategies = {"first_available": FirstAvailableStrategy(), "round_robin": RoundRobinStrategy(),
                            "shortest_queue": QueueSizeStrategy(), "most_capacity": MostAvailableCapacityStrategy()}

    def select_output(self, outputs, the_item, context=None) -> int:
        value = context.parameters.get(self.parameter_key) if context is not None else None
        if isinstance(value, bool):
            value = None
        if isinstance(value, int):
            return value if 0 <= value < len(outputs) and self.accepts(outputs[value], the_item, context) else -1
        strategy = self._strategies.get(str(value).lower()) if value is not None else None
        return (strategy or self.default).select(outputs, the_item, context)


class DelegateOutputStrategy(OutputStrategy):
    """Routing written as a function ``fn(outputs, item, source) -> index`` (-1 = wait).
    The chosen destination must still be able to accept the item."""

    def __init__(self, fn: Callable[[List[Element], Item, Optional[Element]], int]):
        if fn is None:
            raise ValueError("DelegateOutputStrategy needs a function")
        self.fn = fn

    def select_output(self, outputs, the_item, context=None) -> int:
        index = self.fn(outputs, the_item, context.source if context is not None else None)
        if index is None or not 0 <= index < len(outputs):
            return -1
        return index if self.accepts(outputs[index], the_item, context) else -1


__all__ = ["OutputContext", "OutputStrategy", "FirstAvailableStrategy", "RoundRobinStrategy",
           "QueueSizeStrategy", "ShortestQueueStrategy", "MostAvailableCapacityStrategy",
           "LabelBasedStrategy", "LabelRoutingStrategy", "PriorityRoutingStrategy",
           "ParameterizedRoutingStrategy", "DelegateOutputStrategy"]
