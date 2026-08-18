"""Framework integration adapters used internally by pytest-authz-matrix."""

from pytest_authz_matrix.adapters.base import FrameworkAdapter
from pytest_authz_matrix.adapters.registry import adapter_for

__all__ = ["FrameworkAdapter", "adapter_for"]
