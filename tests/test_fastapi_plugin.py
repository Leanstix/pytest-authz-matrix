from __future__ import annotations

import pytest


def test_fastapi_plugin_expands_cases_and_reports_route_coverage(
    pytester: pytest.Pytester,
) -> None:
    pytester.makeconftest(
        """
import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

app = FastAPI()

@app.get('/bookings/{booking_id}', name='booking-detail')
def get_booking(booking_id: int, x_actor: str | None = Header(default=None)):
    if x_actor == 'owner' and booking_id == 1:
        return {'id': booking_id}
    raise HTTPException(status_code=404)

@pytest.fixture
def owner_client():
    return TestClient(app, headers={'X-Actor': 'owner'})

@pytest.fixture
def outsider_client():
    return TestClient(app, headers={'X-Actor': 'outsider'})

@pytest.fixture
def booking_matrix():
    return {'owned': {'id': 1}, 'foreign': {'id': 2}}
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
    lookup: id
contracts:
  booking.retrieve:
    method: GET
    path: /bookings/{resource}
    route_name: booking-detail
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

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-report",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=4)
    result.stdout.fnmatch_lines(
        [
            "*authorization matrix*",
            "authorization cases: 4/4 asserted, 4 passed, 0 failed",
            "authorization contracts: 1/1 exercised",
            "FastAPI route coverage: 1/1 (100.0%)",
        ]
    )
