"""Input strategies: which items an element accepts (any element: ``element.input_strategy``).

Links check ``element.can_accept(item, origin)`` = not stopped + capacity + input strategy, so an
output strategy never picks a destination that would refuse the item (in SimuLean the input
strategy is checked only after the destination is chosen, and ``InputStrategy.CanAccept`` is
never called, so ``MaxQueueInputStrategy`` has no effect there).

Subclasses implement ``is_valid(item)`` (item only) and/or override
``accepts(target, item, origin)`` (target state and origin element).
"""
from abc import ABC, abstractmethod


class InputStrategy(ABC):
    @abstractmethod
    def is_valid(self, item) -> bool:
        """Determine if the given item satisfies the strategy."""
        pass

    def accepts(self, target, item, origin=None) -> bool:
        """Full check used by links. Default: ``is_valid(item)``."""
        return self.is_valid(item)

    def update_strategy(self, item) -> None:
        """Update the strategy when a (main) item arrives. Default: nothing."""
        pass


class DefaultStrategy(InputStrategy):
    """Accepts every item."""

    def is_valid(self, item) -> bool:
        return True


class SingleLabelStrategy(InputStrategy):
    """Accepts items whose label equals the stored value (updated by ``update_strategy``)."""

    def __init__(self, required_label_name: str, required_label_value=None):
        self.required_label_name = required_label_name
        self.required_label_value = required_label_value

    def update_strategy(self, the_item) -> None:
        self.required_label_value = the_item.get_label_value(self.required_label_name)

    def is_valid(self, the_item) -> bool:
        return (self.required_label_name in the_item.labels and
                self.required_label_value == the_item.get_label_value(self.required_label_name))


class MultiLabelStrategy(InputStrategy):
    """Accepts items that have any of the accepted ``{label: [values]}``."""

    def __init__(self, accepted_labels: dict):
        self.accepted_labels = accepted_labels

    def is_valid(self, the_item) -> bool:
        labels = the_item.get_all_labels()
        for label_name, label_value in labels.items():
            if label_name in self.accepted_labels.keys() and label_value in self.accepted_labels[label_name]:
                return True
        return False

    def update_strategy(self, the_item) -> None:
        labels = the_item.get_all_labels()
        for label_name, label_value in labels.items():
            if label_name in self.accepted_labels:
                self.accepted_labels[label_name] = label_value


class OriginTypeInputStrategy(InputStrategy):
    """Accepts items sent by elements of the given classes (class names, e.g. ``"MultiServer"``)."""

    def __init__(self, allowed_types):
        self.allowed = {allowed_types} if isinstance(allowed_types, str) else set(allowed_types)

    def is_valid(self, item) -> bool:
        return True

    def accepts(self, target, item, origin=None) -> bool:
        return origin is not None and any(cls.__name__ in self.allowed for cls in type(origin).__mro__)


class OriginNameInputStrategy(InputStrategy):
    """Accepts items sent by the named elements."""

    def __init__(self, allowed_names):
        self.allowed = {allowed_names} if isinstance(allowed_names, str) else set(allowed_names)

    def is_valid(self, item) -> bool:
        return True

    def accepts(self, target, item, origin=None) -> bool:
        return origin is not None and origin.name in self.allowed


class MaxQueueInputStrategy(InputStrategy):
    """Accepts items while the target holds fewer than ``max_queue`` items."""

    def __init__(self, max_queue: int):
        self.max_queue = max_queue

    def is_valid(self, item) -> bool:
        return True

    def accepts(self, target, item, origin=None) -> bool:
        return target.get_queue_length() < self.max_queue


class CompositeAndInputStrategy(InputStrategy):
    """All sub-strategies must accept."""

    def __init__(self, *strategies: InputStrategy):
        self.strategies = list(strategies)

    def is_valid(self, item) -> bool:
        return all(s.is_valid(item) for s in self.strategies)

    def accepts(self, target, item, origin=None) -> bool:
        return all(s.accepts(target, item, origin) for s in self.strategies)

    def update_strategy(self, item) -> None:
        for s in self.strategies:
            s.update_strategy(item)


class CompositeOrInputStrategy(CompositeAndInputStrategy):
    """At least one sub-strategy must accept."""

    def is_valid(self, item) -> bool:
        return any(s.is_valid(item) for s in self.strategies)

    def accepts(self, target, item, origin=None) -> bool:
        return any(s.accepts(target, item, origin) for s in self.strategies)


__all__ = ["InputStrategy", "DefaultStrategy", "SingleLabelStrategy", "MultiLabelStrategy",
           "OriginTypeInputStrategy", "OriginNameInputStrategy", "MaxQueueInputStrategy",
           "CompositeAndInputStrategy", "CompositeOrInputStrategy"]
