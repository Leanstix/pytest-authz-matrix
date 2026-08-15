# Design

`pytest-authz-matrix` separates application policy from test execution.

1. YAML defines actors, resource relationships, endpoints, and expected outcomes.
2. The pytest collection hook expands a marked test into immutable `CaseSpec` objects.
3. The `authz_case` fixture resolves the project's existing client and data fixtures at runtime.
4. `AuthorizationCase` renders the path, executes the request, and checks the response contract.
5. The session reporter compares declared contracts with DRF's resolved URL patterns.

This design avoids importing project models, authentication backends, or tenant libraries into the
plugin. Those are application concerns represented by fixtures.

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

