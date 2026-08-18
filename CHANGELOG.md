# Changelog

All notable changes will be documented in this file. The project follows semantic versioning once
the public API leaves alpha.

## [0.2.0] - 2026-08-18

### Added

- Internal framework adapter architecture with a generic fallback client adapter.
- First-class FastAPI/Starlette `TestClient` support through the `fastapi` optional extra.
- Automatic FastAPI and DRF adapter detection from actor client fixtures.
- Optional `authz_app` fixture for custom wrappers that hide their underlying application.
- FastAPI `APIRoute` discovery and authorization route-coverage reporting.
- Dedicated FastAPI and DRF adapter regression tests.
- FastAPI documentation and a runnable example project.

### Changed

- DRF request execution and route discovery now live behind the same adapter boundary used by
  FastAPI.
- Route coverage reports are framework-neutral. JSON reports use schema version 2 and expose
  `route_coverage` instead of the DRF-specific `drf_routes` object.
- `request.format` now represents adapter-neutral request intent. `json` is translated to DRF
  renderer semantics or FastAPI/HTTPX `json=` semantics as appropriate.
- CLI help and terminal reporting refer to API route coverage rather than assuming DRF.

### Compatibility

- Existing version 1 `authz-matrix.yml` contracts remain valid; no framework key is required.
- Existing DRF actor/resource fixtures and authorization tests keep the same public workflow.
- Generic custom clients retain method-name and `.generic()` fallback execution.

## [0.1.0] - 2026-08-15

### Added

- YAML authorization contracts for actors, resources, relationships, and outcomes.
- Pytest case generation through the `authz_contract` marker and `authz_case` fixture.
- DRF/Django client request execution with payload, query, header, and path-template support.
- Built-in allow, deny, conceal, and unauthenticated outcomes.
- DRF route discovery with terminal coverage, JSON reports, and CI thresholds.
- Python 3.10+ packaging, documentation, examples, and GitHub Actions validation.
