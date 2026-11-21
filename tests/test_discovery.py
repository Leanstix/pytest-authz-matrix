from __future__ import annotations

from pytest_authz_matrix.discovery import (
    DiscoveredRoute,
    DiscoveryResult,
    covered_routes,
    normalize_path,
)
from pytest_authz_matrix.models import ContractSpec, MatrixConfig


def test_normalizes_supported_route_parameter_styles() -> None:
    assert normalize_path("/bookings/{resource}/") == "bookings/{}"
    assert normalize_path("/bookings/{booking_id:path}") == "bookings/{}"
    assert normalize_path("bookings/<uuid:pk>/") == "bookings/{}"
    assert normalize_path(r"^bookings/(?P<pk>[^/.]+)/$") == "bookings/{}"



def test_fastapi_coverage_preserves_trailing_slashes_and_ignores_query() -> None:
    matching = DiscoveredRoute("GET", "booking-detail", "/bookings/{id:int}/")
    missing = DiscoveredRoute("GET", "booking-detail", "/bookings/{id:int}")
    discovery = DiscoveryResult(True, framework="fastapi", routes=(matching, missing))
    contract = ContractSpec(
        name="bookings",
        method="GET",
        path="/bookings/{resource}/?expanded=true",
        route_name="booking-detail",
        matrix={},
    )
    config = MatrixConfig(version=1, actors={}, resources={}, outcomes={}, contracts={
        contract.name: contract,
    })

    assert covered_routes(discovery, config) == ({matching}, {missing})
