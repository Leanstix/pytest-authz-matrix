from __future__ import annotations

from pytest_authz_matrix.discovery import normalize_path


def test_normalizes_supported_route_parameter_styles() -> None:
    assert normalize_path("/bookings/{resource}/") == "bookings/{}"
    assert normalize_path("bookings/<uuid:pk>/") == "bookings/{}"
    assert normalize_path(r"^bookings/(?P<pk>[^/.]+)/$") == "bookings/{}"
