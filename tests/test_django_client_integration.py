from __future__ import annotations

import pytest


def test_django_client_translates_json_multipart_headers_and_query(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView


class EchoView(APIView):
    authentication_classes = []
    permission_classes = []

    def response(self, request, *, status=200):
        return Response(
            {
                'method': request.method,
                'data': request.data,
                'query': {
                    key: request.query_params.getlist(key)
                    for key in request.query_params
                },
                'source': request.headers.get('X-Test-Source'),
                'content_type': request.content_type,
            },
            status=status,
        )

    def get(self, request):
        return self.response(request)

    def post(self, request):
        return self.response(request, status=201)

    def patch(self, request):
        return self.response(request)


urlpatterns = [
    path('echo/', EchoView.as_view(), name='echo'),
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

import pytest
from django.test import Client


@pytest.fixture
def django_client():
    return Client()


@pytest.fixture
def json_payload():
    return {'name': 'django-json', 'enabled': True}


@pytest.fixture
def multipart_payload():
    return {'name': 'django-multipart'}


@pytest.fixture
def query_payload():
    return {'scope': ['owned', 'active']}
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  member: django_client
outcomes:
  created: [201]
contracts:
  echo.list:
    method: GET
    path: /echo/
    request:
      query_fixture: query_payload
      headers:
        X-Test-Source: django-client
    matrix:
      member: allow
  echo.create:
    method: POST
    path: /echo/
    request:
      data_fixture: json_payload
      format: json
    matrix:
      member: created
  echo.partial:
    method: PATCH
    path: /echo/
    request:
      data_fixture: multipart_payload
      format: multipart
    matrix:
      member: allow
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest


@pytest.mark.authz_contract('echo.list')
def test_get_query_and_headers(authz_case):
    response = authz_case.run()
    assert response.json()['method'] == 'GET'
    assert response.json()['query'] == {'scope': ['owned', 'active']}
    assert response.json()['source'] == 'django-client'


@pytest.mark.authz_contract('echo.create')
def test_post_json(authz_case):
    response = authz_case.run()
    assert response.json()['data'] == {'name': 'django-json', 'enabled': True}
    assert response.json()['content_type'] == 'application/json'


@pytest.mark.authz_contract('echo.partial')
def test_patch_multipart(authz_case):
    response = authz_case.run()
    assert response.json()['data']['name'] == 'django-multipart'
    assert response.json()['content_type'].startswith('multipart/form-data;')
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=3)


def test_django_client_rejects_unsupported_request_format(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        api_urls="""
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView


class EchoView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        return Response(request.data)


urlpatterns = [path('echo/', EchoView.as_view())]
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

import pytest
from django.test import Client


@pytest.fixture
def django_client():
    return Client()


@pytest.fixture
def payload():
    return {'name': 'unsupported'}
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  member: django_client
contracts:
  echo.create:
    method: POST
    path: /echo/
    request:
      data_fixture: payload
      format: xml
    matrix:
      member: allow
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest
from pytest_authz_matrix.exceptions import AuthzExecutionError


@pytest.mark.authz_contract('echo.create')
def test_unsupported_format(authz_case):
    with pytest.raises(AuthzExecutionError, match="does not support request format 'xml'"):
        authz_case.execute()
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)
