"""Safe evaluation of small expressions over item labels (replaces ``eval``).

The expression is parsed once with :mod:`ast` and compiled into nested closures.
Only a whitelist of syntax is accepted:

* numbers, strings, ``True/False/None``
* names (looked up in the dict passed at evaluation time)
* ``+ - * / // % **``, unary ``- + not``, comparisons, ``and/or``, ``a if c else b``
* subscripts (``labels['PT']``)
* calls to ``min, max, abs, round, int, float``
* on ``item``: the methods in :data:`ITEM_METHODS` and the attributes in :data:`ITEM_ATTRIBUTES`
* ``x.field`` on objects that expose fields through an ``expression_field(name)`` method
  (list entries, items, resource units, pullers...): only what that method returns is reachable

Anything else (other attributes, dunders, lambdas, comprehensions, imports...) is
rejected when the expression is compiled.
"""
from __future__ import annotations

import ast
import operator
from typing import Any, Callable, Dict, Mapping

Names = Mapping[str, Any]
Compiled = Callable[[Names], Any]

FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "min": min, "max": max, "abs": abs, "round": round, "int": int, "float": float,
}
ITEM_METHODS = frozenset({"get_label_value", "get_type", "get_creation_time", "get_all_labels"})
ITEM_ATTRIBUTES = frozenset({"type", "name", "creation_time", "labels", "item_number"})
MAX_POWER_EXPONENT = 1000

_BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}
_COMPARE = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge, ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class ExpressionError(ValueError):
    pass


def _power(base, exp):
    if isinstance(exp, (int, float)) and abs(exp) > MAX_POWER_EXPONENT:
        raise ExpressionError(f"exponent {exp} too large")
    return base ** exp


def compile_expression(expression: str) -> Compiled:
    """Parse ``expression`` and return ``fn(names) -> value``."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"cannot parse {expression!r}: {exc.msg}") from None
    return _compile(tree.body, expression)


def _compile(node: ast.AST, src: str) -> Compiled:
    if isinstance(node, ast.Constant):
        value = node.value
        if not isinstance(value, (int, float, str, bool, type(None))):
            raise ExpressionError(f"constant {value!r} not allowed")
        return lambda names: value

    if isinstance(node, ast.Name):
        key = node.id
        if key.startswith("_"):
            raise ExpressionError(f"name {key!r} not allowed")

        def name(names: Names):
            try:
                return names[key]
            except KeyError:
                raise ExpressionError(f"unknown name {key!r}") from None
        return name

    if isinstance(node, ast.BinOp):
        left, right = _compile(node.left, src), _compile(node.right, src)
        if isinstance(node.op, ast.Pow):
            return lambda names: _power(left(names), right(names))
        op = _BINARY.get(type(node.op))
        if op is None:
            raise ExpressionError(f"operator {type(node.op).__name__} not allowed")
        return lambda names: op(left(names), right(names))

    if isinstance(node, ast.UnaryOp):
        op = _UNARY.get(type(node.op))
        if op is None:
            raise ExpressionError(f"operator {type(node.op).__name__} not allowed")
        operand = _compile(node.operand, src)
        return lambda names: op(operand(names))

    if isinstance(node, ast.BoolOp):
        values = [_compile(v, src) for v in node.values]
        if isinstance(node.op, ast.And):
            def and_(names):
                result = True
                for v in values:
                    result = v(names)
                    if not result:
                        return result
                return result
            return and_

        def or_(names):
            result = False
            for v in values:
                result = v(names)
                if result:
                    return result
            return result
        return or_

    if isinstance(node, ast.Compare):
        left = _compile(node.left, src)
        ops = []
        for op_node, comp in zip(node.ops, node.comparators):
            op = _COMPARE.get(type(op_node))
            if op is None:
                raise ExpressionError(f"comparison {type(op_node).__name__} not allowed")
            ops.append((op, _compile(comp, src)))

        def compare(names):
            a = left(names)
            for op, right in ops:
                b = right(names)
                if not op(a, b):
                    return False
                a = b
            return True
        return compare

    if isinstance(node, ast.IfExp):
        test, body, orelse = (_compile(n, src) for n in (node.test, node.body, node.orelse))
        return lambda names: body(names) if test(names) else orelse(names)

    if isinstance(node, ast.Subscript):
        value, index = _compile(node.value, src), _compile(node.slice, src)
        return lambda names: value(names)[index(names)]

    if isinstance(node, ast.Attribute):
        attr = node.attr
        if attr.startswith("_"):
            raise ExpressionError(f"attribute {attr!r} not allowed in {src!r}")
        if isinstance(node.value, ast.Name) and node.value.id == "item" and attr in ITEM_ATTRIBUTES:
            return lambda names: getattr(names["item"], attr)
        base = _compile(node.value, src)

        def field(names):
            obj = base(names)
            getter = getattr(type(obj), "expression_field", None)
            if getter is None:
                raise ExpressionError(f"{type(obj).__name__} has no fields ({attr!r} in {src!r})")
            try:
                return getter(obj, attr)
            except KeyError:
                raise ExpressionError(f"{type(obj).__name__} has no field {attr!r} (in {src!r})") from None
        return field

    if isinstance(node, ast.Call):
        if node.keywords:
            raise ExpressionError("keyword arguments not allowed")
        args = [_compile(a, src) for a in node.args]
        func = node.func
        if isinstance(func, ast.Name) and func.id in FUNCTIONS:
            fn = FUNCTIONS[func.id]
            return lambda names: fn(*(a(names) for a in args))
        if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                and func.value.id == "item" and func.attr in ITEM_METHODS):
            method = func.attr

            def call_item(names):
                item = names["item"]
                if item is None:
                    raise ExpressionError(f"{src!r} needs an item, but none is available here")
                return getattr(item, method)(*(a(names) for a in args))
            return call_item
        raise ExpressionError(f"call not allowed in {src!r}")

    raise ExpressionError(f"syntax {type(node).__name__} not allowed in {src!r}")


__all__ = ["compile_expression", "ExpressionError", "FUNCTIONS", "ITEM_METHODS", "ITEM_ATTRIBUTES"]
