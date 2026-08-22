# Changelog

All notable changes will be documented in this file. The project follows semantic versioning once
the public API leaves alpha.

## [0.1.1] - Unreleased

### Added

- An explicit Django/DRF/Python compatibility matrix covering Django 4.2 through 6.1, including
  legacy compatibility for Django 5.0.
- Pinned CI boundary jobs for every declared Django release line.
- Clean-install smoke tests for both wheel and source distribution artifacts.

### Changed

- The Django extra now requires Django 4.2 through 6.1 and DRF 3.15.2 through 3.18.x, matching the
  documented and tested compatibility surface.
- Source distributions deliberately include the complete test suite, including
  `tests/conftest.py` and its `pytester` activation.

## [0.1.0] - 2026-08-15

### Added

- YAML authorization contracts for actors, resources, relationships, and outcomes.
- Pytest case generation through the `authz_contract` marker and `authz_case` fixture.
- DRF/Django client request execution with payload, query, header, and path-template support.
- Built-in allow, deny, conceal, and unauthenticated outcomes.
- DRF route discovery with terminal coverage, JSON reports, and CI thresholds.
- Python 3.10+ packaging, documentation, examples, and GitHub Actions validation.
