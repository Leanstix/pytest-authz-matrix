from __future__ import annotations

import json

import pytest


def test_xdist_workers_merge_into_one_strict_authorization_report(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView


class BookingList(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({'results': []})


urlpatterns = [path('bookings/', BookingList.as_view(), name='booking-list')]
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
def member_client():
    return APIClient()
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  member_1: member_client
  member_2: member_client
  member_3: member_client
  member_4: member_client
  member_5: member_client
  member_6: member_client
  member_7: member_client
  member_8: member_client
contracts:
  booking.list:
    method: GET
    path: /bookings/
    route_name: booking-list
    matrix:
      member_1: allow
      member_2: allow
      member_3: allow
      member_4: allow
      member_5: allow
      member_6: allow
      member_7: allow
      member_8: allow
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
        "-n=2",
        "--dist=load",
        "--authz-report",
        "--authz-report-json=report.json",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=8)
    result.stdout.fnmatch_lines(
        [
            "authorization cases: 8/8 complete, 8 executed, 8 asserted, 8 passed, 0 failed",
            "authorization contracts: 1/1 complete",
            "DRF route coverage: 1/1 (100.0%)",
        ]
    )
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert report["summary"] == {
        "configured_cases": 8,
        "executed_cases": 8,
        "asserted_cases": 8,
        "completed_cases": 8,
        "passed_cases": 8,
        "failed_cases": 0,
        "configured_contracts": 1,
        "exercised_contracts": 1,
        "complete_contracts": 1,
    }
    assert report["execution"]["complete"] is True
    assert len(report["cases"]) == 8
    assert report["drf_routes"]["coverage_percent"] == 100.0
