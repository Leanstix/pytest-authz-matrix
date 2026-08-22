# Configuration reference

The default file is `authz-matrix.yml` under pytest's root directory. Select another file with
`pytest --authz-config=path/to/contracts.yml`.

## Top-level keys

### `version`

Required schema version. The only supported value is `1`.

### `actors`

Maps policy actor names to pytest client fixtures. Shorthand and expanded forms are equivalent:

```yaml
actors:
  owner: owner_client
  tenant_admin:
    client_fixture: tenant_admin_client
```

The fixture may return DRF's `APIClient`, Django's `Client`, or another object with a method named
after the contract HTTP method. A client with only `.generic()` is also supported.

### `resources`

Maps resource names to fixtures containing relationship objects:

```yaml
resources:
  invoice:
    fixture: invoice_matrix
    lookup: public_id
```

`lookup` defaults to `pk`. The fixture may return a mapping or an object whose attributes are the
relationship names used in the matrix.

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

- `method`: an HTTP method;
- `path`: the URL template sent to the actor client;
- `matrix`: actor expectations.

Resource contracts also specify `resource`. `route_name` is optional but strongly recommended for
DRF coverage matching.

```yaml
contracts:
  invoice.retrieve:
    method: GET
    path: /api/invoices/{resource}/
    route_name: billing:invoice-detail
    resource: invoice
    matrix:
      owner:
        owned: allow
        foreign_tenant: conceal
```

Namespaced and unnamespaced `route_name` values are accepted. Coverage is counted per HTTP
method/route pair, so GET and PATCH on the same Django URL are separate coverage targets.

## Endpoint-only contracts

An endpoint that is not tied to one resource omits `resource`. Its actor values are outcomes rather
than relationship mappings:

```yaml
contracts:
  current-profile.retrieve:
    method: GET
    path: /api/profile/me/
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

- `data_fixture` is passed as the client's `data` argument.
- `query_fixture` may return a query-string, mapping, or sequence accepted by `urlencode`.
- With DRF's `APIClient`, `format` is passed through to DRF when request data exists.
- With Django's `Client`, `json` and `multipart` are translated to Django-native request encoding;
  `null` leaves encoding to Django. Other format values raise `AuthzExecutionError`.
- A custom non-Django client receives the configured `format` keyword unchanged.
- `headers` is passed as the client's `headers` argument.

Actor-specific authentication, organization headers, and host selection should normally remain in
the actor's client fixture.

See [Django and DRF integration](django.md) for the tested route, request, and client semantics.

## Static path parameters

```yaml
params:
  estate: estate-123
path: /api/estates/{params.estate}/bookings/{resource}/
```

`{estate}` is also accepted for a direct parameter lookup. Values are URL-encoded.

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
