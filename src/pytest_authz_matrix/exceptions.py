"""Public exceptions raised by pytest-authz-matrix."""


class AuthzMatrixError(Exception):
    """Base error for the package."""


class AuthzConfigurationError(AuthzMatrixError):
    """Raised when an authorization contract file is invalid."""


class AuthzExecutionError(AuthzMatrixError):
    """Raised when a generated authorization case cannot be executed."""

