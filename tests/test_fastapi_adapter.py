from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import RedirectResponse
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



def test_discovers_nested_routers_and_mounted_apps() -> None:
    app = FastAPI(openapi_url=None)
    router = APIRouter()
    nested = APIRouter()
    child = FastAPI()

    @nested.api_route(
        "/{identifier:int}",
        methods=["HEAD", "OPTIONS"],
        name="probe",
        include_in_schema=False,
    )
    def probe(identifier: int):
        return {"id": identifier}

    router.include_router(nested, prefix="/items")
    app.include_router(router, prefix="/v1")
    child.include_router(router)
    app.mount("/internal", child, name="private")

    result = FastAPIAdapter().discover_routes(app)

    assert result.available
    assert {(route.method, route.name, route.pattern) for route in result.routes} == {
        ("HEAD", "probe", "/v1/items/{identifier:int}"),
        ("OPTIONS", "probe", "/v1/items/{identifier:int}"),
        ("HEAD", "private:probe", "/internal/items/{identifier:int}"),
        ("OPTIONS", "private:probe", "/internal/items/{identifier:int}"),
    }



def test_checks_redirect_status_at_the_contract_endpoint() -> None:
    app = build_app()

    @app.get("/private")
    def private():
        return RedirectResponse("/health", status_code=302)

    client = TestClient(app, follow_redirects=True)
    response = FastAPIAdapter().execute(
        client,
        method="GET",
        path="/private",
        data=None,
        format="json",
        headers={},
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/health"


@pytest.mark.parametrize("request_format", ["form", "data", None])
def test_sends_form_payload_with_actor_and_request_headers(request_format: str | None) -> None:
    app = FastAPI()

    @app.post("/form")
    async def form(request: Request):
        return {
            "body": (await request.body()).decode(),
            "type": request.headers["content-type"],
            "actor": request.headers["x-actor"],
            "request": request.headers["x-request"],
        }

    response = FastAPIAdapter().execute(
        TestClient(app, headers={"X-Actor": "owner"}),
        method="POST",
        path="/form",
        data={"label": ["a b", "c"]},
        format=request_format,
        headers={"X-Request": "1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "body": "label=a+b&label=c",
        "type": "application/x-www-form-urlencoded",
        "actor": "owner",
        "request": "1",
    }
