from __future__ import annotations

import pytest


def test_drf_coverage_with_database_and_session_authentication(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        """
import django
import pytest
from django.conf import settings

settings.configure(
    SECRET_KEY="test-only",
    ROOT_URLCONF="booking_urls",
    ALLOWED_HOSTS=["testserver"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    INSTALLED_APPS=[
        "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions"
    ],
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
    ],
    LOGIN_URL="/login/",
)
django.setup()


@pytest.fixture(scope="session")
def database():
    from django.core.management import call_command
    call_command("migrate", verbosity=0)
"""
    )
    pytester.makepyfile(
        booking_urls="""
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.urls import path
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

@login_required
def dashboard(request):
    return HttpResponse(request.user.username)

class AccountDetail(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        account = get_object_or_404(get_user_model(), pk=pk, pk__in=[request.user.pk])
        return Response({"username": account.username})

urlpatterns = [
    path("dashboard/", dashboard),
    path("accounts/<int:pk>/", AccountDetail.as_view()),
]
"""
    )
    pytester.makepyfile(
        """
import os

from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.permissions import AllowAny

from booking_urls import AccountDetail
from pytest_authz_matrix.django import Permission, check_django


def test_account_authorization(database):
    users = get_user_model().objects
    owner = users.create_user(username="owner")
    other = users.create_user(username="other")
    owner_client, other_client = Client(), Client()
    owner_client.force_login(owner)
    other_client.force_login(other)
    key = ("GET", "/accounts/<int:pk>/")
    concrete = f"/accounts/{owner.pk}/"

    result = check_django(
        permissions={
            key: {
                "anonymous": Permission.AUTHENTICATED,
                "owner": 200,
                "other": Permission.CONCEALED,
            },
        },
        actors={"owner": owner_client, "other": other_client},
        paths={key: concrete},
        min_coverage=100,
    )
    assert result.checked == 4
    assert result.coverage_percent == 100
    assert owner_client.get(concrete).json() == {"username": "owner"}

    if os.getenv("AUTHZ_TEST_REMOVE_PERMISSION"):
        AccountDetail.permission_classes = [AllowAny]
    inferred = check_django(paths={key: concrete}, min_coverage=100)
    assert inferred.checked == 2
"""
    )
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=1)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("AUTHZ_TEST_REMOVE_PERMISSION", "1")
        failed = pytester.runpytest_subprocess("-q")
    failed.assert_outcomes(failed=1)
    assert failed.ret == pytest.ExitCode.TESTS_FAILED
    failed.stdout.fnmatch_lines(
        [
            "*Django authorization coverage: 1/2 routes (50.0%), 1 actor checks*",
            "*GET /accounts/<int:pk>/ (no known permission expectation)*",
            "*Required authorization route coverage: 100%*",
        ]
    )


def test_fastapi_lifespan_and_permission_regression(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.security import HTTPBearer

from pytest_authz_matrix.fastapi import check_fastapi


@asynccontextmanager
async def lifespan(app):
    app.state.ready = True
    yield
    app.state.ready = False


def test_api_authorization():
    app = FastAPI(lifespan=lifespan)
    secure = APIRouter(dependencies=[Depends(HTTPBearer())])
    secure.add_api_route("/account", lambda: {"ok": True}, methods=["GET"])
    app.include_router(secure, prefix="/api")

    router = APIRouter()
    if not os.getenv("AUTHZ_TEST_REMOVE_PERMISSION"):
        router = APIRouter(dependencies=[Depends(HTTPBearer())])

    @router.get("/records/{record_id}")
    def record(record_id: int):
        assert app.state.ready
        return {"id": record_id}

    app.include_router(router, prefix="/api")
    result = check_fastapi(
        app,
        paths={("GET", "/api/records/{record_id}"): "/api/records/42"},
        min_coverage=100,
    )
    assert result.checked == 2
    assert app.state.ready is False
"""
    )
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=1)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("AUTHZ_TEST_REMOVE_PERMISSION", "1")
        failed = pytester.runpytest_subprocess("-q")
    failed.assert_outcomes(failed=1)
    assert failed.ret == pytest.ExitCode.TESTS_FAILED
    failed.stdout.fnmatch_lines(
        [
            "*FastAPI authorization coverage: 1/2 routes (50.0%), 1 actor checks*",
            "*GET /api/records/{record_id} (no known permission expectation)*",
            "*Required authorization route coverage: 100%*",
        ]
    )
