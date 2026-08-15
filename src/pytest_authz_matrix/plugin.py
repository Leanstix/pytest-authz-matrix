"""pytest entry point and authorization-case parametrization."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

from pytest_authz_matrix.case import AuthorizationCase
from pytest_authz_matrix.config import load_config
from pytest_authz_matrix.exceptions import AuthzConfigurationError
from pytest_authz_matrix.models import CaseSpec, MatrixConfig
from pytest_authz_matrix.reporting import AuthorizationReporter

_CONFIG_ATTR = "_authz_matrix_contract_config"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("authz-matrix", "authorization contract testing")
    group.addoption(
        "--authz-config",
        action="store",
        default="authz-matrix.yml",
        metavar="PATH",
        help="authorization matrix YAML file (default: authz-matrix.yml)",
    )
    group.addoption(
        "--authz-report",
        action="store_true",
        help="print authorization case and DRF route coverage",
    )
    group.addoption(
        "--authz-report-json",
        action="store",
        metavar="PATH",
        help="write a machine-readable authorization report",
    )
    group.addoption(
        "--authz-fail-under",
        action="store",
        type=_percentage,
        metavar="PERCENT",
        help="fail when discovered DRF route coverage is below this percentage",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "authz_contract(name): expand a test across every case in an authorization contract",
    )
    if _reporting_requested(config):
        config.__dict__["_authz_matrix_reporter"] = AuthorizationReporter()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    reporter = _get_recorder(session.config)
    if reporter is None:
        return
    try:
        reporter.finalize(_get_config(session.config))
        json_path = session.config.getoption("--authz-report-json")
        if json_path:
            requested = Path(json_path)
            path = (
                requested if requested.is_absolute() else Path(session.config.rootpath) / requested
            )
            reporter.write_json(path)
        threshold = session.config.getoption("--authz-fail-under")
        coverage = reporter.route_coverage
        if threshold is not None and (coverage is None or coverage < threshold):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
    except (AuthzConfigurationError, pytest.UsageError, OSError) as exc:
        reporter.error = str(exc)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, exitstatus: int, config: pytest.Config
) -> None:
    if not config.getoption("--authz-report"):
        return
    reporter = _get_recorder(config)
    if reporter is None:
        return
    terminalreporter.section("authorization matrix")
    for line in reporter.terminal_lines():
        terminalreporter.write_line(line)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "authz_case" not in metafunc.fixturenames:
        return
    marker = metafunc.definition.get_closest_marker("authz_contract")
    if marker is None or len(marker.args) != 1 or not isinstance(marker.args[0], str):
        raise pytest.UsageError(
            'Tests using authz_case must declare @pytest.mark.authz_contract("contract.name")'
        )

    config = _get_config(metafunc.config)
    contract_name = marker.args[0]
    try:
        contract = config.contracts[contract_name]
    except KeyError as exc:
        available = ", ".join(sorted(config.contracts))
        raise pytest.UsageError(
            f"Unknown authorization contract {contract_name!r}. Available: {available}"
        ) from exc

    cases: list[CaseSpec] = []
    resource = config.resources.get(contract.resource) if contract.resource else None
    for actor_name, relationships in contract.matrix.items():
        for relationship, expectation in relationships.items():
            cases.append(
                CaseSpec(
                    contract=contract,
                    actor=config.actors[actor_name],
                    resource=resource,
                    relationship=relationship,
                    expectation=expectation,
                )
            )
    metafunc.parametrize(
        "authz_case",
        cases,
        indirect=True,
        ids=[case.id for case in cases],
    )


@pytest.fixture
def authz_case(request: pytest.FixtureRequest) -> AuthorizationCase:
    """Return one generated authorization case for a marked test."""

    return AuthorizationCase(request, request.param, recorder=_get_recorder(request.config))


def _get_config(pytest_config: pytest.Config) -> MatrixConfig:
    cached: MatrixConfig | None = getattr(pytest_config, _CONFIG_ATTR, None)
    if cached is not None:
        return cached
    requested = Path(pytest_config.getoption("--authz-config"))
    path = requested if requested.is_absolute() else Path(pytest_config.rootpath) / requested
    try:
        loaded = load_config(path)
    except AuthzConfigurationError as exc:
        raise pytest.UsageError(str(exc)) from exc
    setattr(pytest_config, _CONFIG_ATTR, loaded)
    return loaded


def _get_recorder(pytest_config: pytest.Config) -> Any | None:
    # Reporting is installed lazily so using the core plugin has near-zero overhead.
    return getattr(pytest_config, "_authz_matrix_reporter", None)


def _reporting_requested(config: pytest.Config) -> bool:
    return bool(
        config.getoption("--authz-report")
        or config.getoption("--authz-report-json")
        or config.getoption("--authz-fail-under") is not None
    )


def _percentage(value: str) -> float:
    try:
        percentage = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number from 0 through 100") from exc
    if percentage < 0 or percentage > 100:
        raise argparse.ArgumentTypeError("must be from 0 through 100")
    return percentage
