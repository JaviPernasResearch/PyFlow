"""Spec → live PyFlow object builders (thin wrappers over :mod:`PyFlow.spec`)."""

from PyFlow.spec import BuildContext, build_output_strategy, build_sampler, get_element_type


def build_distribution(spec):
    """Sampler specification accepted by the elements (frozen scipy distribution, string or number)."""
    return build_sampler(spec)


build_service_time = build_distribution


def build_element(spec, model):
    """Instantiate the element described by *spec* in *model* (a ``Model`` or its ``SimClock``)."""
    from PyFlow.model import resolve_model
    return get_element_type(spec.type).build(spec, BuildContext(resolve_model(model)))


def build_strategy(spec):
    """A fresh output strategy for a name ('RoundRobin') or a strategy object."""
    return build_output_strategy(spec)
