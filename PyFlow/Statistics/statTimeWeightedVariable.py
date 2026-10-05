from typing import Optional


class StatTimeWeightedVariable:
    """Piecewise-constant level (e.g. WIP) with its time-weighted average since the
    last reset: ``average(t) = integral(value dt over [t0, t]) / (t - t0)``."""

    def __init__(self, t0: float = 0.0, value: float = 0.0):
        self.reset(t0, value)

    def reset(self, t: float, value: Optional[float] = None) -> None:
        """Restart the statistics at time ``t``; the current level is kept unless given."""
        if value is not None:
            self.value = value
        elif not hasattr(self, "value"):
            self.value = 0.0
        self.t0 = t
        self.last_t = t
        self.area = 0.0
        self.count = 0
        self.max_value = self.value
        self.min_value = self.value

    def _advance(self, t: float) -> None:
        if t < self.last_t:
            raise ValueError(f"time went backwards: {t} < {self.last_t}")
        self.area += self.value * (t - self.last_t)
        self.last_t = t

    def update(self, delta: float, t: float) -> None:
        """Change the level by ``delta`` at time ``t``."""
        self.set(self.value + delta, t)

    def set(self, value: float, t: float) -> None:
        last_t = self.last_t
        if t < last_t:
            raise ValueError(f"time went backwards: {t} < {last_t}")
        self.area += self.value * (t - last_t)
        self.last_t = t
        self.value = value
        self.count += 1
        if value > self.max_value:
            self.max_value = value
        elif value < self.min_value:
            self.min_value = value

    def average(self, t: float) -> float:
        """Time-weighted mean over ``[t0, t]`` (the current level if no time elapsed)."""
        elapsed = t - self.t0
        if elapsed <= 0:
            return float(self.value)
        return (self.area + self.value * (t - self.last_t)) / elapsed

    def get_stats(self, t: float) -> dict:
        return {
            "max": self.max_value,
            "min": self.min_value,
            "average": self.average(t),
            "count": self.count,
            "current": self.value,
        }

    # StatVariable-like getters (current level / extremes)
    def get_stats_value(self) -> float:
        return self.value

    def get_stats_max(self) -> float:
        return self.max_value

    def get_stats_min(self) -> float:
        return self.min_value

    def get_stats_count(self) -> int:
        return self.count
