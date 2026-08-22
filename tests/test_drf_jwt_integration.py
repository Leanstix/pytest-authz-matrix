from __future__ import annotations

from textwrap import dedent

import pytest


def _write_project_file(pytester: pytest.Pytester, path: str, content: str) -> None:
    target = pytester.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(content).lstrip(), encoding="utf-8")


def test_simplejwt_and_authentication_class_ordering(pytester: pytest.Pytester) -> None:
    _write_project_file(pytester, "jwt_project/__init__.py", "")
    _write_project_file(
        pytester,
        "jwt_project/settings.py",
        """
        from pathlib import Path

        BASE_DIR = Path(__file__).resolve().parent.parent
        SECRET_KEY = 'test'
        DEBUG = False
        ALLOWED_HOSTS = ['testserver']
        ROOT_URLCONF = 'jwt_project.urls'
        INSTALLED_APPS = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'rest_framework',
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
        "jwt_project/urls.py",
        """
        from django.urls import path
        from rest_framework.authentication import SessionAuthentication
        from rest_framework.permissions import IsAuthenticated
        from rest_framework.response import Response
        from rest_framework.views import APIView
        from rest_framework_simplejwt.authentication import JWTAuthentication


        class ProtectedView(APIView):
            permission_classes = (IsAuthenticated,)

            def get(self, request):
                return Response({'username': request.user.username})


        class JWTView(ProtectedView):
            authentication_classes = (JWTAuthentication,)


        class SessionFirstView(ProtectedView):
            authentication_classes = (SessionAuthentication, JWTAuthentication)


        class JWTFirstView(ProtectedView):
            authentication_classes = (JWTAuthentication, SessionAuthentication)


        urlpatterns = [
            path('jwt/', JWTView.as_view(), name='jwt-protected'),
            path('session-first/', SessionFirstView.as_view(), name='session-first'),
            path('jwt-first/', JWTFirstView.as_view(), name='jwt-first'),
        ]
        """,
    )
    _write_project_file(
        pytester,
        "pytest.ini",
        """
        [pytest]
        DJANGO_SETTINGS_MODULE = jwt_project.settings
        """,
    )
    _write_project_file(
        pytester,
        "conftest.py",
        """
        from datetime import timedelta

        import pytest
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


        @pytest.fixture
        def user(db):
            return get_user_model().objects.create_user(username='jwt-member')


        def bearer_client(token):
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            return client


        @pytest.fixture
        def jwt_client(user):
            return bearer_client(AccessToken.for_user(user))


        @pytest.fixture
        def expired_jwt_client(user):
            token = AccessToken.for_user(user)
            token.set_exp(lifetime=timedelta(seconds=-1))
            return bearer_client(token)


        @pytest.fixture
        def malformed_jwt_client():
            return bearer_client('not-a-jwt')


        @pytest.fixture
        def refresh_jwt_client(user):
            return bearer_client(RefreshToken.for_user(user))


        @pytest.fixture
        def anonymous_client():
            return APIClient()


        @pytest.fixture
        def session_client(user):
            client = APIClient()
            client.force_login(user)
            return client


        @pytest.fixture
        def invalid_jwt_with_session_client(user):
            client = APIClient()
            client.force_login(user)
            client.credentials(HTTP_AUTHORIZATION='Bearer not-a-jwt')
            return client
        """,
    )
    _write_project_file(
        pytester,
        "authz-matrix.yml",
        """
        version: 1
        actors:
          jwt: jwt_client
          expired_jwt: expired_jwt_client
          malformed_jwt: malformed_jwt_client
          refresh_jwt: refresh_jwt_client
          anonymous: anonymous_client
          session: session_client
          invalid_jwt_with_session: invalid_jwt_with_session_client
        contracts:
          authentication.jwt:
            method: GET
            path: /jwt/
            route_name: jwt-protected
            matrix:
              jwt: allow
              expired_jwt: unauthenticated
              malformed_jwt: unauthenticated
              refresh_jwt: unauthenticated
              anonymous: unauthenticated
          authentication.session-first:
            method: GET
            path: /session-first/
            route_name: session-first
            matrix:
              session: allow
              anonymous: deny
          authentication.jwt-first:
            method: GET
            path: /jwt-first/
            route_name: jwt-first
            matrix:
              session: allow
              invalid_jwt_with_session: unauthenticated
              anonymous: unauthenticated
        """,
    )
    _write_project_file(
        pytester,
        "test_jwt.py",
        """
        import pytest


        @pytest.mark.django_db
        @pytest.mark.authz_contract('authentication.jwt')
        def test_jwt_authentication(authz_case):
            response = authz_case.run()
            if authz_case.actor == 'jwt':
                assert response.data == {'username': 'jwt-member'}
            else:
                assert response['WWW-Authenticate'].startswith('Bearer')


        @pytest.mark.django_db
        @pytest.mark.authz_contract('authentication.session-first')
        def test_session_first_authentication(authz_case):
            response = authz_case.run()
            if authz_case.actor == 'anonymous':
                assert 'WWW-Authenticate' not in response


        @pytest.mark.django_db
        @pytest.mark.authz_contract('authentication.jwt-first')
        def test_jwt_first_authentication(authz_case):
            response = authz_case.run()
            if authz_case.actor != 'session':
                assert response['WWW-Authenticate'].startswith('Bearer')
        """,
    )

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-report",
        "--authz-require-complete",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=10)
    result.stdout.fnmatch_lines(["*DRF route coverage: 3/3 (100.0%)*"])
