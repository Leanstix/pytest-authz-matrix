"""Runtime API exposed to generated pytest authorization cases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlencode

from pytest_authz_matrix.exceptions import AuthzExecutionError
from pytest_authz_matrix.models import CaseSpec
from pytest_authz_matrix.templating import related_object, render_path

_UNSET = object()


class CaseRecorder(Protocol):
    """Reporting hook implemented by the pytest runtime."""

    def record_case(self, spec: CaseSpec, *, passed: bool, actual_status: int | None) -> None:
        """Record the result of one case assertion."""


class AuthorizationCase:
    """A generated actor/resource test case.

    Call :meth:`run` for the standard request-and-assert workflow. Use
    :meth:`execute` and :meth:`assert_response` separately when a test needs to
    inspect the response or application state between those operations.
    """

    def __init__(self, request: Any, spec: CaseSpec, recorder: CaseRecorder | None = None) -> None:
        self._request = request
        self.spec = spec
        self._recorder = recorder
        self._resource_object: Any = _UNSET

    @property
    def actor(self) -> str:
        return self.spec.actor.name

    @property
    def relationship(self) -> str | None:
        return self.spec.relationship

    @property
    def outcome(self) -> str:
        return self.spec.expectation.outcome

    @property
    def resource(self) -> Any | None:
        """Resolve and cache the current relationship object."""

        if self._resource_object is _UNSET:
            if self.spec.resource is None:
                self._resource_object = None
            else:
                container = self._fixture(self.spec.resource.fixture)
                if self.relationship is None:
                    raise AuthzExecutionError("Generated resource case has no relationship name")
                self._resource_object = related_object(container, self.relationship)
        return self._resource_object

    @property
    def path(self) -> str:
        """Return the URL for this case after resolving its resource placeholder."""

        return render_path(
            self.spec.contract.path,
            resource=self.resource,
            resource_spec=self.spec.resource,
            params=self.spec.contract.params,
        )

    def execute(
        self,
        *,
        data: Any = _UNSET,
        query: Any = _UNSET,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Send this case through the actor's configured API client fixture."""

        client = self._fixture(self.spec.actor.client_fixture)
        request_spec = self.spec.contract.request
        request_data = self._optional_fixture(request_spec.data_fixture) if data is _UNSET else data
        query_data = (
            self._optional_fixture(request_spec.query_fixture) if query is _UNSET else query
        )
        path = _append_query(self.path, query_data)
        request_headers = dict(request_spec.headers)
        if headers:
            request_headers.update(headers)

        kwargs = _request_kwargs(
            client,
            method=self.spec.contract.method,
            data=request_data,
            format=request_spec.format,
            headers=request_headers,
        )

        method = self.spec.contract.method.lower()
        sender = getattr(client, method, None)
        if callable(sender):
            return sender(path, **kwargs)
        generic = getattr(client, "generic", None)
        if callable(generic):
            return generic(self.spec.contract.method, path, **kwargs)
        raise AuthzExecutionError(
            f"Fixture {self.spec.actor.client_fixture!r} has neither {method}() nor generic()"
        )

    def assert_response(self, response: Any) -> Any:
        """Assert the configured status outcome and return the response unchanged."""

        status = getattr(response, "status_code", None)
        expected = self.spec.expectation.statuses
        passed = isinstance(status, int) and status in expected
        if self._recorder is not None:
            self._recorder.record_case(self.spec, passed=passed, actual_status=status)
        if not passed:
            expected_text = ", ".join(str(item) for item in expected)
            detail = _response_detail(response)
            raise AssertionError(
                f"{self.spec.id} expected HTTP {expected_text}, got {status!r}{detail}"
            )
        return response

    def run(self, **request_overrides: Any) -> Any:
        """Execute this case, assert its status, and return the response."""

        return self.assert_response(self.execute(**request_overrides))

    def _fixture(self, name: str) -> Any:
        try:
            return self._request.getfixturevalue(name)
        except Exception as exc:
            raise AuthzExecutionError(f"Could not resolve pytest fixture {name!r}") from exc

    def _optional_fixture(self, name: str | None) -> Any | None:
        return self._fixture(name) if name else None


def _append_query(path: str, query: Any | None) -> str:
    if query is None:
        return path
    if isinstance(query, str):
        encoded = query.lstrip("?")
    else:
        try:
            encoded = urlencode(query, doseq=True)
        except (TypeError, ValueError) as exc:
            raise AuthzExecutionError(
                "Query fixture must be a string or urlencode-compatible value"
            ) from exc
    if not encoded:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{encoded}"


def _request_kwargs(
    client: Any,
    *,
    method: str,
    data: Any | None,
    format: str | None,
    headers: dict[str, str],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if data is not None:
        kwargs["data"] = data
        if _is_drf_client(client):
            if format is not None:
                kwargs["format"] = format
        elif _is_django_client(client):
            django_data, content_type = _django_request_data(method, data, format)
            kwargs["data"] = django_data
            if content_type is not None:
                kwargs["content_type"] = content_type
        elif format is not None:
            kwargs["format"] = format
    if headers:
        kwargs["headers"] = headers
    return kwargs


def _is_drf_client(client: Any) -> bool:
    return any(cls.__module__.startswith("rest_framework.") for cls in type(client).__mro__)


def _is_django_client(client: Any) -> bool:
    return any(cls.__module__.startswith("django.test") for cls in type(client).__mro__)


def _django_request_data(method: str, data: Any, format: str | None) -> tuple[Any, str | None]:
    if format is None:
        return data, None
    if format == "json":
        return data, "application/json"
    if format == "multipart":
        try:
            from django.test.client import (  # type: ignore[import-untyped]
                BOUNDARY,
                MULTIPART_CONTENT,
                encode_multipart,
            )
        except ImportError as exc:
            raise AuthzExecutionError("Django test client support requires Django") from exc
        if method == "POST":
            return data, MULTIPART_CONTENT
        try:
            encoded = encode_multipart(BOUNDARY, data)
        except (AttributeError, TypeError, ValueError) as exc:
            raise AuthzExecutionError(
                "Django multipart request data must be a mapping"
            ) from exc
        return encoded, MULTIPART_CONTENT
    raise AuthzExecutionError(
        f"Django test client does not support request format {format!r}; "
        "use 'json', 'multipart', or null"
    )


def _response_detail(response: Any) -> str:
    value = getattr(response, "data", None)
    if value is None:
        value = getattr(response, "content", None)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if value in (None, "", b""):
        return ""
    rendered = repr(value)
    if len(rendered) > 300:
        rendered = rendered[:297] + "..."
    return f"; response={rendered}"
