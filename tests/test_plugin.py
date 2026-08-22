from __future__ import annotations

import json

import pytest


def make_project(pytester: pytest.Pytester, test_body: str | None = None) -> None:
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
        test_body
        or """
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
            "authorization cases: 4/4 complete, 4 executed, 4 asserted, 4 passed, 0 failed",
            "authorization contracts: 1/1 complete",
        ]
    )


def test_writes_json_report(pytester: pytest.Pytester) -> None:
    make_project(pytester)

    result = pytester.runpytest("-q", "--authz-report-json=report.json")

    result.assert_outcomes(passed=4)
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["configured_cases"] == 4
    assert report["summary"]["executed_cases"] == 4
    assert report["summary"]["completed_cases"] == 4
    assert report["summary"]["passed_cases"] == 4
    assert report["summary"]["complete_contracts"] == 1
    assert report["execution"] == {
        "complete": True,
        "missing_execution": [],
        "missing_assertion": [],
        "asserted_without_execution": [],
        "incomplete_contracts": [],
    }
    assert len(report["cases"]) == 4


def test_require_complete_rejects_executed_but_unasserted_cases(
    pytester: pytest.Pytester,
) -> None:
    make_project(
        pytester,
        """
import pytest

@pytest.mark.authz_contract('booking.retrieve')
def test_booking_authorization(authz_case):
    authz_case.execute()
""",
    )

    result = pytester.runpytest("-q", "--authz-require-complete")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.assert_outcomes(passed=4)
    result.stdout.fnmatch_lines(
        [
            "authorization cases: 0/4 complete, 4 executed, 0 asserted, 0 passed, 0 failed",
            "authorization contracts: 0/1 complete",
            "  not asserted: booking.retrieve[outsider-foreign-conceal]",
            "  not asserted: booking.retrieve[outsider-owned-conceal]",
            "  not asserted: booking.retrieve[owner-foreign-conceal]",
            "  not asserted: booking.retrieve[owner-owned-allow]",
        ]
    )


def test_require_complete_rejects_assertions_without_case_execution(
    pytester: pytest.Pytester,
) -> None:
    make_project(
        pytester,
        """
import pytest

class Response:
    def __init__(self, status_code):
        self.status_code = status_code

@pytest.mark.authz_contract('booking.retrieve')
def test_booking_authorization(authz_case):
    authz_case.assert_response(Response(authz_case.spec.expectation.statuses[0]))
""",
    )

    result = pytester.runpytest("-q", "--authz-require-complete")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.assert_outcomes(passed=4)
    result.stdout.fnmatch_lines(
        [
            "authorization cases: 0/4 complete, 0 executed, 4 asserted, 4 passed, 0 failed",
            "authorization contracts: 0/1 complete",
            "  asserted without execution: booking.retrieve[outsider-foreign-conceal]",
            "  asserted without execution: booking.retrieve[outsider-owned-conceal]",
            "  asserted without execution: booking.retrieve[owner-foreign-conceal]",
            "  asserted without execution: booking.retrieve[owner-owned-allow]",
        ]
    )


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
  health.retrieve:
    method: GET
    path: /health/
    route_name: health-check
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
            "authorization cases: 1/2 complete, 1 executed, 1 asserted, 1 passed, 0 failed",
            "authorization contracts: 1/2 complete",
            "  not executed: health.retrieve[owner-endpoint-allow]",
            "DRF route coverage: 1/2 (50.0%)",
            "  missing: GET health-check",
        ]
    )


def test_reasoned_route_exclusion_passes_strict_cli_and_json_reporting(
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
coverage:
  exclude:
    - method: GET
      route_name: health-check
      reason: Public infrastructure liveness endpoint
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

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-fail-under=100",
        "--authz-report-json=report.json",
    )

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        [
            "DRF route coverage: 1/1 (100.0%)",
            "  excluded: GET health-check (Public infrastructure liveness endpoint)",
        ]
    )
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert report["drf_routes"]["total"] == 2
    assert report["drf_routes"]["eligible"] == 1
    assert report["drf_routes"]["coverage_percent"] == 100.0
    assert report["drf_routes"]["excluded"][0]["id"] == "GET health-check"
    assert report["drf_routes"]["excluded"][0]["reasons"] == [
        "Public infrastructure liveness endpoint"
    ]
