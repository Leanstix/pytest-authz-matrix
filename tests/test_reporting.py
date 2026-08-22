from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

import pytest_authz_matrix.reporting as reporting_module
from pytest_authz_matrix.config import load_config
from pytest_authz_matrix.discovery import DiscoveredRoute, DiscoveryResult
from pytest_authz_matrix.models import CaseSpec
from pytest_authz_matrix.reporting import AuthorizationReporter


def test_route_exclusions_are_method_specific_and_auditable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    config_path = tmp_path / "authz-matrix.yml"
    config_path.write_text(
        """
version: 1
actors:
  member: member_client
coverage:
  exclude:
    - route_name: api-root
      reason: Generated router index
    - method: GET
      route_name: health-check
      reason: Public liveness read
contracts:
  booking.list:
    method: GET
    path: /bookings/
    route_name: booking-list
    matrix:
      member: allow
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    discovery = DiscoveryResult(
        True,
        routes=(
            DiscoveredRoute("GET", "api-root", ""),
            DiscoveredRoute("GET", "booking-list", "bookings/"),
            DiscoveredRoute("GET", "health-check", "health/"),
            DiscoveredRoute("POST", "health-check", "health/"),
        ),
    )
    monkeypatch.setattr(reporting_module, "discover_drf_routes", lambda: discovery)

    contract = config.contracts["booking.list"]
    spec = CaseSpec(
        contract=contract,
        actor=config.actors["member"],
        resource=None,
        relationship=None,
        expectation=contract.matrix["member"][None],
    )
    reporter = AuthorizationReporter()
    reporter.record_execution(spec)
    reporter.record_case(spec, passed=True, actual_status=200)
    reporter.finalize(config)

    assert reporter.route_coverage == 50.0
    assert {route.id for route in reporter.covered} == {"GET booking-list"}
    assert {route.id for route in reporter.uncovered} == {"POST health-check"}
    assert {route.id for route in reporter.excluded} == {
        "GET api-root",
        "GET health-check",
    }

    report = reporter.as_dict()["drf_routes"]
    assert report["total"] == 4
    assert report["eligible"] == 2
    assert report["covered"] == 1
    assert report["excluded"] == [
        {
            "id": "GET api-root",
            "method": "GET",
            "name": "api-root",
            "pattern": "",
            "reasons": ["Generated router index"],
        },
        {
            "id": "GET health-check",
            "method": "GET",
            "name": "health-check",
            "pattern": "health/",
            "reasons": ["Public liveness read"],
        },
    ]
    assert "  excluded: GET api-root (Generated router index)" in reporter.terminal_lines()
    assert "  excluded: GET health-check (Public liveness read)" in reporter.terminal_lines()
