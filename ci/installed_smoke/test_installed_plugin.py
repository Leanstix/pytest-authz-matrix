from __future__ import annotations

from importlib.metadata import version

import pytest

from pytest_authz_matrix import __version__


@pytest.mark.authz_contract("health.retrieve")
def test_installed_distribution_loads_the_plugin(authz_case) -> None:
    assert version("pytest-authz-matrix") == __version__
    response = authz_case.run()
    assert response.status_code == 200
