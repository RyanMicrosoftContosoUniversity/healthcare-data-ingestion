"""Immutable release configuration; logical identities never contain physical resource IDs."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


class ConfigurationError(ValueError):
    """A configuration cannot be published or resolved safely."""


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ConfigurationError("Configuration object keys must be strings")
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ConfigurationError(f"Configuration is not JSON-compatible: {type(value).__name__}")


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(thaw(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _no_secrets(value: Any) -> None:
    if isinstance(value, Mapping):
        forbidden = {
            "password",
            "access_token",
            "connection_string",
            "client_secret",
            "sas_token",
            "bearer_token",
            "secret",
        }
        if any(key.casefold() in forbidden for key in value):
            raise ConfigurationError(
                "Use logical connection/secret-store references, not credentials"
            )
        for child in value.values():
            _no_secrets(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _no_secrets(child)
    elif isinstance(value, str) and re.search(r"[?&]sig=", value, re.IGNORECASE):
        raise ConfigurationError("Signed artifact URLs must not enter immutable metadata")


def _id(value: str, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ConfigurationError(f"Invalid {label}: {value!r}")


def validate_parameters(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    """Validate the deliberately bounded JSON-schema subset used by registered functions."""
    supported = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
    }
    if set(schema) - supported:
        raise ConfigurationError(f"{path}: unsupported parameter schema keywords")
    types = {
        "object": lambda v: isinstance(v, Mapping),
        "array": lambda v: isinstance(v, (list, tuple)),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    expected = schema.get("type")
    if expected not in types or not types[expected](value):
        raise ConfigurationError(f"{path}: expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ConfigurationError(f"{path}: value outside registered enum")
    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        if set(schema.get("required", ())) - set(value):
            raise ConfigurationError(f"{path}: missing required parameters")
        unknown = set(value) - set(properties)
        if unknown and not schema.get("additionalProperties", False):
            raise ConfigurationError(f"{path}: unknown parameters {sorted(unknown)}")
        for key, child in value.items():
            if key in properties:
                validate_parameters(child, properties[key], f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ConfigurationError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ConfigurationError(f"{path}: too many items")
        if "items" not in schema:
            raise ConfigurationError(f"{path}: array schema must specify items")
        for index, child in enumerate(value):
            validate_parameters(child, schema["items"], f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 2**31):
            raise ConfigurationError(f"{path}: invalid string length")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", float("-inf")):
            raise ConfigurationError(f"{path}: below minimum")
        if value > schema.get("maximum", float("inf")):
            raise ConfigurationError(f"{path}: above maximum")
    canonical_json(value)


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    name: str
    layer: str
    external: bool = False
    retired: bool = False
    freshness_seconds: int = 86400
    physical_maps: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _id(self.dataset_id, "dataset ID")
        if self.layer not in {"source", "bronze", "silver1", "silver2", "gold"}:
            raise ConfigurationError(f"Unknown dataset layer {self.layer}")
        if not self.name or self.freshness_seconds < 0:
            raise ConfigurationError("Dataset name and nonnegative freshness are required")
        object.__setattr__(self, "physical_maps", freeze(self.physical_maps))


@dataclass(frozen=True)
class InputSpec:
    dataset_id: str
    alias: str
    required: bool = True
    freshness_seconds: int | None = None
    allow_stale: bool = False

    def __post_init__(self) -> None:
        _id(self.dataset_id, "input dataset ID")
        _id(self.alias, "input alias")
        if self.freshness_seconds is not None and self.freshness_seconds < 0:
            raise ConfigurationError("Input freshness cannot be negative")


@dataclass(frozen=True)
class FunctionSpec:
    occurrence_id: str
    function: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    input_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _id(self.occurrence_id, "function occurrence ID")
        _id(self.function, "registered function ID")
        object.__setattr__(self, "parameters", freeze(self.parameters))
        object.__setattr__(self, "input_aliases", tuple(self.input_aliases))


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    workflow: str
    primary_output: str
    inputs: tuple[InputSpec, ...]
    functions: tuple[FunctionSpec, ...] = ()
    pipeline_object_id: str | None = None
    ordering_after: tuple[str, ...] = ()
    scope: str = "default"
    retired: bool = False
    overrides: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _id(self.task_id, "task ID")
        _id(self.primary_output, "primary output ID")
        _id(self.scope, "processing scope")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "functions", tuple(self.functions))
        object.__setattr__(self, "ordering_after", tuple(self.ordering_after))
        object.__setattr__(self, "overrides", freeze(self.overrides))


_SETTING_FIELDS = {
    "scheduler": {"retries", "retry_delay_seconds", "timeout_seconds", "priority"},
    "spark": {"startup", "runtime"},
    "execution": {
        "notebook_ref",
        "environment_ref",
        "compute_profile_ref",
        "concurrency_limit",
        "ingestion_strategy",
    },
    "events": {"coalesce", "reconcile_seconds", "max_retries", "retry_delay_seconds"},
    "observability": {"logging_level", "profile_transformations", "diagnostics_enabled"},
}


def _merge_settings(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = thaw(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            existing = result.get(key, {})
            if not isinstance(existing, Mapping):
                raise ConfigurationError(f"Incompatible settings shape for {key}")
            result[key] = _merge_settings(existing, value)
        else:
            result[key] = thaw(value)
    return result


def _settings(settings: Mapping[str, Any]) -> None:
    if set(settings) - set(_SETTING_FIELDS):
        raise ConfigurationError("Unknown settings namespace; scheduler and Spark are separate")
    for namespace, values in settings.items():
        if values is None:
            continue
        if not isinstance(values, Mapping) or set(values) - _SETTING_FIELDS[namespace]:
            raise ConfigurationError(f"Unknown {namespace} settings")
        for name, value in values.items():
            if value is None:
                continue
            if name in {"retries", "priority", "max_retries"}:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ConfigurationError(f"{namespace}.{name} must be nonnegative integer")
            elif name.endswith("_seconds") or name == "concurrency_limit":
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                    raise ConfigurationError(f"{namespace}.{name} must be positive")
            elif namespace == "spark":
                if not isinstance(value, Mapping):
                    raise ConfigurationError(f"spark.{name} must be an object")
            elif name in {"coalesce", "profile_transformations", "diagnostics_enabled"}:
                if not isinstance(value, bool):
                    raise ConfigurationError(f"{namespace}.{name} must be boolean")
            elif name == "logging_level":
                if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                    raise ConfigurationError("Unknown structured logging level")
            elif not isinstance(value, str) or not value:
                raise ConfigurationError(f"{namespace}.{name} must be a nonempty logical reference")
    canonical_json(settings)


@dataclass(frozen=True)
class ReleaseSnapshot:
    version: str
    framework_version: str
    datasets: tuple[DatasetSpec, ...]
    tasks: tuple[TaskSpec, ...]
    artifacts: Mapping[str, Any]
    framework_defaults: Mapping[str, Any] = field(default_factory=dict)
    stage_defaults: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "datasets", tuple(self.datasets))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        for name in ("artifacts", "framework_defaults", "stage_defaults"):
            object.__setattr__(self, name, freeze(getattr(self, name)))
        self.validate()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReleaseSnapshot:
        if set(value) - set(cls.__dataclass_fields__):
            raise ConfigurationError("Unknown release snapshot fields")
        datasets = tuple(DatasetSpec(**item) for item in value["datasets"])
        tasks = []
        for item in value["tasks"]:
            task = dict(item)
            task["inputs"] = tuple(InputSpec(**i) for i in task["inputs"])
            task["functions"] = tuple(FunctionSpec(**f) for f in task.get("functions", ()))
            tasks.append(TaskSpec(**task))
        return cls(
            value["version"],
            value["framework_version"],
            datasets,
            tuple(tasks),
            value["artifacts"],
            value.get("framework_defaults", {}),
            value.get("stage_defaults", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        # asdict performs deepcopy, which deliberately immutable mapping proxies disallow.
        def fields(obj: Any) -> dict[str, Any]:
            return {key: thaw(getattr(obj, key)) for key in obj.__dataclass_fields__}

        result = fields(self)
        result["datasets"] = [fields(d) for d in self.datasets]
        result["tasks"] = []
        for task in self.tasks:
            item = fields(task)
            item["inputs"] = [fields(i) for i in task.inputs]
            item["functions"] = [fields(f) for f in task.functions]
            result["tasks"].append(item)
        return result

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())

    def task(self, task_id: str) -> TaskSpec:
        try:
            return next(t for t in self.tasks if t.task_id == task_id)
        except StopIteration as error:
            raise ConfigurationError(f"Unknown task {task_id}") from error

    def dataset(self, dataset_id: str) -> DatasetSpec:
        try:
            return next(d for d in self.datasets if d.dataset_id == dataset_id)
        except StopIteration as error:
            raise ConfigurationError(f"Unknown dataset {dataset_id}") from error

    def physical(self, dataset_id: str, environment: str) -> Mapping[str, Any]:
        dataset = self.dataset(dataset_id)
        try:
            return dataset.physical_maps[environment]
        except KeyError as error:
            raise ConfigurationError(f"No approved {environment} map for {dataset_id}") from error

    def effective_settings(self, task_id: str) -> Mapping[str, Any]:
        task = self.task(task_id)
        stage = self.dataset(task.primary_output).layer
        settings = _merge_settings(self.framework_defaults, self.stage_defaults.get(stage, {}))
        return freeze(_merge_settings(settings, task.overrides))

    def validate(self, registry: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", self.version):
            raise ConfigurationError("A candidate must have a stable semantic version before CI")
        if self.framework_version != self.version:
            raise ConfigurationError("DAG and framework version must match")
        if len({d.dataset_id.casefold() for d in self.datasets}) != len(self.datasets):
            raise ConfigurationError("Duplicate logical dataset ID")
        if len({t.task_id.casefold() for t in self.tasks}) != len(self.tasks):
            raise ConfigurationError("Duplicate logical task ID")
        if not self.artifacts:
            raise ConfigurationError("An immutable release needs pinned artifacts")
        _settings(self.framework_defaults)
        if set(self.stage_defaults) - {"source", "bronze", "silver1", "silver2", "gold"}:
            raise ConfigurationError("Unknown output-stage defaults")
        for settings in self.stage_defaults.values():
            _settings(settings)
        for task in self.tasks:
            _settings(task.overrides)
            output = self.dataset(task.primary_output)
            if not task.inputs:
                raise ConfigurationError(f"{task.task_id} requires explicit input lineage")
            if not task.retired and (output.retired or output.external):
                raise ConfigurationError("Active producer cannot write retired/external dataset")
            if len({i.alias for i in task.inputs}) != len(task.inputs):
                raise ConfigurationError("Task input aliases must be unique")
            if len({f.occurrence_id for f in task.functions}) != len(task.functions):
                raise ConfigurationError(
                    "Repeated functions require distinct stable occurrence IDs"
                )
            for item in task.inputs:
                if not task.retired and self.dataset(item.dataset_id).retired:
                    raise ConfigurationError("New dependencies cannot reference retired datasets")
            aliases = {i.alias for i in task.inputs}
            for function in task.functions:
                if set(function.input_aliases) - aliases:
                    raise ConfigurationError("Function has an untracked auxiliary input")
                if registry is not None:
                    if function.function not in registry:
                        raise ConfigurationError(f"Unregistered function {function.function}")
                    validate_parameters(function.parameters, registry[function.function])
        self.graph()
        _no_secrets(self.to_dict())
        canonical_json(self.to_dict())

    def graph(self) -> dict[str, tuple[str, ...]]:
        active = {t.task_id: t for t in self.tasks if not t.retired}
        producers: dict[tuple[str, str], str] = {}
        for task in active.values():
            key = (task.primary_output, task.scope)
            if key in producers:
                raise ConfigurationError(f"Ambiguous producer for {key}")
            producers[key] = task.task_id
        parents: dict[str, set[str]] = {key: set() for key in active}
        for task in active.values():
            for item in task.inputs:
                dataset = self.dataset(item.dataset_id)
                producer = producers.get((item.dataset_id, task.scope))
                if producer:
                    parents[task.task_id].add(producer)
                elif not dataset.external:
                    raise ConfigurationError(f"Missing producer for {item.dataset_id}/{task.scope}")
            for parent in task.ordering_after:
                if parent not in active:
                    raise ConfigurationError(f"Missing exceptional ordering task {parent}")
                if parent in parents[task.task_id]:
                    raise ConfigurationError(
                        "Explicit ordering must not duplicate an inferred edge"
                    )
                parents[task.task_id].add(parent)
        pending = {key: set(value) for key, value in parents.items()}
        while pending:
            ready = {key for key, value in pending.items() if not value}
            if not ready:
                raise ConfigurationError("Cyclic processing graph")
            pending = {key: value - ready for key, value in pending.items() if key not in ready}
        return {key: tuple(sorted(value)) for key, value in parents.items()}

    def descendants(self, dataset_id: str) -> tuple[str, ...]:
        affected = {dataset_id}
        changed = True
        while changed:
            changed = False
            for task in self.tasks:
                if not task.retired and any(i.dataset_id in affected for i in task.inputs):
                    if task.primary_output not in affected:
                        affected.add(task.primary_output)
                        changed = True
        return tuple(sorted(affected))
