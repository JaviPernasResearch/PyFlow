"""Declared correspondence between a spec class and the engine class it builds.

A :class:`Binding` says how the fields of a Pydantic spec map to the constructor parameters
of the engine class. ``tests/unit/test_spec_sync.py`` compares every binding with the real
constructor signature, so changing an element, strategy or downtime generator without
updating its spec makes the test suite fail with an explicit message.

    Binding(MultiServer, field_map={"service_time": "delay_strategy"})

* constructor parameters must be covered by a spec field with the same name, by a
  ``field_map`` entry (spec field -> parameter) or be listed in ``not_exposed`` with a reason;
* spec fields must be a parameter, a ``field_map`` key or be listed in ``spec_only``;
* when a parameter and its 1:1 spec field both have a default, the defaults must be equal
  (a spec default of ``None`` means "use the engine default" and is not compared; fields
  listed in ``converted`` are transformed before reaching the constructor and are skipped).

Structural parameters (``self``, the element name, the model/clock, the downtime target)
are never compared. A ``**kwargs`` parameter is expanded with the parameters of the parent
class constructor it is forwarded to.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Type

STRUCTURAL_PARAMS = frozenset({"self", "name", "clock", "sim_clock", "model", "target"})
BASE_SPEC_FIELDS = frozenset({"type", "id", "name", "input_strategy", "targets"})


@dataclass(frozen=True)
class Binding:
    target: type
    field_map: Dict[str, str] = field(default_factory=dict)      # spec field -> constructor parameter
    not_exposed: Dict[str, str] = field(default_factory=dict)    # constructor parameter -> reason
    spec_only: Dict[str, str] = field(default_factory=dict)      # spec field -> reason
    converted: Dict[str, str] = field(default_factory=dict)      # spec field -> how its value is converted


def constructor_params(cls: type) -> Dict[str, inspect.Parameter]:
    """Named constructor parameters, following ``**kwargs`` up the class hierarchy."""
    params: Dict[str, inspect.Parameter] = {}
    for klass in cls.__mro__:
        if klass is object:
            break
        init = klass.__dict__.get("__init__")
        if init is None:
            continue
        forwards = False
        for p in inspect.signature(init).parameters.values():
            if p.kind is p.VAR_KEYWORD:
                forwards = True
            elif p.name not in STRUCTURAL_PARAMS and p.name not in params:
                params[p.name] = p
        if not forwards:
            break
    return params


def check_binding(spec_cls: Type[Any], binding: Binding) -> List[str]:
    """Differences between ``spec_cls`` and the constructor of ``binding.target`` (empty = in sync)."""
    problems: List[str] = []
    where = f"{spec_cls.__name__} -> {binding.target.__name__}"
    params = constructor_params(binding.target)
    fields = {name: info for name, info in spec_cls.model_fields.items() if name not in BASE_SPEC_FIELDS}

    for name in binding.field_map.values():
        if name not in params:
            problems.append(f"{where}: field_map points to '{name}', which is not a constructor parameter "
                            f"(parameters: {', '.join(params) or 'none'})")
    for name in binding.field_map:
        if name not in fields:
            problems.append(f"{where}: field_map uses spec field '{name}', which does not exist")
    for name in binding.not_exposed:
        if name not in params:
            problems.append(f"{where}: not_exposed lists '{name}', which is not a constructor parameter")
    for name in binding.spec_only:
        if name not in fields:
            problems.append(f"{where}: spec_only lists '{name}', which is not a spec field")
    for name in binding.converted:
        if name not in fields:
            problems.append(f"{where}: converted lists '{name}', which is not a spec field")

    covered: Set[str] = set(binding.field_map.values()) | set(binding.not_exposed)
    covered |= {name for name in fields if name in params}
    for name in params:
        if name not in covered:
            problems.append(f"{where}: constructor parameter '{name}' has no spec field. Add a field "
                            f"'{name}' to {spec_cls.__name__}, map one in field_map or list it in "
                            "not_exposed with a reason")

    for name, info in fields.items():
        if name in params or name in binding.field_map or name in binding.spec_only:
            continue
        problems.append(f"{where}: spec field '{name}' is not a constructor parameter. Map it in field_map "
                        "or list it in spec_only with a reason")

    targets: Dict[str, List[str]] = {}
    for spec_name, param_name in binding.field_map.items():
        targets.setdefault(param_name, []).append(spec_name)
    for name, info in fields.items():
        param_name = name if name in params else binding.field_map.get(name)
        if (param_name not in params or name in binding.converted
                or len(targets.get(param_name, [name])) > 1):
            continue  # several spec fields build one parameter (e.g. labels -> model_item)
        param = params[param_name]
        if param.default is inspect.Parameter.empty or info.is_required():
            continue
        spec_default = info.get_default(call_default_factory=True)
        if spec_default is None:
            continue
        if spec_default != param.default:
            problems.append(f"{where}: default of '{name}' is {spec_default!r} in the spec but "
                            f"{param.default!r} in {binding.target.__name__}.__init__")
    return problems


def first_paragraph(text: Optional[str]) -> str:
    return " ".join((text or "").strip().split("\n\n")[0].split())


__all__ = ["Binding", "check_binding", "constructor_params", "STRUCTURAL_PARAMS", "BASE_SPEC_FIELDS"]
