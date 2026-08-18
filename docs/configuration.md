# Configuration reference

The default file is `authz-matrix.yml` under pytest's root directory. Select another file with
`pytest --authz-config=path/to/contracts.yml`.

The version 1 schema is shared by Django REST Framework, FastAPI, and generic clients. Framework
selection is runtime behavior and does not require a `framework` key.

## Top-level keys

### `version`

Required schema version. The supported value is `1`.

### `actors`

Maps policy actor names to pytest client fixtures. Shorthand and expanded forms are equivalent:

```yaml
actors:
  owner: owner_client
  tenant_admin:
    client_fixture: tenant_admin_client
```

A fixture can return DRF `APIClient`, FastAPI/Starlette `TestClient`, Django `Client`, or another
object supported by the generic adapter.

Authentication, organization headers, hosts, cookies, and token construction should normally remain
inside actor fixtures.

### `resources`

Maps resource names to fixtures containing relationship objects:

```yaml
resources:
  invoice:
    fixture: invoice_matrix
    lookup: public_id
```

`lookup` defaults to `pk`. A resource fixture may return a mapping or an object whose attributes are
the relationship names used in the matrix.

### `outcomes`

Optional global status mappings. Defaults:

```yaml
outcomes:
  allow: [200]
  deny: [403]
  conceal: [404]
  unauthenticated: [401]
```

Every status must be an integer from 100 through 599.

### `contracts`

Each contract requires:

- `method`: HTTP method;
- `path`: URL template sent to the actor client;
- `matrix`: actor expectations.

Resource contracts also specify `resource`. `route_name` is optional but recommended when the
framework exposes stable route names.

```yaml
contracts:
  invoice.retrieve:
    method: GET
    path: /api/invoices/{resource}
    route_name: invoice-detail
    resource: invoice
    matrix:
      owner:
        owned: allow
        foreign_tenant: conceal
```

Coverage is counted per HTTP method/route pair, so GET and PATCH on the same path are separate
coverage targets.

## Endpoint-only contracts

An endpoint that is not tied to one resource omits `resource`. Actor values are outcomes rather than
relationship mappings:

```yaml
contracts:
  current-profile.retrieve:
    method: GET
    path: /api/profile/me
    route_name: current-profile
    matrix:
      member: allow
      anonymous: unauthenticated
```

## Request configuration

```yaml
request:
  data_fixture: update_payload
  query_fixture: query_parameters
  format: json
  headers:
    X-Test-Source: authz-matrix
```

`data_fixture` provides the request payload. `query_fixture` may return a query string, mapping, or
sequence accepted by `urlencode`. `headers` are merged with per-test overrides.

`format` is adapter-neutral intent:

- DRF: `json` is passed through DRF's `data=...`, `format="json"` behavior;
- FastAPI: `json` uses `TestClient(..., json=payload)` semantics;
- FastAPI: `form`, `data`, or `null` use `data=payload` semantics;
- generic clients retain the original `data`/`format` keyword behavior.

The default is `json`.

## FastAPI application override

A normal FastAPI `TestClient` exposes its application and needs no extra configuration. If an
application-specific wrapper hides it, override the plugin's optional fixture:

```python
@pytest.fixture
def authz_app():
    return app
```

The fixture is used only for adapter selection and framework route discovery.

## Static path parameters

```yaml
params:
  estate: estate-123
path: /api/estates/{params.estate}/bookings/{resource}
```

`{estate}` is also accepted for direct parameter lookup. Values are URL-encoded.

## Expectations

Each matrix cell supports:

```yaml
owned: allow
owned: 200
owned: [200, 204]
owned:
  outcome: allow
  statuses: [200, 204]
```

The expanded form may use singular `status` instead of `statuses`.

## Reporting

`--authz-report-json` writes report schema version 2. Framework route information appears under
`route_coverage`:

```json
{
  "schema_version": 2,
  "route_coverage": {
    "framework": "fastapi",
    "available": true,
    "total": 10,
    "covered": 8,
    "coverage_percent": 80.0,
    "uncovered": []
  }
}
```
