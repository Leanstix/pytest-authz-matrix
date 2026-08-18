"""Framework adapter registration and automatic runtime selection."""

from __future__ import annotations

from typing import Any

from pytest_authz_matrix.adapters.base import FrameworkAdapter
from pytest_authz_matrix.adapters.django import DjangoRESTFrameworkAdapter
from pytest_authz_matrix.adapters.fastapi import FastAPIAdapter
from pytest_authz_matrix.adapters.generic import GenericAdapter

_FRAMEWORK_ADAPTERS: tuple[FrameworkAdapter, ...] = (
    FastAPIAdapter(),
    DjangoRESTFrameworkAdapter(),
)
_GENERIC_ADAPTER = GenericAdapter()


def adapter_for(client: Any, *, app: Any | None = None) -> FrameworkAdapter:
    """Return the most specific adapter available for ``client`` or ``app``."""

    if app is not None:
        for adapter in _FRAMEWORK_ADAPTERS:
            if adapter.supports_app(app):
                return adapter
    for adapter in _FRAMEWORK_ADAPTERS:
        if adapter.supports_client(client):
            return adapter
    return _GENERIC_ADAPTER
