from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pytest_authz_matrix.adapters.fastapi import FastAPIAdapter
from pytest_authz_matrix.exceptions import AuthzExecutionError


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/bookings/{booking_id}", name="booking-detail")
    def get_booking(booking_id: int):
        return {"id": booking_id}

    @app.patch("/bookings/{booking_id}", name="booking-update")
    def update_booking(booking_id: int, payload: dict[str, str]):
        return {"id": booking_id, **payload}

    @app.get("/health", name="health")
    def health():
        return {"ok": True}

    return app


def test_executes_json_requests_with_httpx_semantics() -> None:
    client = TestClient(build_app())
    response = FastAPIAdapter().execute(
        client,
        method="PATCH",
        path="/bookings/1",
        data={"status": "approved"},
        format="json",
        headers={"X-Test": "1"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_rejects_unknown_fastapi_request_format() -> None:
    client = TestClient(build_app())
    with pytest.raises(AuthzExecutionError, match="request format 'xml'"):
        FastAPIAdapter().execute(
            client,
            method="POST",
            path="/",
            data={"x": 1},
            format="xml",
            headers={},
        )


def test_discovers_fastapi_routes() -> None:
    result = FastAPIAdapter().discover_routes(build_app())
    assert result.available
    assert result.framework == "fastapi"
    assert {(route.method, route.name, route.pattern) for route in result.routes} == {
        ("GET", "booking-detail", "/bookings/{booking_id}"),
        ("PATCH", "booking-update", "/bookings/{booking_id}"),
        ("GET", "health", "/health"),
    }
