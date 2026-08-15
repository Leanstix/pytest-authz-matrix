"""Typed domain models used by the configuration and pytest plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_OUTCOMES: dict[str, tuple[int, ...]] = {
    "allow": (200,),
    "deny": (403,),
    "conceal": (404,),
    "unauthenticated": (401,),
}


@dataclass(frozen=True, slots=True)
class ActorSpec:
    """An authenticated (or anonymous) API client exposed by a pytest fixture."""

    name: str
    client_fixture: str


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """A mapping of relationship names to application objects."""

    name: str
    fixture: str
    lookup: str = "pk"


@dataclass(frozen=True, slots=True)
class Expectation:
    """The HTTP statuses accepted for a named authorization outcome."""

    outcome: str
    statuses: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RequestSpec:
    """Optional request data used by a contract."""

    data_fixture: str | None = None
    query_fixture: str | None = None
    format: str | None = "json"
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContractSpec:
    """An endpoint and its complete actor-to-resource access contract."""

    name: str
    method: str
    path: str
    matrix: dict[str, dict[str | None, Expectation]]
    resource: str | None = None
    route_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    request: RequestSpec = field(default_factory=RequestSpec)


@dataclass(frozen=True, slots=True)
class MatrixConfig:
    """Validated top-level authorization configuration."""

    version: int
    actors: dict[str, ActorSpec]
    resources: dict[str, ResourceSpec]
    outcomes: dict[str, tuple[int, ...]]
    contracts: dict[str, ContractSpec]


@dataclass(frozen=True, slots=True)
class CaseSpec:
    """One generated actor/resource authorization test."""

    contract: ContractSpec
    actor: ActorSpec
    resource: ResourceSpec | None
    relationship: str | None
    expectation: Expectation

    @property
    def id(self) -> str:
        relationship = self.relationship or "endpoint"
        return f"{self.contract.name}[{self.actor.name}-{relationship}-{self.expectation.outcome}]"

