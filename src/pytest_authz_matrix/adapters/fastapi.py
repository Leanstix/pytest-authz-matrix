"""FastAPI TestClient request execution."""

from __future__ import annotations

from typing import Any

from pytest_authz_matrix.discovery import DiscoveryResult
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
        kwargs: dict[str, Any] = {}
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
        return DiscoveryResult(
            False,
            framework=self.name,
            reason="FastAPI route discovery is not enabled in this adapter version",
        )
