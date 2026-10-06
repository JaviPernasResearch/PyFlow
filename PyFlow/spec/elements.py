"""Element types of a model specification and their registry.

Every element type is declared once: a Pydantic spec class (``type`` literal + fields) and a
builder registered with :func:`register_element`. The registry is the single source of
truth for the model builder, the validation, the MCP server (``get_supported_types``) and
the JSON/YAML readers.

    class ConveyorSpec(ElementSpecBase):
        type: Literal["Conveyor"]
        length: float = Field(gt=0)

    @register_element(ConveyorSpec, role="flow")
    def _build_conveyor(spec, ctx):
        return Conveyor(spec.length, spec.name, ctx.model)
"""
from __future__ import annotations

import typing
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Tuple, Type, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..Elements import (Combiner, InfiniteSource, InterArrivalBufferingSource, InterArrivalSource, ItemsQueue,
                        MultiAssembler, MultiServer, ScheduleSource, Sink)
from ..Elements.combinerInput import CombinerInput
from ..Elements.constrainedInput import ConstrainedInput
from ..Elements.element import Element
from ..Items.item import Item
from .bindings import Binding, first_paragraph
from .resources import RELEASE_DESCRIPTION, RESOURCES_DESCRIPTION, ResourceUse, build_requirements
from .samplers import SamplerSpec, build_sampler
from .strategies import InputStrategySpec, Scalar

ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"

ROLES = ("source", "flow", "sink")


class ElementSpecBase(BaseModel):
    """Fields shared by every element type."""
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str = Field(min_length=1, pattern=ID_PATTERN,
                    description="Unique identifier used to reference this element in connections")
    name: Optional[str] = Field(default=None, description="Display name (default: the id). Random "
                                "streams are keyed by name, so renaming changes the random numbers.")
    input_strategy: Optional[InputStrategySpec] = Field(
        default=None, description="Which items this element accepts (default: all)")

    @model_validator(mode="after")
    def _default_name(self):
        if self.name is None:
            self.name = self.id
        return self


@dataclass(frozen=True)
class BuildContext:
    """What a builder may use: the model being built and its resource pools by id."""
    model: Any
    resources: Dict[str, Any] = field(default_factory=dict)

    def requirements(self, spec: Any) -> list:
        """``ResourceRequirement`` objects for the ``resources`` field of ``spec``."""
        return build_requirements(getattr(spec, "resources", None) or [], self.resources)


@dataclass(frozen=True)
class ElementType:
    name: str
    spec: Type[ElementSpecBase]
    build: Callable[[Any, BuildContext], Element]
    role: str                                   # "source" | "flow" | "sink"
    ports: Optional[Callable[[Any], int]]       # number of component input ports (Combiner...)
    description: str
    main_input: bool = True                     # False: items only enter through the ports
    binding: Optional[Binding] = None           # engine class + field correspondence (sync test)

    @property
    def examples(self) -> List[Dict[str, Any]]:
        extra = self.spec.model_config.get("json_schema_extra") or {}
        return list(extra.get("examples", [])) if isinstance(extra, dict) else []

    def port_count(self, spec: Any) -> int:
        return self.ports(spec) if self.ports is not None else 0


_REGISTRY: Dict[str, ElementType] = {}


def _type_name(spec_cls: Type[ElementSpecBase]) -> str:
    field = spec_cls.model_fields.get("type")
    args = typing.get_args(field.annotation) if field is not None else ()
    if len(args) != 1 or not isinstance(args[0], str):
        raise TypeError(f"{spec_cls.__name__}.type must be a single Literal['Name']")
    return args[0]


