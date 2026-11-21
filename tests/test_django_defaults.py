from __future__ import annotations

import pytest


@pytest.fixture
def django_project(pytester: pytest.Pytester) -> pytest.Pytester:
    pytester.makeconftest(
        """
import django
from django.conf import settings

settings.configure(
    SECRET_KEY="test",
    ROOT_URLCONF="app_urls",
    ALLOWED_HOSTS=["testserver"],
    INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes"],
    LOGIN_URL="/login/",
)
# Keep the anonymous client independent of sessions and a database.
class AnonymousMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        return self.get_response(request)

settings.MIDDLEWARE = ["conftest.AnonymousMiddleware"]
django.setup()
"""
    )
    return pytester


def test_django_builtin_and_explicit_permissions(django_project: pytest.Pytester) -> None:
    django_project.makepyfile(
        app_urls="""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import include, path
from django.views import View
from django.views.decorators.http import require_POST

@login_required(login_url="/sign-in/")
@require_POST
def protected(request, pk):
    raise AssertionError("anonymous actor reached the protected view")

class Private(LoginRequiredMixin, View):
    raise_exception = True

    def get(self, request):
        raise AssertionError("anonymous actor reached the protected view")

@user_passes_test(lambda user: True)
def public(request):
    return HttpResponse()

urlpatterns = [
    path("team/", include(([path("private/", Private.as_view()),
                            path("edit/<int:pk>/", protected),
                            path("open/", public)], "team"), namespace="team")),
]
"""
    )
    django_project.makepyfile(
        """
import pytest

from pytest_authz_matrix.django import Permission, check_django
from pytest_authz_matrix.exceptions import AuthzConfigurationError

def test_builtin_permissions():
    result = check_django()
    assert result.checked == 1
    assert result.unclassified == (("GET", "/team/open/"),)
    assert result.needs_path == (("POST", "/team/edit/<int:pk>/"),)

def test_custom_permissions_and_paths():
    key = ("POST", "/team/edit/<int:pk>/")
    result = check_django(
        permissions={("GET", "/team/open/"): Permission.PUBLIC},
        paths={key: "/team/edit/4/"},
    )
    assert result.checked == 3
    assert not result.needs_path
    with pytest.raises(AuthzConfigurationError, match="does not match"):
        check_django(paths={key: "/team/open/"})
"""
    )
    django_project.runpytest_subprocess("-q").assert_outcomes(passed=2)


def test_django_requires_a_login_redirect_and_rejects_unclassified_projects(
    django_project: pytest.Pytester,
) -> None:
    django_project.makepyfile(
        app_urls="""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.urls import path
from django.views import View

class Private(LoginRequiredMixin, View):
    def handle_no_permission(self):
        return HttpResponseRedirect("/wrong/")

    def get(self, request):
        return HttpResponseRedirect("/wrong/")

urlpatterns = [path("private/", Private.as_view())]
"""
    )
    django_project.makepyfile(
        """
import pytest
from django.test import override_settings
from django.urls import path
from django.http import HttpResponse

from pytest_authz_matrix.django import check_django
from pytest_authz_matrix.exceptions import AuthzConfigurationError

class PublicURLs:
    urlpatterns = [path("public/", lambda request: HttpResponse())]

def test_wrong_redirect():
    with pytest.raises(AssertionError, match="login redirect to /login/"):
        check_django()

def test_no_cases():
    with override_settings(ROOT_URLCONF=PublicURLs):
        with pytest.raises(AuthzConfigurationError, match="No Django authorization checks"):
            check_django()
"""
    )
    django_project.runpytest_subprocess("-q").assert_outcomes(passed=2)
