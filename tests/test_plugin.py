from __future__ import annotations

import json

import pytest


def make_project(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        """
import pytest

class Response:
    def __init__(self, status_code):
        self.status_code = status_code

class Client:
    def __init__(self, actor):
        self.actor = actor

    def get(self, path, **kwargs):
        booking_id = int(path.strip('/').split('/')[-1])
        if self.actor == 'owner' and booking_id == 1:
            return Response(200)
        return Response(404)

@pytest.fixture
def owner_client():
    return Client('owner')

@pytest.fixture
def outsider_client():
    return Client('outsider')

@pytest.fixture
def booking_matrix():
    return {'owned': {'pk': 1}, 'foreign': {'pk': 2}}
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  owner: owner_client
  outsider: outsider_client
resources:
  booking:
    fixture: booking_matrix
contracts:
  booking.retrieve:
    method: GET
    path: /bookings/{resource}/
    resource: booking
    matrix:
      owner:
        owned: allow
        foreign: conceal
      outsider:
        owned: conceal
        foreign: conceal
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest

@pytest.mark.authz_contract('booking.retrieve')
def test_booking_authorization(authz_case):
    authz_case.run()
"""
    )


def test_expands_and_runs_every_matrix_case(pytester: pytest.Pytester) -> None:
    make_project(pytester)

    result = pytester.runpytest("-q", "--authz-report")

    result.assert_outcomes(passed=4)
    result.stdout.fnmatch_lines(
        [
            "*authorization matrix*",
            "authorization cases: 4/4 asserted, 4 passed, 0 failed",
            "authorization contracts: 1/1 exercised",
        ]
    )


def test_writes_json_report(pytester: pytest.Pytester) -> None:
    make_project(pytester)

    result = pytester.runpytest("-q", "--authz-report-json=report.json")

    result.assert_outcomes(passed=4)
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["configured_cases"] == 4
    assert report["summary"]["passed_cases"] == 4
    assert len(report["cases"]) == 4


def test_requires_contract_marker(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_authz(authz_case): pass")

    result = pytester.runpytest("-q")

    assert result.ret != 0
    result.stdout.fnmatch_lines(
        ["*Tests using authz_case must declare*@pytest.mark.authz_contract*"]
    )


def test_discovers_uncovered_drf_routes_and_enforces_threshold(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

class BookingList(APIView):
    def get(self, request):
        return Response({'results': []})

class HealthCheck(APIView):
    def get(self, request):
        return Response({'ok': True})

urlpatterns = [
    path('bookings/', BookingList.as_view(), name='booking-list'),
    path('health/', HealthCheck.as_view(), name='health-check'),
]
"""
    )
    pytester.makeconftest(
        """
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='test',
        ROOT_URLCONF='api_urls',
        ALLOWED_HOSTS=['testserver'],
        REST_FRAMEWORK={'UNAUTHENTICATED_USER': None},
    )

import django
django.setup()

import pytest
from rest_framework.test import APIClient

@pytest.fixture
def owner_client():
    return APIClient()
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  owner: owner_client
contracts:
  booking.list:
    method: GET
    path: /bookings/
    route_name: booking-list
    matrix:
      owner: allow
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest

@pytest.mark.authz_contract('booking.list')
def test_booking_list_authorization(authz_case):
    authz_case.run()
"""
    )

    result = pytester.runpytest_subprocess("-q", "--authz-report", "--authz-fail-under=60")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        [
            "DRF route coverage: 1/2 (50.0%)",
            "  missing: GET health-check",
        ]
    )
