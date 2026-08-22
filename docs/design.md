# Design

`pytest-authz-matrix` separates application policy from test execution.

1. YAML defines actors, resource relationships, endpoints, and expected outcomes.
2. The pytest collection hook expands a marked test into immutable `CaseSpec` objects.
3. The `authz_case` fixture resolves the project's existing client and data fixtures at runtime.
4. `AuthorizationCase` renders the path, executes the request, and checks the response contract.
5. The session reporter compares declared contracts with DRF's resolved URL patterns.

This design avoids importing project models, authentication backends, or tenant libraries into the
plugin. Those are application concerns represented by fixtures.

## Execution boundary

`AuthorizationCase` is intentionally synchronous in 0.1.1. Django async views are reached through
the synchronous `django.test.Client` adapter. A client method that returns an awaitable is rejected
before the case is recorded as executed, preventing a false completeness result and an unawaited
coroutine warning.

Configured and explicit HTTP headers are merged by case-insensitive name. Explicit request headers
win while retaining their supplied spelling. Authentication, cookies, host selection, proxy
headers, and other client-wide state remain owned by actor fixtures.

## Extension points

- Framework adapters should produce a common method/route inventory rather than alter contracts.
- Additional assertions should compose with `AuthorizationCase`; they should not hide application
  state or side-effect checks behind magic.
- New report formats should consume the reporter's stable dictionary representation.
- OpenAPI support should generate or validate contract skeletons, never infer access decisions.

## Security model

The configuration file is an executable policy specification only in the testing sense. The plugin
does not enforce production authorization. A passing matrix proves that the selected fixtures,
objects, requests, and assertions behaved as declared during that test run. It cannot prove that
all possible object relationships, request fields, or side effects were tested.
