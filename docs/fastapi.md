# FastAPI integration

Use one pytest test to discover and check FastAPI authentication requirements. Add Python
overrides for your application's roles or resource rules.

## Install

```bash
pip install "pytest-authz-matrix[fastapi]"
```

The extra installs FastAPI 0.110.1 or later and HTTPX. FastAPI's synchronous test client is Starlette's
HTTPX-backed `TestClient`.

## Start without configuration

```python
from pytest_authz_matrix.fastapi import check_fastapi

from app.main import app


def test_authorization():
    check_fastapi(app)
```

FastAPI's required built-in security dependencies identify routes that must reject anonymous
requests. This includes bearer tokens, API keys, and OAuth2, including dependencies inherited
from routers. The checker creates an anonymous in-process test client and asserts the first
HTTP response.

| Permission | Expected HTTP response |
| --- | --- |
| `Permission.PUBLIC` | Any 2xx |
| `Permission.AUTHENTICATED` | 401 or 403 for the actor being checked |
| `Permission.FORBIDDEN` | 403 |
| `Permission.CONCEALED` | 404 |
| An integer such as `201` | That exact status |

`check_fastapi()` returns the number of checks plus `unclassified` and `needs_path` route
lists. Routes with optional authentication or app-specific policies need an explicit
expectation. URLs with placeholders need a concrete test path. A call that generates zero
checks fails.

## Enforce executed coverage in CI

Pass `min_coverage` to enforce a percentage of discovered method and path pairs:

```python
check_fastapi(app, min_coverage=100)
```

Every route with at least one completed check counts once, even when several actors are
tested. Routes with an unknown permission expectation or missing concrete URL stay in the
denominator. Status assertion failures fail the test at any threshold. A run that
generates zero checks remains a configuration error.

Incomplete runs emit `AuthzCoverageWarning`, visible in pytest's warnings summary by
default. Use `result.summary()` to display coverage on demand. Full route coverage can
include routes checked with just one actor. Declare explicit expectations for any roles
and object ownership rules you want to test.

## Customize in Python

```python
from pytest_authz_matrix.fastapi import Permission, check_fastapi


def test_booking_permissions(app, owner_client, viewer_client):
    booking = ("GET", "/bookings/{booking_id}")
    check_fastapi(
        app,
        permissions={
            ("GET", "/health"): Permission.PUBLIC,
            booking: {
                "anonymous": Permission.AUTHENTICATED,
                "viewer": Permission.FORBIDDEN,
                "owner": 200,
            },
        },
        actors={"owner": owner_client, "viewer": viewer_client},
        paths={booking: "/bookings/42"},
    )
```

Use actor fixtures that return test clients for your isolated app. Role names and ownership
come from your fixtures and assertions. Use `payloads={route: body}` to send JSON, and put a
query string in a `paths` value when needed. For a mutating route, provide test data backed by
an isolated test database.

## YAML contracts

Existing YAML contracts provide per-case pytest parametrization and route coverage reporting.

### Actor fixtures

Return a `TestClient` that already represents the actor:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def admin_client(admin_token):
    with TestClient(app, headers={"Authorization": f"Bearer {admin_token}"}) as client:
        yield client


@pytest.fixture
def anonymous_client():
    with TestClient(app) as client:
        yield client
```

The adapter is selected automatically from the client. Use the context-managed fixtures above
when your app relies on startup and shutdown events. The adapter checks the first response from
the contract endpoint. Declare the expected 3xx status in the YAML outcomes when the endpoint
redirects.

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

FastAPI route discovery inventories registered path operations on the app, included routers, and
mounted apps. It includes schema-hidden operations and explicit `HEAD` and `OPTIONS` handlers.
Built-in documentation routes, WebSockets, and static files are outside this inventory.

A contract matches the HTTP method and path template. Parameter names can differ, but prefixes
and trailing slashes must match. If supplied, `route_name` must also match. For named mounts,
use the qualified name such as `admin:booking-detail`.

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

The wrapper should forward the HTTPX request keywords, including `follow_redirects`, to its client.
