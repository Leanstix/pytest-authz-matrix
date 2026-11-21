"""Permission expectations shared by the directly callable framework checks."""

from __future__ import annotations

from collections.abc import Container, Mapping
from enum import Enum

from pytest_authz_matrix.exceptions import AuthzConfigurationError

RouteKey = tuple[str, str]


class Permission(str, Enum):
    """Expected access outcome for one actor."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    FORBIDDEN = "forbidden"
    CONCEALED = "concealed"


_EXPECTED: Mapping[Permission, Container[int]] = {
    Permission.PUBLIC: range(200, 300),
    Permission.AUTHENTICATED: (401, 403),
    Permission.FORBIDDEN: (403,),
    Permission.CONCEALED: (404,),
}


def expected_statuses(expectation: Permission | int) -> Container[int]:
    if type(expectation) is int and 100 <= expectation <= 599:
        return (expectation,)
    if isinstance(expectation, Permission):
        return _EXPECTED[expectation]
    raise AuthzConfigurationError(f"Invalid permission expectation: {expectation!r}")
