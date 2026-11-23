"""Bounded metadata-only operational records; never raw logs or quarantined patient payloads."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from healthcare_ingestion.configuration import _no_secrets, canonical_json, freeze, thaw

SPARK_METRIC_TYPES = {
    "ShuffleWriteRecords": "bigint",
    "AllocatedExecutorsMin": "int",
    "AllocatedExecutorsMax": "int",
    "IsAnomalous": "bit",
    "ExpectedDuration": "decimal(20,6)",
    "PotentialCausesJson": "nvarchar(max)",
    "TotalDuration": "decimal(20,6)",
    **dict.fromkeys(
        (
            "JobCount",
            "QueryCount",
            "TaskCount",
            "ReadRows",
            "WriteRows",
            "JoinCount",
            "ScanCount",
            "FilterCount",
            "UnionCount",
            "CollectCount",
            "HashAggregateCount",
            "ExchangeCount",
            "ShuffleReadLocalBytes",
            "ShuffleReadRemoteBytes",
            "ShuffleWriteBytes",
            "ReadBytes",
            "WriteBytes",
            "MemorySpilledBytes",
            "DiskSpilledBytes",
        ),
        "bigint",
    ),
    "GCTime": "decimal(20,6)",
    **dict.fromkeys(("StageCount", "ShuffleMapStageCount", "ResultStageCount"), "bigint"),
    "CompilationTime": "decimal(20,6)",
    "ExecutionTime": "decimal(20,6)",
    "IdleTime": "decimal(20,6)",
    "CoreAllocation": "decimal(18,4)",
    "UtilizationPercentage": "decimal(9,4)",
    **dict.fromkeys(
        (
            "TaskDuration",
            "ShuffleTime",
            "IOTime",
            "CPUTime",
            "ShuffleReadTime",
            "ShuffleWriteTime",
            "ReadTime",
            "WriteTime",
            "SerializationTime",
            "DeserializeTime",
            "ExecutorComputingTime",
            "ApplicationRunTime",
            "OverheadTime",
            "QueueingTime",
            "StartingTime",
        ),
        "decimal(20,6)",
    ),
}


class OperationalRecordError(ValueError):
    """Record shape, bounds or provenance is invalid."""


@dataclass(frozen=True, kw_only=True)
class OperationalRecord:
    operation_id: str
    attempt_id: str
    release_version: str
    status: str
    record_id: str | None = None
    revision: int | None = None

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, Mapping):
                object.__setattr__(self, item.name, freeze(_json_value(value)))

    def to_dict(self) -> dict[str, Any]:
        return {item.name: _json_value(getattr(self, item.name)) for item in fields(self)}


@dataclass(frozen=True, kw_only=True)
class DiagnosticAttemptRecord(OperationalRecord):
    scope_key: str
    collection_attempt: int = 0
    max_attempts: int = 3
    availability: str | None = None
    reason: str | None = None
    spark: Mapping[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True, kw_only=True)
class DiagnosticLogRecord(OperationalRecord):
    collection_id: str
    kind: str
    filename: str
    source_identity: str
    artifact: str | None = None
    bytes: int | None = None
    sha256: str | None = None
    complete: bool = True
    availability: str | None = None
    reason: str | None = None
    source_modified_at: str | None = None
    collected_at: str | None = None
    retrieval_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class SparkMetricRecord(OperationalRecord):
    activity_run_id: str
    workspace_id: str
    item_id: str
    item_type: str
    livy_id: str
    application_id: str
    application_attempt_id: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    collected_at: str | None = None
    execution_evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class BenchmarkTrialRecord(OperationalRecord):
    run_id: str
    trial: int
    warmup: bool = False
    input_versions: Mapping[str, str] = field(default_factory=dict)
    snapshot_context: Mapping[str, Any] = field(default_factory=dict)
    compute_context: Mapping[str, Any] = field(default_factory=dict)
    artifact: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True, kw_only=True)
class BenchmarkStepRecord(BenchmarkTrialRecord):
    ordinal: int
    function: str
    occurrence_id: str | None = None
    parameters: Mapping[str, Any] | None = None
    attempt_number: int = 1
    plan_seconds: float | str | None = None
    materialization_seconds: float | str | None = None
    reread_seconds: float | str | None = None
    total_seconds: float | str | None = None
    rows: int | None = None
    exception_type: str | None = None
    execution_metrics: Mapping[str, Any] = field(default_factory=dict)
    collection_status: str = "UNAVAILABLE"


@dataclass(frozen=True, kw_only=True)
class QualityOutcomeRecord(OperationalRecord):
    check: str
    evidence_digest: str
    severity: str = "critical"
    reason: str | None = None
    expected_value: float | str | None = None
    actual_value: float | str | None = None
    artifact: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class QuarantineManifestRecord(OperationalRecord):
    quality_record_id: str
    artifact: str
    reason_code: str
    row_count: int
    schema_digest: str
    identifiers_manifest_ref: str | None = None
    input_versions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class CleanupOutcomeRecord(OperationalRecord):
    artifact_id: str
    artifact: str | None = None
    artifact_kind: str | None = None
    attempt_number: int = 1
    reason: str | None = None
    proof_digest: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


RECORD_TYPES = {
    "diagnostic_attempt": DiagnosticAttemptRecord,
    "diagnostic_log": DiagnosticLogRecord,
    "spark_metric": SparkMetricRecord,
    "benchmark_trial": BenchmarkTrialRecord,
    "benchmark_step": BenchmarkStepRecord,
    "quality_outcome": QualityOutcomeRecord,
    "quarantine_manifest": QuarantineManifestRecord,
    "cleanup_outcome": CleanupOutcomeRecord,
}

RECORD_KEYS = {
    "diagnostic_attempt": ("scope_key", "collection_attempt"),
    "diagnostic_log": ("collection_id", "source_identity"),
    "spark_metric": ("activity_run_id", "application_id", "application_attempt_id"),
    "benchmark_trial": ("run_id", "trial"),
    "benchmark_step": ("run_id", "trial", "ordinal", "attempt_number"),
    "quality_outcome": ("check",),
    "quarantine_manifest": ("quality_record_id", "artifact"),
    "cleanup_outcome": ("artifact_id", "attempt_number"),
}


def record_schema(kind: str) -> Mapping[str, Any]:
    """Return exact public field/default metadata for one closed operational record type."""
    if kind not in RECORD_TYPES:
        raise OperationalRecordError("Unknown operational record kind")
    result = {}
    for item in fields(RECORD_TYPES[kind]):
        description = {
            "type": str(item.type),
            "required": item.default is MISSING and item.default_factory is MISSING,
        }
        if item.default is not MISSING:
            description["default"] = _json_value(item.default)
        elif item.default_factory is not MISSING:
            description["default"] = _json_value(item.default_factory())
        result[item.name] = description
    return freeze(
        {
            "kind": kind,
            "fields": result,
            "metric_columns": SPARK_METRIC_TYPES if kind == "spark_metric" else {},
        }
    )


JSON_COLUMNS = {
    "spark": "spark_json",
    "retrieval_context": "retrieval_context_json",
    "execution_evidence": "execution_evidence_json",
    "input_versions": "input_versions_json",
    "snapshot_context": "snapshot_context_json",
    "compute_context": "compute_context_json",
    "parameters": "parameters_json",
    "execution_metrics": "execution_metrics_json",
    "details": "details_json",
}

TEXT_LIMITS = {
    "attempt_id": 36,
    "release_version": 40,
    "status": 32,
    "collection_id": 128,
    "kind": 32,
    "item_type": 32,
    "function": 128,
    "occurrence_id": 128,
    "collection_status": 32,
    "availability": 32,
    "quality_record_id": 128,
    "severity": 16,
    "artifact": 2048,
    "reason": 2048,
    "source_identity": 2048,
    "identifiers_manifest_ref": 2048,
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    return thaw(value)


def _metadata_only(value: Any) -> None:
    if isinstance(value, Mapping):
        forbidden = {
            "raw_log_body",
            "raw_patient_payload",
            "patient_records",
            "raw_records",
            "body",
            "content",
            "patientid",
            "medicalrecordnumber",
        }
        if any(key.casefold() in forbidden for key in value):
            raise OperationalRecordError(
                "Raw logs/patient identifiers belong in protected artifacts"
            )
        for child in value.values():
            _metadata_only(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _metadata_only(child)


def _integer(value: Any, low: int, high: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise OperationalRecordError(f"{name} must be an integer in [{low},{high}]")


def decimal_text(
    value: Any,
    precision: int = 20,
    scale: int = 6,
    *,
    nonnegative: bool = True,
) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise OperationalRecordError("A measured numeric value cannot be boolean")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or nonnegative and number < 0:
            raise OperationalRecordError(
                "Measurements must be finite and within allowed sign bounds"
            )
        with localcontext() as context:
            context.prec = precision + scale + 4
            rounded = number.quantize(Decimal(1).scaleb(-scale))
        if rounded.copy_abs() >= Decimal(10) ** (precision - scale):
            raise OperationalRecordError("Measurement exceeds its physical decimal range")
        return format(rounded, "f")
    except (InvalidOperation, ValueError) as error:
        raise OperationalRecordError("Invalid decimal measurement") from error


def normalize_record(kind: str, value: OperationalRecord | Mapping[str, Any]) -> dict[str, Any]:
    cls = RECORD_TYPES[kind]
    if isinstance(value, Mapping):
        value = dict(value)
        if "framework_version" in value:
            if value.pop("framework_version") != value.get("release_version"):
                raise OperationalRecordError("Benchmark framework/release versions differ")
        try:
            value = cls(**value)
        except TypeError as error:
            raise OperationalRecordError(f"Unknown or missing {kind} record fields") from error
    if not isinstance(value, cls):
        raise OperationalRecordError(f"Expected {cls.__name__}")
    data = value.to_dict()
    for item in fields(cls):
        annotation, field_value = str(item.type), data[item.name]
        if annotation in {"str", "str | None"} and not (
            isinstance(field_value, str) or field_value is None and annotation.endswith("| None")
        ):
            raise OperationalRecordError(f"{item.name} requires string metadata")
        if "Mapping" in annotation and not (
            isinstance(field_value, Mapping)
            or field_value is None
            and annotation.endswith("| None")
        ):
            raise OperationalRecordError(f"{item.name} requires an object")
    for key in ("operation_id", "attempt_id", "release_version"):
        if not isinstance(data[key], str) or not data[key] or len(data[key]) > 128:
            raise OperationalRecordError(f"Missing/bounded lineage field {key}")
    if data["record_id"] is not None and (
        not isinstance(data["record_id"], str) or not 1 <= len(data["record_id"]) <= 128
    ):
        raise OperationalRecordError("Invalid record ID")
    if data["revision"] is not None:
        _integer(data["revision"], 1, 1_000_000, "revision")
    if not isinstance(data["status"], str):
        raise OperationalRecordError("Status must be explicit")
    data["status"] = data["status"].upper()
    aliases = {
        "COLLECTED": "SUCCEEDED",
        "RECORDED": "SUCCEEDED",
        "QUARANTINED": "SUCCEEDED",
        "AVAILABLE": "COMPLETE",
    }
    data["status"] = aliases.get(data["status"], data["status"])
    allowed = {
        "quality_outcome": {"PASS", "FAIL", "UNAVAILABLE"},
        "spark_metric": {"PENDING", "RUNNING", "PARTIAL", "COMPLETE", "UNAVAILABLE"},
    }.get(
        kind,
        {
            "PENDING",
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            "CANCELED",
            "INTERRUPTED",
            "PARTIAL",
            "COMPLETE",
            "UNAVAILABLE",
            "SKIPPED",
        },
    )
    if data["status"] not in allowed:
        raise OperationalRecordError(f"Illegal {kind} status")
    for key, item in data.items():
        if isinstance(item, str) and len(item) > TEXT_LIMITS.get(key, 512):
            raise OperationalRecordError(f"Record {key} exceeds its metadata budget")
        if isinstance(item, float) and not math.isfinite(item):
            raise OperationalRecordError("Nonfinite record values are forbidden")
    for key in RECORD_KEYS[kind]:
        if data[key] is None or data[key] == "":
            raise OperationalRecordError(f"Required record identity field {key}")
    if kind == "diagnostic_attempt":
        _integer(data["max_attempts"], 1, 6, "max_attempts")
        _integer(data["collection_attempt"], 0, data["max_attempts"], "collection_attempt")
    if kind == "diagnostic_log":
        if data["kind"] not in {
            "driver",
            "rolling_driver",
            "executor",
            "event",
            "livy",
            "evidence",
        }:
            raise OperationalRecordError("Unsupported diagnostic log kind")
        if data["bytes"] is not None:
            _integer(data["bytes"], 0, 2**63 - 1, "bytes")
        if not isinstance(data["complete"], bool):
            raise OperationalRecordError("Log completeness must be explicit boolean")
        if not data["complete"] and data["status"] in {"SUCCEEDED", "COMPLETE"}:
            data["status"] = "PARTIAL"
        if data["status"] in {"SUCCEEDED", "COMPLETE", "PARTIAL"} and not data["artifact"]:
            raise OperationalRecordError("Collected logs require a protected artifact reference")
        if data["sha256"] is not None:
            if len(data["sha256"]) != 64 or any(
                c not in "0123456789abcdefABCDEF" for c in data["sha256"]
            ):
                raise OperationalRecordError("Archived log digest must be SHA-256 hex")
    if kind in {"diagnostic_attempt", "diagnostic_log"}:
        if data["availability"] is None:
            data["availability"] = (
                "AVAILABLE" if data["status"] in {"SUCCEEDED", "COMPLETE"} else data["status"]
            )
        if data["status"] == "UNAVAILABLE" and not data["reason"]:
            raise OperationalRecordError("Unavailable diagnostic evidence needs a reason")
        if data["availability"] not in {
            "AVAILABLE",
            "UNAVAILABLE",
            "PENDING",
            "RUNNING",
            "PARTIAL",
            "FAILED",
            "SKIPPED",
            "CANCELED",
            "INTERRUPTED",
        }:
            raise OperationalRecordError("Unknown diagnostic availability")
    if kind in {"benchmark_trial", "benchmark_step"}:
        _integer(data["trial"], 0, 3, "trial")
        if not isinstance(data["warmup"], bool) or data["warmup"] != (data["trial"] == 0):
            raise OperationalRecordError(
                "Trial zero is warmup; trials one through three are measured"
            )
        if kind == "benchmark_step":
            _integer(data["ordinal"], 0, 127, "ordinal")
            _integer(data["attempt_number"], 1, 6, "attempt_number")
            for key in (
                "plan_seconds",
                "materialization_seconds",
                "reread_seconds",
                "total_seconds",
            ):
                data[key] = decimal_text(data[key])
                if data[key] is not None and Decimal(data[key]) > 1800:
                    raise OperationalRecordError("Step duration exceeds the bounded benchmark case")
            if data["rows"] is not None:
                _integer(data["rows"], 0, 2**63 - 1, "rows")
            if data["collection_status"] not in {"PENDING", "COMPLETE", "PARTIAL", "UNAVAILABLE"}:
                raise OperationalRecordError("Unknown benchmark metric collection status")
            if not data["execution_metrics"]:
                data["execution_metrics"] = {
                    "availability": "UNAVAILABLE",
                    "reason": "NOT_ATTRIBUTABLE",
                }
    if kind == "quality_outcome":
        if data["severity"] not in {"critical", "warning"} or not data["evidence_digest"]:
            raise OperationalRecordError("Quality outcomes need severity and evidence digest")
        if data["status"] in {"FAIL", "UNAVAILABLE"} and not data["reason"]:
            raise OperationalRecordError("Failed/unavailable quality outcomes need a reason")
        for key in ("expected_value", "actual_value"):
            data[key] = decimal_text(data[key], 38, 6, nonnegative=False)
    if kind == "quarantine_manifest":
        _integer(data["row_count"], 0, 2**63 - 1, "row_count")
        if not data["schema_digest"] or not data["reason_code"]:
            raise OperationalRecordError("Quarantine needs schema/cause evidence")
    if kind == "cleanup_outcome":
        _integer(data["attempt_number"], 1, 6, "attempt_number")
        if data["status"] == "FAILED" and not data["reason"]:
            raise OperationalRecordError("Cleanup failure needs a sanitized reason")
    _no_secrets(data)
    _metadata_only(data)
    if len(canonical_json(data).encode()) > 65536:
        raise OperationalRecordError(
            "Operational metadata exceeds its 64 KiB budget; store an artifact reference"
        )
    return data


def metric_columns(data: dict[str, Any]) -> dict[str, Any]:
    metrics = data["metrics"]
    if not isinstance(metrics, Mapping) or set(metrics) - set(SPARK_METRIC_TYPES):
        raise OperationalRecordError("Unknown Spark measurement fields")
    if data["item_type"] not in {"notebooks", "sparkJobDefinitions", "lakehouses"}:
        raise OperationalRecordError("Unsupported actual session-owning item type")
    for key in (
        "activity_run_id",
        "workspace_id",
        "item_id",
        "livy_id",
        "application_id",
        "application_attempt_id",
    ):
        if not isinstance(data[key], str) or not data[key]:
            raise OperationalRecordError("Metrics require an actual application/attempt identity")
    if data["application_attempt_id"].casefold() == "latest":
        raise OperationalRecordError(
            "Metrics require an explicit application attempt, never latest"
        )
    normalized, columns = {}, {}
    for name, sql_type in SPARK_METRIC_TYPES.items():
        if name in metrics and not isinstance(metrics[name], Mapping):
            raise OperationalRecordError(
                "Each Spark field needs a value/availability/source mapping"
            )
        measure = dict(
            metrics.get(
                name,
                {
                    "value": None,
                    "availability": "UNAVAILABLE",
                    "reason": "NOT_COLLECTED",
                },
            )
        )
        if set(measure) - {"value", "availability", "reason", "source", "unit"}:
            raise OperationalRecordError("Unknown measurement attribution fields")
        for key in ("availability", "reason", "source", "unit"):
            if measure.get(key) is not None and (
                not isinstance(measure[key], str) or len(measure[key]) > 2048
            ):
                raise OperationalRecordError("Measurement attribution needs bounded strings")
        value = measure.get("value")
        availability = measure.get("availability")
        if value is None:
            if availability not in {"UNAVAILABLE", "NOT_APPLICABLE", "DELAYED"} or not measure.get(
                "reason"
            ):
                raise OperationalRecordError("Null measurements need explicit availability/reason")
            columns[name] = None
        else:
            if availability != "AVAILABLE" or not measure.get("source"):
                raise OperationalRecordError("Measured values need supported source attribution")
            if sql_type in {"bigint", "int"}:
                _integer(value, 0, 2 ** (63 if sql_type == "bigint" else 31) - 1, name)
                columns[name] = value
            elif sql_type == "bit":
                if not isinstance(value, bool):
                    raise OperationalRecordError("Anomaly flags must be boolean or null")
                columns[name] = int(value)
            elif sql_type.startswith("decimal"):
                precision, scale = (int(n) for n in sql_type[8:-1].split(","))
                columns[name] = decimal_text(value, precision, scale)
                measure["value"] = columns[name]
                if name == "UtilizationPercentage" and Decimal(columns[name]) > 100:
                    raise OperationalRecordError("Utilization percentage exceeds 100")
            else:
                if not isinstance(value, (list, tuple)):
                    raise OperationalRecordError("Potential causes must be a JSON array")
                columns[name] = canonical_json(value)
        normalized[name] = measure
    low, high = columns["AllocatedExecutorsMin"], columns["AllocatedExecutorsMax"]
    if low is not None and high is not None and low > high:
        raise OperationalRecordError("Allocated executor minimum exceeds maximum")
    data["metrics"] = normalized
    columns["source_mapping_json"] = canonical_json(
        {
            name: {k: v for k, v in value.items() if k != "value"}
            for name, value in normalized.items()
        }
    )
    return columns
