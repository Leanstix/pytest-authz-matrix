"""Authorization contract testing for pytest."""

from pytest_authz_matrix.case import AuthorizationCase
from pytest_authz_matrix.exceptions import AuthzConfigurationError

__all__ = ["AuthorizationCase", "AuthzConfigurationError"]
__version__ = "0.1.1"
