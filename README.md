# pytest-authz-matrix

[![CI](https://github.com/Leanstix/pytest-authz-matrix/actions/workflows/ci.yml/badge.svg)](https://github.com/Leanstix/pytest-authz-matrix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/Leanstix/pytest-authz-matrix/blob/main/LICENSE)

Authorization contract testing for Python web APIs.

`pytest-authz-matrix` expands one pytest test into the complete actor x resource-relationship
matrix for an endpoint. It has first-class adapters for **Django REST Framework** and **FastAPI**,
with a generic fallback for custom test clients.

It is built for authorization bugs ordinary authentication tests miss:

- a user retrieves another user's object by changing an ID;
- a tenant administrator reaches an object belonging to another tenant;
- a list endpoint leaks foreign rows while its detail endpoint is protected;
- an endpoint returns `403` when policy requires concealing existence with `404`;
- a new API route ships without a corresponding authorization contract.

> **Status:** `0.2.0` is alpha. Contracts remain explicit: the plugin discovers routes and tests
> declared authorization policy, but it does not guess arbitrary business authorization rules.

## Installation

Core only:

```bash
pip install pytest-authz-matrix
```

Django REST Framework:

```bash
pip install "pytest-authz-matrix[django]"
```

FastAPI:

```bash
pip install "pytest-authz-matrix[fastapi]"
```

## Quick start

Create `authz-matrix.yml` in the pytest root:

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
    path: /api/bookings/{resource}
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

Bind a pytest test to that contract:

```python
import pytest


@pytest.mark.authz_contract("booking.retrieve")
def test_booking_retrieve_authorization(authz_case):
    authz_case.run()
```

That single test expands into every configured actor/relationship combination with readable case
IDs.

## Django REST Framework

Actor fixtures can return DRF `APIClient` instances. Authentication remains application-owned:

```python
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def owner_client(owner):
    client = APIClient()
    client.force_authenticate(owner)
    return client
```

The DRF adapter preserves the existing `data=...`, `format=...`, and Django URL-resolver behavior.

## FastAPI

Actor fixtures return FastAPI/Starlette `TestClient` instances:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def owner_client(owner_token):
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
```

The framework is detected automatically. For a normal `TestClient`, no `framework:` key and no app
configuration are required. If a custom client wrapper hides the underlying application, override
the optional fixture:

```python
@pytest.fixture
def authz_app():
    return app
```

With `format: json` (the default), the FastAPI adapter sends the body through the client's `json=`
parameter. `format: form`, `format: data`, and `format: null` use form/data semantics.

See [`docs/fastapi.md`](docs/fastapi.md) and [`examples/fastapi`](examples/fastapi).

## Resource relationships

A resource fixture maps relationship names in YAML to real objects or mappings:

```python
@pytest.fixture
def booking_matrix(owner_booking, foreign_booking):
    return {
        "owned": owner_booking,
        "foreign": foreign_booking,
    }
```

`lookup` defaults to `pk`. Use `id`, `uuid`, `public_id`, or a nested attribute/key path when your
API uses another identifier.

## Outcomes

Built-in outcomes are HTTP status contracts:

| Outcome | Default status | Meaning |
|---|---:|---|
| `allow` | `200` | Actor may perform the operation. |
| `deny` | `403` | Authenticated but forbidden. |
| `conceal` | `404` | Resource existence must not be disclosed. |
| `unauthenticated` | `401` | Authentication is required. |

Override defaults globally or override a single matrix cell when an endpoint legitimately returns
another success/error status.

## Mutating endpoints

Request bodies, query strings, and headers can come from fixtures:

```yaml
contracts:
  booking.update:
    method: PATCH
    path: /api/bookings/{resource}
    route_name: booking-update
    resource: booking
    request:
      data_fixture: booking_update_payload
      query_fixture: update_query
      format: json
      headers:
        X-Test-Source: authz-matrix
    matrix:
      owner:
        owned: allow
        foreign: conceal
```

For side-effect assertions, split execution from the response assertion:

```python
response = authz_case.execute()
# inspect state here
authz_case.assert_response(response)
```

`execute()` also accepts per-test `data`, `query`, and `headers` overrides.

## Route coverage

Enable coverage reporting:

```bash
pytest --authz-report
```

The reporter records which framework adapter actually executed the authorization cases and then
compares declared contracts against that framework's route inventory.

Example:

```text
authorization cases: 12/12 asserted, 12 passed, 0 failed
authorization contracts: 1/1 exercised
FastAPI route coverage: 8/10 (80.0%)
  missing: DELETE delete-booking
  missing: GET health
```

Write a machine-readable report:

```bash
pytest --authz-report-json=authz-report.json
```

Report schema version 2 uses a framework-neutral `route_coverage` object containing the detected
framework, totals, percentage, and uncovered routes.

Fail CI below a route-contract threshold:

```bash
pytest --authz-fail-under=90
```

## Framework behavior

The authorization contract format is intentionally framework-neutral. Framework adapters are
responsible for request execution and route inventory only:

- `django-rest-framework` - DRF/Django clients and URL resolver discovery;
- `fastapi` - Starlette `TestClient` execution and FastAPI `APIRoute` discovery;
- `generic` - method/generic client execution when no first-class adapter matches.

This keeps application models, authentication backends, tenancy systems, and business policy in
project fixtures rather than importing them into the plugin.

## Configuration and design

- [`docs/configuration.md`](docs/configuration.md)
- [`docs/design.md`](docs/design.md)
- [`docs/fastapi.md`](docs/fastapi.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)

## License

MIT
