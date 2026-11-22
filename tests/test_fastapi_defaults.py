from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from fastapi.testclient import TestClient

from pytest_authz_matrix.exceptions import AuthzConfigurationError
from pytest_authz_matrix.fastapi import Permission, check_fastapi


def test_infers_required_security_in_nested_routers_and_mounts() -> None:
    app = FastAPI(openapi_url=None)
    router = APIRouter()
    bearer = HTTPBearer()

    def authorize(credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]):
        return credentials

    @router.get("/secret", dependencies=[Depends(authorize)], include_in_schema=False)
    def secret():
        raise AssertionError("Anonymous request reached a protected endpoint")

    @router.get("/records/{record_id}", dependencies=[Depends(bearer)])
    def record(record_id: int):
        return {"id": record_id}

    @router.get("/optional", dependencies=[Depends(HTTPBearer(auto_error=False))])
    def optional():
        raise AssertionError("Unknown permissions must not be assumed public")

    child = FastAPI()
    child.include_router(router, prefix="/v1")
    app.mount("/admin", child)
    result = check_fastapi(app)

    assert result.checked == 1
    assert result.unclassified == (("GET", "/admin/v1/optional"),)
    assert result.needs_path == (("GET", "/admin/v1/records/{record_id}"),)
    result = check_fastapi(
        app, paths={("GET", "/admin/v1/records/{record_id}"): "/admin/v1/records/42"}
    )
    assert result.checked == 2
    assert result.needs_path == ()


def test_detects_when_an_inferred_authentication_gate_accepts_anonymous() -> None:
    app = FastAPI()
    bearer = HTTPBearer()

    @app.get("/secret", dependencies=[Depends(bearer)])
    def secret():
        return {"status": "ok"}

    app.dependency_overrides[bearer] = lambda: None
    with pytest.raises(AssertionError, match=r"GET /secret \(anonymous\).*HTTP 200"):
        check_fastapi(app)


def test_custom_permissions_cover_anonymous_and_application_roles() -> None:
    app = FastAPI()
    api_key = APIKeyHeader(name="X-Role", auto_error=False)

    @app.post("/books/{book_id:int}", status_code=201)
    def publish(book_id: int, book: dict[str, str], role: Annotated[str | None, Depends(api_key)]):
        if role is None:
            raise HTTPException(404)
        if role != "editor":
            raise HTTPException(403)
        return {"id": book_id, **book}

    @app.get("/public")
    def public():
        return {"status": "ok"}

    key = ("POST", "/books/{book_id:int}")
    with (
        TestClient(app, headers={"X-Role": "editor"}) as editor,
        TestClient(app, headers={"X-Role": "viewer"}) as viewer,
    ):
        result = check_fastapi(
            app,
            permissions={
                key: {
                    "anonymous": Permission.CONCEALED,
                    "viewer": Permission.FORBIDDEN,
                    "editor": 201,
                },
                ("GET", "/public"): Permission.PUBLIC,
            },
            actors={"editor": editor, "viewer": viewer},
            paths={key: "/books/42"},
            payloads={key: {"title": "Sample"}},
        )

    assert result.checked == 4
    assert not result.unclassified
    assert not result.needs_path


def test_explicit_redirect_status_can_be_checked() -> None:
    app = FastAPI()

    @app.get("/sign-in")
    def sign_in():
        return RedirectResponse("/landing", status_code=302)

    assert check_fastapi(app, permissions={("GET", "/sign-in"): 302}).checked == 1


def test_unknown_policies_cannot_pass_without_running_checks() -> None:
    app = FastAPI()

    @app.get("/public")
    def public():
        return {"status": "ok"}

    with pytest.raises(AuthzConfigurationError, match="No FastAPI authorization checks"):
        check_fastapi(app)
    with pytest.raises(AuthzConfigurationError, match="Unknown FastAPI routes"):
        check_fastapi(app, permissions={("GET", "/missing"): Permission.PUBLIC})
    with pytest.raises(AuthzConfigurationError, match="No test client supplied"):
        check_fastapi(app, permissions={("GET", "/public"): {"editor": Permission.PUBLIC}})
    with pytest.raises(AuthzConfigurationError, match="does not match"):
        check_fastapi(
            app,
            permissions={("GET", "/public"): Permission.PUBLIC},
            paths={("GET", "/public"): "//external.test/public"},
        )


def test_executed_coverage_counts_routes_instead_of_actors() -> None:
    from pytest_authz_matrix.coverage import AuthzCoverageWarning

    app = FastAPI()

    @app.get("/status")
    def status():
        return {"ok": True}

    @app.get("/records/{record_id}", dependencies=[Depends(HTTPBearer())])
    def record(record_id: int):
        return {"id": record_id}

    @app.get("/custom")
    def custom():
        return {"ok": True}

    key = ("GET", "/status")
    with TestClient(app) as viewer:
        options = {
            "permissions": {key: {"anonymous": 200, "viewer": 200}},
            "actors": {"viewer": viewer},
        }
        with pytest.warns(AuthzCoverageWarning, match="1/3 routes"):
            result = check_fastapi(app, **options, min_coverage=100 / 3)
        with pytest.raises(AssertionError, match="Required authorization route coverage: 34%"):
            check_fastapi(app, **options, min_coverage=34)

    assert result.checked == 2
    assert result.total_routes == 3
    assert result.checked_routes == (key,)
    assert "GET /custom (no known permission expectation)" in result.summary()
    assert "GET /records/{record_id} (provide a concrete path)" in result.summary()


@pytest.mark.parametrize("minimum", [-1, 101, float("nan"), float("inf"), True])
def test_invalid_coverage_threshold_fails_before_starting_the_app(minimum: float) -> None:
    with pytest.raises(AuthzConfigurationError, match="finite percentage"):
        check_fastapi(FastAPI(), min_coverage=minimum)
