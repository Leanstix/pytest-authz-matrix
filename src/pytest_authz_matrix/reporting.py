"""Collect authorization results and render terminal/JSON coverage reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pytest_authz_matrix.discovery import (
    DiscoveredRoute,
    DiscoveryResult,
    covered_routes,
    discover_drf_routes,
)
from pytest_authz_matrix.models import CaseSpec, MatrixConfig


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Last assertion observed for a generated case."""

    case_id: str
    contract: str
    passed: bool
    actual_status: int | None
    expected_statuses: tuple[int, ...]


class AuthorizationReporter:
    """Session-scoped result and route coverage collector."""

    def __init__(self) -> None:
        self.results: dict[str, CaseResult] = {}
        self.config: MatrixConfig | None = None
        self.discovery = DiscoveryResult(False, reason="report has not been finalized")
        self.covered: set[DiscoveredRoute] = set()
        self.uncovered: set[DiscoveredRoute] = set()
        self.error: str | None = None

    def record_case(self, spec: CaseSpec, *, passed: bool, actual_status: int | None) -> None:
        self.results[spec.id] = CaseResult(
            case_id=spec.id,
            contract=spec.contract.name,
            passed=passed,
            actual_status=actual_status,
            expected_statuses=spec.expectation.statuses,
        )

    def finalize(self, config: MatrixConfig) -> None:
        self.config = config
        self.discovery = discover_drf_routes()
        self.covered, self.uncovered = covered_routes(self.discovery, config)

    @property
    def total_cases(self) -> int:
        if self.config is None:
            return 0
        return sum(
            len(relationships)
            for contract in self.config.contracts.values()
            for relationships in contract.matrix.values()
        )

    @property
    def route_coverage(self) -> float | None:
        if not self.discovery.available:
            return None
        total = len(self.discovery.routes)
        return 100.0 if total == 0 else len(self.covered) * 100.0 / total

    def as_dict(self) -> dict[str, Any]:
        passed = sum(result.passed for result in self.results.values())
        route_coverage = self.route_coverage
        contracts_exercised = sorted({result.contract for result in self.results.values()})
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "configured_cases": self.total_cases,
                "asserted_cases": len(self.results),
                "passed_cases": passed,
                "failed_cases": len(self.results) - passed,
                "configured_contracts": len(self.config.contracts) if self.config else 0,
                "exercised_contracts": len(contracts_exercised),
            },
            "cases": [
                {
                    "id": result.case_id,
                    "contract": result.contract,
                    "passed": result.passed,
                    "actual_status": result.actual_status,
                    "expected_statuses": list(result.expected_statuses),
                }
                for result in sorted(self.results.values(), key=lambda item: item.case_id)
            ],
            "drf_routes": {
                "available": self.discovery.available,
                "reason": self.discovery.reason,
                "total": len(self.discovery.routes),
                "covered": len(self.covered),
                "coverage_percent": (
                    round(route_coverage, 2) if route_coverage is not None else None
                ),
                "uncovered": [
                    route.id for route in sorted(self.uncovered, key=lambda item: item.id)
                ],
            },
            "error": self.error,
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")

    def terminal_lines(self) -> list[str]:
        if self.error:
            return [f"report unavailable: {self.error}"]
        summary = self.as_dict()["summary"]
        lines = [
            (
                "authorization cases: "
                f"{summary['asserted_cases']}/{summary['configured_cases']} asserted, "
                f"{summary['passed_cases']} passed, {summary['failed_cases']} failed"
            ),
            (
                "authorization contracts: "
                f"{summary['exercised_contracts']}/{summary['configured_contracts']} exercised"
            ),
        ]
        coverage = self.route_coverage
        if coverage is None:
            lines.append(f"DRF route coverage: unavailable ({self.discovery.reason})")
        else:
            lines.append(
                "DRF route coverage: "
                f"{len(self.covered)}/{len(self.discovery.routes)} ({coverage:.1f}%)"
            )
            for route in sorted(self.uncovered, key=lambda item: item.id)[:20]:
                lines.append(f"  missing: {route.method} {route.name or route.pattern}")
            if len(self.uncovered) > 20:
                lines.append(f"  ... and {len(self.uncovered) - 20} more")
        return lines
