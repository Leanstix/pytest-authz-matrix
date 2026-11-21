# Django and Django REST Framework authorization

Install the Django extra:

```bash
python -m pip install "pytest-authz-matrix[django]"
```

Add a test to your existing Django pytest suite:

```python
from pytest_authz_matrix.django import check_django


def test_authorization():
    check_django()
```

The checker uses the project's initialized test settings and URLconf, including included URLs
and DRF router actions. It sends requests through Django's in-process test client and checks
the first response. It requires no configuration file.

| Declaration | Default anonymous check |
| --- | --- |
| Django `login_required` or `LoginRequiredMiddleware` | Redirect to the configured login destination |
| Django `LoginRequiredMixin` | Redirect to the login destination, or 403 with `raise_exception=True` |
| DRF `IsAuthenticated`, `IsAdminUser`, `DjangoModelPermissions`, or `DjangoObjectPermissions` | 401 or 403 |
| DRF `IsAuthenticatedOrReadOnly` | 401 or 403 on non-safe methods |

## Override expectations in Python

```python
from pytest_authz_matrix.django import Permission, check_django


def test_booking_permissions(staff_client, member_client):
    booking = ("GET", "/bookings/<int:pk>/")
    check_django(
        permissions={
            ("GET", "/health/"): Permission.PUBLIC,
            booking: {
                "anonymous": Permission.AUTHENTICATED,
                "member": Permission.FORBIDDEN,
                "staff": 200,
            },
        },
        actors={"member": member_client, "staff": staff_client},
        paths={booking: "/bookings/42/"},
    )
```

`PUBLIC` accepts 2xx, `AUTHENTICATED` accepts 401 or 403, `FORBIDDEN` expects 403, and
`CONCEALED` expects 404. Use an integer to check an exact status. The built-in Django login
checks also verify the redirect destination.

Use `paths` to provide concrete sample URLs for parameterized routes and `payloads` to provide
JSON request bodies. Use an isolated test database for mutating routes. Authenticated actors
use your project's existing Django or DRF client fixtures.

The result includes a check count and the `unclassified` and `needs_path` route lists.
A run with zero checks fails. App-specific rules, overrides of DRF `get_permissions()`,
and public routes can be covered by declaring expectations. Function-based Django views
without a standard HTTP method decorator default to `GET` and accept explicit method overrides.
