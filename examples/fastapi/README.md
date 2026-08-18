# FastAPI example

This example uses FastAPI `TestClient` actors and the same version 1 authorization contract format
used by the DRF integration.

From the repository root:

```bash
pip install -e ".[fastapi]"
pytest examples/fastapi/test_authorization.py \
  --authz-config=examples/fastapi/authz-matrix.yml \
  --authz-report
```

The example deliberately uses a simple `X-Actor` header instead of prescribing a JWT/OAuth library.
In a real application, actor fixtures should construct clients using the application's existing
authentication mechanism.
