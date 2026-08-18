"""Framework-neutral API route inventory and contract coverage matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pytest_authz_matrix.models import ContractSpec, MatrixConfig

_TEMPLATE_PARAMETER = re.compile(r"\{[^{}]+\}")
_DJANGO_CONVERTER = re.compile(r"<(?:(?:[^:<>]+):)?([^<>]+)>")
_REGEX_GROUP = re.compile(r"\(\?P<[^>]+>[^)]+\)")


@dataclass(frozen=True, slots=True)
class DiscoveredRoute:
    """One HTTP method exposed by a framework route."""

    method: str
    name: str | None
    pattern: str

    @property
    def id(self) -> str:
        label = self.name or self.pattern
        return f"{self.method} {label}"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """The outcome of optional framework route discovery."""

    available: bool
    framework: str | None = None
    routes: tuple[DiscoveredRoute, ...] = ()
    reason: str | None = None


def discover_drf_routes() -> DiscoveryResult:
    """Compatibility entry point for the existing DRF route reporter."""

    from pytest_authz_matrix.adapters.django import DjangoRESTFrameworkAdapter

    return DjangoRESTFrameworkAdapter().discover_routes(None)


def covered_routes(
    discovery: DiscoveryResult, config: MatrixConfig
) -> tuple[set[DiscoveredRoute], set[DiscoveredRoute]]:
    """Split discovered routes into covered and uncovered method-route pairs."""

    if not discovery.available:
        return set(), set()
    covered: set[DiscoveredRoute] = set()
    uncovered: set[DiscoveredRoute] = set()
    contracts = tuple(config.contracts.values())
    for route in discovery.routes:
        target = covered if any(_matches(route, contract) for contract in contracts) else uncovered
        target.add(route)
    return covered, uncovered


def normalize_path(path: str) -> str:
    """Normalize OpenAPI/FastAPI, Django converter, and regex path parameters."""

    normalized = _TEMPLATE_PARAMETER.sub("{}", path)
    normalized = _REGEX_GROUP.sub("{}", normalized)
    normalized = _DJANGO_CONVERTER.sub("{}", normalized)
    normalized = normalized.replace("^", "").replace("$", "")
    normalized = normalized.replace("\\Z", "")
    normalized = re.sub(r"/+$", "", normalized.lstrip("/"))
    return normalized


def _matches(route: DiscoveredRoute, contract: ContractSpec) -> bool:
    if route.method != contract.method:
        return False
    if contract.route_name and route.name:
        return contract.route_name in {route.name, route.name.rsplit(":", 1)[-1]}
    return normalize_path(route.pattern) == normalize_path(contract.path)
