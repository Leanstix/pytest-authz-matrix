from __future__ import annotations

import pytest


def test_django_adapter_preserves_drf_route_discovery(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

class BookingList(APIView):
    def get(self, request):
        return Response({'results': []})

urlpatterns = [
    path('bookings/', BookingList.as_view(), name='booking-list'),
]
"""
    )
    pytester.makeconftest(
        """
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
"""
    )
    pytester.makepyfile(
        """
from rest_framework.test import APIClient
from pytest_authz_matrix.adapters.django import DjangoRESTFrameworkAdapter


def test_drf_adapter():
    adapter = DjangoRESTFrameworkAdapter()
    assert adapter.supports_client(APIClient())
    result = adapter.discover_routes(None)
    assert result.available
    assert result.framework == 'django-rest-framework'
    assert [(route.method, route.name) for route in result.routes] == [
        ('GET', 'booking-list'),
    ]
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)