def register_element(spec_cls: Type[ElementSpecBase], *, role: str = "flow",
                     ports: Optional[Callable[[Any], int]] = None, main_input: bool = True,
                     binding: Optional[Binding] = None, replace: bool = False):
    """Decorator registering ``build(spec, ctx) -> Element`` for ``spec_cls``.

    ``role``: "source" (cannot receive), "sink" (cannot send) or "flow". ``ports(spec)``:
    number of component input ports, reached with destination ``"<id>:<port>"`` and
    resolved with ``element.get_component_input(port)``. ``main_input=False``: items only
    enter through the ports. ``binding``: the engine class built and how the spec fields map
    to its constructor (checked by ``tests/unit/test_spec_sync.py``). Give the spec class at
    least one example in ``model_config = ConfigDict(json_schema_extra={"examples": [...]})``."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    if not issubclass(spec_cls, ElementSpecBase):
        raise TypeError("spec_cls must derive from ElementSpecBase")
    name = _type_name(spec_cls)

    def decorator(build: Callable[[Any, BuildContext], Element]):
        if name in _REGISTRY and not replace:
            raise ValueError(f"element type {name!r} is already registered (use replace=True)")
        doc = spec_cls.__doc__
        _REGISTRY[name] = ElementType(name, spec_cls, build, role, ports, first_paragraph(doc), main_input,
                                      binding)
        return build

    return decorator


def unregister_element(name: str) -> None:
    _REGISTRY.pop(name, None)


def element_types() -> Dict[str, ElementType]:
    """Registered element types (copy)."""
    return dict(_REGISTRY)


def get_element_type(name: str) -> ElementType:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"E_UNKNOWN_TYPE: unknown element type {name!r}. Known: {', '.join(sorted(_REGISTRY))}") from None


def parse_element_spec(value: Any) -> ElementSpecBase:
    """Validate a dict (or spec object) against the class registered for its ``type``."""
    if isinstance(value, ElementSpecBase):
        get_element_type(value.type)
        return value
    if not isinstance(value, dict):
        raise ValueError(f"an element spec must be an object, got {type(value).__name__}")
    type_name = value.get("type")
    if type_name not in _REGISTRY:
        raise ValueError(f"unknown element type {type_name!r}. Known: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[type_name].spec.model_validate(value)


def _model_item(spec: Any) -> Optional[Item]:
    if spec.item_type is None and not spec.labels and not spec.priority:
        return None
    return Item(0.0, item_type=spec.item_type or "Default", labels=dict(spec.labels or {}),
                item_id=0, priority=spec.priority)


# ---------------------------------------------------------------------------
# Built-in element types
# ---------------------------------------------------------------------------

class _SourceSpecBase(ElementSpecBase):
    """Item template shared by the generating sources."""
    item_type: Optional[str] = Field(default=None, description="Type stamped on every generated item "
                                     "(per-type counts in sinks, setup times, routing)")
    labels: Optional[Dict[str, Scalar]] = Field(default=None, description="Labels copied onto every "
                                                "generated item. Example: {\"PT1\": 10}")
    priority: int = Field(default=0, description="Item priority (PriorityRouting)")


class InterArrivalSourceSpec(_SourceSpecBase):
    """Generates items with random inter-arrival times. While the item cannot leave, the
    source is blocked and the next arrival is not scheduled (no arrivals are lost)."""
    type: Literal["InterArrivalSource"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'InterArrivalSource', 'id': 'orders', 'interarrival': 'ExponentialMean~4', 'item_type': 'Frame', 'labels': {'PT': 3.5}}]})
    interarrival: SamplerSpec


class InterArrivalBufferingSourceSpec(_SourceSpecBase):
    """Like InterArrivalSource, but arrivals keep coming while blocked and wait in an
    unbounded FIFO buffer inside the source."""
    type: Literal["InterArrivalBufferingSource"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'InterArrivalBufferingSource', 'id': 'arrivals', 'interarrival': 'Exponential~0.25'}]})
    interarrival: SamplerSpec


class InfiniteSourceSpec(_SourceSpecBase):
    """Pushes items as fast as the downstream elements accept them (saturated line)."""
    type: Literal["InfiniteSource"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'InfiniteSource', 'id': 'parts', 'item_type': 'Bolt'}]})


class JobSpec(BaseModel):
    """One release record of a ScheduleSource: ``qty`` items named ``name`` at ``time``."""
    model_config = ConfigDict(extra="forbid")
    time: float = Field(ge=0, description="Simulation time at which this job is released")
    name: str = Field(min_length=1, description="Job name; also used as the item type tag")
    qty: int = Field(default=1, gt=0, description="Number of identical items to release at this time")
    labels: Dict[str, Any] = Field(default_factory=dict, description="Labels of each generated item")


class ScheduleSourceSpec(ElementSpecBase):
    """Releases a list of jobs at given times, from ``jobs`` or from a file (``file``: .xlsx,
    .csv or .data with columns Time, Name, Q, then one column per label)."""
    type: Literal["ScheduleSource"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'ScheduleSource', 'id': 'jobs', 'jobs': [{'time': 0, 'name': 'J1', 'qty': 2, 'labels': {'PT': 10}}, {'time': 30, 'name': 'J2', 'labels': {'PT': 5}}]}]})
    jobs: Optional[List[JobSpec]] = Field(default=None, min_length=1)
    file: Optional[str] = Field(default=None, description="Path to the schedule file")
    sheet: Optional[str] = Field(default=None, description="Sheet name (xlsx only)")

    @model_validator(mode="after")
    def _one_source(self):
        if (self.jobs is None) == (self.file is None):
            raise ValueError("ScheduleSource needs exactly one of 'jobs' or 'file'")
        return self

    def to_data_dict(self) -> dict:
        """The jobs in the column format of :class:`~PyFlow.Elements.ScheduleSource`."""
        label_keys: List[str] = []
        for job in self.jobs or []:
            for key in job.labels:
                if key not in label_keys:
                    label_keys.append(key)
        data: Dict[str, list] = {"Time": [], "Name": [], "Q": [], **{k: [] for k in label_keys}}
        for job in self.jobs or []:
            data["Time"].append(job.time)
            data["Name"].append(job.name)
            data["Q"].append(job.qty)
            for key in label_keys:
                data[key].append(job.labels.get(key))
        return data


class ItemsQueueSpec(ElementSpecBase):
    """Finite-capacity FIFO buffer. When full it refuses items and the sender stays blocked
    until space is available (items are never dropped)."""
    type: Literal["ItemsQueue"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'ItemsQueue', 'id': 'buffer', 'capacity': 20}]})
    capacity: int = Field(gt=0, description="Maximum number of items held")


class SetupChangeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_type: str
    to_type: str
    time: SamplerSpec


class SetupSpec(BaseModel):
    """Setup (changeover) times by item type. ``changes`` (from -> to) take precedence over
    ``by_type`` (any change to that type); missing combinations have no setup."""
    model_config = ConfigDict(extra="forbid")
    by_type: Dict[str, SamplerSpec] = Field(default_factory=dict)
    changes: List[SetupChangeSpec] = Field(default_factory=list)


class _ServiceSpecBase(ElementSpecBase):
    """Elements with active service time: they can need shared resources while working."""
    resources: List[ResourceUse] = Field(default_factory=list, description=RESOURCES_DESCRIPTION)
    resource_release: Literal["on_finish", "on_exit"] = Field(default="on_finish", description=RELEASE_DESCRIPTION)


class MultiServerSpec(_ServiceSpecBase):
    """N parallel servers without internal queue. A finished item that cannot leave keeps
    its server blocked."""
    type: Literal["MultiServer"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'MultiServer', 'id': 'lathe', 'num_servers': 2, 'service_time': 'Triangular~3~4~6', 'setup_time': {'by_type': {'B': 2}, 'changes': [{'from_type': 'B', 'to_type': 'A', 'time': 3}]}}]})
    num_servers: int = Field(gt=0, description="Number of parallel processing slots")
    service_time: SamplerSpec
    setup_time: Optional[Union[SamplerSpec, SetupSpec]] = Field(
        default=None, description="Changeover time when the item type changes on a server: one sampler "
                                  "for every change, or a SetupSpec by type")


def _setup_value(spec: Any) -> Any:
    if spec is None:
        return None
    if isinstance(spec, SetupSpec):
        table: Dict[Any, Any] = {t: build_sampler(s) for t, s in spec.by_type.items()}
        for change in spec.changes:
            table[(change.from_type, change.to_type)] = build_sampler(change.time)
        return table
    return build_sampler(spec)


class CombinerSpec(_ServiceSpecBase):
    """Assembly with one main item and component ports. The main item enters through normal
    connections; components through the ports (destination ``"<id>:<port>"``). When every
    port holds its requirement the components are consumed and the main item is processed."""
    type: Literal["Combiner"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'Combiner', 'id': 'assembly', 'requirements': [4, 1], 'service_time': 'Uniform~2~3', 'batch_mode': True, 'pull_mode': {'type': 'SingleLabel', 'label': 'order'}}]})
    requirements: List[int] = Field(min_length=1, description="Components needed per port")
    service_time: SamplerSpec
    batch_mode: bool = Field(default=False, description="Components travel as sub-items of the main item")
    pull_mode: Optional[InputStrategySpec] = Field(default=None, description="Filter of the component ports, "
                                                   "updated with each main item (e.g. SingleLabel)")
    update_requirements: bool = Field(default=False, description="Read requirements from main-item labels")
    update_labels: Optional[List[str]] = Field(default=None, description="Label per port with its requirement")


class MultiAssemblerSpec(_ServiceSpecBase):
    """N parallel assembly servers that create a new item when every component port holds
    its requirement. All inputs arrive through ports (destination ``"<id>:<port>"``)."""
    type: Literal["MultiAssembler"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'MultiAssembler', 'id': 'kitting', 'num_servers': 2, 'requirements': [1, 2], 'service_time': 5}]})
    num_servers: int = Field(gt=0)
    requirements: List[int] = Field(min_length=1)
    service_time: SamplerSpec
    batch_mode: bool = False


class SinkSpec(ElementSpecBase):
    """Terminal absorber; counts items per type."""
    type: Literal["Sink"]
    model_config = ConfigDict(json_schema_extra={"examples": [{'type': 'Sink', 'id': 'shipping'}]})
    keep_items: bool = Field(default=False, description="Keep the absorbed items (memory grows)")


_ITEM_TEMPLATE = {"item_type": "model_item", "labels": "model_item", "priority": "model_item"}


@register_element(InterArrivalSourceSpec, role="source", binding=Binding(
    InterArrivalSource, field_map={"interarrival": "interarrival_dist", **_ITEM_TEMPLATE}))
def _build_interarrival(spec: InterArrivalSourceSpec, ctx: BuildContext) -> Element:
    return InterArrivalSource(spec.name, ctx.model, build_sampler(spec.interarrival), model_item=_model_item(spec))


@register_element(InterArrivalBufferingSourceSpec, role="source", binding=Binding(
    InterArrivalBufferingSource, field_map={"interarrival": "interarrival_dist", **_ITEM_TEMPLATE}))
def _build_buffering(spec: InterArrivalBufferingSourceSpec, ctx: BuildContext) -> Element:
    return InterArrivalBufferingSource(spec.name, ctx.model, build_sampler(spec.interarrival),
                                       model_item=_model_item(spec))


@register_element(InfiniteSourceSpec, role="source", binding=Binding(InfiniteSource, field_map=_ITEM_TEMPLATE))
def _build_infinite(spec: InfiniteSourceSpec, ctx: BuildContext) -> Element:
    return InfiniteSource(spec.name, ctx.model, model_item=_model_item(spec))


@register_element(ScheduleSourceSpec, role="source", binding=Binding(
    ScheduleSource, field_map={"jobs": "data_dict", "file": "file_name", "sheet": "sheet_name"},
    not_exposed={"model_item": "each job row carries its own name (type) and labels"}))
def _build_schedule(spec: ScheduleSourceSpec, ctx: BuildContext) -> Element:
    if spec.file is not None:
        return ScheduleSource(spec.name, ctx.model, file_name=spec.file, sheet_name=spec.sheet)
    return ScheduleSource(spec.name, ctx.model, data_dict=spec.to_data_dict())


@register_element(ItemsQueueSpec, binding=Binding(ItemsQueue))
def _build_queue(spec: ItemsQueueSpec, ctx: BuildContext) -> Element:
    return ItemsQueue(spec.capacity, spec.name, ctx.model)


_RESOURCES_CONVERTED = {"resources": "pool ids -> ResourceRequirement objects"}


@register_element(MultiServerSpec, binding=Binding(MultiServer, field_map={"service_time": "delay_strategy"},
                                                   converted=_RESOURCES_CONVERTED))
def _build_multiserver(spec: MultiServerSpec, ctx: BuildContext) -> Element:
    return MultiServer(spec.num_servers, build_sampler(spec.service_time), spec.name, ctx.model,
                       setup_time=_setup_value(spec.setup_time), resources=ctx.requirements(spec),
                       resource_release=spec.resource_release)


@register_element(CombinerSpec, ports=lambda spec: len(spec.requirements), binding=Binding(
    Combiner, field_map={"service_time": "delay_strategy"}, converted=_RESOURCES_CONVERTED))
def _build_combiner(spec: CombinerSpec, ctx: BuildContext) -> Element:
    from .strategies import build_input_strategy
    pull_mode = build_input_strategy(spec.pull_mode) if spec.pull_mode is not None else None
    return Combiner(list(spec.requirements), build_sampler(spec.service_time), spec.name, ctx.model,
                    batch_mode=spec.batch_mode, pull_mode=pull_mode, update_requirements=spec.update_requirements,
                    update_labels=spec.update_labels, resources=ctx.requirements(spec),
                    resource_release=spec.resource_release)


@register_element(MultiAssemblerSpec, ports=lambda spec: len(spec.requirements), main_input=False,
                  binding=Binding(MultiAssembler, field_map={"service_time": "delay_strategy"},
                                  converted=_RESOURCES_CONVERTED))
def _build_multiassembler(spec: MultiAssemblerSpec, ctx: BuildContext) -> Element:
    return MultiAssembler(spec.num_servers, list(spec.requirements), build_sampler(spec.service_time),
                          spec.name, ctx.model, batch_mode=spec.batch_mode, resources=ctx.requirements(spec),
                          resource_release=spec.resource_release)


@register_element(SinkSpec, role="sink", binding=Binding(Sink))
def _build_sink(spec: SinkSpec, ctx: BuildContext) -> Element:
    return Sink(spec.name, ctx.model, keep_items=spec.keep_items)


# Engine element classes that are deliberately not spec types (checked by the sync test)
INTERNAL_ELEMENT_CLASSES = {
    CombinerInput: "component port created by Combiner (destination '<id>:<port>')",
    ConstrainedInput: "component port created by MultiAssembler (destination '<id>:<port>')",
}

BUILTIN_ELEMENT_SPECS: Tuple[Type[ElementSpecBase], ...] = (
    InterArrivalSourceSpec, InterArrivalBufferingSourceSpec, InfiniteSourceSpec, ScheduleSourceSpec,
    ItemsQueueSpec, MultiServerSpec, CombinerSpec, MultiAssemblerSpec, SinkSpec)

# Static union of the built-in types (typed tool signatures, JSON schema). Custom types
# registered later are accepted by ModelSpec through the registry.
ElementSpec = Annotated[Union[BUILTIN_ELEMENT_SPECS], Field(discriminator="type")]


__all__ = ["INTERNAL_ELEMENT_CLASSES", "ElementSpecBase", "ElementType", "BuildContext", "register_element", "unregister_element",
           "element_types", "get_element_type", "parse_element_spec", "ElementSpec", "BUILTIN_ELEMENT_SPECS",
           "InterArrivalSourceSpec", "InterArrivalBufferingSourceSpec", "InfiniteSourceSpec", "JobSpec",
           "ScheduleSourceSpec", "ItemsQueueSpec", "MultiServerSpec", "SetupSpec", "SetupChangeSpec",
           "CombinerSpec", "MultiAssemblerSpec", "SinkSpec", "ID_PATTERN"]
