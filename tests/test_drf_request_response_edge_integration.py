from __future__ import annotations

import pytest


def test_request_and_response_edges_through_real_drf_and_django_clients(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        edge_api="""
import json

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import path
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView


class VendorJSONParser(JSONParser):
    media_type = 'application/vnd.authz+json'


class VendorJSONRenderer(JSONRenderer):
    media_type = 'application/vnd.authz+json'
    format = 'vendor'


class UploadView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = (MultiPartParser,)

    def post(self, request):
        upload = request.FILES['evidence']
        return Response(
            {
                'name': upload.name,
                'size': upload.size,
                'content_type': upload.content_type,
                'content': upload.read().decode(),
                'label': request.data['label'],
            },
            status=201,
        )


class VendorView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = (VendorJSONParser,)

    def patch(self, request):
        return Response(
            {'data': request.data, 'content_type': request.content_type},
            status=200,
        )


class HeaderView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response(
            {
                'policy': request.headers.get('X-Policy'),
                'client_default': request.headers.get('X-Client-Default'),
            }
        )


class RedirectView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return HttpResponseRedirect('/target/')


class EmptyView(APIView):
    authentication_classes = []
    permission_classes = []

    def delete(self, request):
        return Response(status=204)


class ExceptionView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        if request.headers.get('X-Error') == 'missing':
            raise NotFound('resource hidden')
        raise PermissionDenied('policy rejected')


class OpaqueView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return HttpResponse(
            b'\\xff\\xfe',
            status=418,
            content_type='application/octet-stream',
        )


async def async_view(request):
    return JsonResponse({'mode': 'async', 'method': request.method})


def slash_target(request):
    return JsonResponse({'slash': True})


def redirect_target(request):
    return JsonResponse({'target': True})


urlpatterns = [
    path('upload/', UploadView.as_view(), name='upload'),
    path('vendor/', VendorView.as_view(), name='vendor'),
    path('headers/', HeaderView.as_view(), name='headers'),
    path('redirect/', RedirectView.as_view(), name='redirect'),
    path('empty/', EmptyView.as_view(), name='empty'),
    path('exception/', ExceptionView.as_view(), name='exception'),
    path('opaque/', OpaqueView.as_view(), name='opaque'),
    path('async/', async_view, name='async-view'),
    path('slash-target/', slash_target, name='slash-target'),
    path('target/', redirect_target, name='redirect-target'),
]
"""
    )
    pytester.makeconftest(
        """
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='test',
        ROOT_URLCONF='edge_api',
        ALLOWED_HOSTS=['testserver'],
        APPEND_SLASH=True,
        MIDDLEWARE=['django.middleware.common.CommonMiddleware'],
        REST_FRAMEWORK={
            'UNAUTHENTICATED_USER': None,
            'TEST_REQUEST_RENDERER_CLASSES': [
                'rest_framework.renderers.MultiPartRenderer',
                'rest_framework.renderers.JSONRenderer',
                'edge_api.VendorJSONRenderer',
            ],
        },
    )

import django
django.setup()

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient(headers={'X-Client-Default': 'fixture'})


@pytest.fixture
def django_client():
    return Client()


@pytest.fixture
def upload_payload():
    return {
        'evidence': SimpleUploadedFile(
            'policy.txt',
            b'authorization-data',
            content_type='text/plain',
        ),
        'label': 'review',
    }


@pytest.fixture
def vendor_payload():
    return {'decision': 'allow', 'metadata': {'source': 'matrix'}}
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  api: api_client
  django: django_client
outcomes:
  created: [201]
  redirected: [301, 302]
  empty: [204]
  teapot: [418]
contracts:
  edge.upload:
    method: POST
    path: /upload/
    route_name: upload
    request:
      data_fixture: upload_payload
      format: multipart
    matrix:
      api: created
  edge.vendor:
    method: PATCH
    path: /vendor/
    route_name: vendor
    request:
      data_fixture: vendor_payload
      format: vendor
    matrix:
      api: allow
  edge.headers:
    method: GET
    path: /headers/
    route_name: headers
    request:
      headers:
        X-Policy: contract
    matrix:
      api: allow
  edge.redirect:
    method: GET
    path: /redirect/
    route_name: redirect
    matrix:
      api: redirected
  edge.trailing-slash:
    method: GET
    path: /slash-target
    matrix:
      django: redirected
  edge.empty:
    method: DELETE
    path: /empty/
    route_name: empty
    matrix:
      api: empty
  edge.not-found:
    method: GET
    path: /exception/
    route_name: exception
    request:
      headers:
        X-Error: missing
    matrix:
      api: conceal
  edge.permission-denied:
    method: GET
    path: /exception/
    route_name: exception
    request:
      headers:
        X-Error: denied
    matrix:
      api: deny
  edge.opaque:
    method: GET
    path: /opaque/
    route_name: opaque
    matrix:
      api: teapot
  edge.async:
    method: GET
    path: /async/
    matrix:
      django: allow
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest


@pytest.mark.authz_contract('edge.upload')
def test_upload(authz_case):
    response = authz_case.run()
    assert response.data == {
        'name': 'policy.txt',
        'size': 18,
        'content_type': 'text/plain',
        'content': 'authorization-data',
        'label': 'review',
    }


@pytest.mark.authz_contract('edge.vendor')
def test_vendor_media_type(authz_case):
    response = authz_case.run()
    assert response.data['data'] == {
        'decision': 'allow',
        'metadata': {'source': 'matrix'},
    }
    assert response.data['content_type'] == 'application/vnd.authz+json'


@pytest.mark.authz_contract('edge.headers')
def test_explicit_header_override(authz_case):
    response = authz_case.run(headers={'X-Policy': 'override'})
    assert response.data == {
        'policy': 'override',
        'client_default': 'fixture',
    }


@pytest.mark.authz_contract('edge.redirect')
def test_redirect_is_not_followed(authz_case):
    response = authz_case.run()
    assert response.status_code == 302
    assert response['Location'] == '/target/'


@pytest.mark.authz_contract('edge.trailing-slash')
def test_append_slash_redirect(authz_case):
    response = authz_case.run()
    assert response.status_code == 301
    assert response['Location'] == '/slash-target/'


@pytest.mark.authz_contract('edge.empty')
def test_empty_response(authz_case):
    response = authz_case.run()
    assert response.status_code == 204
    assert response.content == b''


@pytest.mark.authz_contract('edge.not-found')
def test_not_found_exception(authz_case):
    response = authz_case.run()
    assert response.data['detail'].code == 'not_found'


@pytest.mark.authz_contract('edge.permission-denied')
def test_permission_exception(authz_case):
    response = authz_case.run()
    assert response.data['detail'].code == 'permission_denied'


@pytest.mark.authz_contract('edge.opaque')
def test_opaque_response(authz_case):
    response = authz_case.run()
    assert response.content == b'\\xff\\xfe'
    assert response['Content-Type'] == 'application/octet-stream'


@pytest.mark.authz_contract('edge.async')
def test_async_django_view(authz_case):
    response = authz_case.run()
    assert response.json() == {'mode': 'async', 'method': 'GET'}
"""
    )

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-report",
        "--authz-require-complete",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=10)
    result.stdout.fnmatch_lines(["*DRF route coverage: 7/7 (100.0%)*"])
