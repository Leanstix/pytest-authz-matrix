from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from pytest_authz_matrix.case import AuthorizationCase
from pytest_authz_matrix.models import (
    ActorSpec,
    CaseSpec,
    ContractSpec,
    Expectation,
    ResourceSpec,
)


@dataclass
class Booking:
    id: int


class FakeRequest:
    def __init__(self, fixtures: dict[str, Any]) -> None:
        self.fixtures = fixtures

    def getfixturevalue(self, name: str) -> Any:
        return self.fixtures[name]


def test_authorization_case_runs_through_fastapi_adapter() -> None:
    app = FastAPI()

    @app.get("/bookings/{booking_id}")
    def get_booking(booking_id: int, x_actor: str | None = Header(default=None)):
        if x_actor != "owner" or booking_id != 1:
            raise HTTPException(status_code=404)
        return {"id": booking_id}

    client = TestClient(app, headers={"X-Actor": "owner"})
    contract = ContractSpec(
        name="booking.retrieve",
        method="GET",
        path="/bookings/{resource}",
        resource="booking",
        matrix={},
    )
    spec = CaseSpec(
        contract=contract,
        actor=ActorSpec("owner", "owner_client"),
        resource=ResourceSpec("booking", "booking_matrix", lookup="id"),
        relationship="owned",
        expectation=Expectation("allow", (200,)),
    )
    request = FakeRequest(
        {
            "owner_client": client,
            "booking_matrix": {"owned": Booking(1)},
        }
    )

    response = AuthorizationCase(request, spec).run()

    assert response.status_code == 200
