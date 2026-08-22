from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pytest_authz_matrix.case import AuthorizationCase
from pytest_authz_matrix.exceptions import AuthzExecutionError
from pytest_authz_matrix.models import (
    ActorSpec,
    CaseSpec,
    ContractSpec,
    Expectation,
    RequestSpec,
    ResourceSpec,
)


@dataclass
class Booking:
    pk: int
    public_id: str


@dataclass
class Response:
    status_code: int
    data: Any = None


class FakeClient:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def patch(self, path: str, **kwargs: Any) -> Response:
        self.calls.append(("PATCH", path, kwargs))
        return Response(self.status, {"path": path})


class GenericOnlyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def generic(self, method: str, path: str, **kwargs: Any) -> Response:
        self.calls.append((method, path, kwargs))
        return Response(200)


class FakeRequest:
    def __init__(self, fixtures: dict[str, Any]) -> None:
        self.fixtures = fixtures

    def getfixturevalue(self, name: str) -> Any:
        return self.fixtures[name]


def make_case(
    status: int = 200, expected: tuple[int, ...] = (200,)
) -> tuple[AuthorizationCase, FakeClient]:
    client = FakeClient(status)
    contract = ContractSpec(
        name="booking.update",
        method="PATCH",
        path="/estates/{params.estate}/bookings/{resource.public_id}/",
        resource="booking",
        params={"estate": "estate 1"},
        request=RequestSpec(
            data_fixture="payload",
            query_fixture="query",
            format="json",
            headers={"X-Request-Source": "authz"},
        ),
        matrix={},
    )
    spec = CaseSpec(
        contract=contract,
        actor=ActorSpec("owner", "owner_client"),
        resource=ResourceSpec("booking", "booking_matrix", lookup="pk"),
        relationship="owned",
        expectation=Expectation("allow", expected),
    )
    request = FakeRequest(
        {
            "owner_client": client,
            "booking_matrix": {"owned": Booking(pk=4, public_id="B/42")},
            "payload": {"status": "approved"},
            "query": {"notify": "yes", "tag": ["a", "b"]},
        }
    )
    return AuthorizationCase(request, spec), client


def test_executes_request_with_rendered_path_and_fixture_data() -> None:
    case, client = make_case()

    response = case.run()

    assert response.status_code == 200
    assert client.calls == [
        (
            "PATCH",
            "/estates/estate%201/bookings/B%2F42/?notify=yes&tag=a&tag=b",
            {
                "data": {"status": "approved"},
                "format": "json",
                "headers": {"X-Request-Source": "authz"},
            },
        )
    ]


def test_allows_request_overrides() -> None:
    case, client = make_case()

    case.run(data={"status": "rejected"}, query="dry_run=1", headers={"X-Test": "1"})

    assert client.calls[0][1].endswith("?dry_run=1")
    assert client.calls[0][2]["data"] == {"status": "rejected"}
    assert client.calls[0][2]["headers"]["X-Test"] == "1"


def test_failure_explains_case_and_response() -> None:
    case, _ = make_case(status=403, expected=(200, 204))

    with pytest.raises(AssertionError, match=r"booking.update\[owner-owned-allow\].*200, 204.*403"):
        case.run()


def test_missing_relationship_has_actionable_error() -> None:
    case, _ = make_case()
    case._request.fixtures["booking_matrix"] = {}  # type: ignore[attr-defined]

    with pytest.raises(AuthzExecutionError, match="relationship 'owned'"):
        _ = case.resource


def test_falls_back_to_generic_client_method() -> None:
    case, _ = make_case()
    client = GenericOnlyClient()
    case._request.fixtures["owner_client"] = client  # type: ignore[attr-defined]

    case.run()

    assert client.calls == [
        (
            "PATCH",
            "/estates/estate%201/bookings/B%2F42/?notify=yes&tag=a&tag=b",
            {
                "data": {"status": "approved"},
                "format": "json",
                "headers": {"X-Request-Source": "authz"},
            },
        )
    ]


def test_rejects_client_without_method_or_generic_sender() -> None:
    case, _ = make_case()
    case._request.fixtures["owner_client"] = object()  # type: ignore[attr-defined]

    with pytest.raises(AuthzExecutionError, match=r"neither patch\(\) nor generic\(\)"):
        case.execute()
