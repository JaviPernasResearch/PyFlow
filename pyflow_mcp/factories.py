"""Spec → live PyFlow object builders."""

from scipy import stats

from PyFlow import InterArrivalSource, ItemsQueue, MultiServer, Sink, SimClock
from PyFlow.Link.outputStrategy import FirstAvailableStrategy, RoundRobinStrategy

from .schemas import ConnectionSpec, DistributionSpec, ElementSpec


def build_distribution(spec: DistributionSpec):
    """Return a frozen scipy.stats distribution for the given spec."""
    if spec.type == "expon":
        return stats.expon(scale=spec.scale)
    if spec.type == "uniform":
        return stats.uniform(loc=spec.loc, scale=spec.scale)
    if spec.type == "norm":
        return stats.norm(loc=spec.loc, scale=spec.scale)
    if spec.type == "triang":
        return stats.triang(c=spec.c, loc=spec.loc, scale=spec.scale)
    raise ValueError(f"Unknown distribution type: {spec.type!r}")


def build_element(spec: ElementSpec, clock: SimClock):
    """Instantiate the PyFlow element described by *spec* and register it with *clock*."""
    if spec.type == "InterArrivalSource":
        return InterArrivalSource(spec.name, clock, build_distribution(spec.interarrival))
    if spec.type == "ItemsQueue":
        return ItemsQueue(spec.capacity, spec.name, clock)
    if spec.type == "MultiServer":
        return MultiServer(spec.num_servers, build_distribution(spec.service_time), spec.name, clock)
    if spec.type == "Sink":
        return Sink(spec.name, clock)
    raise ValueError(f"Unknown element type: {spec.type!r}")


def build_strategy(name: str):
    """Return a fresh OutputStrategy instance for the given strategy name."""
    if name == "FirstAvailable":
        return FirstAvailableStrategy()
    if name == "RoundRobin":
        return RoundRobinStrategy()
    raise ValueError(f"Unknown strategy: {name!r}")
