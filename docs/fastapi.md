# FastAPI integration

`pytest-authz-matrix` 0.2 adds first-class FastAPI support while keeping the same authorization
contract format used by Django REST Framework.

## Install

```bash
pip install "pytest-authz-matrix[fastapi]"
```

The extra installs FastAPI and HTTPX. FastAPI's synchronous test client is Starlette's
HTTPX-backed `TestClient`.

## Actor fixtures

Return a `TestClient` that already represents the actor:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def admin_client(admin_token):
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {admin_token}"},
    )


@pytest.fixture
def anonymous_client():
    return TestClient(app)
```

The adapter is selected automatically from the client. No framework key is needed in YAML.

## Resource fixture

```python
@pytest.fixture
def booking_matrix(owner_booking, foreign_booking):
    return {
        "owned": owner_booking,
        "foreign": foreign_booking,
    }
```

Choose the API identifier using `lookup`:

```yaml
resources:
  booking:
    fixture: booking_matrix
    lookup: id
```

## Contract

```yaml
version: 1

actors:
  owner: owner_client
  outsider: outsider_client
  anonymous: anonymous_client

resources:
  booking:
    fixture: booking_matrix
    lookup: id

contracts:
  booking.retrieve:
    method: GET
    path: /bookings/{resource}
    route_name: booking-detail
    resource: booking
    matrix:
      owner:
        owned: allow
        foreign: conceal
      outsider:
        owned: conceal
        foreign: conceal
      anonymous:
        owned: unauthenticated
        foreign: unauthenticated
```

## Test

```python
import pytest


@pytest.mark.authz_contract("booking.retrieve")
def test_booking_authorization(authz_case):
    authz_case.run()
```

## JSON and form bodies

`format: json` is the default and is translated to FastAPI/HTTPX `json=payload` semantics.

```yaml
request:
  data_fixture: update_payload
  format: json
```

For form-encoded requests use `format: form`, `format: data`, or `format: null`.

## Route coverage

FastAPI route discovery inventories registered `APIRoute` objects and excludes framework utility
routes that are not API path operations. A contract is matched by HTTP method plus route name when
available, falling back to normalized path matching.

```bash
pytest --authz-report
pytest --authz-fail-under=90
```

Example output:

```text
FastAPI route coverage: 12/14 (85.7%)
  missing: DELETE delete-booking
  missing: GET health
```

## Wrapped clients

If a custom fixture returns a wrapper rather than the `TestClient` itself, the plugin might not be
able to extract the FastAPI application for route discovery. Override `authz_app`:

```python
@pytest.fixture
def authz_app():
    return app
```

## What is not auto-detected yet

Version 0.2 detects the framework and route surface. It does not claim to infer arbitrary business
permission policy. OAuth scopes and structured FastAPI security dependencies are candidates for a
future permission-introspection layer, while ownership and tenant policy will still require
application context or developer confirmation.
