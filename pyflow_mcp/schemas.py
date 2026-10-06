"""Spec types accepted by the MCP tools.

They are the core specification types of :mod:`PyFlow.spec` (one source of truth for the
library, the MCP server and the JSON/YAML files); this module re-exports them under the
names the server has always used.
"""

from PyFlow.spec import (CalendarSpec, CombinerSpec, ConnectionSpec, DistributionSpec, DowntimeSpec, ElementSpec,
                         ExponDist, InfiniteSourceSpec, InterArrivalBufferingSourceSpec, InterArrivalSourceSpec,
                         ItemsQueueSpec, JobSpec, LabelExprSpec, ListSpec, ModelSpec, MultiAssemblerSpec, MultiServerSpec,
                         NormDist, ResourcePoolSpec, ResourceUseSpec, RunSpec, SamplerSpec, ScheduleSourceSpec,
                         SinkSpec, TriangDist, UniformDist)

# Service times accept every sampler form (number, "Type~p" string, expression, object)
ServiceTimeSpec = SamplerSpec

__all__ = [
    "ExponDist", "UniformDist", "NormDist", "TriangDist", "LabelExprSpec", "DistributionSpec", "ServiceTimeSpec",
    "SamplerSpec", "InterArrivalSourceSpec", "InterArrivalBufferingSourceSpec", "InfiniteSourceSpec",
    "ScheduleSourceSpec", "JobSpec", "ItemsQueueSpec", "MultiServerSpec", "CombinerSpec", "MultiAssemblerSpec",
    "SinkSpec", "ElementSpec", "ConnectionSpec", "ListSpec", "ResourcePoolSpec", "ResourceUseSpec", "DowntimeSpec", "CalendarSpec", "RunSpec", "ModelSpec",
]
