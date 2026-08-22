"""Best-effort discovery of Django REST Framework URL routes."""

from __future__ import annotations

import re
from collections.abc import Collection
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
        from django.conf import settings  # type: ignore[import-untyped]
        from django.urls import (  # type: ignore[import-untyped]
            URLPattern,
            URLResolver,
            get_resolver,
        )
    except ImportError:
        return DiscoveryResult(False, reason="Django REST Framework is not installed")
    if not settings.configured:
        return DiscoveryResult(False, reason="Django settings are not configured")
    try:
        from rest_framework.views import APIView  # type: ignore[import-untyped]
    except Exception as exc:
        return DiscoveryResult(False, reason=f"Django REST Framework is unavailable: {exc}")

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
                    child_namespace = (
                        f"{namespace}:{item.namespace}" if namespace else item.namespace
                    )
                walk(list(item.url_patterns), current_pattern, child_namespace)
                continue
            if not isinstance(item, URLPattern):
                continue
            if _is_format_suffix_pattern(item):
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
    discovery: DiscoveryResult,
    config: MatrixConfig,
    *,
    contract_names: Collection[str] | None = None,
) -> tuple[set[DiscoveredRoute], set[DiscoveredRoute]]:
    """Split routes by contracts, optionally restricting coverage to completed contracts."""

    if not discovery.available:
        return set(), set()
    covered: set[DiscoveredRoute] = set()
    uncovered: set[DiscoveredRoute] = set()
    contracts = tuple(
        contract
        for name, contract in config.contracts.items()
        if contract_names is None or name in contract_names
    )
    for route in discovery.routes:
        target = covered if any(_matches(route, contract) for contract in contracts) else uncovered
        target.add(route)
    return covered, uncovered


def normalize_path(path: str) -> str:
    """Normalize OpenAPI-like, Django converter, and regex path parameters."""

    normalized = _TEMPLATE_PARAMETER.sub("{}", path)
    normalized = _REGEX_GROUP.sub("{}", normalized)
    normalized = _DJANGO_CONVERTER.sub("{}", normalized)
    normalized = normalized.replace("^", "").replace("$", "")
    normalized = normalized.replace("\\Z", "")
    normalized = re.sub(r"/+$", "", normalized.lstrip("/"))
    return normalized


def _view_methods(callback: Any, view_class: type[Any]) -> tuple[str, ...]:
    declared = tuple(str(method).lower() for method in getattr(view_class, "http_method_names", ()))
    enabled = {
        method.upper() for method in declared if method.upper() not in {"HEAD", "OPTIONS"}
    }
    actions = getattr(callback, "actions", None)
    if actions:
        methods = (method for method in actions if str(method).upper() in enabled)
    else:
        methods = (
            method
            for method in declared
            if method.upper() in enabled
            if callable(getattr(view_class, method, None))
        )
    allowed = {str(method).upper() for method in methods}
    return tuple(sorted(allowed))


def _is_format_suffix_pattern(pattern: Any) -> bool:
    """Return whether DRF added this as a content-negotiation URL alias."""

    rendered = str(pattern.pattern)
    return "<drf_format_suffix:format>" in rendered or r"\.(?P<format>" in rendered


def _matches(route: DiscoveredRoute, contract: ContractSpec) -> bool:
    if route.method != contract.method:
        return False
    if contract.route_name and route.name:
        name_matches = contract.route_name in {route.name, route.name.rsplit(":", 1)[-1]}
        return name_matches and normalize_path(route.pattern) == normalize_path(contract.path)
    return normalize_path(route.pattern) == normalize_path(contract.path)
