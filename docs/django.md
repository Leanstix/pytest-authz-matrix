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

Coverage is tracked for each application HTTP method and route pair. Django's automatic `HEAD`
and `OPTIONS` handlers are excluded because they do not represent separately implemented
authorization operations.

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

The executable integration coverage includes authenticated and anonymous actors, allow and deny
responses, concealed resources, owner and foreign-tenant relationships, repeated query
parameters, request payload fixtures, and namespaced custom actions.

The plugin intentionally does not create users, authenticate actors, or infer authorization
policy. It executes the actor clients and expectations declared by the application.
