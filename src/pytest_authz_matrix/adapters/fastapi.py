"""FastAPI TestClient request execution and route discovery."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from pytest_authz_matrix.discovery import DiscoveredRoute, DiscoveryResult
from pytest_authz_matrix.exceptions import AuthzExecutionError


class FastAPIAdapter:
    """Adapter for FastAPI applications exercised through Starlette TestClient."""

    name = "fastapi"
    display_name = "FastAPI"

    def supports_client(self, client: Any) -> bool:
        return any(
            cls.__module__ == "starlette.testclient" and cls.__name__ == "TestClient"
            for cls in type(client).__mro__
        )

    def supports_app(self, app: Any) -> bool:
        return any(
            cls.__module__ == "fastapi.applications" and cls.__name__ == "FastAPI"
            for cls in type(app).__mro__
        )

    def extract_app(self, client: Any) -> Any | None:
        app = getattr(client, "app", None)
        return app if app is not None and self.supports_app(app) else None

    def execute(
        self,
        client: Any,
        *,
        method: str,
        path: str,
        data: Any | None,
        format: str | None,
        headers: dict[str, str],
    ) -> Any:
        # Assert the response from the contract endpoint, including any redirect.
        kwargs: dict[str, Any] = {"follow_redirects": False}
        if data is not None:
            if format == "json":
                kwargs["json"] = data
            elif format in {None, "form", "data"}:
                kwargs["data"] = data
            else:
                raise AuthzExecutionError(
                    f"FastAPI adapter does not support request format {format!r}; "
                    "use 'json', 'form', 'data', or null"
                )
        if headers:
            kwargs["headers"] = headers
        return client.request(method, path, **kwargs)

    def discover_routes(self, app: Any | None) -> DiscoveryResult:
        if app is None:
            return DiscoveryResult(
                False,
                framework=self.name,
                reason="FastAPI application is unavailable from the configured test client",
            )
        if not self.supports_app(app):
            return DiscoveryResult(
                False,
                framework=self.name,
                reason=f"object {type(app).__name__!r} is not a FastAPI application",
            )
        try:
            routes = {route for route, _ in iter_fastapi_routes(app)}
        except ImportError:
            return DiscoveryResult(
                False,
                framework=self.name,
                reason="FastAPI is not installed",
            )

        return DiscoveryResult(
            True,
            framework=self.name,
            routes=tuple(sorted(routes, key=lambda route: (route.id, route.pattern))),
        )


def iter_fastapi_routes(app: Any) -> Iterator[tuple[DiscoveredRoute, Any]]:
    """Yield effective HTTP routes with their dependency metadata."""
    from fastapi import routing
    from starlette.routing import Mount

    def walk(
        registered: Sequence[Any], prefix: str = "", namespace: str = ""
    ) -> Iterator[tuple[DiscoveredRoute, Any]]:
        for original, effective in _route_contexts(routing, registered):
            if isinstance(original, Mount):
                mount = getattr(effective, "starlette_route", None) or effective
                yield from walk(
                    original.routes,
                    prefix + mount.path,
                    namespace + (f"{original.name}:" if original.name else ""),
                )
            elif isinstance(original, routing.APIRoute):
                for method in sorted(effective.methods or ()):
                    route = DiscoveredRoute(
                        method=method.upper(),
                        name=namespace + effective.name,
                        pattern=prefix + effective.path,
                    )
                    yield route, effective.dependant

    yield from walk(app.routes)


def _route_contexts(
    routing: Any, routes: Sequence[Any]
) -> Iterator[tuple[Any, Any]]:
    """Resolve effective paths without relying on the OpenAPI schema."""
    iter_contexts = getattr(routing, "iter_route_contexts", None)
    if iter_contexts is not None:
        for context in iter_contexts(routes):
            yield context.original_route, context
        return

    for route in routes:
        # Early lazy router versions predate the public context iterator.
        included = getattr(route, "effective_route_contexts", None)
        if included is None:
            yield route, route
        else:
            for context in included():
                yield context.original_route, context
