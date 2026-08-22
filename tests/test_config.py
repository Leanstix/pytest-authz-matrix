from __future__ import annotations

from pathlib import Path

import pytest

from pytest_authz_matrix.config import load_config
from pytest_authz_matrix.exceptions import AuthzConfigurationError


def write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_resource_and_endpoint_contracts(tmp_path: Path) -> None:
    path = write_config(
        tmp_path / "authz.yml",
        """
version: 1
actors:
  owner: owner_client
  anonymous:
    client_fixture: anonymous_client
resources:
  booking:
    fixture: booking_matrix
    lookup: uuid
outcomes:
  allow: [200, 204]
coverage:
  exclude:
    - method: get
      route_name: api-root
      reason: Generated router index
    - path: /health/
      reason: Public liveness probe
contracts:
  booking.retrieve:
    method: get
    path: /bookings/{resource}/
    route_name: booking-detail
    resource: booking
    matrix:
      owner:
        owned: allow
        foreign: conceal
      anonymous:
        owned: unauthenticated
  profile.current:
    method: GET
    path: /profile/me/
    matrix:
      owner: allow
      anonymous: 401
""",
    )

    config = load_config(path)

    assert config.version == 1
    assert config.actors["owner"].client_fixture == "owner_client"
    assert config.resources["booking"].lookup == "uuid"
    assert config.contracts["booking.retrieve"].method == "GET"
    assert config.contracts["booking.retrieve"].matrix["owner"]["owned"].statuses == (
        200,
        204,
    )
    assert config.contracts["profile.current"].matrix["anonymous"][None].statuses == (401,)
    assert config.coverage.exclusions[0].method == "GET"
    assert config.coverage.exclusions[0].route_name == "api-root"
    assert config.coverage.exclusions[1].path == "/health/"
    assert config.coverage.exclusions[1].reason == "Public liveness probe"


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ("resource: missing", "unknown resource"),
        ("matrix:\n      stranger:\n        owned: allow", "unknown actor"),
        ("owned: maybe", "unknown outcome"),
        ("owned: 99", "invalid HTTP statuses"),
    ],
)
def test_rejects_invalid_references_and_expectations(
    tmp_path: Path, fragment: str, message: str
) -> None:
    base = """
version: 1
actors:
  owner: owner_client
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
"""
    if fragment.startswith("resource:"):
        base = base.replace("resource: booking", fragment)
    elif fragment.startswith("matrix:"):
        base = base.replace("matrix:\n      owner:\n        owned: allow", fragment)
    else:
        base = base.replace("owned: allow", fragment)
    path = write_config(tmp_path / "authz.yml", base)

    with pytest.raises(AuthzConfigurationError, match=message):
        load_config(path)


def test_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    path = write_config(tmp_path / "authz.yml", "version: 2\n")

    with pytest.raises(AuthzConfigurationError, match="Unsupported config version"):
        load_config(path)


@pytest.mark.parametrize(
    ("coverage", "message"),
    [
        ("exclude: api-root", "coverage.exclude must be a list"),
        (
            "exclude:\n  - route_name: api-root",
            r"coverage.exclude\[0\].reason",
        ),
        (
            "exclude:\n  - reason: ambiguous\n    route_name: api-root\n    path: /api/",
            "exactly one of route_name or path",
        ),
        (
            "exclude:\n  - reason: no selector",
            "exactly one of route_name or path",
        ),
        (
            "exclude:\n  - reason: blank selector\n    path: '   '",
            "path must be a non-empty string",
        ),
        (
            "exclude:\n  - reason: '   '\n    route_name: api-root",
            "reason must not be blank",
        ),
        (
            """exclude:
  - reason: first
    method: GET
    route_name: api-root
  - reason: duplicate
    method: get
    route_name: api-root""",
            "duplicates an earlier route exclusion",
        ),
    ],
)
def test_rejects_invalid_route_exclusions(
    tmp_path: Path, coverage: str, message: str
) -> None:
    indented_coverage = "\n".join(f"  {line}" for line in coverage.splitlines())
    path = write_config(
        tmp_path / "authz.yml",
        f"""
version: 1
actors:
  owner: owner_client
coverage:
{indented_coverage}
contracts:
  profile.current:
    method: GET
    path: /profile/me/
    matrix:
      owner: allow
""",
    )

    with pytest.raises(AuthzConfigurationError, match=message):
        load_config(path)
