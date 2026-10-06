"""``ModelSpec``: a whole model as data (JSON today, YAML later), and its builder.

    spec = ModelSpec.from_file("line.json")
    issues = spec.validate()              # errors and warnings, nothing is built
    built = spec.build(seed=7)            # Model + elements by id + downtime generators
    results = built.run(until=10_000, warmup=1_000)
    spec.to_file("copy.json")             # round trip

Build order (as SimuLean's ``HeadlessModelFactory``): model (seed, calendar, parameters) →
elements → connections → input strategies (they may reference any element) → downtimes.
The same :class:`ModelBuilder` is used incrementally by the MCP server.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SerializeAsAny, model_validator, create_model

from ..model import Model
from ..reporting import summarize
from ..simcalendar import SimCalendar, parse_date
from .downtimes import DowntimeSpec, ShiftSpec, TimetableSpec, build_downtime
from .elements import (ID_PATTERN, BuildContext, ElementSpecBase, element_types, get_element_type,
                       parse_element_spec)
from .strategies import (LabelBasedOutputSpec, LabelRoutingOutputSpec, OutputStrategySpec, ParameterizedOutputSpec,
                         Scalar, build_input_strategy, build_output_strategy, input_strategy_origins)

SPEC_VERSION = 1
DESTINATION_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*(:[0-9]+)?$"
_DEST_RE = re.compile(DESTINATION_PATTERN)


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CalendarSpec(_Spec):
    """Maps simulation time to dates (needed by shifts and date-stamped downtimes)."""
    start: str = Field(description="Date of t = 0, e.g. '2026-01-05 00:00'")
    seconds_per_unit: float = Field(default=1.0, gt=0, description="Seconds per simulation time unit "
                                    "(60 = the model works in minutes)")

    @model_validator(mode="after")
    def _check_start(self):
        parse_date(self.start)
        return self

    def build(self) -> SimCalendar:
        return SimCalendar(self.start, self.seconds_per_unit)


class RunSpec(_Spec):
    """Default run settings (``BuiltModel.run()`` without arguments)."""
    until: float = Field(gt=0, description="Simulation end time")
    warmup: Optional[float] = Field(default=None, ge=0, description="Statistics are reset at this time")

    @model_validator(mode="after")
    def _check_warmup(self):
        if self.warmup is not None and self.warmup > self.until:
            raise ValueError("warmup must not exceed until")
        return self


class ConnectionSpec(_Spec):
    """Directed connection from one origin to one or more destinations.

    Put every destination of an origin in one connection: the strategy chooses among them.
    A destination ``"<id>:<port>"`` is a component port of a Combiner / MultiAssembler."""
    origin: str = Field(pattern=ID_PATTERN, description="Element id of the upstream element")
    destinations: List[Annotated[str, Field(pattern=DESTINATION_PATTERN)]] = Field(
        min_length=1, description="Element ids ('q1') or component ports ('assembly:0')")
    strategy: OutputStrategySpec = Field(default="FirstAvailable", description="Output routing strategy")


def parse_destination(text: str) -> Tuple[str, Optional[int]]:
    element_id, _, port = text.partition(":")
    return element_id, (int(port) if port else None)


ElementField = Annotated[SerializeAsAny[ElementSpecBase], BeforeValidator(parse_element_spec)]


class ModelSpec(_Spec):
    """A complete model. ``elements`` accepts every registered element type
    (see :func:`PyFlow.spec.element_types`)."""
    spec_version: Literal[1] = SPEC_VERSION
    name: str = "Model"
    seed: Optional[int] = Field(default=None, ge=0, description="Random seed (None: random)")
    calendar: Optional[CalendarSpec] = None
    parameters: Dict[str, Scalar] = Field(default_factory=dict, description="Model parameters "
                                          "(Parameterized routing, experiments)")
    elements: List[ElementField] = Field(default_factory=list)
    connections: List[ConnectionSpec] = Field(default_factory=list)
    downtimes: List[DowntimeSpec] = Field(default_factory=list)
    run: Optional[RunSpec] = None

    # ------------------------------------------------------------------ IO
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelSpec":
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, text: str) -> "ModelSpec":
        return cls.model_validate_json(text)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "ModelSpec":
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            return cls.from_dict(_yaml().safe_load(text))
        return cls.from_json(text)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-compatible dict; fields left at ``None`` are omitted."""
        return self.model_dump(mode="json", exclude_none=True)

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_file(self, path: Union[str, Path]) -> None:
        path = Path(path)
        if path.suffix.lower() in (".yaml", ".yml"):
            text = _yaml().safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)
        else:
            text = self.to_json() + "\n"
        path.write_text(text, encoding="utf-8")

    @classmethod
    def json_schema(cls) -> Dict[str, Any]:
        """JSON schema with the element field expanded to every registered type."""
        specs = tuple(t.spec for t in element_types().values())
        union = Annotated[Union[specs], Field(discriminator="type")] if len(specs) > 1 else specs[0]
        schema_model = create_model("ModelSpec", __base__=ModelSpec, elements=(List[union], Field(default_factory=list)))
        return schema_model.model_json_schema()

    # ------------------------------------------------------------------ use
    def validate_model(self) -> List["Issue"]:
        """Errors and warnings found without building the model (see :func:`validate_spec`)."""
        return validate_spec(self)

    def build(self, *, seed: Optional[int] = None, strict_warnings: bool = False) -> "BuiltModel":
        """Validate, then build the model. ``seed`` overrides ``self.seed`` (replications).
        Raises :class:`SpecError` if there are errors (or warnings with ``strict_warnings``)."""
        issues = validate_spec(self)
        blocking = [i for i in issues if i.severity == "error" or strict_warnings]
        if blocking:
            raise SpecError(blocking)
        builder = ModelBuilder(seed=self.seed if seed is None else seed, name=self.name,
                               parameters=self.parameters,
                               calendar=self.calendar.build() if self.calendar else None)
        for element in self.elements:
            builder.add_element(element)
        for connection in self.connections:
            builder.add_connection(connection)
        builder.finalize()
        for downtime in self.downtimes:
            builder.add_downtime(downtime)
        return BuiltModel(self, builder, issues)


