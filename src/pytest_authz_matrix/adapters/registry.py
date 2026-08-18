"""Framework adapter registration and automatic runtime selection."""

from __future__ import annotations

from typing import Any

from pytest_authz_matrix.adapters.base import FrameworkAdapter
from pytest_authz_matrix.adapters.django import DjangoRESTFrameworkAdapter
from pytest_authz_matrix.adapters.generic import GenericAdapter

_FRAMEWORK_ADAPTERS: tuple[FrameworkAdapter, ...] = (DjangoRESTFrameworkAdapter(),)
_GENERIC_ADAPTER = GenericAdapter()


def adapter_for(client: Any) -> FrameworkAdapter:
    """Return the most specific adapter available for ``client``."""

    for adapter in _FRAMEWORK_ADAPTERS:
        if adapter.supports_client(client):
            return adapter
    return _GENERIC_ADAPTER
