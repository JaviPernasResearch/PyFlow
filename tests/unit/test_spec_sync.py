"""Guard: the Pydantic specification must stay in sync with the engine.

If one of these tests fails after changing an element, a strategy or a downtime generator,
update its spec in ``PyFlow/spec/`` (field, ``Binding`` entry, example) — the message says
what is missing. See ``PyFlow/spec/bindings.py`` for the rules.
"""
import inspect
import re
from pathlib import Path
from typing import Literal, Optional

import pytest
from pydantic import BaseModel

from PyFlow.downtime import DowntimeGenerator
from PyFlow.Elements.element import Element
from PyFlow.Elements.inputStrategy import InputStrategy
from PyFlow.Link.outputStrategy import OutputStrategy
from PyFlow.sampling import _SPEC_TYPES
from PyFlow.spec import BUILTIN_ELEMENT_SPECS, ModelBuilder, element_types
from PyFlow.spec.bindings import Binding, check_binding
from PyFlow.spec.downtimes import DOWNTIME_BINDINGS
from PyFlow.spec.elements import INTERNAL_ELEMENT_CLASSES
from PyFlow.spec.model_spec import CALENDAR_BINDING, CalendarSpec
from PyFlow.spec.resources import RESOURCE_BINDINGS
from PyFlow.spec.samplers import SAMPLER_DESCRIPTION
from PyFlow.spec.strategies import (INPUT_STRATEGY_BINDINGS, NOT_SERIALIZABLE_OUTPUT_STRATEGIES,
                                    OUTPUT_STRATEGY_BINDINGS)

ROOT = Path(__file__).resolve().parents[2]
BUILTIN_TYPES = {name: t for name, t in element_types().items() if t.spec in BUILTIN_ELEMENT_SPECS}


def engine_subclasses(base: type) -> set:
    """Concrete subclasses of ``base`` defined in the PyFlow package (not tests, not the MCP)."""
    found, stack = set(), [base]
    while stack:
        for cls in stack.pop().__subclasses__():
            stack.append(cls)
            if cls.__module__.startswith("PyFlow.") and not inspect.isabstract(cls):
                found.add(cls)
    return found


def assert_in_sync(spec_cls, binding):
    problems = check_binding(spec_cls, binding)
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------------ elements
@pytest.mark.parametrize("type_name", sorted(BUILTIN_TYPES))
def test_element_spec_matches_constructor(type_name):
    etype = BUILTIN_TYPES[type_name]
    assert etype.binding is not None, f"register_element({etype.spec.__name__}) needs binding=Binding(<class>)"
    assert_in_sync(etype.spec, etype.binding)


def test_every_engine_element_class_has_a_spec():
    bound = {t.binding.target for t in BUILTIN_TYPES.values()}
    missing = {cls.__name__ for cls in engine_subclasses(Element)} - {c.__name__ for c in bound} \
        - {c.__name__ for c in INTERNAL_ELEMENT_CLASSES}
    assert not missing, (f"element classes without spec: {sorted(missing)}. Register a spec class in "
                         "PyFlow/spec/elements.py (and add it to BUILTIN_ELEMENT_SPECS) or list the class in "
                         "INTERNAL_ELEMENT_CLASSES with a reason")


def test_registry_and_typed_union_agree():
    """The MCP tool schemas use BUILTIN_ELEMENT_SPECS: every built-in registered type must be in it."""
    registered_here = {t.spec for t in element_types().values() if t.spec.__module__ == "PyFlow.spec.elements"}
    assert registered_here == set(BUILTIN_ELEMENT_SPECS)


@pytest.mark.parametrize("type_name", sorted(BUILTIN_TYPES))
def test_element_examples_validate_and_build(type_name):
    etype = BUILTIN_TYPES[type_name]
    assert etype.examples, (f"{etype.spec.__name__} needs an example: model_config = "
                            "ConfigDict(json_schema_extra={'examples': [...]})")
    assert etype.description, f"{etype.spec.__name__} needs a docstring (shown to agents)"
    for example in etype.examples:
        spec = etype.spec.model_validate(example)
        assert etype.spec.model_validate(spec.model_dump(mode="json")) == spec    # round trip
        element = ModelBuilder(seed=1).add_element(spec)
        assert isinstance(element, etype.binding.target)


# ------------------------------------------------------------------ strategies, downtimes, calendar
@pytest.mark.parametrize("spec_cls, binding", [(s, b) for s, bs in OUTPUT_STRATEGY_BINDINGS.items() for b in bs],
                         ids=lambda v: getattr(v, "__name__", None) or v.target.__name__)
def test_output_strategy_specs_match_constructors(spec_cls, binding):
    assert_in_sync(spec_cls, binding)


@pytest.mark.parametrize("spec_cls", list(INPUT_STRATEGY_BINDINGS), ids=lambda c: c.__name__)
def test_input_strategy_specs_match_constructors(spec_cls):
    assert_in_sync(spec_cls, INPUT_STRATEGY_BINDINGS[spec_cls])


@pytest.mark.parametrize("spec_cls", list(DOWNTIME_BINDINGS), ids=lambda c: c.__name__)
def test_downtime_specs_match_constructors(spec_cls):
    assert_in_sync(spec_cls, DOWNTIME_BINDINGS[spec_cls])


def test_calendar_spec_matches_constructor():
    assert_in_sync(CalendarSpec, CALENDAR_BINDING)


