from __future__ import annotations

import pytest


def test_discovers_namespaced_router_views_and_custom_actions(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import include, path
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet


class BookingViewSet(ViewSet):
    def list(self, request):
        return Response([])

    def create(self, request):
        return Response(request.data, status=201)

    def retrieve(self, request, pk=None):
        return Response({'id': pk})

    def update(self, request, pk=None):
        return Response(request.data)

    def partial_update(self, request, pk=None):
        return Response(request.data)

    def destroy(self, request, pk=None):
        return Response(status=204)

    @action(detail=True, methods=['post', 'delete'])
    def archive(self, request, pk=None):
        return Response({'id': pk, 'method': request.method})


@api_view(['GET', 'POST'])
def search_bookings(request):
    return Response({'method': request.method})


class ReportDetail(APIView):
    def get(self, request, report_id):
        return Response({'id': str(report_id)})


router = SimpleRouter()
router.register('bookings', BookingViewSet, basename='booking')

booking_patterns = (
    [
        *router.urls,
        path('search/', search_bookings, name='booking-search'),
        path('reports/<uuid:report_id>/', ReportDetail.as_view(), name='report-detail'),
    ],
    'bookings',
)
api_patterns = (
    [path('v1/', include(booking_patterns, namespace='bookings'))],
    'api',
)

urlpatterns = [
    path('api/', include(api_patterns, namespace='v1')),
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
from pytest_authz_matrix.discovery import discover_drf_routes


def test_route_inventory():
    result = discover_drf_routes()

    assert result.available, result.reason
    assert {(route.method, route.name) for route in result.routes} == {
        ('GET', 'v1:bookings:booking-list'),
        ('POST', 'v1:bookings:booking-list'),
        ('GET', 'v1:bookings:booking-detail'),
        ('PUT', 'v1:bookings:booking-detail'),
        ('PATCH', 'v1:bookings:booking-detail'),
        ('DELETE', 'v1:bookings:booking-detail'),
        ('POST', 'v1:bookings:booking-archive'),
        ('DELETE', 'v1:bookings:booking-archive'),
        ('GET', 'v1:bookings:booking-search'),
        ('POST', 'v1:bookings:booking-search'),
        ('GET', 'v1:bookings:report-detail'),
    }
    assert not any(route.method in {'HEAD', 'OPTIONS'} for route in result.routes)
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)


def test_namespaced_router_routes_match_qualified_and_short_contract_names(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import include, path
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ViewSet


class BookingViewSet(ViewSet):
    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({'id': pk})


router = SimpleRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('api/v1/', include((router.urls, 'api'), namespace='v1')),
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
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  member: member_client
contracts:
  booking.list:
    method: GET
    path: /api/v1/bookings/
    route_name: v1:booking-list
    matrix:
      member: allow
  booking.retrieve:
    method: GET
    path: /api/v1/bookings/{resource}/
    route_name: booking-detail
    resource: booking
    matrix:
      member:
        owned: allow
resources:
  booking:
    fixture: booking_matrix
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def member_client():
    return APIClient()


@pytest.fixture
def booking_matrix():
    return {'owned': {'pk': 7}}


def test_route_name_matching():
    from pytest_authz_matrix.config import load_config
    from pytest_authz_matrix.discovery import covered_routes, discover_drf_routes

    config = load_config('authz-matrix.yml')
    discovery = discover_drf_routes()
    covered, uncovered = covered_routes(discovery, config)

    assert {route.id for route in covered} == {
        'GET v1:booking-list',
        'GET v1:booking-detail',
    }
    assert not uncovered
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)


def test_default_router_discovers_canonical_routes_without_format_aliases(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import include, path
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.viewsets import ViewSet


class BookingViewSet(ViewSet):
    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({'id': pk})


router = DefaultRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('api/', include((router.urls, 'api'), namespace='v1')),
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
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  member: member_client
coverage:
  exclude:
    - method: GET
      route_name: api-root
      reason: Generated DefaultRouter index
contracts:
  booking.list:
    method: GET
    path: /api/bookings/
    route_name: booking-list
    matrix:
      member: allow
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
from pytest_authz_matrix.config import load_config
from pytest_authz_matrix.discovery import discover_drf_routes, excluded_routes


def test_default_router_inventory():
    result = discover_drf_routes()

    assert result.available, result.reason
    assert {(route.method, route.name) for route in result.routes} == {
        ('GET', 'v1:api-root'),
        ('GET', 'v1:booking-list'),
        ('GET', 'v1:booking-detail'),
    }
    assert len(result.routes) == 3
    assert not any('format' in route.pattern for route in result.routes)
    excluded = excluded_routes(result, load_config('authz-matrix.yml'))
    assert {route.id: reasons for route, reasons in excluded.items()} == {
        'GET v1:api-root': ('Generated DefaultRouter index',),
    }
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)


def test_discovery_retains_real_format_parameters_and_respects_disabled_methods(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls=r"""
from django.urls import include, path, re_path
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet


class ExportView(APIView):
    def get(self, request, format):
        return Response({'format': format})


class ReadOnlyBookingViewSet(ModelViewSet):
    http_method_names = ['get', 'head', 'options']

    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({'id': pk})


router = SimpleRouter()
router.register('bookings', ReadOnlyBookingViewSet, basename='booking')

urlpatterns = [
    re_path(r'^exports/(?P<format>json|csv)/$', ExportView.as_view(), name='export'),
    path('api/', include(router.urls)),
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
        r"""
from pytest_authz_matrix.discovery import discover_drf_routes


def test_precise_inventory():
    result = discover_drf_routes()

    assert result.available, result.reason
    assert {(route.method, route.name) for route in result.routes} == {
        ('GET', 'export'),
        ('GET', 'booking-list'),
        ('GET', 'booking-detail'),
    }
    export = next(route for route in result.routes if route.name == 'export')
    assert r'(?P<format>json|csv)' in export.pattern
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)


def test_duplicate_names_require_path_match_and_unnamed_routes_use_paths(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView


class ExampleView(APIView):
    def get(self, request):
        return Response({'ok': True})


urlpatterns = [
    path('alpha/', ExampleView.as_view(), name='duplicate'),
    path('beta/', ExampleView.as_view(), name='duplicate'),
    path('unnamed/', ExampleView.as_view()),
    path('ignored/', ExampleView.as_view()),
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
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  member: member_client
coverage:
  exclude:
    - method: GET
      path: /ignored/
      reason: Deliberately public endpoint
contracts:
  alpha.retrieve:
    method: GET
    path: /alpha/
    route_name: duplicate
    matrix:
      member: allow
  unnamed.retrieve:
    method: GET
    path: /unnamed/
    matrix:
      member: allow
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
from pytest_authz_matrix.config import load_config
from pytest_authz_matrix.discovery import covered_routes, discover_drf_routes, excluded_routes


def test_unambiguous_matching():
    config = load_config('authz-matrix.yml')
    discovery = discover_drf_routes()
    covered, uncovered = covered_routes(discovery, config)
    excluded = excluded_routes(discovery, config)

    assert {route.pattern for route in covered} == {'alpha/', 'unnamed/'}
    assert {route.pattern for route in uncovered} == {'beta/'}
    assert {route.pattern for route in excluded} == {'ignored/'}
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)
