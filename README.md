# pytest-authz-matrix

[![CI](https://github.com/Leanstix/pytest-authz-matrix/actions/workflows/ci.yml/badge.svg)](https://github.com/Leanstix/pytest-authz-matrix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Authorization contract testing for Python web APIs.

`pytest-authz-matrix` expands one pytest test into the complete actor × resource-relationship
matrix for an endpoint. For Django REST Framework projects, it can also inventory API routes
and report which HTTP method/route pairs do not have an authorization contract.

It is built for the bugs that ordinary authentication tests miss:

- a user retrieves another user's object by changing an ID;
- a tenant administrator reaches an object belonging to another tenant;
- a list endpoint leaks foreign rows while its detail endpoint is protected;
- an endpoint returns `403` when policy requires concealing the object's existence with `404`;
- a new DRF route ships without any ownership or cross-tenant test.

> **Status:** `0.1.1` is an alpha focused on explicit DRF authorization contracts. The plugin
> discovers untested routes; it deliberately does not guess your business authorization policy.

## Quick start

Install the plugin with its DRF integration:

```bash
pip install "pytest-authz-matrix[django]"
```

Projects that run pytest in parallel can install the tested xdist integration:

```bash
pip install "pytest-authz-matrix[django,xdist]"
```

Version 0.1.1 explicitly tests Django 4.2, 5.0, 5.1, 5.2 LTS, 6.0, and 6.1 across their compatible
Python and Django REST Framework boundaries. Django 4.2, 5.0, and 5.1 are retained as legacy
compatibility targets even though upstream security support has ended. See the complete
[`Django compatibility matrix`](docs/compatibility.md).

The integration suite exercises real router-registered ViewSets, custom actions, namespaces,
request formats, primary HTTP methods, and authenticated DRF and plain Django clients. See
[`Django and DRF integration`](docs/django.md) for the production-tested behavior.

It also applies real migrations and exercises ORM-backed `ModelViewSet` list, create, retrieve,
update, partial-update, and destroy operations through pytest-django.

Create `authz-matrix.yml` in the pytest root:

```yaml
version: 1

actors:
  owner: owner_client
  same_tenant_user: same_tenant_client
  foreign_tenant_user: foreign_tenant_client
  anonymous: anonymous_client

resources:
  booking:
    fixture: booking_matrix
    lookup: pk

contracts:
  booking.retrieve:
    method: GET
    path: /api/bookings/{resource}/
    route_name: booking-detail
    resource: booking
    matrix:
      owner:
        owned: allow
        same_tenant: conceal
        foreign_tenant: conceal
      same_tenant_user:
        owned: conceal
        same_tenant: allow
        foreign_tenant: conceal
      foreign_tenant_user:
        owned: conceal
        same_tenant: conceal
        foreign_tenant: allow
      anonymous:
        owned: unauthenticated
        same_tenant: unauthenticated
        foreign_tenant: unauthenticated
```

The actor fixtures return the API clients that already know how your project authenticates:

```python
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def owner_client(owner):
    client = APIClient()
    client.force_authenticate(owner)
    return client


@pytest.fixture
def same_tenant_client(same_tenant_user):
    client = APIClient()
    client.force_authenticate(same_tenant_user)
    return client


@pytest.fixture
def foreign_tenant_client(foreign_tenant_user):
    client = APIClient()
    client.force_authenticate(foreign_tenant_user)
    return client


@pytest.fixture
def anonymous_client():
    return APIClient()
```

The resource fixture maps the relationship names in YAML to real model instances:

```python
@pytest.fixture
def booking_matrix(owner_booking, same_tenant_booking, foreign_tenant_booking):
    return {
        "owned": owner_booking,
        "same_tenant": same_tenant_booking,
        "foreign_tenant": foreign_tenant_booking,
    }
```

Finally, bind a test to the contract:

```python
import pytest


@pytest.mark.authz_contract("booking.retrieve")
def test_booking_retrieve_authorization(authz_case):
    authz_case.run()
```

That single function becomes 12 independent pytest cases with readable IDs such as:

```text
booking.retrieve[owner-owned-allow]
booking.retrieve[owner-foreign_tenant-conceal]
booking.retrieve[anonymous-owned-unauthenticated]
```

## Outcomes

The built-in outcomes are HTTP status contracts:

| Outcome | Default status | Meaning |
|---|---:|---|
| `allow` | `200` | The actor may perform the operation. |
| `deny` | `403` | The actor is authenticated but forbidden. |
| `conceal` | `404` | The resource's existence must not be disclosed. |
| `unauthenticated` | `401` | Authentication is required. |

Override defaults globally when an endpoint legitimately returns another success status:

```yaml
outcomes:
  allow: [200, 201, 204]
  deny: [403]
  conceal: [404]
  unauthenticated: [401]
```

Or override one matrix cell:

```yaml
matrix:
  owner:
    owned:
      outcome: allow
      statuses: [200, 204]
```

An integer or list is also accepted for a status-only expectation:

```yaml
matrix:
  owner:
    owned: [200, 206]
```

## Mutating endpoints

Request bodies and query strings can come from fixtures:

```yaml
contracts:
  booking.update:
    method: PATCH
    path: /api/bookings/{resource}/
    route_name: booking-detail
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
        foreign_tenant: conceal
```

For state or side-effect assertions, split execution from the status assertion:

```python
@pytest.mark.authz_contract("booking.update")
def test_booking_update_authorization(authz_case):
    original_status = authz_case.resource.status

    response = authz_case.execute()

    authz_case.resource.refresh_from_db()
    if authz_case.outcome != "allow":
        assert authz_case.resource.status == original_status
    authz_case.assert_response(response)
```

`authz_case.execute()` also accepts per-test `data`, `query`, and `headers` overrides.

## Route coverage

Add `route_name` to contracts whenever possible. The plugin matches the contract's HTTP method
and Django URL name against DRF's URL resolver. Without a route name, it falls back to normalized
path matching.

```bash
pytest --authz-report
```

Example output:

```text
============================= authorization matrix =============================
authorization cases: 12/12 complete, 12 executed, 12 asserted, 12 passed, 0 failed
authorization contracts: 1/1 complete
DRF route coverage: 9/11 (81.8%)
  missing: PATCH children-detail
  missing: POST booking-refund
```

Fail CI when route coverage drops below a threshold:

```bash
pytest --authz-report --authz-fail-under=85
```

Route coverage is execution-backed: a matching YAML entry does not cover a route by itself. Every
matrix case in the matching contract must complete its configured request and call
`authz_case.assert_response()`. `authz_case.run()` performs both operations.

`--authz-fail-under` also requires every configured case to be complete, preventing a configured
but uncollected contract from producing a false-green CI result. Enforce execution completeness
without a route threshold with:

```bash
pytest --authz-require-complete
```

The terminal and JSON reports distinguish cases that were never executed, executed without an
assertion, and asserted without their configured request.

Parallel execution with `pytest -n auto` is supported. Workers send their authorization results
to the xdist controller, which performs route discovery, completeness and threshold gates, and
terminal/JSON reporting once. See [parallel pytest execution](docs/django.md#parallel-pytest-execution).

Deliberately public or generated endpoints can be removed from the denominator with an auditable
exclusion:

```yaml
coverage:
  exclude:
    - method: GET
      route_name: api-root
      reason: Generated router index has no object policy
```

Every exclusion requires a reason and appears in terminal and JSON reports. See the
[configuration reference](docs/configuration.md#route-coverage-exclusions) for name, path, and
method matching rules.

Write machine-readable results:

```bash
pytest --authz-report-json=build/authz-report.json
```

Discovery is best-effort and only runs when Django is configured in the pytest session. A plain
Python or non-Django test suite can still use explicit matrices with any client fixture exposing
HTTP method functions such as `.get()` or `.patch()`.

## Path templates

Given a resource fixture object, the following placeholders are available:

| Placeholder | Resolution |
|---|---|
| `{resource}` | The resource field configured by `lookup` (`pk` by default). |
| `{resource.uuid}` | Any mapping key or object attribute on the selected resource. |
| `{params.estate}` | A static value from the contract's `params` mapping. |

Values are URL-encoded before insertion. See [the full configuration reference](docs/configuration.md)
for endpoint-only contracts, request options, and validation rules.

## What this version does not do

- It does not infer who should own an object. Fixtures define that truth explicitly.
- It does not prove that response bodies contain no foreign objects; add a list-response assertion.
- It does not intercept emails, Celery tasks, or external API calls automatically.
- It does not yet generate contracts from OpenAPI or support a first-class FastAPI adapter.
- It does not replace database row-level-security tests or a security review.

These boundaries are intentional. The first release makes authorization policy executable and
shows what remains untested without claiming to solve authorization automatically.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. The architecture and planned
extension points are documented in [docs/design.md](docs/design.md). Runtime details for Django
and DRF are documented in [docs/django.md](docs/django.md).

## License

MIT
