"""Run Django authorization checks directly from Python."""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import FunctionType
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

from pytest_authz_matrix.adapters.django import _view_methods
from pytest_authz_matrix.exceptions import AuthzConfigurationError
from pytest_authz_matrix.permissions import Permission as Permission
from pytest_authz_matrix.permissions import RouteKey, expected_statuses

_LOGIN_MIDDLEWARE = "django.contrib.auth.middleware.LoginRequiredMiddleware"
_LITERAL_REGEX = re.compile(r"(?:[\w/ -]|\\\.)*")


class _DjangoClient(Protocol):
    def generic(self, method: str, path: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class DjangoCheckResult:
    """Number of checks performed and routes that still need test input."""

    checked: int
    unclassified: tuple[RouteKey, ...]
    needs_path: tuple[RouteKey, ...]


@dataclass(frozen=True)
class _LoginRedirect:
    url: str

    def accepts(self, response: Any) -> bool:
        location = response.get("Location")
        if response.status_code != 302 or not location:
            return False
        actual = urlsplit(location)
        expected = urlsplit(self.url)
        return (actual.scheme, actual.netloc, actual.path) == (
            expected.scheme,
            expected.netloc,
            expected.path,
        )


def check_django(
    *,
    permissions: Mapping[RouteKey, Permission | int | Mapping[str, Permission | int]] | None = None,
    actors: Mapping[str, _DjangoClient] | None = None,
    paths: Mapping[RouteKey, str] | None = None,
    payloads: Mapping[RouteKey, Any] | None = None,
) -> DjangoCheckResult:
    """Check declared authentication requirements against the configured Django URLconf."""
    from django.apps import apps  # type: ignore[import-untyped]
    from django.test import Client  # type: ignore[import-untyped]
    from django.urls import Resolver404, get_resolver, resolve  # type: ignore[import-untyped]

    if not apps.ready:
        raise AuthzConfigurationError("Initialize Django before calling check_django()")

    overrides = permissions or {}
    urls = paths or {}
    bodies = payloads or {}
    clients = dict(actors or {})
    explicit = overrides.keys() | urls.keys() | bodies.keys()
    routes: dict[RouteKey, tuple[str | None, Any, Any]] = {}
    for pattern, literal, callback in _patterns(get_resolver().url_patterns):
        view = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
        methods = (
            set(_view_methods(callback, view)) if view is not None else _function_methods(callback)
        )
        if view is None:
            methods.update(method for method, route in explicit if route == pattern)
        for method in sorted(methods):
            routes.setdefault((method, pattern), (literal, callback, view))

    unknown = explicit - routes.keys()
    if unknown:
        raise AuthzConfigurationError(f"Unknown Django routes: {sorted(unknown)!r}")

    unclassified = []
    needs_path = []
    checks = []
    for key, (literal, callback, view) in routes.items():
        method, pattern = key
        policy = overrides.get(key)
        inferred = _django_policy(callback, view, method) if policy is None else None
        if policy is None and inferred is None:
            unclassified.append(key)
            continue

        target = urls.get(key, literal)
        if target is None:
            if key in overrides:
                raise AuthzConfigurationError(f"Provide a concrete test path for {key!r}")
            needs_path.append(key)
            continue

        parsed = urlsplit(target)
        if not target.startswith("/") or target.startswith("//") or parsed.fragment:
            raise AuthzConfigurationError(f"Test path must be a local URL path: {target!r}")
        try:
            match = resolve(unquote(parsed.path))
        except Resolver404:
            match = None
        if match is None or match.func is not callback or _route_label(match.route) != pattern:
            if key in urls or key in overrides:
                raise AuthzConfigurationError(f"Test path {target!r} does not match {pattern!r}")
            needs_path.append(key)
            continue

        expectations: Mapping[str, Permission | int | _LoginRedirect | None]
        if policy is None:
            expectations = {"anonymous": inferred}
        elif isinstance(policy, Mapping):
            expectations = policy
        else:
            expectations = {"anonymous": policy}
        if not expectations:
            raise AuthzConfigurationError(f"Empty permission policy for {method} {pattern}")

        for actor, expectation in expectations.items():
            if actor != "anonymous" and actor not in clients:
                raise AuthzConfigurationError(f"No test client supplied for actor {actor!r}")
            assert expectation is not None
            statuses = (
                expectation
                if isinstance(expectation, _LoginRedirect)
                else expected_statuses(expectation)
            )
            checks.append((method, target, key, actor, expectation, statuses))

    if not checks:
        raise AuthzConfigurationError(
            "No Django authorization checks were generated. "
            f"Unclassified routes: {unclassified!r}. Routes needing paths: {needs_path!r}."
        )

    failures = []
    for method, target, key, actor, expectation, statuses in checks:
        client = clients.get(actor) if actor in clients else Client()
        assert client is not None
        kwargs = (
            {"data": json.dumps(bodies[key]), "content_type": "application/json"}
            if key in bodies
            else {}
        )
        response = client.generic(method, target, **kwargs)
        passed = (
            statuses.accepts(response)
            if isinstance(statuses, _LoginRedirect)
            else response.status_code in statuses
        )
        if not passed:
            label = (
                f"login redirect to {expectation.url}"
                if isinstance(expectation, _LoginRedirect)
                else expectation.value
                if isinstance(expectation, Permission)
                else expectation
            )
            failures.append(
                f"{method} {key[1]} ({actor}): expected {label}, got HTTP {response.status_code}"
            )

    if failures:
        raise AssertionError("Django authorization checks failed:\n" + "\n".join(failures))
    return DjangoCheckResult(len(checks), tuple(unclassified), tuple(needs_path))


def _route_label(pattern: str) -> str:
    return "/" + pattern.lstrip("^/").removesuffix("$").removesuffix(r"\Z")


def _patterns(
    patterns: list[Any], prefix: str = "", base: str | None = ""
) -> Iterator[tuple[str, str | None, Any]]:
    from django.urls import URLPattern, URLResolver
    from django.urls.resolvers import RoutePattern  # type: ignore[import-untyped]

    for item in patterns:
        segment = str(item.pattern).lstrip("^").removesuffix("$").removesuffix(r"\Z")
        if isinstance(item.pattern, RoutePattern):
            literal = segment if not item.pattern.converters else None
        else:
            literal = segment.replace(r"\.", ".") if _LITERAL_REGEX.fullmatch(segment) else None
        concrete = None if literal is None or base is None else base + literal
        full_pattern = prefix + segment
        if isinstance(item, URLResolver):
            yield from _patterns(item.url_patterns, full_pattern, concrete)
        elif isinstance(item, URLPattern):
            yield (
                _route_label(full_pattern),
                ("/" + concrete if concrete is not None else None),
                (item.callback),
            )


def _django_policy(callback: Any, view: Any, method: str) -> Permission | _LoginRedirect | None:
    from django.conf import settings  # type: ignore[import-untyped]
    from django.contrib.auth.decorators import login_required  # type: ignore[import-untyped]
    from django.contrib.auth.mixins import LoginRequiredMixin  # type: ignore[import-untyped]
    from django.shortcuts import resolve_url  # type: ignore[import-untyped]

    if _LOGIN_MIDDLEWARE in settings.MIDDLEWARE and getattr(callback, "login_required", True):
        return _LoginRedirect(
            resolve_url(getattr(callback, "login_url", None) or settings.LOGIN_URL)
        )

    if view is not None and issubclass(view, LoginRequiredMixin):
        kwargs = getattr(callback, "view_initkwargs", {})
        if kwargs.get("raise_exception", view.raise_exception):
            return Permission.FORBIDDEN
        return _LoginRedirect(
            resolve_url(kwargs.get("login_url", view.login_url) or settings.LOGIN_URL)
        )

    # Older Django versions do not attach login metadata to the callback.
    reference = login_required(lambda request: None)
    wrapper_code = reference.__code__
    predicate_code = inspect.getclosurevars(reference).nonlocals["test_func"].__code__
    for wrapper in _wrapped_functions(callback):
        if wrapper.__code__ is wrapper_code:
            values = inspect.getclosurevars(wrapper).nonlocals
            predicate = values["test_func"]
            if getattr(predicate, "__code__", None) is predicate_code:
                login_url = getattr(wrapper, "login_url", values.get("login_url"))
                return _LoginRedirect(resolve_url(login_url or settings.LOGIN_URL))
    if _drf_requires_credentials(callback, view, method):
        return Permission.AUTHENTICATED
    return None


def _drf_requires_credentials(callback: Any, view: Any, method: str) -> bool:
    if view is None or not any(
        base.__module__ == "rest_framework.views" and base.__name__ == "APIView"
        for base in view.__mro__
    ):
        return False

    from rest_framework import permissions as drf  # type: ignore[import-untyped]
    from rest_framework.views import APIView  # type: ignore[import-untyped]

    if view.get_permissions is not APIView.get_permissions:
        return False
    classes = getattr(callback, "initkwargs", {}).get("permission_classes", view.permission_classes)
    return any(
        cls is drf.IsAuthenticated
        or cls is drf.IsAdminUser
        or cls is drf.DjangoModelPermissions
        or cls is drf.DjangoObjectPermissions
        or (cls is drf.IsAuthenticatedOrReadOnly and method not in drf.SAFE_METHODS)
        for cls in classes
    )


def _function_methods(callback: Any) -> set[str]:
    from django.views.decorators.http import require_GET  # type: ignore[import-untyped]

    reference = require_GET(lambda request: None)
    for wrapper in _wrapped_functions(callback):
        if wrapper.__code__ is reference.__code__:
            return set(inspect.getclosurevars(wrapper).nonlocals["request_method_list"])
    return {"GET"}


def _wrapped_functions(callback: Any) -> Iterator[FunctionType]:
    seen = set()
    while isinstance(callback, FunctionType) and id(callback) not in seen:
        seen.add(id(callback))
        yield callback
        callback = getattr(callback, "__wrapped__", None)
