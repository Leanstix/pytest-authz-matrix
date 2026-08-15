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
