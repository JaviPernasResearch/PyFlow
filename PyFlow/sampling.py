"""Random and deterministic samplers (service times, inter-arrival times, ...).

Every sampler draws from its own ``numpy.random.Generator``. Elements bind their
samplers to a per-model stream derived from the model seed and a stable key
(``"<element name>.<purpose>"``), so the same seed gives the same results and
adding an element does not shift the random numbers of the others (common random
numbers between scenarios).

Accepted sampler specifications (see :func:`as_sampler`):

* a number                         -> constant
* a frozen ``scipy.stats`` object  -> drawn with ``rvs(random_state=<stream>)``
* ``"Type~p1~p2"``                 -> SimuLean ``SamplerSpec`` syntax (e.g. ``"Exponential~0.2"``)
* any other string                 -> safe expression over item labels
  (``"tSoldadura + tInspeccion * inspeccionOn"`` or ``"item.get_label_value('PT1')"``)
* a :class:`Sampler` instance
"""
from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np

from .expressions import ExpressionError, compile_expression

NEGATIVE_POLICIES = ("error", "truncate")


class SamplerError(ValueError):
    """Invalid sampler specification or invalid sample. ``code`` is a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class Sampler(ABC):
    """Base class. Subclasses implement ``_draw(item)``.

    ``negative`` decides what happens with a negative (or NaN) sample:
    ``"error"`` raises :class:`SamplerError` (default), ``"truncate"`` returns ``max(0, x)``.
    """

    def __init__(self, *, negative: str = "error"):
        if negative not in NEGATIVE_POLICIES:
            raise SamplerError("E_INVALID_DIST", f"negative must be one of {NEGATIVE_POLICIES}, got {negative!r}")
        self.negative = negative
        self.rng: Optional[np.random.Generator] = None
        self.key: Optional[str] = None

    def bind(self, rng: np.random.Generator, key: Optional[str] = None) -> "Sampler":
        """Attach a random stream (done by the model; see ``Model.bind_sampler``)."""
        self.rng = rng
        self.key = key
        return self

    def _generator(self) -> np.random.Generator:
        if self.rng is None:  # unbound sampler used outside a model: unseeded stream
            self.rng = np.random.default_rng()
        return self.rng

    @abstractmethod
    def _draw(self, item) -> float:
        pass

    def sample(self, item=None) -> float:
        value = float(self._draw(item))
        if not value >= 0:  # negative or NaN
            if self.negative == "truncate" and not math.isnan(value):
                return 0.0
            raise SamplerError(
                "E_NEGATIVE_SAMPLE",
                f"{self!r} produced {value}; use a non-negative distribution or negative='truncate'",
            )
        return value

    __call__ = sample


class ConstantSampler(Sampler):
    def __init__(self, value: float, **kwargs):
        super().__init__(**kwargs)
        self.value = float(value)

    def _draw(self, item) -> float:
        return self.value

    def __repr__(self) -> str:
        return f"ConstantSampler({self.value})"


class ScipySampler(Sampler):
    """Wraps a frozen ``scipy.stats`` distribution."""

    def __init__(self, dist: Any, **kwargs):
        super().__init__(**kwargs)
        if not hasattr(dist, "rvs"):
            raise SamplerError("E_INVALID_DIST", f"{dist!r} is not a scipy.stats frozen distribution")
        self.dist = dist

    def _draw(self, item) -> float:
        return self.dist.rvs(random_state=self._generator())

    def __repr__(self) -> str:
        name = getattr(getattr(self.dist, "dist", None), "name", type(self.dist).__name__)
        return f"ScipySampler({name}, args={getattr(self.dist, 'args', ())}, kwds={getattr(self.dist, 'kwds', {})})"


class SpecSampler(Sampler):
    """Sampler built from a SimuLean ``SamplerSpec`` string; draws with numpy directly."""

    def __init__(self, spec: str, draw: Callable[[np.random.Generator], float], **kwargs):
        super().__init__(**kwargs)
        self.spec = spec
        self._fn = draw

    def _draw(self, item) -> float:
        return self._fn(self._generator())

    def __repr__(self) -> str:
        return f"SpecSampler({self.spec!r})"


class ExpressionSampler(Sampler):
    """Evaluates an arithmetic expression over the item's labels (no ``eval``).

    Available names: every label of the item, ``labels`` (dict), ``item`` (only the
    methods listed in :mod:`PyFlow.expressions`) and the functions
    ``min, max, abs, round, int, float``.
    """

    def __init__(self, expression: str, **kwargs):
        super().__init__(**kwargs)
        self.expression = expression
        try:
            self._fn = compile_expression(expression)
        except ExpressionError as exc:
            raise SamplerError("E_INVALID_EXPRESSION", str(exc)) from None

    def _draw(self, item) -> float:
        names: Dict[str, Any] = dict(item.get_all_labels()) if item is not None else {}
        names["labels"] = item.get_all_labels() if item is not None else {}
        names["item"] = item
        try:
            return float(self._fn(names))
        except (ExpressionError, TypeError, ValueError, ZeroDivisionError, KeyError) as exc:
            raise SamplerError("E_INVALID_EXPRESSION", f"error evaluating {self.expression!r}: {exc}") from None

    def __repr__(self) -> str:
        return f"ExpressionSampler({self.expression!r})"


# ---------------------------------------------------------------------------
# SimuLean SamplerSpec  ("Type~p1~p2...")
# ---------------------------------------------------------------------------

def _bool(text: str) -> bool:
    low = text.strip().lower()
    if low in ("true", "1"):
        return True
    if low in ("false", "0"):
        return False
    raise ValueError(f"not a boolean: {text!r}")


# type -> (parameter converters, builder(params) -> draw(rng), truncate negatives like SimuLean)
_SPEC_TYPES: Dict[str, Tuple[Tuple[Callable[[str], Any], ...], Callable[..., Callable[[np.random.Generator], float]], bool]] = {
    "Constant": ((float,), lambda v: (lambda rng: v), False),
    "Uniform": ((float, float), lambda a, b: (lambda rng: rng.uniform(a, b)), False),
    "Normal": ((float, float), lambda m, s: (lambda rng: rng.normal(m, s)), True),
    "Exponential": ((float,), lambda rate: (lambda rng: rng.exponential(1.0 / rate)), False),
    "ExponentialMean": ((float,), lambda mean: (lambda rng: rng.exponential(mean)), False),
    "Triangular": ((float, float, float), lambda a, m, b: (lambda rng: rng.triangular(a, m, b)), False),
    "Gamma": ((float, float), lambda k, s: (lambda rng: rng.gamma(k, s)), False),
    "Weibull": ((float, float), lambda k, s: (lambda rng: s * rng.weibull(k)), False),
    "LogNormal": ((float, float), lambda mu, sg: (lambda rng: rng.lognormal(mu, sg)), False),
    "Beta": ((float, float, float, float), lambda a, b, lo, hi: (lambda rng: lo + (hi - lo) * rng.beta(a, b)), False),
    "ChiSquare": ((int,), lambda df: (lambda rng: rng.chisquare(df)), False),
    "FDistribution": ((int, int), lambda d1, d2: (lambda rng: rng.f(d1, d2)), False),
    "Poisson": ((float,), lambda lam: (lambda rng: float(rng.poisson(lam))), False),
    "Binomial": ((int, float), lambda n, p: (lambda rng: float(rng.binomial(n, p))), False),
    "DiscreteUniform": ((int, int), lambda a, b: (lambda rng: float(rng.integers(a, b, endpoint=True))), False),
}

_SPEC_RE = re.compile(r"^\s*([A-Za-z]+)\s*~")


def is_sampler_spec(text: str) -> bool:
    """``True`` if ``text`` uses the ``Type~p1~...`` syntax."""
    return bool(_SPEC_RE.match(text))


def parse_sampler_spec(spec: str, *, negative: Optional[str] = None) -> Sampler:
    """Decode a SimuLean ``SamplerSpec`` string such as ``"Exponential~0.2"`` (rate!) or
    ``"Triangular~3~5~8"``. Unlike SimuLean, unknown types and missing/extra/invalid
    parameters raise :class:`SamplerError` instead of silently falling back to defaults.

    ``Normal`` and ``StudentT`` truncate negative samples to 0, as in SimuLean
    (``StudentT~df~false`` disables it). ``LabelExpression~expr`` builds an
    :class:`ExpressionSampler`.
    """
    type_name, _, rest = spec.strip().partition("~")
    type_name = type_name.strip()
    if type_name == "LabelExpression":
        return ExpressionSampler(rest, negative=negative or "error")
    params = [p.strip() for p in rest.split("~")] if rest else []

    if type_name == "StudentT":
        if len(params) not in (1, 2):
            raise SamplerError("E_INVALID_DIST", f"{spec!r}: StudentT expects df[~clamp]")
        try:
            df = int(params[0])
            clamp = _bool(params[1]) if len(params) == 2 else True
        except ValueError as exc:
            raise SamplerError("E_INVALID_DIST", f"{spec!r}: {exc}") from None
        return SpecSampler(spec, lambda rng: rng.standard_t(df),
                           negative=negative or ("truncate" if clamp else "error"))

    if type_name not in _SPEC_TYPES:
        known = ", ".join(sorted([*_SPEC_TYPES, "StudentT", "LabelExpression"]))
        raise SamplerError("E_INVALID_DIST", f"unknown distribution {type_name!r} in {spec!r}. Known: {known}")
    converters, builder, clamp = _SPEC_TYPES[type_name]
    if len(params) != len(converters):
        raise SamplerError("E_INVALID_DIST", f"{spec!r}: {type_name} expects {len(converters)} parameter(s), got {len(params)}")
    try:
        values = [conv(p) for conv, p in zip(converters, params)]
    except ValueError as exc:
        raise SamplerError("E_INVALID_DIST", f"{spec!r}: {exc}") from None
    if type_name == "Exponential" and values[0] <= 0:
        raise SamplerError("E_INVALID_DIST", f"{spec!r}: rate must be > 0")
    return SpecSampler(spec, builder(*values), negative=negative or ("truncate" if clamp else "error"))


def as_sampler(spec: Any, *, negative: Optional[str] = None) -> Sampler:
    """Convert any accepted specification (see module docstring) into a :class:`Sampler`."""
    if isinstance(spec, Sampler):
        return spec
    if isinstance(spec, bool):
        raise SamplerError("E_INVALID_DIST", "a boolean is not a valid sampler")
    kwargs = {"negative": negative} if negative is not None else {}
    if isinstance(spec, (int, float, np.integer, np.floating)):
        return ConstantSampler(float(spec), **kwargs)
    if isinstance(spec, str):
        if is_sampler_spec(spec):
            return parse_sampler_spec(spec, negative=negative)
        return ExpressionSampler(spec, **kwargs)
    if hasattr(spec, "rvs"):
        return ScipySampler(spec, **kwargs)
    raise SamplerError("E_INVALID_DIST", f"cannot build a sampler from {spec!r}")


__all__ = [
    "Sampler", "SamplerError", "ConstantSampler", "ScipySampler", "SpecSampler",
    "ExpressionSampler", "as_sampler", "parse_sampler_spec", "is_sampler_spec",
]
