"""Internal protocol implemented by framework-specific runtime adapters."""

from __future__ import annotations

from typing import Any, Protocol

from pytest_authz_matrix.discovery import DiscoveryResult


class FrameworkAdapter(Protocol):
    """Bridge authorization cases to one HTTP framework's test client."""

    name: str
    display_name: str

    def supports_client(self, client: Any) -> bool:
        """Return whether this adapter recognizes ``client``."""

    def supports_app(self, app: Any) -> bool:
        """Return whether this adapter recognizes ``app``."""

    def extract_app(self, client: Any) -> Any | None:
        """Return the application associated with ``client`` when available."""

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
        """Execute one HTTP request using framework-appropriate semantics."""

    def discover_routes(self, app: Any | None) -> DiscoveryResult:
        """Return the framework route inventory used for coverage reporting."""