def _yaml():
    try:
        import yaml
    except ImportError:
        raise ImportError("YAML files need PyYAML (pip install pyyaml); JSON works without it") from None
    return yaml


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Issue:
    severity: str        # "error" | "warning"
    code: str            # stable code, e.g. E_UNKNOWN_ELEMENT
    message: str
    path: str = ""       # where in the spec, e.g. "connections[2].destinations[0]"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    def __str__(self) -> str:
        where = f" at {self.path}" if self.path else ""
        return f"{self.code}{where}: {self.message}"


class SpecError(ValueError):
    """The specification cannot be built. ``issues`` lists every problem found."""

    def __init__(self, issues: List[Issue]):
        self.issues = list(issues)
        super().__init__("; ".join(str(i) for i in self.issues))


def validate_spec(spec: ModelSpec) -> List[Issue]:
    """Structural checks that Pydantic cannot do (references, roles, ports, routing)."""
    issues: List[Issue] = []

    def error(code, message, path=""):
        issues.append(Issue("error", code, message, path))

    def warning(code, message, path=""):
        issues.append(Issue("warning", code, message, path))

    types = {}
    names = set()
    for i, element in enumerate(spec.elements):
        if element.id in types:
            error("E_DUPLICATE_ID", f"element id {element.id!r} is used more than once", f"elements[{i}].id")
            continue
        types[element.id] = (get_element_type(element.type), element)
        if element.name in names:
            warning("W_DUPLICATE_NAME", f"element name {element.name!r} is used more than once (results and "
                    "random streams are keyed by name)", f"elements[{i}].name")
        names.add(element.name)

    has_input, fed_ports, origins_seen = set(), set(), set()
    for ci, conn in enumerate(spec.connections):
        path = f"connections[{ci}]"
        origin = types.get(conn.origin)
        if origin is None:
            error("E_UNKNOWN_ELEMENT", f"origin {conn.origin!r} is not an element id", f"{path}.origin")
        elif origin[0].role == "sink":
            error("E_SINK_AS_ORIGIN", f"{conn.origin!r} is a {origin[0].name} and cannot send items", f"{path}.origin")
        if conn.origin in origins_seen:
            warning("W_SPLIT_CONNECTION", f"{conn.origin!r} appears in several connections: destinations are "
                    "appended and the last strategy applies to all of them; use one connection", path)
        origins_seen.add(conn.origin)
        for di, text in enumerate(conn.destinations):
            dpath = f"{path}.destinations[{di}]"
            element_id, port = parse_destination(text)
            target = types.get(element_id)
            if target is None:
                error("E_UNKNOWN_ELEMENT", f"destination {element_id!r} is not an element id", dpath)
                continue
            etype, espec = target
            if element_id == conn.origin:
                error("E_SELF_LOOP", f"{element_id!r} is connected to itself", dpath)
            if etype.role == "source":
                error("E_SOURCE_AS_DESTINATION", f"{element_id!r} is a {etype.name} and cannot receive items", dpath)
            if port is None:
                if not etype.main_input:
                    error("E_PORT_REQUIRED", f"{etype.name} {element_id!r} only receives through its ports: "
                          f"use '{element_id}:<port>'", dpath)
                has_input.add(element_id)
            else:
                count = etype.port_count(espec)
                if count == 0:
                    error("E_INVALID_PORT", f"{etype.name} {element_id!r} has no component ports", dpath)
                elif port >= count:
                    error("E_INVALID_PORT", f"{element_id!r} has ports 0..{count - 1}, got {port}", dpath)
                else:
                    fed_ports.add((element_id, port))
        n = len(conn.destinations)
        strategy = conn.strategy
        if isinstance(strategy, LabelRoutingOutputSpec):
            bad = sorted({i for i in [*strategy.mapping.values(), strategy.default_index] if i != -1 and not 0 <= i < n})
            if bad:
                error("E_ROUTING_INDEX", f"LabelRouting uses index(es) {bad} but there are {n} destination(s)",
                      f"{path}.strategy")
        elif isinstance(strategy, LabelBasedOutputSpec) and n == 1:
            warning("W_TRIVIAL_ROUTING", "LabelBased routing with a single destination", f"{path}.strategy")
        elif isinstance(strategy, ParameterizedOutputSpec) and strategy.parameter not in spec.parameters:
            warning("W_MISSING_PARAMETER", f"parameter {strategy.parameter!r} is not in the model parameters "
                    f"(the default {strategy.default!r} applies)", f"{path}.strategy")

    for i, element in enumerate(spec.elements):
        if types.get(element.id, (None, None))[1] is not element:
            continue
        etype = types[element.id][0]
        path = f"elements[{i}]"
        if etype.role != "sink" and element.id not in origins_seen:
            warning("W_UNCONNECTED_OUTPUT", f"{element.id!r} has no outgoing connection: items will stay there",
                    path)
        if etype.role != "source" and etype.main_input and element.id not in has_input:
            warning("W_NO_INPUT", f"{element.id!r} has no incoming connection", path)
        for port in range(etype.port_count(element)):
            if (element.id, port) not in fed_ports:
                warning("W_UNFED_PORT", f"port '{element.id}:{port}' has no incoming connection", path)
        for origin in input_strategy_origins(element.input_strategy):
            if origin not in types:
                error("E_UNKNOWN_ELEMENT", f"OriginName refers to {origin!r}, which is not an element id",
                      f"{path}.input_strategy")

    for di, downtime in enumerate(spec.downtimes):
        for ti, target in enumerate(downtime.targets):
            if target not in types:
                error("E_UNKNOWN_ELEMENT", f"downtime target {target!r} is not an element id",
                      f"downtimes[{di}].targets[{ti}]")
        uses_dates = isinstance(downtime, ShiftSpec) or (
            isinstance(downtime, TimetableSpec) and any(isinstance(iv.start, str) or isinstance(iv.end, str)
                                                        for iv in downtime.intervals))
        if uses_dates and spec.calendar is None:
            warning("W_DEFAULT_CALENDAR", "dates are converted with the default calendar (t=0 is 2000-01-01, "
                    "1 time unit = 1 s); set 'calendar'", f"downtimes[{di}]")

    roles = [t[0].role for t in types.values()]
    if spec.elements and "source" not in roles:
        warning("W_NO_SOURCE", "the model has no source element")
    if spec.elements and "sink" not in roles:
        warning("W_NO_SINK", "the model has no sink element")
    return issues


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

