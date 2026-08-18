from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pytest_authz_matrix.adapters.registry import adapter_for


class CustomClient:
    def get(self, path: str):
        return None


def test_detects_fastapi_test_client() -> None:
    app = FastAPI()
    adapter = adapter_for(TestClient(app))
    assert adapter.name == "fastapi"


def test_explicit_fastapi_app_can_select_adapter_for_wrapped_client() -> None:
    app = FastAPI()
    adapter = adapter_for(CustomClient(), app=app)
    assert adapter.name == "fastapi"


def test_falls_back_to_generic_adapter() -> None:
    assert adapter_for(CustomClient()).name == "generic"
