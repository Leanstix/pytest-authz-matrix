"""Load and validate authorization matrix YAML files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pytest_authz_matrix.exceptions import AuthzConfigurationError
from pytest_authz_matrix.models import (
    DEFAULT_OUTCOMES,
    ActorSpec,
    ContractSpec,
    Expectation,
    MatrixConfig,
    RequestSpec,
    ResourceSpec,
)


def load_config(path: str | Path) -> MatrixConfig:
    """Load a YAML file and return a fully validated immutable configuration."""

    config_path = Path(path)
    if not config_path.is_file():
        raise AuthzConfigurationError(f"Authorization config not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AuthzConfigurationError(f"Invalid YAML in {config_path}: {exc}") from exc

    root = _mapping(raw, "root")
    version = root.get("version", 1)
    if version != 1:
        raise AuthzConfigurationError(f"Unsupported config version {version!r}; expected 1")

    outcomes = _parse_outcomes(root.get("outcomes", {}))
    actors = _parse_actors(_mapping(root.get("actors"), "actors"))
    resources = _parse_resources(_mapping(root.get("resources", {}), "resources"))
    contracts = _parse_contracts(
        _mapping(root.get("contracts"), "contracts"), actors, resources, outcomes
    )
    if not contracts:
        raise AuthzConfigurationError("contracts must define at least one authorization contract")

    return MatrixConfig(
        version=version,
        actors=actors,
        resources=resources,
        outcomes=outcomes,
        contracts=contracts,
    )


def _parse_outcomes(raw: Any) -> dict[str, tuple[int, ...]]:
    outcomes = dict(DEFAULT_OUTCOMES)
    for name, value in _mapping(raw, "outcomes").items():
        outcomes[str(name)] = _statuses(value, f"outcomes.{name}")
    return outcomes


def _parse_actors(raw: Mapping[str, Any]) -> dict[str, ActorSpec]:
    actors: dict[str, ActorSpec] = {}
    for name, value in raw.items():
        if isinstance(value, str):
            fixture = value
        else:
            actor = _mapping(value, f"actors.{name}")
            fixture = _required_string(actor, "client_fixture", f"actors.{name}")
        actors[name] = ActorSpec(name=name, client_fixture=fixture)
    if not actors:
        raise AuthzConfigurationError("actors must define at least one actor")
    return actors


def _parse_resources(raw: Mapping[str, Any]) -> dict[str, ResourceSpec]:
    resources: dict[str, ResourceSpec] = {}
    for name, value in raw.items():
        resource = _mapping(value, f"resources.{name}")
        fixture = _required_string(resource, "fixture", f"resources.{name}")
        lookup = resource.get("lookup", "pk")
        if not isinstance(lookup, str) or not lookup:
            raise AuthzConfigurationError(f"resources.{name}.lookup must be a non-empty string")
        resources[name] = ResourceSpec(name=name, fixture=fixture, lookup=lookup)
    return resources


def _parse_contracts(
    raw: Mapping[str, Any],
    actors: Mapping[str, ActorSpec],
    resources: Mapping[str, ResourceSpec],
    outcomes: Mapping[str, tuple[int, ...]],
) -> dict[str, ContractSpec]:
    contracts: dict[str, ContractSpec] = {}
    for name, value in raw.items():
        location = f"contracts.{name}"
        contract = _mapping(value, location)
        method = _required_string(contract, "method", location).upper()
        path = _required_string(contract, "path", location)
        resource_name = contract.get("resource")
        if resource_name is not None and resource_name not in resources:
            raise AuthzConfigurationError(f"{location}.resource references unknown resource {resource_name!r}")

        matrix = _parse_matrix(
            _mapping(contract.get("matrix"), f"{location}.matrix"),
            actors,
            outcomes,
            has_resource=resource_name is not None,
            location=f"{location}.matrix",
        )
        request = _parse_request(contract.get("request", {}), f"{location}.request")
        params = dict(_mapping(contract.get("params", {}), f"{location}.params"))
        route_name = contract.get("route_name")
        if route_name is not None and not isinstance(route_name, str):
            raise AuthzConfigurationError(f"{location}.route_name must be a string")

        contracts[name] = ContractSpec(
            name=name,
            method=method,
            path=path,
            matrix=matrix,
            resource=resource_name,
            route_name=route_name,
            params=params,
            request=request,
        )
    return contracts


def _parse_matrix(
    raw: Mapping[str, Any],
    actors: Mapping[str, ActorSpec],
    outcomes: Mapping[str, tuple[int, ...]],
    *,
    has_resource: bool,
    location: str,
) -> dict[str, dict[str | None, Expectation]]:
    matrix: dict[str, dict[str | None, Expectation]] = {}
    for actor_name, value in raw.items():
        if actor_name not in actors:
            raise AuthzConfigurationError(f"{location} references unknown actor {actor_name!r}")
        if has_resource:
            relationships = _mapping(value, f"{location}.{actor_name}")
            if not relationships:
                raise AuthzConfigurationError(
                    f"{location}.{actor_name} must define at least one resource relationship"
                )
            matrix[actor_name] = {
                relationship: _expectation(
                    expectation,
                    outcomes,
                    f"{location}.{actor_name}.{relationship}",
                )
                for relationship, expectation in relationships.items()
            }
        else:
            matrix[actor_name] = {
                None: _expectation(value, outcomes, f"{location}.{actor_name}")
            }
    if not matrix:
        raise AuthzConfigurationError(f"{location} must not be empty")
    return matrix


def _expectation(
    raw: Any, outcomes: Mapping[str, tuple[int, ...]], location: str
) -> Expectation:
    if isinstance(raw, str):
        outcome = raw
        statuses = outcomes.get(outcome)
        if statuses is None:
            raise AuthzConfigurationError(f"{location} references unknown outcome {outcome!r}")
        return Expectation(outcome=outcome, statuses=statuses)
    if isinstance(raw, int):
        return Expectation(outcome="status", statuses=(raw,))
    if isinstance(raw, list):
        return Expectation(outcome="status", statuses=_statuses(raw, location))

    value = _mapping(raw, location)
    outcome = value.get("outcome", "custom")
    if not isinstance(outcome, str):
        raise AuthzConfigurationError(f"{location}.outcome must be a string")
    if "statuses" in value:
        statuses = _statuses(value["statuses"], f"{location}.statuses")
    elif "status" in value:
        statuses = _statuses(value["status"], f"{location}.status")
    elif outcome in outcomes:
        statuses = outcomes[outcome]
    else:
        raise AuthzConfigurationError(
            f"{location} must include status/statuses or reference a known outcome"
        )
    return Expectation(outcome=outcome, statuses=statuses)


def _parse_request(raw: Any, location: str) -> RequestSpec:
    value = _mapping(raw, location)
    headers = _mapping(value.get("headers", {}), f"{location}.headers")
    if any(not isinstance(key, str) or not isinstance(item, str) for key, item in headers.items()):
        raise AuthzConfigurationError(f"{location}.headers keys and values must be strings")
    return RequestSpec(
        data_fixture=_optional_string(value, "data_fixture", location),
        query_fixture=_optional_string(value, "query_fixture", location),
        format=_optional_string(value, "format", location, default="json"),
        headers=dict(headers),
    )


def _statuses(value: Any, location: str) -> tuple[int, ...]:
    values = value if isinstance(value, list) else [value]
    if not values or any(not isinstance(status, int) or isinstance(status, bool) for status in values):
        raise AuthzConfigurationError(f"{location} must contain one or more integer HTTP statuses")
    invalid = [status for status in values if status < 100 or status > 599]
    if invalid:
        raise AuthzConfigurationError(f"{location} contains invalid HTTP statuses: {invalid}")
    return tuple(values)


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthzConfigurationError(f"{location} must be a mapping")
    return value


def _required_string(value: Mapping[str, Any], key: str, location: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise AuthzConfigurationError(f"{location}.{key} must be a non-empty string")
    return result


def _optional_string(
    value: Mapping[str, Any], key: str, location: str, *, default: str | None = None
) -> str | None:
    result = value.get(key, default)
    if result is not None and not isinstance(result, str):
        raise AuthzConfigurationError(f"{location}.{key} must be a string or null")
    return result

