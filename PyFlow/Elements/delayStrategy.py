"""Compatibility layer: the delay strategies are now samplers (see ``PyFlow.sampling``)."""
from typing import Union

from scipy import stats

from ..sampling import ConstantSampler, DelayStrategy, ExpressionSampler, ScipySampler, Sampler


class RandomDelayStrategy(Sampler):
    """Delay drawn from a frozen ``scipy.stats`` distribution, or a constant number."""

    def __init__(self, random_times: Union[stats.rv_continuous, stats.rv_discrete, float], **kwargs):
        super().__init__(**kwargs)
        if isinstance(random_times, (int, float)) and not isinstance(random_times, bool):
            self._inner: Sampler = ConstantSampler(random_times)
        else:
            self._inner = ScipySampler(random_times)
        self.random_times = random_times

    def bind(self, rng, key=None):
        self._inner.bind(rng, key)
        return super().bind(rng, key)

    def _draw(self, item) -> float:
        return self._inner._draw(item)

    def __repr__(self) -> str:
        return f"RandomDelayStrategy({self._inner!r})"


class ExpressionDelayStrategy(ExpressionSampler):
    """Delay computed from an expression over item labels (safe evaluation, no ``eval``)."""


__all__ = ["DelayStrategy", "RandomDelayStrategy", "ExpressionDelayStrategy"]
