"""FlexSim-style queries shared by model lists and resource rules.

A query has an optional filter and an optional order:

    Query.parse("WHERE type == puller.type AND age > 5 ORDER BY priority DESC, age DESC")
    Query(where="skills_count >= 2", order_by="utilization ASC")
    Query(where=lambda f: f["type"] == "A", order_by=lambda f: f["age"])     # Python callables

Expressions use the safe evaluator of :mod:`PyFlow.expressions`. SQL spellings are accepted:
``AND``, ``OR``, ``NOT``, a single ``=`` (equality) and ``<>`` (inequality). Each ``ORDER BY``
term is an expression followed by ``ASC`` (default) or ``DESC``; ties keep insertion order.

Names are looked up in a *scope*: a mapping built by the caller (a list entry's fields, a
resource unit's fields...). Objects in the scope expose their own fields with ``x.field``
(see ``expression_field`` in :mod:`PyFlow.expressions`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple, Union

from .expressions import ExpressionError, compile_expression

Scope = Mapping[str, Any]
Where = Union[None, str, Callable[[Scope], bool]]
OrderBy = Union[None, str, Callable[[Scope], Any], Sequence[Tuple[Union[str, Callable], bool]]]

_SQL_WORDS = [(re.compile(r"\bAND\b"), "and"), (re.compile(r"\bOR\b"), "or"), (re.compile(r"\bNOT\b"), "not"),
              (re.compile(r"<>"), "!="), (re.compile(r"(?<![=!<>])=(?!=)"), "==")]
_QUERY_RE = re.compile(r"^\s*(?:WHERE\s+(?P<where>.*?))?\s*(?:ORDER\s+BY\s+(?P<order>.*))?\s*$",
                       re.IGNORECASE | re.DOTALL)
_DIRECTION_RE = re.compile(r"^(?P<expr>.*?)(?:\s+(?P<dir>ASC|DESC))?\s*$", re.IGNORECASE | re.DOTALL)


class QueryError(ValueError):
    pass


def _sql_to_python(text: str) -> str:
    # string literals are left untouched
    parts = re.split(r"('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")", text)
    for i in range(0, len(parts), 2):
        for pattern, repl in _SQL_WORDS:
            parts[i] = pattern.sub(repl, parts[i])
    return "".join(parts)


def _split_terms(text: str) -> List[str]:
    """Split ORDER BY terms on commas that are not inside brackets or strings."""
    terms, depth, quote, current = [], 0, None, []
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            terms.append("".join(current))
            current = []
            continue
        current.append(ch)
    terms.append("".join(current))
    terms = [t.strip() for t in terms]
    if any(not t for t in terms):
        raise QueryError(f"E_INVALID_QUERY: empty ORDER BY term in {text!r}")
    return terms


def _compile(text: str, what: str) -> Callable[[Scope], Any]:
    try:
        return compile_expression(_sql_to_python(text))
    except ExpressionError as exc:
        raise QueryError(f"E_INVALID_QUERY: {what} {text!r}: {exc}") from None


def _parse_order(order: OrderBy) -> List[Tuple[Callable[[Scope], Any], bool]]:
    """``[(key(scope), descending)]``."""
    if order is None:
        return []
    if callable(order):
        return [(order, False)]
    if isinstance(order, str):
        terms = []
        for term in _split_terms(order):
            m = _DIRECTION_RE.match(term)
            expr, direction = m.group("expr").strip(), (m.group("dir") or "ASC").upper()
            if not expr:
                raise QueryError(f"E_INVALID_QUERY: empty ORDER BY term in {order!r}")
            terms.append((_compile(expr, "ORDER BY"), direction == "DESC"))
        return terms
    result = []
    for key, descending in order:
        result.append((_compile(key, "ORDER BY") if isinstance(key, str) else key, bool(descending)))
    return result


class _Desc:
    """Reverses the comparison of a sort key (works for any comparable type)."""
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def __lt__(self, other):
        return other.v < self.v

    def __eq__(self, other):
        return self.v == other.v


def _key_part(value: Any) -> Tuple[int, Any]:
    # None sorts last in ascending order (and first in descending)
    return (1, 0) if value is None else (0, value)


@dataclass
class Query:
    """Filter + order. ``where``/``order_by`` are expressions (strings) or Python callables
    receiving the scope. ``text`` keeps the original string for reports and specs."""
    where: Where = None
    order_by: OrderBy = None
    text: Optional[str] = None
    _where: Optional[Callable[[Scope], Any]] = field(init=False, repr=False, default=None)
    _order: List[Tuple[Callable[[Scope], Any], bool]] = field(init=False, repr=False, default_factory=list)

    def __post_init__(self):
        if isinstance(self.where, str) and self.where.strip():
            self._where = _compile(self.where, "WHERE")
        elif callable(self.where):
            self._where = self.where
        self._order = _parse_order(self.order_by)

    @classmethod
    def parse(cls, text: Optional[str]) -> "Query":
        """``"WHERE <expr> ORDER BY <expr> [ASC|DESC], ..."`` (both parts optional). A string
        without the keywords is an ORDER BY clause."""
        if text is None or not text.strip():
            return cls(text=text)
        m = _QUERY_RE.match(text)
        if m is None or (m.group("where") is None and m.group("order") is None):
            return cls(order_by=text, text=text)
        return cls(where=m.group("where"), order_by=m.group("order"), text=text)

    @classmethod
    def of(cls, value: Union[None, str, "Query"]) -> "Query":
        if isinstance(value, Query):
            return value
        return cls.parse(value)

    @property
    def has_order(self) -> bool:
        return bool(self._order)

    def matches(self, scope: Scope) -> bool:
        if self._where is None:
            return True
        try:
            return bool(self._where(scope))
        except ExpressionError as exc:
            raise QueryError(f"E_QUERY_FAILED: {self.text or self.where!r}: {exc}") from None

    def sort_key(self, scope: Scope) -> Tuple:
        try:
            parts = []
            for key, descending in self._order:
                part = _key_part(key(scope))
                parts.append(_Desc(part) if descending else part)
            return tuple(parts)
        except ExpressionError as exc:
            raise QueryError(f"E_QUERY_FAILED: {self.text or self.order_by!r}: {exc}") from None

    def select(self, candidates: Sequence[Any], scope_of: Callable[[Any], Scope], limit: Optional[int] = None) -> List[Any]:
        """Candidates that match, best first (stable: ties keep the candidates' order)."""
        chosen = [(c, scope_of(c)) for c in candidates]
        chosen = [(c, s) for c, s in chosen if self.matches(s)]
        if self._order:
            chosen.sort(key=lambda cs: self.sort_key(cs[1]))
        result = [c for c, _ in chosen]
        return result if limit is None else result[:limit]

    def __str__(self) -> str:
        return self.text or f"Query(where={self.where!r}, order_by={self.order_by!r})"


def check_query(text: Optional[str]) -> Optional[str]:
    """Validate a query string (raises :class:`QueryError`); returns it unchanged."""
    Query.parse(text)
    return text


__all__ = ["Query", "QueryError", "check_query"]
