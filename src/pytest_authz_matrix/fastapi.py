"""Run FastAPI authorization checks directly from Python."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from pytest_authz_matrix.adapters.fastapi import FastAPIAdapter, iter_fastapi_routes
from pytest_authz_matrix.exceptions import AuthzConfigurationError
from pytest_authz_matrix.permissions import Permission as Permission
from pytest_authz_matrix.permissions import RouteKey, expected_statuses


class _ActorClient(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class FastAPICheckResult:
    """Number of checks performed and any route that still needs test input."""

    checked: int
    unclassified: tuple[RouteKey, ...]
    needs_path: tuple[RouteKey, ...]


def check_fastapi(
    app: Any,
    *,
    permissions: Mapping[RouteKey, Permission | int | Mapping[str, Permission | int]] | None = None,
    actors: Mapping[str, _ActorClient] | None = None,
    paths: Mapping[RouteKey, str] | None = None,
    payloads: Mapping[RouteKey, Any] | None = None,
) -> FastAPICheckResult:
    """Assert the access expectations of explicitly configured and recognized routes.

    The default anonymous actor has no credentials. Built-in required security
    dependencies imply an anonymous rejection. Custom policies can declare
    expected outcomes for any supplied actor client.
    """
    if not FastAPIAdapter().supports_app(app):
        raise AuthzConfigurationError("check_fastapi() requires a FastAPI application")

    from fastapi.testclient import TestClient
    from starlette.routing import compile_path

    policies = permissions or {}
    clients = dict(actors or {})
    route_paths = paths or {}
    bodies = payloads or {}
    routes: dict[RouteKey, Any] = {}
    for route, dependant in iter_fastapi_routes(app):
        routes.setdefault((route.method, route.pattern), dependant)

    unknown = (policies.keys() | route_paths.keys() | bodies.keys()) - routes.keys()
    if unknown:
        raise AuthzConfigurationError(f"Unknown FastAPI routes: {sorted(unknown)!r}")

    unclassified = []
    needs_path = []
    checks = []
    for key, dependant in routes.items():
        policy = policies.get(key)
        if policy is None:
            if not _requires_credentials(dependant):
                unclassified.append(key)
                continue
            policy = Permission.AUTHENTICATED

        path = route_paths.get(key, key[1])
        if key not in route_paths and "{" in path:
            if key in policies:
                raise AuthzConfigurationError(f"Provide a concrete test path for {key!r}")
            needs_path.append(key)
            continue
        url = urlsplit(path)
        pattern, _, _ = compile_path(key[1])
        if (
            not path.startswith("/")
            or path.startswith("//")
            or url.scheme
            or url.netloc
            or url.fragment
            or not pattern.fullmatch(url.path)
        ):
            raise AuthzConfigurationError(f"Test path {path!r} does not match {key[1]!r}")

        expectations = policy if isinstance(policy, Mapping) else {"anonymous": policy}
        if not expectations:
            raise AuthzConfigurationError(f"Empty permission policy for {key[0]} {key[1]}")
        for actor, expectation in expectations.items():
            if actor != "anonymous" and actor not in clients:
                raise AuthzConfigurationError(f"No test client supplied for actor {actor!r}")
            checks.append((key, path, actor, expectation, expected_statuses(expectation)))

    if not checks:
        raise AuthzConfigurationError(
            "No FastAPI authorization checks were generated. "
            f"Unclassified routes: {unclassified!r}. Routes needing paths: {needs_path!r}."
        )

    with ExitStack() as stack:
        anonymous = None
        if "anonymous" not in clients and any(case[2] == "anonymous" for case in checks):
            anonymous = stack.enter_context(TestClient(app))
            clients["anonymous"] = anonymous

        failures = []
        for key, path, actor, expectation, statuses in checks:
            if actor == "anonymous" and anonymous is not None:
                anonymous.cookies.clear()
            request_options = {"json": bodies[key]} if key in bodies else {}
            response = clients[actor].request(
                key[0], path, follow_redirects=False, **request_options
            )
            if response.status_code not in statuses:
                label = expectation.value if isinstance(expectation, Permission) else expectation
                failures.append(
                    f"{key[0]} {path} ({actor}): expected {label}, got HTTP {response.status_code}"
                )

    if failures:
        raise AssertionError("FastAPI authorization checks failed:\n" + "\n".join(failures))
    return FastAPICheckResult(len(checks), tuple(unclassified), tuple(needs_path))


def _requires_credentials(dependant: Any) -> bool:
    from fastapi.security import (
        APIKeyCookie,
        APIKeyHeader,
        APIKeyQuery,
        HTTPBasic,
        HTTPBearer,
        HTTPDigest,
        OAuth2,
        OAuth2AuthorizationCodeBearer,
        OAuth2PasswordBearer,
        OpenIdConnect,
    )

    security_types = {
        APIKeyCookie,
        APIKeyHeader,
        APIKeyQuery,
        HTTPBasic,
        HTTPBearer,
        HTTPDigest,
        OAuth2,
        OAuth2AuthorizationCodeBearer,
        OAuth2PasswordBearer,
        OpenIdConnect,
    }

    def required(node: Any) -> bool:
        call = node.call
        return (type(call) in security_types and bool(call.auto_error)) or any(
            required(child) for child in node.dependencies
        )

    return required(dependant)
