from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class SmokeResponse:
    status_code: int


class SmokeClient:
    def get(self, path: str) -> SmokeResponse:
        assert path == "/health"
        return SmokeResponse(status_code=200)


@pytest.fixture
def smoke_client() -> SmokeClient:
    return SmokeClient()
