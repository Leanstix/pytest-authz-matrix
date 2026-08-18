# Design

`pytest-authz-matrix` separates authorization policy from framework execution.

1. YAML defines actors, resource relationships, endpoints, requests, and expected outcomes.
2. The pytest collection hook expands a marked test into immutable `CaseSpec` objects.
3. The `authz_case` fixture resolves the project's existing client and data fixtures at runtime.
4. `AuthorizationCase` renders the path and selects a framework adapter from the actual test client.
5. The adapter executes the request using framework-appropriate semantics.
6. The session reporter asks the observed adapter for a route inventory and compares it with declared
   contracts.

This design avoids importing project models, authentication backends, or tenant libraries into the
plugin. Those are application concerns represented by fixtures.

## Framework adapter boundary

The authorization matrix is framework-neutral. Framework-specific code lives under
`pytest_authz_matrix.adapters`.

```text
YAML contracts
     |
     v
Config parser -> CaseSpec -> AuthorizationCase
                           |
                           v
                    adapter registry
                   /       |        \
                DRF     FastAPI    Generic
                   \       |       /
                    route inventory
                           |
                           v
                 framework-neutral report
```

Adapters are responsible for:

- recognizing compatible test clients/applications;
- translating the common request specification into client-specific arguments;
- exposing a common method/name/path route inventory.

Adapters are not responsible for understanding application business policy.

### Django REST Framework

The DRF adapter preserves the original `APIClient` request behavior and walks Django's root URL
resolver, selecting DRF `APIView` routes and supported HTTP methods.

### FastAPI

The FastAPI adapter recognizes Starlette/FastAPI `TestClient`, extracts the underlying FastAPI
application, translates JSON bodies to HTTPX-style `json=`, and inventories FastAPI `APIRoute`
objects.

### Generic clients

If no first-class adapter matches, the generic adapter preserves the original plugin behavior: call
the lowercase HTTP method on the client or fall back to `.generic()`.

## Extension points

- Additional framework adapters should implement the same internal runtime contract.
- Additional assertions should compose with `AuthorizationCase`; they should not hide state or
  side-effect checks behind magic.
- New report formats should consume the reporter's stable dictionary representation.
- OpenAPI/security introspection should generate or validate contract suggestions, not silently
  invent business access decisions.

## Permission introspection direction

Route execution/discovery and semantic permission inference are separate concerns. A future
introspection layer can inspect structured signals such as OAuth scopes, OpenAPI security
requirements, and FastAPI security dependencies while attaching confidence levels to inferred
signals.

Arbitrary code such as ownership checks, tenant comparisons, and custom role conditionals cannot be
assumed to represent a complete policy without developer confirmation.

## Security model

The configuration file is an executable policy specification only in the testing sense. The plugin
does not enforce production authorization. A passing matrix proves that the selected fixtures,
objects, requests, and assertions behaved as declared during that test run. It cannot prove that
all possible object relationships, request fields, side effects, or application states were tested.
