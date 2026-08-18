"""Django REST Framework request execution and route discovery."""

from __future__ import annotations

from typing import Any

from pytest_authz_matrix.adapters.generic import GenericAdapter
from pytest_authz_matrix.discovery import DiscoveredRoute, DiscoveryResult


class DjangoRESTFrameworkAdapter(GenericAdapter):
    """Adapter for Django and Django REST Framework test clients."""

    name = "django-rest-framework"
    display_name = "DRF"

    def supports_client(self, client: Any) -> bool:
        modules = {cls.__module__ for cls in type(client).__mro__}
        return any(
            module.startswith("rest_framework.") or module.startswith("django.test")
            for module in modules
        )

    def discover_routes(self, app: Any | None) -> DiscoveryResult:
        """Walk Django's root URL resolver and return DRF methods only."""

        try:
            from django.conf import settings  # type: ignore[import-untyped]
            from django.urls import (  # type: ignore[import-untyped]
                URLPattern,
                URLResolver,
                get_resolver,
            )
        except ImportError:
            return DiscoveryResult(
                False,
                framework=self.name,
                reason="Django is not installed",
            )
        if not settings.configured:
            return DiscoveryResult(
                False,
                framework=self.name,
                reason="Django settings are not configured",
            )
        try:
            from rest_framework.views import APIView  # type: ignore[import-untyped]
        except Exception as exc:
            return DiscoveryResult(
                False,
                framework=self.name,
                reason=f"Django REST Framework is unavailable: {exc}",
            )

        try:
            root = get_resolver()
        except Exception as exc:
            return DiscoveryResult(
                False,
                framework=self.name,
                reason=f"Django URL resolver unavailable: {exc}",
            )

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
            return DiscoveryResult(
                False,
                framework=self.name,
                reason=f"DRF route discovery failed: {exc}",
            )
        return DiscoveryResult(
            True,
            framework=self.name,
            routes=tuple(sorted(routes, key=lambda route: route.id)),
        )


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
    allowed = {
        str(method).upper() for method in methods if str(method).upper() not in {"HEAD", "OPTIONS"}
    }
    return tuple(sorted(allowed))
