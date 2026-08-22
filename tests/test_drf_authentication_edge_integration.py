from __future__ import annotations

from textwrap import dedent

import pytest


def _write_project_file(pytester: pytest.Pytester, path: str, content: str) -> None:
    target = pytester.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(content).lstrip(), encoding="utf-8")


def test_real_session_csrf_cookie_logout_and_token_authentication(
    pytester: pytest.Pytester,
) -> None:
    _write_project_file(pytester, "auth_project/__init__.py", "")
    _write_project_file(
        pytester,
        "auth_project/settings.py",
        """
        from pathlib import Path

        BASE_DIR = Path(__file__).resolve().parent.parent
        SECRET_KEY = 'test'
        DEBUG = False
        ALLOWED_HOSTS = ['testserver']
        ROOT_URLCONF = 'auth_project.urls'
        INSTALLED_APPS = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'rest_framework',
            'rest_framework.authtoken',
        ]
        MIDDLEWARE = [
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
        ]
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
        DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
        USE_TZ = True
        """,
    )
    _write_project_file(
        pytester,
        "auth_project/urls.py",
        """
        from django.http import JsonResponse
        from django.urls import path
        from django.views.decorators.csrf import ensure_csrf_cookie
        from rest_framework.authentication import SessionAuthentication, TokenAuthentication
        from rest_framework.permissions import IsAuthenticated
        from rest_framework.response import Response
        from rest_framework.views import APIView


        @ensure_csrf_cookie
        def csrf_cookie(request):
            return JsonResponse({'csrf': 'set'})


        class SessionView(APIView):
            authentication_classes = (SessionAuthentication,)
            permission_classes = (IsAuthenticated,)

            def post(self, request):
                return Response({'username': request.user.username})


        class TokenView(APIView):
            authentication_classes = (TokenAuthentication,)
            permission_classes = (IsAuthenticated,)

            def get(self, request):
                return Response({'username': request.user.username})


        urlpatterns = [
            path('csrf/', csrf_cookie, name='csrf-cookie'),
            path('session/', SessionView.as_view(), name='session-protected'),
            path('token/', TokenView.as_view(), name='token-protected'),
        ]
        """,
    )
    _write_project_file(
        pytester,
        "pytest.ini",
        """
        [pytest]
        DJANGO_SETTINGS_MODULE = auth_project.settings
        """,
    )
    _write_project_file(
        pytester,
        "conftest.py",
        """
        import pytest
        from django.contrib.auth import get_user_model
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient


        @pytest.fixture
        def user(db):
            return get_user_model().objects.create_user(
                username='matrix-member',
                password='test-password',
            )


        @pytest.fixture
        def session_client(user):
            client = APIClient(enforce_csrf_checks=True)
            client.force_login(user)
            client.get('/csrf/')
            client.credentials(HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
            return client


        @pytest.fixture
        def missing_csrf_client(user):
            client = APIClient(enforce_csrf_checks=True)
            client.force_login(user)
            return client


        @pytest.fixture
        def logged_out_client(user):
            client = APIClient(enforce_csrf_checks=True)
            client.force_login(user)
            client.logout()
            return client


        @pytest.fixture
        def token_client(user):
            token = Token.objects.create(user=user)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
            return client


        @pytest.fixture
        def invalid_token_client():
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION='Token invalid-token')
            return client


        @pytest.fixture
        def anonymous_client():
            return APIClient()
        """,
    )
    _write_project_file(
        pytester,
        "authz-matrix.yml",
        """
        version: 1
        actors:
          session: session_client
          missing_csrf: missing_csrf_client
          logged_out: logged_out_client
          token: token_client
          invalid_token: invalid_token_client
          anonymous: anonymous_client
        contracts:
          authentication.session:
            method: POST
            path: /session/
            route_name: session-protected
            request:
              data_fixture: session_payload
              format: json
            matrix:
              session: allow
              missing_csrf: deny
              logged_out: deny
          authentication.token:
            method: GET
            path: /token/
            route_name: token-protected
            matrix:
              token: allow
              invalid_token: unauthenticated
              anonymous: unauthenticated
        """,
    )
    _write_project_file(
        pytester,
        "test_authentication.py",
        """
        import pytest


        @pytest.fixture
        def session_payload():
            return {'operation': 'write'}


        @pytest.mark.django_db
        @pytest.mark.authz_contract('authentication.session')
        def test_session_authentication(authz_case):
            response = authz_case.run()
            if authz_case.actor == 'session':
                assert response.data == {'username': 'matrix-member'}


        @pytest.mark.django_db
        @pytest.mark.authz_contract('authentication.token')
        def test_token_authentication(authz_case):
            response = authz_case.run()
            if authz_case.actor == 'token':
                assert response.data == {'username': 'matrix-member'}
        """,
    )

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-report",
        "--authz-require-complete",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=6)
    result.stdout.fnmatch_lines(["*DRF route coverage: 2/2 (100.0%)*"])
