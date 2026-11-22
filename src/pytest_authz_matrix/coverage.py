"""Executed route coverage for the Python authorization checkers."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import ClassVar

from pytest_authz_matrix.exceptions import AuthzConfigurationError
from pytest_authz_matrix.permissions import RouteKey


class AuthzCoverageWarning(UserWarning):
    """Some discovered routes had no executable authorization check."""


@dataclass(frozen=True)
class RouteCoverage:
    """Count actor checks separately from unique method and path pairs."""

    checked: int
    unclassified: tuple[RouteKey, ...]
    needs_path: tuple[RouteKey, ...]
    checked_routes: tuple[RouteKey, ...] = ()

    framework: ClassVar[str]

    @property
    def total_routes(self) -> int:
        return len(self.checked_routes) + len(self.unclassified) + len(self.needs_path)

    @property
    def coverage_percent(self) -> float:
        return 100 * len(self.checked_routes) / self.total_routes if self.total_routes else 0.0

    def summary(self) -> str:
        lines = [
            f"{self.framework} authorization coverage: "
            f"{len(self.checked_routes)}/{self.total_routes} routes "
            f"({self.coverage_percent:.1f}%), {self.checked} actor checks"
        ]
        for reason, routes in (
            ("no known permission expectation", self.unclassified),
            ("provide a concrete path", self.needs_path),
        ):
            lines.extend(f"  {method} {path} ({reason})" for method, path in sorted(routes))
        return "\n".join(lines)


def validate_minimum(min_coverage: float | None) -> None:
    if min_coverage is not None and (
        isinstance(min_coverage, bool)
        or not math.isfinite(min_coverage)
        or not 0 <= min_coverage <= 100
    ):
        raise AuthzConfigurationError("min_coverage must be a finite percentage from 0 to 100")


def finish_checks(result: RouteCoverage, failures: list[str], min_coverage: float | None) -> None:
    summary = result.summary()
    if failures:
        details = "\n".join(failures)
        raise AssertionError(
            f"{result.framework} authorization checks failed:\n{details}\n{summary}"
        )
    if min_coverage is not None and result.coverage_percent < min_coverage:
        raise AssertionError(f"{summary}\nRequired authorization route coverage: {min_coverage:g}%")
    if result.unclassified or result.needs_path:
        warnings.warn(summary, AuthzCoverageWarning, stacklevel=3)
