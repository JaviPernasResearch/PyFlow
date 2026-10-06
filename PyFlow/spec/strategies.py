"""Routing strategies in a model specification.

Output strategy (``connections[].strategy``): a name such as ``"RoundRobin"`` or an object
for the strategies with parameters (``{"type": "LabelRouting", "label": "family",
"mapping": {"A": 0, "B": 1}}``).

Input strategy (``elements[].input_strategy``): an object such as ``{"type": "MaxQueue",
"max_queue": 2}``; ``And`` / ``Or`` combine several. ``DelegateOutputStrategy`` (a Python
function) cannot be written in a specification.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ..Elements.inputStrategy import (CompositeAndInputStrategy, CompositeOrInputStrategy, DefaultStrategy,
                                      InputStrategy, MaxQueueInputStrategy, MultiLabelStrategy,
                                      OriginNameInputStrategy, OriginTypeInputStrategy, SingleLabelStrategy)
from ..Link.outputStrategy import (DelegateOutputStrategy, FirstAvailableStrategy, LabelBasedStrategy,
                                   LabelRoutingStrategy, MostAvailableCapacityStrategy, OutputStrategy,
                                   ParameterizedRoutingStrategy, PriorityRoutingStrategy, QueueSizeStrategy,
                                   RoundRobinStrategy)
from .bindings import Binding

Scalar = Union[bool, int, float, str]


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Output strategies
# ---------------------------------------------------------------------------

SimpleOutputName = Literal["FirstAvailable", "RoundRobin", "ShortestQueue", "MostAvailableCapacity",
                           "PriorityRouting"]

_SIMPLE_OUTPUT = {
    "FirstAvailable": FirstAvailableStrategy,
    "RoundRobin": RoundRobinStrategy,
    "ShortestQueue": QueueSizeStrategy,
    "MostAvailableCapacity": MostAvailableCapacityStrategy,
    "PriorityRouting": PriorityRoutingStrategy,
}

OUTPUT_STRATEGY_DOCS = {
    "FirstAvailable": "First destination (in order) that can accept the item.",
    "RoundRobin": "Cycles through the destinations, skipping those that cannot accept.",
    "ShortestQueue": "Available destination holding the fewest items (ties: lowest index).",
    "MostAvailableCapacity": "Available destination with the most free capacity.",
    "PriorityRouting": "Items with priority > 0 take the first available destination, the rest the shortest queue.",
    "LabelBased": "{type, label}: the label value is the destination index (0-based).",
    "LabelRouting": "{type, label, mapping: {value: index}, default_index=-1}: label value -> destination "
                    "index; unmapped values go to default_index (-1 = wait). The item waits if the "
                    "chosen destination is full.",
    "Parameterized": "{type, parameter, default='FirstAvailable'}: model parameter value 'first_available' | "
                     "'round_robin' | 'shortest_queue' | 'most_capacity' or a destination index.",
}


class NamedOutputSpec(_Spec):
    """Object form of the strategies without parameters."""
    type: SimpleOutputName


class LabelBasedOutputSpec(_Spec):
    type: Literal["LabelBased"]
    label: str = Field(min_length=1, description="Label whose value is the destination index")


class LabelRoutingOutputSpec(_Spec):
    type: Literal["LabelRouting"]
    label: str = Field(min_length=1)
    mapping: Dict[str, int] = Field(description="Label value -> destination index. Numeric label values "
                                                "match their text form ('1' matches 1 and 1.0).")
    default_index: int = Field(default=-1, description="Index for unmapped values (-1 = the item waits)")


class ParameterizedOutputSpec(_Spec):
    type: Literal["Parameterized"]
    parameter: str = Field(min_length=1, description="Key in the model parameters")
    default: SimpleOutputName = "FirstAvailable"


OutputStrategyObject = Annotated[Union[NamedOutputSpec, LabelBasedOutputSpec, LabelRoutingOutputSpec,
                                       ParameterizedOutputSpec], Field(discriminator="type")]
OutputStrategySpec = Union[SimpleOutputName, OutputStrategyObject]


# Engine classes behind each spec (checked by tests/unit/test_spec_sync.py)
OUTPUT_STRATEGY_BINDINGS = {
    NamedOutputSpec: [Binding(cls) for cls in _SIMPLE_OUTPUT.values()],
    LabelBasedOutputSpec: [Binding(LabelBasedStrategy, field_map={"label": "label_name"})],
    LabelRoutingOutputSpec: [Binding(LabelRoutingStrategy, field_map={"label": "label_name"},
                                     converted={"mapping": "text keys also map their numeric value"})],
    ParameterizedOutputSpec: [Binding(ParameterizedRoutingStrategy, field_map={"parameter": "parameter_key"},
                                      converted={"default": "strategy name -> a new strategy object"})],
}
NOT_SERIALIZABLE_OUTPUT_STRATEGIES = {
    DelegateOutputStrategy: "routing written as a Python function cannot be stored in a spec",
}


def _mapping_with_numbers(mapping: Mapping[str, int]) -> Dict[Any, int]:
    """JSON keys are text: also map the numeric value so numeric labels match."""
    result: Dict[Any, int] = {}
    for key, index in mapping.items():
        result[key] = index
        try:
            number = float(key)
        except ValueError:
            continue
        result.setdefault(number, index)  # 1.0 == 1, so this also matches integer labels
    return result


def output_strategy_type(spec: OutputStrategySpec) -> str:
    return spec if isinstance(spec, str) else spec.type


def build_output_strategy(spec: OutputStrategySpec) -> OutputStrategy:
    """A fresh strategy object (each origin owns its own: round robin keeps its position)."""
    if isinstance(spec, str):
        return _SIMPLE_OUTPUT[spec]()
    if isinstance(spec, NamedOutputSpec):
        return _SIMPLE_OUTPUT[spec.type]()
    if isinstance(spec, LabelBasedOutputSpec):
        return LabelBasedStrategy(spec.label)
    if isinstance(spec, LabelRoutingOutputSpec):
        return LabelRoutingStrategy(spec.label, _mapping_with_numbers(spec.mapping), spec.default_index)
    if isinstance(spec, ParameterizedOutputSpec):
        return ParameterizedRoutingStrategy(spec.parameter, _SIMPLE_OUTPUT[spec.default]())
    raise ValueError(f"unknown output strategy spec: {spec!r}")


# ---------------------------------------------------------------------------
# Input strategies
# ---------------------------------------------------------------------------

class DefaultInputSpec(_Spec):
    """Accepts every item."""
    type: Literal["Default"]


class SingleLabelInputSpec(_Spec):
    """Accepts items whose label equals ``value``. In a Combiner's ``pull_mode`` the value is
    taken from each main item."""
    type: Literal["SingleLabel"]
    label: str = Field(min_length=1)
    value: Optional[Scalar] = None


class MultiLabelInputSpec(_Spec):
    """Accepts items that have any of the listed label values."""
    type: Literal["MultiLabel"]
    labels: Dict[str, List[Scalar]] = Field(description="{label: [accepted values]}")


class OriginNameInputSpec(_Spec):
    """Accepts items sent by the listed elements (element ids)."""
    type: Literal["OriginName"]
    origins: List[str] = Field(min_length=1, description="Element ids")


class OriginTypeInputSpec(_Spec):
    """Accepts items sent by elements of the listed classes (e.g. 'MultiServer')."""
    type: Literal["OriginType"]
    types: List[str] = Field(min_length=1)


class MaxQueueInputSpec(_Spec):
    """Accepts items while the element holds fewer than ``max_queue`` items."""
    type: Literal["MaxQueue"]
    max_queue: int = Field(ge=0)


class AndInputSpec(_Spec):
    """All sub-strategies must accept."""
    type: Literal["And"]
    strategies: List["InputStrategySpec"] = Field(min_length=1)


class OrInputSpec(_Spec):
    """At least one sub-strategy must accept."""
    type: Literal["Or"]
    strategies: List["InputStrategySpec"] = Field(min_length=1)


InputStrategySpec = Annotated[Union[DefaultInputSpec, SingleLabelInputSpec, MultiLabelInputSpec,
                                    OriginNameInputSpec, OriginTypeInputSpec, MaxQueueInputSpec,
                                    AndInputSpec, OrInputSpec], Field(discriminator="type")]
AndInputSpec.model_rebuild()
OrInputSpec.model_rebuild()

INPUT_STRATEGY_BINDINGS = {
    DefaultInputSpec: Binding(DefaultStrategy),
    SingleLabelInputSpec: Binding(SingleLabelStrategy, field_map={"label": "required_label_name",
                                                                  "value": "required_label_value"}),
    MultiLabelInputSpec: Binding(MultiLabelStrategy, field_map={"labels": "accepted_labels"}),
    OriginNameInputSpec: Binding(OriginNameInputStrategy, field_map={"origins": "allowed_names"},
                                 converted={"origins": "element ids -> element names"}),
    OriginTypeInputSpec: Binding(OriginTypeInputStrategy, field_map={"types": "allowed_types"}),
    MaxQueueInputSpec: Binding(MaxQueueInputStrategy),
    AndInputSpec: Binding(CompositeAndInputStrategy),
    OrInputSpec: Binding(CompositeOrInputStrategy),
}


def input_strategy_origins(spec: Optional[InputStrategySpec]) -> List[str]:
    """Element ids referenced by ``OriginName`` strategies (for validation)."""
    if spec is None:
        return []
    if isinstance(spec, OriginNameInputSpec):
        return list(spec.origins)
    if isinstance(spec, (AndInputSpec, OrInputSpec)):
        return [origin for sub in spec.strategies for origin in input_strategy_origins(sub)]
    return []


def build_input_strategy(spec: InputStrategySpec, names: Optional[Mapping[str, str]] = None) -> InputStrategy:
    """``names`` maps element ids to element names (``OriginName`` checks names)."""
    names = names or {}
    if isinstance(spec, DefaultInputSpec):
        return DefaultStrategy()
    if isinstance(spec, SingleLabelInputSpec):
        return SingleLabelStrategy(spec.label, spec.value)
    if isinstance(spec, MultiLabelInputSpec):
        return MultiLabelStrategy({k: list(v) for k, v in spec.labels.items()})
    if isinstance(spec, OriginNameInputSpec):
        return OriginNameInputStrategy([names.get(origin, origin) for origin in spec.origins])
    if isinstance(spec, OriginTypeInputSpec):
        return OriginTypeInputStrategy(spec.types)
    if isinstance(spec, MaxQueueInputSpec):
        return MaxQueueInputStrategy(spec.max_queue)
    if isinstance(spec, AndInputSpec):
        return CompositeAndInputStrategy(*(build_input_strategy(s, names) for s in spec.strategies))
    if isinstance(spec, OrInputSpec):
        return CompositeOrInputStrategy(*(build_input_strategy(s, names) for s in spec.strategies))
    raise ValueError(f"unknown input strategy spec: {spec!r}")


__all__ = ["OUTPUT_STRATEGY_BINDINGS", "NOT_SERIALIZABLE_OUTPUT_STRATEGIES", "INPUT_STRATEGY_BINDINGS",
           "OutputStrategySpec", "OutputStrategyObject", "SimpleOutputName", "NamedOutputSpec",
           "LabelBasedOutputSpec", "LabelRoutingOutputSpec", "ParameterizedOutputSpec", "OUTPUT_STRATEGY_DOCS",
           "build_output_strategy", "output_strategy_type", "InputStrategySpec", "DefaultInputSpec",
           "SingleLabelInputSpec", "MultiLabelInputSpec", "OriginNameInputSpec", "OriginTypeInputSpec",
           "MaxQueueInputSpec", "AndInputSpec", "OrInputSpec", "build_input_strategy", "input_strategy_origins"]
