from __future__ import annotations

from typing import Any

from pytest_authz_matrix.discovery import DiscoveredRoute, DiscoveryResult
from pytest_authz_matrix.models import ActorSpec, ContractSpec, Expectation, MatrixConfig
from pytest_authz_matrix.reporting import AuthorizationReporter


class FakeFastAPIAdapter:
    name = "fastapi"
    display_name = "FastAPI"

    def supports_client(self, client: Any) -> bool:
        return True

    def supports_app(self, app: Any) -> bool:
        return True

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
        return None

    def discover_routes(self, app: Any | None) -> DiscoveryResult:
        return DiscoveryResult(
            True,
            framework="fastapi",
            routes=(
                DiscoveredRoute("GET", "booking-detail", "/bookings/{booking_id}"),
                DiscoveredRoute("GET", "health", "/health"),
            ),
        )


def make_config() -> MatrixConfig:
    expectation = Expectation("allow", (200,))
    contract = ContractSpec(
        name="booking.retrieve",
        method="GET",
        path="/bookings/{resource}",
        route_name="booking-detail",
        matrix={"owner": {None: expectation}},
    )
    return MatrixConfig(
        version=1,
        actors={"owner": ActorSpec("owner", "client")},
        resources={},
        outcomes={},
        contracts={contract.name: contract},
    )


def test_report_schema_is_framework_neutral() -> None:
    reporter = AuthorizationReporter()
    reporter.register_framework(FakeFastAPIAdapter(), object())
    reporter.finalize(make_config())
    payload = reporter.as_dict()
    assert payload["schema_version"] == 2
    assert "drf_routes" not in payload
    assert payload["route_coverage"]["framework"] == "fastapi"
    assert payload["route_coverage"]["coverage_percent"] == 50.0
    assert "FastAPI route coverage: 1/2 (50.0%)" in reporter.terminal_lines()
