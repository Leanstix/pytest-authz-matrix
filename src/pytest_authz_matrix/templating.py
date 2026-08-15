"""Resolve contract path templates against relationship fixtures."""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter
from typing import Any
from urllib.parse import quote

from pytest_authz_matrix.exceptions import AuthzExecutionError
from pytest_authz_matrix.models import ResourceSpec


def render_path(
    template: str,
    *,
    resource: Any | None,
    resource_spec: ResourceSpec | None,
    params: Mapping[str, Any],
) -> str:
    """Render ``{resource}``, ``{resource.attr}``, and ``{params.key}`` placeholders."""

    values: dict[str, str] = {}
    for _, field_name, format_spec, conversion in Formatter().parse(template):
        if field_name is None:
            continue
        if format_spec or conversion:
            raise AuthzExecutionError(
                f"Path placeholder {field_name!r} may not use conversion or format syntax"
            )
        value = _resolve_placeholder(field_name, resource, resource_spec, params)
        values[field_name] = quote(str(value), safe="")

    rendered = template
    for field_name, value in values.items():
        rendered = rendered.replace("{" + field_name + "}", value)
    return rendered


def related_object(container: Any, relationship: str) -> Any:
    """Return one relationship object from a mapping or attribute container."""

    try:
        if isinstance(container, Mapping):
            return container[relationship]
        return getattr(container, relationship)
    except (KeyError, AttributeError) as exc:
        raise AuthzExecutionError(
            f"Resource fixture does not contain relationship {relationship!r}"
        ) from exc


def _resolve_placeholder(
    name: str,
    resource: Any | None,
    resource_spec: ResourceSpec | None,
    params: Mapping[str, Any],
) -> Any:
    if name == "resource":
        if resource_spec is None or resource is None:
            raise AuthzExecutionError("{resource} used by a contract without a resource")
        return _resolve_value(resource, resource_spec.lookup)
    if name.startswith("resource."):
        if resource is None:
            raise AuthzExecutionError(f"{{{name}}} used but the resource fixture returned null")
        return _resolve_value(resource, name.removeprefix("resource."))
    if name.startswith("params."):
        return _resolve_value(params, name.removeprefix("params."))
    if name in params:
        return params[name]
    raise AuthzExecutionError(
        f"Unknown path placeholder {name!r}; use resource, resource.<field>, or params.<key>"
    )


def _resolve_value(value: Any, path: str) -> Any:
    current = value
    try:
        for part in path.split("."):
            current = current[part] if isinstance(current, Mapping) else getattr(current, part)
    except (KeyError, AttributeError) as exc:
        raise AuthzExecutionError(f"Could not resolve {path!r} from {value!r}") from exc
    if current is None:
        raise AuthzExecutionError(f"Resolved path value {path!r} is null")
    return current
