"""Sampler fields of a model specification (service times, inter-arrival times, ...).

A sampler field is:

* a number                     -> constant (``5``)
* a SimuLean spec string       -> ``"Exponential~0.5"`` (rate), ``"Triangular~3~5~8"``, ...
* a label expression string    -> ``"PT1 * 60"`` or ``"item.get_label_value('PT1')"``

Strings are checked when the spec is validated (unknown distribution, wrong number of
parameters, invalid expression), so errors appear before the model is built.
"""
from __future__ import annotations

from typing import Annotated, Any, Union

from pydantic import AfterValidator, Field

from ..sampling import SamplerError, as_sampler

SAMPLER_DESCRIPTION = (
    "Number (constant), SimuLean spec string 'Type~p1~p2' (Constant, Uniform~min~max, Normal~mean~sd, "
    "Exponential~rate, ExponentialMean~mean, Triangular~min~mode~max, Gamma~shape~scale, "
    "Weibull~shape~scale, LogNormal~mu~sigma, Beta~a~b~min~max, ChiSquare~df, StudentT~df, "
    "FDistribution~d1~d2, Poisson~lambda, Binomial~n~p, DiscreteUniform~min~max) or a label "
    "expression ('PT1 * 60', 'item.get_label_value(\"PT1\")')."
)


def _check_sampler(value: Any) -> Any:
    if isinstance(value, str):
        try:
            as_sampler(value)
        except SamplerError as exc:
            raise ValueError(str(exc)) from None
    return value


SamplerSpec = Annotated[Union[float, str], AfterValidator(_check_sampler), Field(description=SAMPLER_DESCRIPTION)]


def build_sampler(spec: Any) -> Any:
    """A validated sampler field is accepted as is by :func:`PyFlow.sampling.as_sampler`."""
    return spec


__all__ = ["SamplerSpec", "build_sampler", "SAMPLER_DESCRIPTION"]
