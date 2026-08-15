"""Adapt these fixtures to the factories and user model in your DRF project."""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def owner_client(owner):
    client = APIClient()
    client.force_authenticate(owner)
    return client


@pytest.fixture
def foreign_tenant_client(foreign_tenant_user):
    client = APIClient()
    client.force_authenticate(foreign_tenant_user)
    return client


@pytest.fixture
def anonymous_client():
    return APIClient()


@pytest.fixture
def booking_matrix(owner_booking, foreign_tenant_booking):
    return {
        "owned": owner_booking,
        "foreign_tenant": foreign_tenant_booking,
    }

