"""Fallback adapter for request-like custom pytest clients."""

from __future__ import annotations

from typing import Any

from pytest_authz_matrix.discovery import DiscoveryResult
from pytest_authz_matrix.exceptions import AuthzExecutionError


class GenericAdapter:
    """Preserve the package's original method/generic client behavior."""

    name = "generic"
    display_name = "API"

    def supports_client(self, client: Any) -> bool:
        return True

    def supports_app(self, app: Any) -> bool:
        return False

    def extract_app(self, client: Any) -> Any | None:
        return None

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
            kwargs["data"] = data
            if format is not None:
                kwargs["format"] = format
        if headers:
            kwargs["headers"] = headers

        sender = getattr(client, method.lower(), None)
        if callable(sender):
            return sender(path, **kwargs)
        generic = getattr(client, "generic", None)
        if callable(generic):
            return generic(method, path, **kwargs)
        raise AuthzExecutionError(
            f"Client {type(client).__name__!r} has neither {method.lower()}() nor generic()"
        )

    def discover_routes(self, app: Any | None) -> DiscoveryResult:
        return DiscoveryResult(
            False,
            framework=self.name,
            reason="route discovery is unavailable for the generic client adapter",
        )
