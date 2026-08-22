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
    excluded_routes,
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
        self.executed: set[str] = set()
        self.results: dict[str, CaseResult] = {}
        self.config: MatrixConfig | None = None
        self.discovery = DiscoveryResult(False, reason="report has not been finalized")
        self.covered: set[DiscoveredRoute] = set()
        self.uncovered: set[DiscoveredRoute] = set()
        self.excluded: dict[DiscoveredRoute, tuple[str, ...]] = {}
        self.error: str | None = None

    def record_execution(self, spec: CaseSpec) -> None:
        self.executed.add(spec.id)

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
        self.excluded = excluded_routes(self.discovery, config)
        self.covered, self.uncovered = covered_routes(
            self.discovery,
            config,
            contract_names=self.complete_contracts,
        )

    @property
    def configured_cases(self) -> dict[str, str]:
        """Map every configured case ID to its contract name."""

        if self.config is None:
            return {}
        cases: dict[str, str] = {}
        for contract in self.config.contracts.values():
            for actor_name, relationships in contract.matrix.items():
                for relationship, expectation in relationships.items():
                    relationship_name = relationship or "endpoint"
                    case_id = (
                        f"{contract.name}[{actor_name}-{relationship_name}-"
                        f"{expectation.outcome}]"
                    )
                    cases[case_id] = contract.name
        return cases

    @property
    def total_cases(self) -> int:
        return len(self.configured_cases)

    @property
    def asserted(self) -> set[str]:
        return set(self.results)

    @property
    def completed_cases(self) -> set[str]:
        return self.executed & self.asserted

    @property
    def missing_execution(self) -> set[str]:
        return set(self.configured_cases) - self.executed

    @property
    def missing_assertion(self) -> set[str]:
        return self.executed - self.asserted

    @property
    def asserted_without_execution(self) -> set[str]:
        return self.asserted - self.executed

    @property
    def complete_contracts(self) -> set[str]:
        configured = self.configured_cases
        complete: set[str] = set()
        for contract_name in set(configured.values()):
            contract_cases = {
                case_id for case_id, name in configured.items() if name == contract_name
            }
            if contract_cases and contract_cases <= self.completed_cases:
                complete.add(contract_name)
        return complete

    @property
    def incomplete_contracts(self) -> set[str]:
        if self.config is None:
            return set()
        return set(self.config.contracts) - self.complete_contracts

    @property
    def execution_complete(self) -> bool:
        return not (
            self.missing_execution
            or self.missing_assertion
            or self.asserted_without_execution
        )

    @property
    def route_coverage(self) -> float | None:
        if not self.discovery.available:
            return None
        total = self.eligible_routes
        return 100.0 if total == 0 else len(self.covered) * 100.0 / total

    @property
    def eligible_routes(self) -> int:
        return len(self.discovery.routes) - len(self.excluded)

    def as_dict(self) -> dict[str, Any]:
        passed = sum(result.passed for result in self.results.values())
        route_coverage = self.route_coverage
        contracts_exercised = {result.contract for result in self.results.values()}
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "configured_cases": self.total_cases,
                "executed_cases": len(self.executed),
                "asserted_cases": len(self.results),
                "completed_cases": len(self.completed_cases),
                "passed_cases": passed,
                "failed_cases": len(self.results) - passed,
                "configured_contracts": len(self.config.contracts) if self.config else 0,
                "exercised_contracts": len(contracts_exercised),
                "complete_contracts": len(self.complete_contracts),
            },
            "execution": {
                "complete": self.execution_complete,
                "missing_execution": sorted(self.missing_execution),
                "missing_assertion": sorted(self.missing_assertion),
                "asserted_without_execution": sorted(self.asserted_without_execution),
                "incomplete_contracts": sorted(self.incomplete_contracts),
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
                "eligible": self.eligible_routes,
                "covered": len(self.covered),
                "coverage_percent": (
                    round(route_coverage, 2) if route_coverage is not None else None
                ),
                "uncovered": [
                    route.id for route in sorted(self.uncovered, key=lambda item: item.id)
                ],
                "excluded": [
                    {
                        "id": route.id,
                        "method": route.method,
                        "name": route.name,
                        "pattern": route.pattern,
                        "reasons": list(reasons),
                    }
                    for route, reasons in sorted(
                        self.excluded.items(), key=lambda item: item[0].id
                    )
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
                f"{summary['completed_cases']}/{summary['configured_cases']} complete, "
                f"{summary['executed_cases']} executed, {summary['asserted_cases']} asserted, "
                f"{summary['passed_cases']} passed, {summary['failed_cases']} failed"
            ),
            (
                "authorization contracts: "
                f"{summary['complete_contracts']}/{summary['configured_contracts']} complete"
            ),
        ]
        execution = self.as_dict()["execution"]
        lines.extend(_incomplete_case_lines("not executed", execution["missing_execution"]))
        lines.extend(_incomplete_case_lines("not asserted", execution["missing_assertion"]))
        lines.extend(
            _incomplete_case_lines(
                "asserted without execution", execution["asserted_without_execution"]
            )
        )
        coverage = self.route_coverage
        if coverage is None:
            lines.append(f"DRF route coverage: unavailable ({self.discovery.reason})")
        else:
            lines.append(
                "DRF route coverage: "
                f"{len(self.covered)}/{self.eligible_routes} ({coverage:.1f}%)"
            )
            for route, reasons in sorted(self.excluded.items(), key=lambda item: item[0].id):
                lines.append(
                    f"  excluded: {route.method} {route.name or route.pattern} "
                    f"({'; '.join(reasons)})"
                )
            for route in sorted(self.uncovered, key=lambda item: item.id)[:20]:
                lines.append(f"  missing: {route.method} {route.name or route.pattern}")
            if len(self.uncovered) > 20:
                lines.append(f"  ... and {len(self.uncovered) - 20} more")
        return lines


def _incomplete_case_lines(label: str, case_ids: list[str]) -> list[str]:
    lines = [f"  {label}: {case_id}" for case_id in case_ids[:20]]
    if len(case_ids) > 20:
        lines.append(f"  ... and {len(case_ids) - 20} more {label} cases")
    return lines
