# DRF example

Copy the YAML into the pytest root and adapt the fixtures to your project's users and factories.
Then run:

```bash
pytest path/to/test_authorization.py --authz-report
```

The example intentionally uses fixtures rather than prescribing a factory library, authentication
backend, or multi-tenancy implementation.

