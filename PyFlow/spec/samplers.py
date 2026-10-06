"""Sampler fields of a model specification (service times, inter-arrival times, ...).

A sampler field accepts, in order of preference:

* a number                     -> constant (``5``)
* a SimuLean spec string       -> ``"Exponential~0.5"`` (rate), ``"Triangular~3~5~8"``, ...
* a label expression string    -> ``"PT1 * 60"`` or ``"item.get_label_value('PT1')"``
* a scipy-style object         -> ``{"type": "expon", "scale": 2}`` (legacy MCP format)

Strings are checked when the spec is validated (unknown distribution, wrong number of
parameters, invalid expression), so errors appear before the model is built.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from scipy import stats

from ..sampling import SamplerError, as_sampler


class _Dist(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExponDist(_Dist):
    type: Literal["expon"]
    scale: float = Field(gt=0, description="Mean of the exponential distribution")


class UniformDist(_Dist):
    type: Literal["uniform"]
    loc: float = Field(description="Lower bound")
    scale: float = Field(ge=0, description="Width (use 0 for a deterministic value equal to loc)")


class NormDist(_Dist):
    type: Literal["norm"]
    loc: float = Field(description="Mean")
    scale: float = Field(gt=0, description="Standard deviation")


class TriangDist(_Dist):
    type: Literal["triang"]
    c: float = Field(
        ge=0, le=1,
        description=(
            "Mode expressed as a fraction of the interval [loc, loc+scale]. "
            "c = (mode - loc) / scale. "
            "Example: triangle with min=2, mode=5, max=8 → loc=2, scale=6, c=0.5 (since (5-2)/6=0.5)."
        ),
    )
    loc: float = Field(description="Lower bound (minimum value)")
    scale: float = Field(gt=0, description="Width = max - min")


class LabelExprSpec(_Dist):
    """Service time read from item labels at runtime (safe expression, no ``eval``).

    Examples: ``{"type": "label_expr", "expression": "item.get_label_value('PT1')"}``,
    ``{"type": "label_expr", "expression": "PT1 * 60"}``."""
    type: Literal["label_expr"]
    expression: str = Field(
        min_length=1,
        description=(
            "Expression evaluated per item. Labels can be used by name (PT1) or through "
            "item.get_label_value('PT1'). Must return a non-negative number."
        ),
    )


DistributionSpec = Annotated[Union[ExponDist, UniformDist, NormDist, TriangDist], Field(discriminator="type")]
ObjectSamplerSpec = Annotated[Union[ExponDist, UniformDist, NormDist, TriangDist, LabelExprSpec],
                              Field(discriminator="type")]

SAMPLER_DESCRIPTION = (
    "Number (constant), SimuLean spec string 'Type~p1~p2' (Constant, Uniform~min~max, Normal~mean~sd, "
    "Exponential~rate, ExponentialMean~mean, Triangular~min~mode~max, Gamma~shape~scale, "
    "Weibull~shape~scale, LogNormal~mu~sigma, Beta~a~b~min~max, ChiSquare~df, StudentT~df, "
    "FDistribution~d1~d2, Poisson~lambda, Binomial~n~p, DiscreteUniform~min~max), a label "
    "expression ('PT1 * 60') or an object {type: expon|uniform|norm|triang|label_expr, ...}."
)


def _check_sampler(value: Any) -> Any:
    if isinstance(value, str):
        try:
            as_sampler(value)
        except SamplerError as exc:
            raise ValueError(str(exc)) from None
    return value


SamplerSpec = Annotated[Union[float, str, ObjectSamplerSpec], AfterValidator(_check_sampler),
                        Field(description=SAMPLER_DESCRIPTION)]


def build_sampler(spec: Any) -> Any:
    """Turn a validated sampler field into something :func:`PyFlow.sampling.as_sampler` accepts."""
    if isinstance(spec, ExponDist):
        return stats.expon(scale=spec.scale)
    if isinstance(spec, UniformDist):
        return stats.uniform(loc=spec.loc, scale=spec.scale)
    if isinstance(spec, NormDist):
        return stats.norm(loc=spec.loc, scale=spec.scale)
    if isinstance(spec, TriangDist):
        return stats.triang(c=spec.c, loc=spec.loc, scale=spec.scale)
    if isinstance(spec, LabelExprSpec):
        return spec.expression
    return spec


__all__ = ["ExponDist", "UniformDist", "NormDist", "TriangDist", "LabelExprSpec", "DistributionSpec",
           "ObjectSamplerSpec", "SamplerSpec", "build_sampler", "SAMPLER_DESCRIPTION"]
