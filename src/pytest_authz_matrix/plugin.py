"""pytest entry point and authorization-case parametrization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pytest_authz_matrix.case import AuthorizationCase
from pytest_authz_matrix.config import load_config
from pytest_authz_matrix.exceptions import AuthzConfigurationError
from pytest_authz_matrix.models import CaseSpec, MatrixConfig

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
        type=float,
        metavar="PERCENT",
        help="fail when discovered DRF route coverage is below this percentage",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "authz_contract(name): expand a test across every case in an authorization contract",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "authz_case" not in metafunc.fixturenames:
        return
    marker = metafunc.definition.get_closest_marker("authz_contract")
    if marker is None or len(marker.args) != 1 or not isinstance(marker.args[0], str):
        raise pytest.UsageError(
            "Tests using authz_case must declare @pytest.mark.authz_contract(\"contract.name\")"
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
    cached = getattr(pytest_config, _CONFIG_ATTR, None)
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

