"""Best-effort discovery of Django REST Framework URL routes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pytest_authz_matrix.models import ContractSpec, MatrixConfig

_TEMPLATE_PARAMETER = re.compile(r"\{[^{}]+\}")
_DJANGO_CONVERTER = re.compile(r"<(?:(?:[^:<>]+):)?([^<>]+)>")
_REGEX_GROUP = re.compile(r"\(\?P<[^>]+>[^)]+\)")


@dataclass(frozen=True, slots=True)
class DiscoveredRoute:
    """One HTTP method exposed by a DRF URL pattern."""

    method: str
    name: str | None
    pattern: str

    @property
    def id(self) -> str:
        label = self.name or self.pattern
        return f"{self.method} {label}"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """The outcome of optional DRF route discovery."""

    available: bool
    routes: tuple[DiscoveredRoute, ...] = ()
    reason: str | None = None


def discover_drf_routes() -> DiscoveryResult:
    """Walk Django's root URL resolver and return DRF methods only."""

    try:
        from django.urls import URLPattern, URLResolver, get_resolver
        from rest_framework.views import APIView
    except ImportError:
        return DiscoveryResult(False, reason="Django REST Framework is not installed")

    try:
        root = get_resolver()
    except Exception as exc:  # Django may be installed but not configured in this test run.
        return DiscoveryResult(False, reason=f"Django URL resolver unavailable: {exc}")

    routes: set[DiscoveredRoute] = set()

    def walk(patterns: list[Any], prefix: str = "", namespace: str = "") -> None:
        for item in patterns:
            current_pattern = prefix + str(item.pattern)
            if isinstance(item, URLResolver):
                child_namespace = namespace
                if item.namespace:
                    child_namespace = f"{namespace}:{item.namespace}" if namespace else item.namespace
                walk(list(item.url_patterns), current_pattern, child_namespace)
                continue
            if not isinstance(item, URLPattern):
                continue

            callback = item.callback
            view_class = getattr(callback, "cls", None)
            if view_class is None:
                view_class = getattr(callback, "view_class", None)
            if not isinstance(view_class, type) or not issubclass(view_class, APIView):
                continue

            route_name = item.name
            if route_name and namespace:
                route_name = f"{namespace}:{route_name}"
            for method in _view_methods(callback, view_class):
                routes.add(
                    DiscoveredRoute(
                        method=method,
                        name=route_name,
                        pattern=current_pattern,
                    )
                )

    try:
        walk(list(root.url_patterns))
    except Exception as exc:
        return DiscoveryResult(False, reason=f"DRF route discovery failed: {exc}")
    return DiscoveryResult(True, routes=tuple(sorted(routes, key=lambda route: route.id)))


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
    """Normalize OpenAPI-like, Django converter, and regex path parameters."""

    normalized = _TEMPLATE_PARAMETER.sub("{}", path)
    normalized = _DJANGO_CONVERTER.sub("{}", normalized)
    normalized = _REGEX_GROUP.sub("{}", normalized)
    normalized = normalized.replace("^", "").replace("$", "")
    normalized = normalized.replace("\\Z", "")
    normalized = re.sub(r"/+$", "", normalized.lstrip("/"))
    return normalized


def _view_methods(callback: Any, view_class: type[Any]) -> tuple[str, ...]:
    actions = getattr(callback, "actions", None)
    if actions:
        methods = actions.keys()
    else:
        methods = (
            method
            for method in getattr(view_class, "http_method_names", ())
            if callable(getattr(view_class, method, None))
        )
    return tuple(
        sorted({str(method).upper() for method in methods if str(method).upper() not in {"HEAD", "OPTIONS"}})
    )


def _matches(route: DiscoveredRoute, contract: ContractSpec) -> bool:
    if route.method != contract.method:
        return False
    if contract.route_name and route.name:
        return contract.route_name in {route.name, route.name.rsplit(":", 1)[-1]}
    return normalize_path(route.pattern) == normalize_path(contract.path)

