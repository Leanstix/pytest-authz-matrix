# Contributing

Thank you for helping make authorization tests harder to forget.

## Before coding

Open an issue for a substantial feature or framework adapter. A good proposal includes the manual
workflow it replaces, a minimal public API, failure behaviour, and why fixtures cannot already solve
the problem cleanly.

## Local checks

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest --cov=pytest_authz_matrix --cov-report=term-missing
ruff check src tests
mypy src
python -m build
```

Add a regression test for every bug fix. New configuration syntax requires parsing tests, runtime
tests, documentation, and a backward-compatibility note.

## Pull requests

Keep changes focused and explain:

- what developer problem is solved;
- why the API has the proposed shape;
- what was tested;
- whether configuration or report schemas change.

Never include credentials, real customer payloads, or personally identifiable production data in
fixtures.

