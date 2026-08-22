from __future__ import annotations

import pytest


def test_negotiation_exceptions_streaming_throttling_and_secure_requests(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        boundary_api="""
from io import BytesIO

from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from django.urls import path
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView, exception_handler


class VendorJSONRenderer(JSONRenderer):
    media_type = 'application/vnd.authz+json'
    format = 'vendor'


class PlainTextRenderer(BaseRenderer):
    media_type = 'text/plain'
    format = 'plain'
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return str(data).encode()


class BrokenJSONRenderer(BaseRenderer):
    media_type = 'application/json'
    format = 'broken-json'
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return b'{\"broken\":'


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if isinstance(exc, PermissionDenied) and response is not None:
        response.status_code = 451
        response.data = {'code': 'policy_blocked'}
    return response


class VendorResponseView(APIView):
    authentication_classes = []
    permission_classes = []
    renderer_classes = (VendorJSONRenderer,)

    def get(self, request):
        return Response({'media': 'vendor'})


class JSONOnlyView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = (JSONParser,)

    def post(self, request):
        return Response(request.data)


class PolicyExceptionView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        raise PermissionDenied('blocked by policy')


class AlwaysThrottle(BaseThrottle):
    def allow_request(self, request, view):
        return False

    def wait(self):
        return 2


class ThrottledView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = (AlwaysThrottle,)

    def get(self, request):
        return Response({'unreachable': True})


def stream_view(request):
    return StreamingHttpResponse(
        iter((b'authorization-', b'stream')),
        content_type='text/plain',
    )


def file_view(request):
    return FileResponse(
        BytesIO(b'policy-file'),
        filename='policy.txt',
        content_type='text/plain',
    )


def secure_view(request):
    response = JsonResponse(
        {'secure': request.is_secure(), 'host': request.get_host()}
    )
    response.set_cookie('session_probe', 'set', secure=True, httponly=True, samesite='Lax')
    return response


urlpatterns = [
    path('vendor-response/', VendorResponseView.as_view(), name='vendor-response'),
    path('json-only/', JSONOnlyView.as_view(), name='json-only'),
    path('policy-exception/', PolicyExceptionView.as_view(), name='policy-exception'),
    path('throttled/', ThrottledView.as_view(), name='throttled'),
    path('stream/', stream_view, name='stream'),
    path('file/', file_view, name='file'),
    path('secure/', secure_view, name='secure'),
]
"""
    )
    pytester.makeconftest(
        """
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='test',
        ROOT_URLCONF='boundary_api',
        ALLOWED_HOSTS=['testserver', 'api.example.test'],
        SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
        REST_FRAMEWORK={
            'UNAUTHENTICATED_USER': None,
            'EXCEPTION_HANDLER': 'boundary_api.custom_exception_handler',
            'TEST_REQUEST_RENDERER_CLASSES': [
                'rest_framework.renderers.JSONRenderer',
                'boundary_api.PlainTextRenderer',
                'boundary_api.BrokenJSONRenderer',
            ],
        },
    )

import django
django.setup()

import pytest
from django.test import Client
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def django_client():
    return Client()


@pytest.fixture
def secure_client():
    return Client(
        headers={
            'Host': 'api.example.test',
            'X-Forwarded-Proto': 'https',
        }
    )


@pytest.fixture
def plain_payload():
    return 'not-json'


@pytest.fixture
def malformed_payload():
    return {'ignored': True}
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  api: api_client
  django: django_client
  secure: secure_client
outcomes:
  bad_request: [400]
  not_acceptable: [406]
  unsupported_media: [415]
  policy_blocked: [451]
  throttled: [429]
contracts:
  boundary.vendor-response:
    method: GET
    path: /vendor-response/
    route_name: vendor-response
    request:
      headers:
        Accept: application/vnd.authz+json
    matrix:
      api: allow
  boundary.not-acceptable:
    method: GET
    path: /vendor-response/
    route_name: vendor-response
    request:
      headers:
        Accept: application/xml
    matrix:
      api: not_acceptable
  boundary.unsupported-media:
    method: POST
    path: /json-only/
    route_name: json-only
    request:
      data_fixture: plain_payload
      format: plain
    matrix:
      api: unsupported_media
  boundary.malformed-json:
    method: POST
    path: /json-only/
    route_name: json-only
    request:
      data_fixture: malformed_payload
      format: broken-json
    matrix:
      api: bad_request
  boundary.custom-exception:
    method: GET
    path: /policy-exception/
    route_name: policy-exception
    matrix:
      api: policy_blocked
  boundary.throttled:
    method: GET
    path: /throttled/
    route_name: throttled
    matrix:
      api: throttled
  boundary.streaming:
    method: GET
    path: /stream/
    matrix:
      django: allow
  boundary.file:
    method: GET
    path: /file/
    matrix:
      django: allow
  boundary.secure:
    method: GET
    path: /secure/
    matrix:
      secure: allow
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest


@pytest.mark.authz_contract('boundary.vendor-response')
def test_vendor_response(authz_case):
    response = authz_case.run()
    assert response.data == {'media': 'vendor'}
    assert response['Content-Type'] == 'application/vnd.authz+json'


@pytest.mark.authz_contract('boundary.not-acceptable')
def test_not_acceptable(authz_case):
    response = authz_case.run()
    assert response.data['detail'].code == 'not_acceptable'


@pytest.mark.authz_contract('boundary.unsupported-media')
def test_unsupported_media(authz_case):
    response = authz_case.run()
    assert response.data['detail'].code == 'unsupported_media_type'


@pytest.mark.authz_contract('boundary.malformed-json')
def test_malformed_json(authz_case):
    response = authz_case.run()
    assert response.data['detail'].code == 'parse_error'


@pytest.mark.authz_contract('boundary.custom-exception')
def test_custom_exception_handler(authz_case):
    response = authz_case.run()
    assert response.data == {'code': 'policy_blocked'}


@pytest.mark.authz_contract('boundary.throttled')
def test_throttled_response(authz_case):
    response = authz_case.run()
    assert response['Retry-After'] == '2'


@pytest.mark.authz_contract('boundary.streaming')
def test_streaming_response(authz_case):
    response = authz_case.run()
    assert b''.join(response.streaming_content) == b'authorization-stream'


@pytest.mark.authz_contract('boundary.file')
def test_file_response(authz_case):
    response = authz_case.run()
    assert b''.join(response.streaming_content) == b'policy-file'
    assert response['Content-Disposition'].endswith('filename="policy.txt"')


@pytest.mark.authz_contract('boundary.secure')
def test_secure_host_and_cookie_state(authz_case):
    response = authz_case.run()
    assert response.json() == {'secure': True, 'host': 'api.example.test'}
    cookie = response.cookies['session_probe']
    assert cookie['secure'] is True
    assert cookie['httponly'] is True
    assert cookie['samesite'] == 'Lax'
"""
    )

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-report",
        "--authz-require-complete",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=9)
    result.stdout.fnmatch_lines(["*DRF route coverage: 4/4 (100.0%)*"])
