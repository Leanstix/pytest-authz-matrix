from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pytest_authz_matrix.adapters.fastapi import FastAPIAdapter
from pytest_authz_matrix.exceptions import AuthzExecutionError


def test_executes_json_requests_with_httpx_semantics() -> None:
    app = FastAPI()

    @app.patch("/bookings/{booking_id}")
    def update_booking(booking_id: int, payload: dict[str, str]):
        return {"id": booking_id, **payload}

    client = TestClient(app)
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
    app = FastAPI()
    client = TestClient(app)

    try:
        FastAPIAdapter().execute(
            client,
            method="POST",
            path="/",
            data={"x": 1},
            format="xml",
            headers={},
        )
    except AuthzExecutionError as exc:
        assert "request format 'xml'" in str(exc)
    else:
        raise AssertionError("unsupported FastAPI request format should fail")
