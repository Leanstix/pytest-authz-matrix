from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def owner_client():
    return TestClient(app, headers={"X-Actor": "owner"})


@pytest.fixture
def outsider_client():
    return TestClient(app, headers={"X-Actor": "outsider"})


@pytest.fixture
def anonymous_client():
    return TestClient(app)


@pytest.fixture
def booking_matrix():
    return {
        "owned": {"id": 1},
        "foreign": {"id": 2},
    }


@pytest.fixture
def booking_update_payload():
    return {"status": "approved"}
