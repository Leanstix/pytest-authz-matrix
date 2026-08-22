# Django and Django REST Framework integration

Version 0.1.1 treats Django REST Framework as a production integration, not only as an optional
route-discovery dependency. The integration suite builds executable Django projects and exercises
the generated authorization cases through real DRF and Django test clients.

## Route discovery

The DRF route inventory understands:

- `ViewSet` routes registered with `SimpleRouter` or `DefaultRouter`;
- standard list, create, retrieve, update, partial-update, and destroy actions;
- detail and collection methods created with DRF's `@action` decorator;
- `APIView` and function views decorated with `@api_view`;
- nested Django URL namespaces and fully qualified or short route names; and
- path converters, including UUID converters, and router-generated regular-expression paths.

DRF-generated content-negotiation suffix aliases are collapsed into their canonical routes. A
real application parameter named `format` remains discoverable. ViewSet actions disabled through
`http_method_names` are not inventoried, and duplicate route names require both the configured
name and normalized path to match. Unnamed routes continue to match contracts by normalized path.

Coverage is tracked for each application HTTP method and route pair. Django's automatic `HEAD`
and `OPTIONS` handlers are excluded because they do not represent separately implemented
authorization operations.

The API root created by `DefaultRouter` is a real reachable endpoint and is included by default.
Applications that intentionally leave it outside their authorization matrix must declare a
reasoned `coverage.exclude` entry. Exclusions are never inferred from names such as `health` or
`schema`.

Coverage is also execution-backed. A route is covered only when every configured actor and
relationship case in a matching contract both completes its request and asserts the response.
Listing a contract in YAML without collecting its pytest test does not cover the route.

Use `--authz-require-complete` to fail when any configured case was not executed and asserted.
`--authz-fail-under` enables the same completeness requirement automatically in addition to its
route percentage threshold.

## Request execution

DRF's `APIClient` is the first-class execution client. The plugin preserves DRF's native
`format=` behavior, so configured JSON and multipart renderers work as they do in an ordinary DRF
test. The integration suite covers `GET`, `POST`, `PUT`, `PATCH`, and `DELETE`, including JSON,
multipart, and default form requests.

Plain `django.test.Client` is also supported. Because it does not accept DRF's `format=` keyword,
the plugin translates the request configuration as follows:

| Contract `format` | Django client behavior |
|---|---|
| `json` | Sends `application/json` using Django's JSON encoding |
| `multipart` | Uses Django multipart encoding, including non-POST methods |
| `null` | Leaves encoding to the Django client |

Other format names raise `AuthzExecutionError` with an actionable message instead of leaking an
unexpected-keyword error from Django. A custom client may expose either a method named after the
contract HTTP method or a generic `generic()` sender; non-Django clients retain the configured
`format=` value.

## Client and authorization semantics

Actor fixtures own authentication and client-wide state. This includes DRF
`force_authenticate()`, credentials, default tenant headers, cookies, and host configuration.
Contract request headers are merged into that client state, and explicit headers supplied to
`authz_case.execute()` take precedence over contract headers.

The authentication integration project uses Django's migrated auth, session, and DRF token
tables. It verifies these concrete actor-fixture patterns:

| Actor state | Tested behavior |
|---|---|
| Logged-in session with CSRF cookie and header | Authenticated write succeeds |
| Logged-in session without a CSRF token | `SessionAuthentication` rejects the write with 403 |
| Client after `logout()` | Session cookie state no longer authenticates the request |
| `APIClient.credentials()` with a real DRF token | `TokenAuthentication` resolves the database user |
| Invalid token or no credentials | Token-protected endpoint returns 401 |

The plugin does not manufacture these states. Each actor fixture remains responsible for login,
cookies, CSRF acquisition, and credential headers, exactly as it would be in the application's
ordinary test suite.

The executable integration coverage includes authenticated and anonymous actors, allow and deny
responses, concealed resources, owner and foreign-tenant relationships, repeated query
parameters, request payload fixtures, and namespaced custom actions.

## Request and response boundaries

The Stage 5 integration project extends request execution beyond scalar form fields. A multipart
contract sends a real `SimpleUploadedFile` and verifies its name, size, media type, and bytes after
DRF parsing. A registered vendor JSON renderer/parser pair verifies that custom DRF test formats
retain their declared media type and structured request data.

Header precedence is deterministic:

1. state configured on the actor client remains in effect;
2. contract `request.headers` are added for the generated case; and
3. headers passed directly to `authz_case.run()` or `execute()` override matching contract keys.

Responses are asserted by HTTP status without assuming a JSON body. The integration suite covers
an empty 204 response, a binary non-UTF-8 response, an ordinary 302 response without following its
location, Django's `APPEND_SLASH` 301 behavior, and DRF responses generated from `NotFound` and
`PermissionDenied`. Failure diagnostics decode opaque bytes with replacement characters rather
than raising a secondary Unicode error.

Plain Django async views are supported through Django's synchronous test-client adaptation. The
plugin invokes the configured client method normally and does not impose its own sync/async event
loop behavior.

## ORM and ModelViewSet behavior

The `django` extra installs `pytest-django` alongside Django and DRF. Configure pytest-django as
usual, for example:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = project.settings
```

Authorization tests that use ORM-backed actor or resource fixtures must opt into database access
with `@pytest.mark.django_db`. The plugin deliberately does not add the marker automatically
because the application owns its database and transaction requirements.

The production integration suite applies real migrations and runs all six standard
`ModelViewSet` actions through a serializer and SQLite test database. It verifies:

- tenant isolation implemented by `get_queryset()`;
- object-level permissions after queryset filtering;
- UUID resources resolved through a custom `lookup_field`;
- list results containing only objects from the actor's tenant;
- create ownership and tenant fields supplied by `perform_create()`;
- persisted `PUT` and `PATCH` changes for an allowed owner;
- unchanged database state after denied or concealed writes; and
- deletion only for the allowed owner, including a transactional database test.

Actor and resource fixtures remain ordinary pytest fixtures, so applications may use factories,
`db`, `transactional_db`, or their existing pytest-django fixture stack.

## Parallel pytest execution

Install the optional xdist integration and run pytest normally:

```bash
pip install "pytest-authz-matrix[django,xdist]"
pytest -n auto --authz-report --authz-fail-under=100
```

Each worker records only the cases it executes. At worker shutdown, that serializable state is
sent through xdist's controller channel. The controller then:

1. merges and deduplicates executed and asserted case IDs;
2. preserves a failing result if duplicate executions disagree;
3. performs Django route discovery once;
4. evaluates execution completeness and route thresholds once; and
5. writes one terminal report and one JSON report.

Workers never write the configured JSON path or independently apply coverage gates, avoiding file
races and false failures from their intentionally partial test allocations. If a worker fails to
return cases, strict execution completeness leaves those configured cases missing and the
controller gate fails rather than reporting false success.

The plugin intentionally does not create users, authenticate actors, or infer authorization
policy. It executes the actor clients and expectations declared by the application.
