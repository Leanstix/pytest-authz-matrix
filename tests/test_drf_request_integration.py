from __future__ import annotations

import pytest


def test_api_client_executes_all_http_methods_and_request_formats(
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

    def put(self, request):
        return self.response(request)

    def patch(self, request):
        return self.response(request)

    def delete(self, request):
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
from rest_framework.test import APIClient


@pytest.fixture
def member_client():
    return APIClient()


@pytest.fixture
def json_payload():
    return {'name': 'updated', 'nested': {'enabled': True}}


@pytest.fixture
def multipart_payload():
    return {'name': 'partial', 'enabled': 'true'}


@pytest.fixture
def form_payload():
    return {'name': 'form-default'}


@pytest.fixture
def echo_query():
    return {'tag': ['owned', 'active']}
"""
    )
    (pytester.path / "authz-matrix.yml").write_text(
        """
version: 1
actors:
  member: member_client
outcomes:
  created: [201]
contracts:
  echo.list:
    method: GET
    path: /echo/?existing=yes
    route_name: echo
    request:
      query_fixture: echo_query
      headers:
        X-Test-Source: matrix
    matrix:
      member: allow
  echo.create:
    method: POST
    path: /echo/
    route_name: echo
    request:
      data_fixture: json_payload
      format: json
      headers:
        X-Test-Source: matrix
    matrix:
      member: created
  echo.replace:
    method: PUT
    path: /echo/
    route_name: echo
    request:
      data_fixture: json_payload
      format: json
    matrix:
      member: allow
  echo.partial:
    method: PATCH
    path: /echo/
    route_name: echo
    request:
      data_fixture: multipart_payload
      format: multipart
    matrix:
      member: allow
  echo.delete:
    method: DELETE
    path: /echo/
    route_name: echo
    request:
      data_fixture: json_payload
      format: json
    matrix:
      member: allow
  echo.form:
    method: POST
    path: /echo/
    route_name: echo
    request:
      data_fixture: form_payload
      format: null
    matrix:
      member: created
""",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
import pytest


@pytest.mark.authz_contract('echo.list')
def test_get_query_and_headers(authz_case):
    response = authz_case.run()
    assert response.data['method'] == 'GET'
    assert response.data['query'] == {
        'existing': ['yes'],
        'tag': ['owned', 'active'],
    }
    assert response.data['source'] == 'matrix'


@pytest.mark.authz_contract('echo.create')
def test_post_json(authz_case):
    response = authz_case.run()
    assert response.data['method'] == 'POST'
    assert response.data['data'] == {
        'name': 'updated',
        'nested': {'enabled': True},
    }
    assert response.data['source'] == 'matrix'
    assert response.data['content_type'] == 'application/json'


@pytest.mark.authz_contract('echo.replace')
def test_put_json(authz_case):
    response = authz_case.run()
    assert response.data['method'] == 'PUT'
    assert response.data['data']['name'] == 'updated'
    assert response.data['content_type'] == 'application/json'


@pytest.mark.authz_contract('echo.partial')
def test_patch_multipart(authz_case):
    response = authz_case.run()
    assert response.data['method'] == 'PATCH'
    assert response.data['data']['name'] == 'partial'
    assert response.data['content_type'].startswith('multipart/form-data;')


@pytest.mark.authz_contract('echo.delete')
def test_delete_json(authz_case):
    response = authz_case.run()
    assert response.data['method'] == 'DELETE'
    assert response.data['data']['name'] == 'updated'
    assert response.data['content_type'] == 'application/json'


@pytest.mark.authz_contract('echo.form')
def test_post_default_form(authz_case):
    response = authz_case.run()
    assert response.data['method'] == 'POST'
    assert response.data['data']['name'] == 'form-default'
    assert response.data['content_type'].startswith('multipart/form-data;')
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=6)