class ModelBuilder:
    """Builds a :class:`Model` element by element (used by ``ModelSpec.build`` and the MCP
    session). Every call validates its references and raises :class:`SpecError`."""

    def __init__(self, model: Optional[Model] = None, *, seed: Optional[int] = None, name: str = "Model",
                 parameters: Optional[Dict[str, Any]] = None, calendar: Optional[SimCalendar] = None):
        self.requested_seed = seed
        self.model = model if model is not None else Model(seed, name=name, parameters=parameters,
                                                           calendar=calendar)
        self.elements: Dict[str, Any] = {}
        self.specs: Dict[str, ElementSpecBase] = {}
        self.connections: List[ConnectionSpec] = []
        self.downtimes: List[Any] = []
        self.generators: List[Any] = []
        self._finalized = False
        self._ctx = BuildContext(self.model)

    @staticmethod
    def _fail(code: str, message: str, path: str = "") -> None:
        raise SpecError([Issue("error", code, message, path)])

    def add_element(self, spec: Union[ElementSpecBase, Dict[str, Any]]) -> Any:
        spec = parse_element_spec(spec)
        if spec.id in self.specs:
            self._fail("E_DUPLICATE_ID", f"element id {spec.id!r} already exists in this model")
        etype = get_element_type(spec.type)
        element = etype.build(spec, self._ctx)
        self.elements[spec.id] = element
        self.specs[spec.id] = spec
        if self._finalized:
            self._apply_input_strategy(spec.id)
        return element

    def _resolve(self, text: str, path: str) -> Any:
        element_id, port = parse_destination(text)
        if element_id not in self.elements:
            self._fail("E_UNKNOWN_ELEMENT", f"destination {element_id!r} does not exist", path)
        etype = get_element_type(self.specs[element_id].type)
        if etype.role == "source":
            self._fail("E_SOURCE_AS_DESTINATION", f"{element_id!r} is a source and cannot receive items", path)
        if port is None:
            if not etype.main_input:
                self._fail("E_PORT_REQUIRED", f"{element_id!r} only receives through its ports: "
                           f"use '{element_id}:<port>'", path)
            return self.elements[element_id]
        count = etype.port_count(self.specs[element_id])
        if not 0 <= port < count:
            self._fail("E_INVALID_PORT", f"{element_id!r} has {count} component port(s), got {port}", path)
        return self.elements[element_id].get_component_input(port)

    def add_connection(self, conn: Union[ConnectionSpec, Dict[str, Any]]) -> None:
        if not isinstance(conn, ConnectionSpec):
            conn = ConnectionSpec.model_validate(conn)
        if conn.origin not in self.elements:
            self._fail("E_UNKNOWN_ELEMENT", f"origin {conn.origin!r} does not exist", "origin")
        if get_element_type(self.specs[conn.origin].type).role == "sink":
            self._fail("E_SINK_AS_ORIGIN", f"{conn.origin!r} is a sink and cannot send items", "origin")
        destinations = [self._resolve(d, f"destinations[{i}]") for i, d in enumerate(conn.destinations)]
        if any(d is self.elements[conn.origin] for d in destinations):
            self._fail("E_SELF_LOOP", f"{conn.origin!r} is connected to itself", "destinations")
        self.elements[conn.origin].connect(destinations, strategy=build_output_strategy(conn.strategy))
        self.connections.append(conn)

    def add_downtime(self, spec: Any) -> List[Any]:
        if isinstance(spec, dict):
            from pydantic import TypeAdapter
            spec = TypeAdapter(DowntimeSpec).validate_python(spec)
        for i, target in enumerate(spec.targets):
            if target not in self.elements:
                self._fail("E_UNKNOWN_ELEMENT", f"downtime target {target!r} does not exist", f"targets[{i}]")
        try:
            generators = [build_downtime(spec, self.elements[t], self.model) for t in spec.targets]
        except ValueError as exc:
            self._fail("E_INVALID_DOWNTIME", str(exc))
        self.downtimes.append(spec)
        self.generators.extend(generators)
        return generators

    def _apply_input_strategy(self, element_id: str) -> None:
        spec = self.specs[element_id]
        if spec.input_strategy is None:
            return
        for origin in input_strategy_origins(spec.input_strategy):
            if origin not in self.specs:
                self._fail("E_UNKNOWN_ELEMENT", f"OriginName of {element_id!r} refers to {origin!r}, "
                           "which does not exist", "input_strategy")
        names = {eid: s.name for eid, s in self.specs.items()}
        self.elements[element_id].set_input_strategy(build_input_strategy(spec.input_strategy, names))

    def finalize(self) -> None:
        """Apply the input strategies (they may reference elements added later). Idempotent."""
        if self._finalized:
            return
        for element_id in self.specs:
            self._apply_input_strategy(element_id)
        self._finalized = True

    def to_spec(self, *, name: Optional[str] = None, run: Optional[RunSpec] = None,
                calendar: Optional[CalendarSpec] = None) -> ModelSpec:
        """The specification of what has been built so far (export)."""
        cal = calendar
        if cal is None and not self.model.calendar.is_default:
            cal = CalendarSpec(start=self.model.calendar.start.isoformat(sep=" "),
                               seconds_per_unit=self.model.calendar.seconds_per_unit)
        return ModelSpec(name=name or self.model.name, seed=self.requested_seed, calendar=cal,
                         parameters=dict(self.model.parameters), elements=list(self.specs.values()),
                         connections=list(self.connections), downtimes=list(self.downtimes), run=run)


