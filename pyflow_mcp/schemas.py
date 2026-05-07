"""Pydantic v2 models for every spec type accepted by the MCP tools."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------

class ExponDist(BaseModel):
    type: Literal["expon"]
    scale: float = Field(gt=0, description="Mean of the exponential distribution")


class UniformDist(BaseModel):
    type: Literal["uniform"]
    loc: float = Field(description="Lower bound")
    scale: float = Field(ge=0, description="Width (use 0 for a deterministic value equal to loc)")


class NormDist(BaseModel):
    type: Literal["norm"]
    loc: float = Field(description="Mean")
    scale: float = Field(gt=0, description="Standard deviation")


class TriangDist(BaseModel):
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


DistributionSpec = Annotated[
    Union[ExponDist, UniformDist, NormDist, TriangDist],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------

class InterArrivalSourceSpec(BaseModel):
    type: Literal["InterArrivalSource"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
                    description="Unique identifier used to reference this element in connections")
    name: str = Field(description="Human-readable display name")
    interarrival: DistributionSpec = Field(description="Distribution of time between consecutive arrivals")


class ItemsQueueSpec(BaseModel):
    type: Literal["ItemsQueue"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    name: str
    capacity: int = Field(
        gt=0,
        description=(
            "Maximum number of items the queue can hold. "
            "When full, the queue rejects new items: the upstream source blocks "
            "and does NOT schedule its next arrival until space becomes available. "
            "Items are never silently dropped — the source retries when notified."
        ),
    )


class MultiServerSpec(BaseModel):
    type: Literal["MultiServer"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    name: str
    num_servers: int = Field(gt=0, description="Number of parallel processing slots")
    service_time: DistributionSpec = Field(description="Distribution of service time per item")


class SinkSpec(BaseModel):
    type: Literal["Sink"]
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    name: str


ElementSpec = Annotated[
    Union[InterArrivalSourceSpec, ItemsQueueSpec, MultiServerSpec, SinkSpec],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

class ConnectionSpec(BaseModel):
    """A directed connection from one origin element to one or more destinations.

    All destinations sharing the same origin must be passed in a single spec so
    that PyFlow's connect() receives the full destination list at once — this
    is required for strategies like RoundRobin to work across the whole set.
    """

    origin: str = Field(description="Element id of the upstream element")
    destinations: list[str] = Field(min_length=1,
                                    description="One or more element ids to receive items from origin")
    strategy: Literal["FirstAvailable", "RoundRobin"] = Field(
        default="FirstAvailable",
        description="Output routing strategy applied to this connection",
    )