@pytest.mark.parametrize("base, bound, excluded, where", [
    (OutputStrategy, {b.target for bs in OUTPUT_STRATEGY_BINDINGS.values() for b in bs},
     set(NOT_SERIALIZABLE_OUTPUT_STRATEGIES), "OUTPUT_STRATEGY_BINDINGS / NOT_SERIALIZABLE_OUTPUT_STRATEGIES"),
    (InputStrategy, {b.target for b in INPUT_STRATEGY_BINDINGS.values()}, set(), "INPUT_STRATEGY_BINDINGS"),
    (DowntimeGenerator, {b.target for b in DOWNTIME_BINDINGS.values()}, set(), "DOWNTIME_BINDINGS"),
], ids=["output_strategies", "input_strategies", "downtimes"])
def test_every_engine_class_has_a_spec(base, bound, excluded, where):
    missing = sorted(cls.__name__ for cls in engine_subclasses(base) - bound - excluded)
    assert not missing, f"{base.__name__} classes without spec: {missing}. Add them to {where} in PyFlow/spec/"


def test_every_sampler_type_is_documented():
    documented = set(re.findall(r"([A-Z][A-Za-z]+)(?:~|\b)", SAMPLER_DESCRIPTION))
    missing = sorted((set(_SPEC_TYPES) | {"StudentT"}) - documented)
    assert not missing, f"sampler types missing from SAMPLER_DESCRIPTION (PyFlow/spec/samplers.py): {missing}"


# ------------------------------------------------------------------ documentation for people and agents
def test_every_element_type_is_documented():
    docs = (ROOT / "DOCUMENTATION.md").read_text(encoding="utf-8")
    section = docs[docs.index("## 14c."):docs.index("## 15.")]
    missing = sorted(name for name in BUILTIN_TYPES if f"`{name}`" not in section)
    assert not missing, f"element types missing from DOCUMENTATION.md §14c: {missing}"


def test_every_element_type_is_listed_in_the_mcp_tool():
    pytest.importorskip("mcp")
    from pyflow_mcp.server import create_elements_batch
    doc = create_elements_batch.__doc__
    missing = sorted(name for name in BUILTIN_TYPES if not re.search(rf"\b{name}\b", doc))
    assert not missing, f"element types missing from the create_elements_batch docstring: {missing}"


# ------------------------------------------------------------------ the checker itself
class _Machine:
    def __init__(self, capacity: int, delay, name: str, clock, *, speed: float = 1.0, color: str = "red"):
        pass


class _MachineSpec(BaseModel):
    type: Literal["Machine"]
    id: str
    capacity: int
    service_time: float
    speed: float = 1.0
    color: Optional[str] = None


GOOD = Binding(_Machine, field_map={"service_time": "delay"})


def test_checker_accepts_a_matching_spec():
    assert check_binding(_MachineSpec, GOOD) == []


@pytest.mark.parametrize("binding, spec_extra, expected", [
    (GOOD, {"weight": (float, 0.0)}, "spec field 'weight' is not a constructor parameter"),
    (Binding(_Machine), {}, "constructor parameter 'delay' has no spec field"),
    (Binding(_Machine, field_map={"service_time": "dly"}), {}, "field_map points to 'dly'"),
    (Binding(_Machine, field_map={"service_time": "delay", "old": "delay"}), {}, "spec field 'old', which does not exist"),
    (GOOD, {"speed": (float, 2.0)}, "default of 'speed' is 2.0 in the spec but 1.0"),
    (Binding(_Machine, field_map={"service_time": "delay"}, not_exposed={"size": "x"}), {}, "not_exposed lists 'size'"),
])
def test_checker_reports_mismatches(binding, spec_extra, expected):
    from pydantic import create_model
    spec_cls = create_model("_Changed", __base__=_MachineSpec, **spec_extra) if spec_extra else _MachineSpec
    problems = check_binding(spec_cls, binding)
    assert any(expected in p for p in problems), problems


def test_checker_sees_new_constructor_parameters():
    class _Upgraded(_Machine):
        def __init__(self, capacity, delay, name, clock, *, speed=1.0, color="red", setup=None):
            super().__init__(capacity, delay, name, clock, speed=speed, color=color)

    problems = check_binding(_MachineSpec, Binding(_Upgraded, field_map={"service_time": "delay"}))
    assert problems == ["_MachineSpec -> _Upgraded: constructor parameter 'setup' has no spec field. Add a field "
                        "'setup' to _MachineSpec, map one in field_map or list it in not_exposed with a reason"]


def test_checker_follows_kwargs_to_the_parent():
    class _Child(_Machine):
        def __init__(self, capacity, delay, name, clock, *, mode="fast", **kw):
            super().__init__(capacity, delay, name, clock, **kw)

    problems = check_binding(_MachineSpec, Binding(_Child, field_map={"service_time": "delay"}))
    assert problems == ["_MachineSpec -> _Child: constructor parameter 'mode' has no spec field. Add a field "
                        "'mode' to _MachineSpec, map one in field_map or list it in not_exposed with a reason"]


def test_engine_scan_finds_new_element_classes():
    class Conveyor(Element):
        def start(self): pass
        def receive(self, item): return False
        def unblock(self): return False
        def check_availability(self, item): return False

    assert Conveyor not in engine_subclasses(Element)       # defined in a test module: ignored
    Conveyor.__module__ = "PyFlow.Elements.conveyor"         # as if added to the engine
    try:
        assert Conveyor in engine_subclasses(Element)
    finally:
        Conveyor.__module__ = __name__


@pytest.mark.parametrize("spec_cls", list(RESOURCE_BINDINGS), ids=lambda c: c.__name__)
def test_resource_specs_match_constructors(spec_cls):
    assert_in_sync(spec_cls, RESOURCE_BINDINGS[spec_cls])


def test_resource_pool_examples_build():
    from PyFlow.spec import ResourcePoolSpec
    for example in ResourcePoolSpec.model_config["json_schema_extra"]["examples"]:
        pool = ModelBuilder(seed=1).add_resource(example)
        assert pool.capacity == ResourcePoolSpec.model_validate(example).count()
