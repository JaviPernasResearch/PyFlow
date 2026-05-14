"""Spec → live PyFlow object builders."""

from scipy import stats

from PyFlow import InterArrivalSource, ItemsQueue, SimClock
from PyFlow.Elements.scheduleSource import ScheduleSource
from PyFlow.Items.item import Item
from PyFlow.Link.outputStrategy import FirstAvailableStrategy, RoundRobinStrategy

from .inspection import TrackingMultiServer, TypeTrackingSink
from .schemas import ConnectionSpec, DistributionSpec, ElementSpec, LabelExprSpec, ServiceTimeSpec


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


def build_service_time(spec: ServiceTimeSpec):
    """Return either a frozen scipy distribution or the expression string for MultiServer.

    Gap 1: MultiServer's delay_strategy accepts both a scipy distribution and
    a Python expression string — this function selects the right form.
    """
    if spec.type == "label_expr":
        return spec.expression          # MultiServer / ExpressionDelayStrategy
    return build_distribution(spec)     # MultiServer / RandomDelayStrategy


def build_element(spec: ElementSpec, clock: SimClock):
    """Instantiate the PyFlow element described by *spec* and register it with *clock*."""

    if spec.type == "InterArrivalSource":
        # Gap 2: build a model_item when item_type or labels are provided.
        model_item = None
        if spec.item_type is not None or spec.labels:
            model_item = Item(
                0,
                item_type=spec.item_type or "Default",
                labels=spec.labels or {},
                model_item=True,
            )
        return InterArrivalSource(spec.name, clock, build_distribution(spec.interarrival),
                                  model_item=model_item)

    if spec.type == "ItemsQueue":
        return ItemsQueue(spec.capacity, spec.name, clock)

    if spec.type == "MultiServer":
        # Gap 1+5: TrackingMultiServer supports both dist and expression delays
        # and always tracks blockage_count.
        return TrackingMultiServer(spec.num_servers, build_service_time(spec.service_time),
                                   spec.name, clock)

    if spec.type == "Sink":
        # Gap 4: TypeTrackingSink always tracks per-type counts.
        return TypeTrackingSink(spec.name, clock)

    if spec.type == "ScheduleSource":
        # Gap 3: convert the jobs list to PyFlow's data_dict format.
        return ScheduleSource(spec.name, clock, data_dict=spec.to_data_dict())

    raise ValueError(f"Unknown element type: {spec.type!r}")


def build_strategy(name: str):
    """Return a fresh OutputStrategy instance for the given strategy name."""
    if name == "FirstAvailable":
        return FirstAvailableStrategy()
    if name == "RoundRobin":
        return RoundRobinStrategy()
    raise ValueError(f"Unknown strategy: {name!r}")
