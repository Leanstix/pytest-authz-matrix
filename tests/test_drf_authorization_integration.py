from __future__ import annotations

import pytest


def test_authenticated_clients_execute_namespaced_custom_action_matrix(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import include, path
from rest_framework.authentication import BasicAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ViewSet


class BookingViewSet(ViewSet):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if request.headers.get('X-Tenant') != 'tenant-a':
            return Response({'detail': 'wrong tenant'}, status=403)
        if request.headers.get('X-Test-Source') != 'authz-matrix':
            return Response({'detail': 'missing source'}, status=400)
        if request.user.role == 'owner' and pk == '1':
            return Response(
                {
                    'id': pk,
                    'decision': request.data['decision'],
                    'actor': request.user.role,
                }
            )
        return Response({'detail': 'not found'}, status=404)


router = SimpleRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('api/v1/', include((router.urls, 'api'), namespace='v1')),
]
"""
    )
    pytester.makeconftest(
        """
from dataclasses import dataclass

from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='test',
        ROOT_URLCONF='api_urls',
        ALLOWED_HOSTS=['testserver'],
        REST_FRAMEWORK={'UNAUTHENTICATED_USER': None},
    )

import django
django.setup()

import pytest
from rest_framework.test import APIClient


@dataclass
class Actor:
    role: str
    is_authenticated: bool = True


def authenticated_client(role, tenant='tenant-a'):
    client = APIClient(headers={'X-Tenant': tenant})
    client.force_authenticate(Actor(role))
    return client


@pytest.fixture
def owner_client():
    return authenticated_client('owner')


@pytest.fixture
def outsider_client():
    return authenticated_client('outsider')


@pytest.fixture
def foreign_tenant_client():
    return authenticated_client('owner', tenant='tenant-b')


@pytest.fixture
def anonymous_client():
    return APIClient(headers={'X-Tenant': 'tenant-a'})


@pytest.fixture
def booking_matrix():
    return {
        'owned': {'pk': 1},
        'foreign': {'pk': 2},
    }


@pytest.fixture
def approval_payload():
    return {'decision': 'approve'}
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  owner: owner_client
  outsider: outsider_client
  foreign_tenant: foreign_tenant_client
  anonymous: anonymous_client
resources:
  booking:
    fixture: booking_matrix
contracts:
  booking.approve:
    method: POST
    path: /api/v1/bookings/{resource}/approve/
    route_name: booking-approve
    resource: booking
    request:
      data_fixture: approval_payload
      format: json
      headers:
        X-Test-Source: authz-matrix
    matrix:
      owner:
        owned: allow
        foreign: conceal
      outsider:
        owned: conceal
        foreign: conceal
      foreign_tenant:
        owned: deny
        foreign: deny
      anonymous:
        owned: unauthenticated
        foreign: unauthenticated
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest


@pytest.mark.authz_contract('booking.approve')
def test_booking_approval_policy(authz_case):
    response = authz_case.run()
    if authz_case.actor == 'owner' and authz_case.relationship == 'owned':
        assert response.data == {
            'id': '1',
            'decision': 'approve',
            'actor': 'owner',
        }
"""
    )

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-report",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=8)
    result.stdout.fnmatch_lines(["DRF route coverage: 1/1 (100.0%)"])