class BuiltModel:
    """A built specification: the :class:`Model`, the elements by id and the generators."""

    def __init__(self, spec: ModelSpec, builder: ModelBuilder, issues: List[Issue]):
        self.spec = spec
        self.builder = builder
        self.model: Model = builder.model
        self.elements: Dict[str, Any] = builder.elements
        self.generators: List[Any] = builder.generators
        self.issues = issues
        self.warmup: Optional[float] = None

    def __getitem__(self, element_id: str) -> Any:
        return self.elements[element_id]

    def run(self, until: Optional[float] = None, *, warmup: Optional[float] = None) -> Dict[str, Any]:
        """Fresh run from t = 0 (``initialize`` + ``run``); defaults come from ``spec.run``.
        Returns :meth:`results`."""
        if until is None:
            if self.spec.run is None:
                raise ValueError("E_NO_HORIZON: give 'until' or set 'run.until' in the spec")
            until = self.spec.run.until
            if warmup is None:
                warmup = self.spec.run.warmup
        self.model.initialize()
        self.warmup = warmup
        self.model.run(until, warmup=warmup)
        return self.results()

    def results(self) -> Dict[str, Any]:
        """JSON-ready results: time, seed, warmup and the summary of every element by id."""
        return {"time": self.model.now, "seed": self.model.seed, "warmup": self.warmup,
                "elements": summarize(self.elements)}


__all__ = ["ModelSpec", "ConnectionSpec", "CalendarSpec", "RunSpec", "Issue", "SpecError", "validate_spec",
           "ModelBuilder", "BuiltModel", "parse_destination", "SPEC_VERSION"]
