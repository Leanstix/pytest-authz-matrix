# Django compatibility

Version 0.1.1 is a Django REST Framework maintenance release. FastAPI support is reserved for
version 0.2.0.

## Supported versions

The following combinations define the supported Django integration surface for 0.1.1:

| Django | Python | Django REST Framework | Support level |
|---|---|---|---|
| 4.2 | 3.10-3.12 | 3.15.2-3.17.x | Legacy compatibility |
| 5.0 | 3.10-3.12 | 3.15.2-3.17.x | Legacy compatibility |
| 5.1 | 3.10-3.13 | 3.16.1-3.17.x | Legacy compatibility |
| 5.2 LTS | 3.10-3.14 | 3.16.1-3.18.x | Maintained upstream |
| 6.0 | 3.12-3.14 | 3.17.2-3.18.x | Maintained upstream |
| 6.1 | 3.12-3.14 | 3.18.x | Maintained upstream |

`Legacy compatibility` means pytest-authz-matrix continues to test the integration, but the
corresponding Django release no longer receives upstream security fixes. Production applications
should prefer a Django version that is still maintained upstream.

The optional `django` extra constrains installations to the complete tested family:

```text
Django>=4.2,<6.2
djangorestframework>=3.15.2,<3.19
pytest-django>=4.8,<5
```

Pip will select a mutually compatible Django/DRF pair. For example, DRF 3.18 requires Django 5.2
or newer, so an environment pinned to Django 5.0 resolves to the latest compatible DRF 3.17
release.

## CI policy

CI uses two complementary matrices:

- the core Python matrix runs the full suite on every supported Python version from 3.10 through
  3.14 using the newest dependencies resolvable for that interpreter;
- the Django compatibility matrix pins the oldest and newest supported DRF boundary for every
  Django release line, using that Django line's oldest and newest supported Python boundary.

Every compatibility job prints and verifies the resolved Django, DRF, and Python versions before
running the complete test suite. A version combination is not added to this table until it has an
explicit green CI job.

Every compatibility job also installs pytest-django 4.x and runs the real migrated ORM and
`ModelViewSet` integration project, not only client and route-discovery unit tests.

The complete suite includes executable DRF applications. It covers router-registered ViewSets,
standard and custom actions, nested namespaces, APIViews, function views, primary HTTP methods,
JSON and multipart request formats, and authenticated and anonymous `APIClient` behavior. It also
verifies plain Django `Client` encoding and generic custom-client fallback. See
[Django and DRF integration](django.md) for the precise behavior.
