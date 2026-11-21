"""Transactional Fabric SQL control plane with a durable local SQLite reference adapter.

Delta and SQL are not a distributed transaction. A runner must persist a stable operation
token in Delta, verify that evidence, and reconcile it before SQL exposes readiness.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from healthcare_ingestion.configuration import (
    ReleaseSnapshot,
    canonical_json,
    digest_json,
    freeze,
    thaw,
)
from healthcare_ingestion.operational_records import (
    JSON_COLUMNS,
    RECORD_KEYS,
    RECORD_TYPES,
    BenchmarkStepRecord,
    BenchmarkTrialRecord,
    CleanupOutcomeRecord,
    DiagnosticAttemptRecord,
    DiagnosticLogRecord,
    OperationalRecord,
    QualityOutcomeRecord,
    QuarantineManifestRecord,
    SparkMetricRecord,
    metric_columns,
    normalize_record,
)


class ControlError(RuntimeError):
    """A control-plane transition is unsafe."""


class MetadataUnavailable(ControlError):
    """No new starts or readiness publication are allowed while metadata is unavailable."""


class LeaseLost(ControlError):
    """An expired/replaced attempt may not advance SQL or write further Delta output."""


class DependencyBlocked(ControlError):
    """The operation has not failed; its immutable input requirements are not ready."""


def utc_text(value: str | datetime) -> str:
    seventh = "0"
    if isinstance(value, str):
        fraction = re.search(r"\.(\d+)", value)
        if fraction:
            if len(fraction[1]) > 7:
                raise ValueError("Processing windows support at most datetime2(7) precision")
            seventh = fraction[1].ljust(7, "0")[6]
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
    if value.tzinfo is None:
        raise ValueError("Datetime windows must be timezone-aware")
    return value.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="microseconds") + seventh


def utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


@dataclass(frozen=True)
class InputBinding:
    dataset_id: str
    version: str
    window_start: str
    window_end: str
    output_id: str | None = None
    source_snapshot_id: str | None = None
    source_coverage_start: str | None = None
    source_coverage_end: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_start", utc_text(self.window_start))
        object.__setattr__(self, "window_end", utc_text(self.window_end))
        if self.window_start >= self.window_end or not self.version:
            raise ValueError("Input bindings require a version and positive half-open UTC window")
        if self.output_id and self.source_snapshot_id:
            raise ValueError("An input binds a Delta output OR a source snapshot, not both")
        _normalize_source_coverage(self)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class Claim:
    operation_id: str
    attempt_id: str
    owner: str
    fence: int
    lease_until: str


@dataclass(frozen=True)
class CommitEvidence:
    operation_id: str
    dataset_id: str
    delta_version: str
    window_start: str
    window_end: str
    input_versions: Mapping[str, str]
    validation_digest: str
    coverage_verified: bool
    changed_rows: int
    commit_token: str
    source_coverage_start: str | None = None
    source_coverage_end: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_start", utc_text(self.window_start))
        object.__setattr__(self, "window_end", utc_text(self.window_end))
        object.__setattr__(self, "input_versions", freeze(self.input_versions))
        if self.changed_rows < 0 or self.window_start >= self.window_end:
            raise ValueError("Invalid commit row count or coverage window")
        if not self.delta_version or not self.validation_digest or not self.commit_token:
            raise ValueError(
                "Version, validation digest and stable Delta commit token are required"
            )
        _normalize_source_coverage(self)

    def to_dict(self) -> dict[str, Any]:
        return {name: thaw(getattr(self, name)) for name in self.__dataclass_fields__}


def _normalize_source_coverage(value: InputBinding | CommitEvidence) -> None:
    if (value.source_coverage_start is None) != (value.source_coverage_end is None):
        raise ValueError("Source coverage requires both bounds")
    if value.source_coverage_start is not None:
        start, end = utc_text(value.source_coverage_start), utc_text(value.source_coverage_end)
        if start >= end:
            raise ValueError("Source coverage requires a positive half-open UTC interval")
        object.__setattr__(value, "source_coverage_start", start)
        object.__setattr__(value, "source_coverage_end", end)


_TABLES = {
    "release": ("cfg", "FrameworkRelease"),
    "identity": ("cfg", "DatasetIdentity"),
    "dataset": ("cfg", "Dataset"),
    "mapping": ("cfg", "DatasetPhysicalMap"),
    "task": ("cfg", "ProcessingTask"),
    "input": ("cfg", "TaskInput"),
    "dependency": ("cfg", "TaskDependency"),
    "pipeline": ("cfg", "PipelineObjectMapping"),
    "policy": ("cfg", "PipelineDefinitionRelease"),
    "legacy": ("cfg", "LegacyStepAttribution"),
    "activation": ("ops", "ReleaseActivation"),
    "active": ("ops", "ActiveRelease"),
    "operation": ("ops", "TaskOperation"),
    "attempt": ("ops", "TaskAttempt"),
    "binding": ("ops", "OperationInput"),
    "waiting": ("ops", "WaitingOperation"),
    "source": ("ops", "SourceSnapshot"),
    "output": ("ops", "DatasetOutput"),
    "readiness": ("ops", "DatasetReadiness"),
    "block": ("ops", "DatasetBlock"),
    "event": ("ops", "ReadinessOutbox"),
    "receipt": ("ops", "EventReceipt"),
    "reconcile": ("ops", "ReconciliationRun"),
    "hold": ("ops", "ReferenceHold"),
    "audit": ("ops", "ControlAudit"),
    "diagnostic_attempt": ("ops", "TaskDiagnosticAttempt"),
    "diagnostic_log": ("ops", "TaskDiagnosticLog"),
    "spark_metric": ("ops", "TaskSparkMetric"),
    "benchmark_trial": ("ops", "TransformationBenchmarkTrial"),
    "benchmark_step": ("ops", "TransformationBenchmarkStep"),
    "quality_outcome": ("ops", "TaskQualityOutcome"),
    "quarantine_manifest": ("ops", "TaskQuarantineManifest"),
    "cleanup_outcome": ("ops", "ArtifactCleanupOutcome"),
    "record_revision": ("ops", "OperationalRecordRevision"),
}


class _Session:
    def __init__(self, cursor: Any, sqlserver: bool, now: str):
        self.cursor, self.sqlserver, self.now = cursor, sqlserver, now

    def table(self, key: str) -> str:
        schema, table = _TABLES[key]
        return f"[{schema}].[{table}]" if self.sqlserver else f"{schema}_{table}"

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Session:
        self.cursor.execute(sql, params)
        return self

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        self.execute(sql, params)
        row = self.cursor.fetchone()
        if row is None:
            return None
        return self._row(row)

    def all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.execute(sql, params)
        return [self._row(row) for row in self.cursor.fetchall()]

    def _row(self, row: Any) -> dict[str, Any]:
        result = dict(zip([d[0] for d in self.cursor.description], row, strict=True))
        return {
            k: utc_text(v.replace(tzinfo=UTC)) if isinstance(v, datetime) else v
            for k, v in result.items()
        }

    def insert(self, key: str, **values: Any) -> None:
        columns = ",".join(f"[{name}]" for name in values)
        placeholders = ",".join("?" for _ in values)
        self.execute(
            f"INSERT INTO {self.table(key)} ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )

    def update(self, key: str, where: str, params: tuple[Any, ...], **values: Any) -> None:
        setters = ",".join(f"[{name}]=?" for name in values)
        self.execute(
            f"UPDATE {self.table(key)} SET {setters} WHERE {where}", (*values.values(), *params)
        )


class ControlStore:
    """Shared transitions. All read/modify/write operations execute in one SQL transaction."""

    legacy_same_window_coverage = False

    @contextlib.contextmanager
    def transaction(self) -> Iterator[_Session]:
        raise NotImplementedError
        yield  # pragma: no cover

    @staticmethod
    def _audit(tx: _Session, kind: str, reference: str, detail: Mapping[str, Any]) -> None:
        tx.insert(
            "audit",
            audit_id=str(uuid.uuid4()),
            kind=kind,
            reference_id=reference,
            detail_json=canonical_json(detail),
            created_at=tx.now,
        )

    def snapshot(self, version: str) -> ReleaseSnapshot:
        with self.transaction() as tx:
            row = tx.one(
                f"SELECT snapshot_json FROM {tx.table('release')} WHERE version=?", (version,)
            )
            if not row:
                raise ControlError(f"Unknown approved/candidate release {version}")
            return ReleaseSnapshot.from_dict(json.loads(row["snapshot_json"]))

    def active_version(self, environment: str) -> str:
        with self.transaction() as tx:
            row = tx.one(
                f"SELECT version FROM {tx.table('active')} WHERE environment=?", (environment,)
            )
            if not row:
                raise ControlError("No technically activated framework release")
            return row["version"]

    @staticmethod
    def _operation(tx: _Session, operation_id: str) -> dict[str, Any]:
        row = tx.one(f"SELECT * FROM {tx.table('operation')} WHERE operation_id=?", (operation_id,))
        if not row:
            raise ControlError(f"Unknown operation {operation_id}")
        return row

    @staticmethod
    def _bindings(tx: _Session, operation_id: str) -> tuple[InputBinding, ...]:
        rows = tx.all(
            f"SELECT dataset_id,version,window_start,window_end,output_id,source_snapshot_id,"
            "source_coverage_start,source_coverage_end "
            f"FROM {tx.table('binding')} WHERE operation_id=? ORDER BY dataset_id",
            (operation_id,),
        )
        return tuple(InputBinding(**row) for row in rows)

    @staticmethod
    def _snapshot(tx: _Session, version: str) -> ReleaseSnapshot:
        row = tx.one(f"SELECT snapshot_json FROM {tx.table('release')} WHERE version=?", (version,))
        if not row:
            raise ControlError(f"Unknown release {version}")
        return ReleaseSnapshot.from_dict(json.loads(row["snapshot_json"]))

    def queue_operation(
        self,
        *,
        operation_id: str,
        task_id: str,
        environment: str,
        window_start: str | datetime,
        window_end: str | datetime,
        inputs: tuple[InputBinding, ...],
        release_version: str | None = None,
        kind: str = "daily",
        source_mode: str = "current",
        original_operation_id: str | None = None,
        authorize_substitution: str | None = None,
    ) -> str:
        """Idempotently queue intended work, freezing release, Delta inputs and window.

        Backfills default to explicitly supplied current corrected versions. Historical
        backfills require retained versions; there is never implicit current substitution.
        """
        start, end = utc_text(window_start), utc_text(window_end)
        if start >= end or kind not in {"daily", "backfill", "rerun"}:
            raise ValueError("Invalid operation window or kind")
        if source_mode not in {"current", "historical"}:
            raise ValueError("Unknown backfill source mode")
        if len({b.dataset_id for b in inputs}) != len(inputs):
            raise ValueError("Input binding dataset identities must be unique")
        inputs = tuple(sorted(inputs, key=lambda binding: binding.dataset_id))
        with self.transaction() as tx:
            if original_operation_id:
                original = self._operation(tx, original_operation_id)
                if release_version is None:
                    release_version = original["release_version"]
                if source_mode == "historical":
                    originals = self._bindings(tx, original_operation_id)
                    if inputs != originals and not authorize_substitution:
                        raise ControlError(
                            "Historical inputs unavailable/different: explicit approval"
                        )
            if release_version is None:
                active = tx.one(
                    f"SELECT version FROM {tx.table('active')} WHERE environment=?", (environment,)
                )
                if not active:
                    raise ControlError("No active release")
                release_version = active["version"]
            approved = tx.one(
                f"SELECT * FROM {tx.table('activation')} "
                "WHERE environment=? AND version=? AND action IN ('activate','rollback')",
                (environment, release_version),
            )
            if not approved:
                raise ControlError("Execution requires an activated/approved release")
            snapshot = self._snapshot(tx, release_version)
            task = snapshot.task(task_id)
            if task.retired:
                raise ControlError("Retired task cannot start")
            inputs = self._validate_input_bindings(
                tx,
                snapshot,
                task_id,
                environment,
                start,
                end,
                inputs,
                source_mode=source_mode,
                authorize_substitution=authorize_substitution,
                kind=kind,
            )
            fingerprint = digest_json(
                {
                    "task": task_id,
                    "environment": environment,
                    "start": start,
                    "end": end,
                    "release": release_version,
                    "inputs": [b.to_dict() for b in inputs],
                    "kind": kind,
                    "source_mode": source_mode,
                    "original": original_operation_id,
                    "substitution": authorize_substitution,
                }
            )
            existing = tx.one(
                f"SELECT request_hash FROM {tx.table('operation')} WHERE operation_id=?",
                (operation_id,),
            )
            if existing:
                if existing["request_hash"] != fingerprint:
                    raise ControlError(
                        "Logical operation ID reused with different immutable binding"
                    )
                return operation_id
            tx.insert(
                "operation",
                operation_id=operation_id,
                task_id=task_id,
                dataset_id=task.primary_output,
                environment=environment,
                scope=task.scope,
                release_version=release_version,
                snapshot_hash=snapshot.digest,
                window_start=start,
                window_end=end,
                kind=kind,
                source_mode=source_mode,
                original_operation_id=original_operation_id,
                substitution_approval=authorize_substitution,
                request_hash=fingerprint,
                status="QUEUED",
                fence=0,
                owner=None,
                lease_until=None,
                attempt_id=None,
                created_at=tx.now,
                updated_at=tx.now,
                last_error=None,
            )
            for binding in inputs:
                tx.insert("binding", operation_id=operation_id, **binding.to_dict())
            ready = tx.one(
                f"SELECT * FROM {tx.table('readiness')} "
                "WHERE dataset_id=? AND environment=? AND scope=?",
                (task.primary_output, environment, task.scope),
            )
            if not ready:
                tx.insert(
                    "readiness",
                    dataset_id=task.primary_output,
                    environment=environment,
                    scope=task.scope,
                    output_id=None,
                    progress_end=None,
                    expected_operation_id=operation_id,
                    expected_end=end,
                    expected_status="QUEUED",
                    updated_at=tx.now,
                )
            elif ready["expected_end"] is None or end >= ready["expected_end"]:
                tx.update(
                    "readiness",
                    "dataset_id=? AND environment=? AND scope=?",
                    (task.primary_output, environment, task.scope),
                    expected_operation_id=operation_id,
                    expected_end=end,
                    expected_status="QUEUED",
                    updated_at=tx.now,
                )
            self._audit(
                tx, "queued", operation_id, {"release": release_version, "request": fingerprint}
            )
            return operation_id

    def _validate_input_bindings(
        self,
        tx: _Session,
        snapshot: ReleaseSnapshot,
        task_id: str,
        environment: str,
        start: str,
        end: str,
        inputs: tuple[InputBinding, ...],
        *,
        source_mode: str = "current",
        authorize_substitution: str | None = None,
        kind: str = "daily",
    ) -> tuple[InputBinding, ...]:
        task = snapshot.task(task_id)
        specified = {i.dataset_id for i in task.inputs}
        required = {i.dataset_id for i in task.inputs if i.required}
        bound = {b.dataset_id for b in inputs}
        if required - bound or bound - specified:
            raise ControlError("Missing required or unregistered task input binding")
        resolved = []
        for binding in inputs:
            if not (kind == "backfill" and source_mode == "current") and (
                binding.window_start > start or binding.window_end < end
            ):
                raise DependencyBlocked("Pinned input does not cover requested half-open window")
            if (
                source_mode == "historical"
                and binding.output_id is None
                and binding.source_snapshot_id is None
                and not authorize_substitution
            ):
                raise ControlError("Historical source requires retained snapshot evidence")
            if binding.source_snapshot_id:
                source = tx.one(
                    f"SELECT * FROM {tx.table('source')} WHERE source_snapshot_id=?",
                    (binding.source_snapshot_id,),
                )
                if (
                    not source
                    or source["dataset_id"] != binding.dataset_id
                    or source["version"] != binding.version
                    or source["environment"] != environment
                    or source["scope"] != task.scope
                    or source["retired_at"] is not None
                ):
                    raise ControlError(
                        "Selected historical source snapshot is unavailable/mismatched"
                    )
            if binding.output_id:
                output = tx.one(
                    f"SELECT * FROM {tx.table('output')} WHERE output_id=?",
                    (binding.output_id,),
                )
                if (
                    not output
                    or output["dataset_id"] != binding.dataset_id
                    or output["delta_version"] != binding.version
                    or output["environment"] != environment
                    or output["scope"] != task.scope
                    or output["window_start"] != binding.window_start
                    or output["window_end"] != binding.window_end
                ):
                    raise ControlError(
                        "Selected historical/current output is unavailable or mismatched"
                    )
            if not snapshot.dataset(binding.dataset_id).external and binding.output_id is None:
                raise ControlError("Nonexternal input must bind an exact committed output instance")
            coverage = self._binding_source_coverage(tx, binding)
            resolved.append(
                replace(
                    binding,
                    source_coverage_start=coverage[0],
                    source_coverage_end=coverage[1],
                )
            )
        return tuple(resolved)

    def _binding_source_coverage(
        self,
        tx: _Session,
        binding: InputBinding,
    ) -> tuple[str, str]:
        if binding.source_snapshot_id:
            source = tx.one(
                f"SELECT * FROM {tx.table('source')} WHERE source_snapshot_id=?",
                (binding.source_snapshot_id,),
            )
            if not source or source["retired_at"]:
                raise DependencyBlocked("Selected source coverage is unavailable")
            if source["dataset_id"] != binding.dataset_id or source["version"] != binding.version:
                raise ControlError("Source coverage identity/version mismatches frozen input")
            coverage = (source["window_start"], source["window_end"])
        elif binding.output_id:
            output = tx.one(
                f"SELECT * FROM {tx.table('output')} WHERE output_id=?",
                (binding.output_id,),
            )
            if not output:
                raise DependencyBlocked("Selected upstream source coverage is unavailable")
            if (
                output["dataset_id"] != binding.dataset_id
                or output["delta_version"] != binding.version
                or output["window_start"] != binding.window_start
                or output["window_end"] != binding.window_end
            ):
                raise ControlError(
                    "Upstream coverage identity/version/window mismatches frozen input"
                )
            coverage = (output["source_coverage_start"], output["source_coverage_end"])
            if not all(coverage):
                if not self.legacy_same_window_coverage or tx.sqlserver:
                    raise DependencyBlocked("Upstream source coverage is unverified")
                coverage = (output["window_start"], output["window_end"])
        elif self.legacy_same_window_coverage and not tx.sqlserver:
            coverage = (binding.window_start, binding.window_end)
        else:
            raise ControlError("Verified source coverage requires a registered source snapshot")
        if (
            binding.source_coverage_start is not None
            and (binding.source_coverage_start, binding.source_coverage_end) != coverage
        ):
            raise ControlError(
                "Input source coverage is forged or mismatches authoritative evidence"
            )
        return coverage

    def queue_waiting_operation(
        self,
        *,
        operation_id: str,
        task_id: str,
        environment: str,
        window_start: str | datetime,
        window_end: str | datetime,
        release_version: str,
    ) -> str:
        """Record daily intent with a pinned approved release, but no invented data versions."""
        start, end = utc_text(window_start), utc_text(window_end)
        if start >= end or any(
            not isinstance(value, str) or not value or len(value) > limit
            for value, limit in (
                (operation_id, 128),
                (task_id, 128),
                (environment, 128),
                (release_version, 40),
            )
        ):
            raise ValueError("A positive waiting window and explicit pinned release are required")
        with self.transaction() as tx:
            approved = tx.one(
                f"SELECT activation_id FROM {tx.table('activation')} WHERE environment=? "
                "AND version=? AND action IN ('activate','rollback')",
                (environment, release_version),
            )
            if not approved:
                raise ControlError("Execution requires an activated/approved release")
            snapshot = self._snapshot(tx, release_version)
            task = snapshot.task(task_id)
            if task.retired:
                raise ControlError("Retired task cannot start")
            declared = [
                {name: getattr(spec, name) for name in spec.__dataclass_fields__}
                for spec in task.inputs
            ]
            declared_json = canonical_json(declared)
            if len(declared_json.encode()) > 65536:
                raise ValueError("Waiting input declaration exceeds the metadata budget")
            fingerprint = digest_json(
                {
                    "mode": "waiting_daily",
                    "task": task_id,
                    "environment": environment,
                    "start": start,
                    "end": end,
                    "release": release_version,
                    "snapshot": snapshot.digest,
                    "declared_inputs": declared,
                }
            )
            existing = tx.one(
                f"SELECT request_hash FROM {tx.table('operation')} WHERE operation_id=?",
                (operation_id,),
            )
            if existing:
                if existing["request_hash"] != fingerprint:
                    raise ControlError(
                        "Logical operation ID reused with different immutable binding"
                    )
                return operation_id
            tx.insert(
                "operation",
                operation_id=operation_id,
                task_id=task_id,
                dataset_id=task.primary_output,
                environment=environment,
                scope=task.scope,
                release_version=release_version,
                snapshot_hash=snapshot.digest,
                window_start=start,
                window_end=end,
                kind="daily",
                source_mode="current",
                original_operation_id=None,
                substitution_approval=None,
                request_hash=fingerprint,
                status="BLOCKED_BY_DEPENDENCY",
                fence=0,
                owner=None,
                lease_until=None,
                attempt_id=None,
                created_at=tx.now,
                updated_at=tx.now,
                last_error="Input bindings unresolved",
            )
            tx.insert(
                "waiting",
                operation_id=operation_id,
                declared_inputs_json=declared_json,
                binding_hash=None,
                bound_at=None,
                created_at=tx.now,
                updated_at=tx.now,
            )
            ready = tx.one(
                f"SELECT * FROM {tx.table('readiness')} WHERE dataset_id=? "
                "AND environment=? AND scope=?",
                (task.primary_output, environment, task.scope),
            )
            if not ready:
                tx.insert(
                    "readiness",
                    dataset_id=task.primary_output,
                    environment=environment,
                    scope=task.scope,
                    output_id=None,
                    progress_end=None,
                    expected_operation_id=operation_id,
                    expected_end=end,
                    expected_status="BLOCKED_BY_DEPENDENCY",
                    updated_at=tx.now,
                )
            elif ready["expected_end"] is None or end >= ready["expected_end"]:
                tx.update(
                    "readiness",
                    "dataset_id=? AND environment=? AND scope=?",
                    (task.primary_output, environment, task.scope),
                    expected_operation_id=operation_id,
                    expected_end=end,
                    expected_status="BLOCKED_BY_DEPENDENCY",
                    updated_at=tx.now,
                )
            self._audit(
                tx,
                "waiting_queued",
                operation_id,
                {
                    "release": release_version,
                    "request": fingerprint,
                    "declared_inputs": declared,
                },
            )
            return operation_id

    def bind_waiting_operation(
        self,
        operation_id: str,
        inputs: tuple[InputBinding, ...],
    ) -> str:
        """Atomically freeze complete real bindings before the first attempt; never rebind."""
        if any(not isinstance(binding, InputBinding) for binding in inputs):
            raise ValueError("Waiting inputs must be InputBinding values")
        if len({binding.dataset_id for binding in inputs}) != len(inputs):
            raise ValueError("Input binding dataset identities must be unique")
        if any(
            not isinstance(binding.version, str) or binding.version.upper() == "PENDING"
            for binding in inputs
        ):
            raise ControlError("Waiting inputs require actual versions, not placeholders")
        inputs = tuple(sorted(inputs, key=lambda binding: binding.dataset_id))
        fingerprint = digest_json([binding.to_dict() for binding in inputs])
        blocked = None
        with self.transaction() as tx:
            op = self._operation(tx, operation_id)
            waiting = tx.one(
                f"SELECT * FROM {tx.table('waiting')} WHERE operation_id=?",
                (operation_id,),
            )
            if not waiting:
                raise ControlError("Operation is not a deferred daily request")
            if waiting["bound_at"] is not None:
                saved = {
                    binding.dataset_id: binding for binding in self._bindings(tx, operation_id)
                }
                inputs = tuple(
                    replace(
                        binding,
                        source_coverage_start=saved[binding.dataset_id].source_coverage_start,
                        source_coverage_end=saved[binding.dataset_id].source_coverage_end,
                    )
                    if binding.source_coverage_start is None and binding.dataset_id in saved
                    else binding
                    for binding in inputs
                )
                fingerprint = digest_json([binding.to_dict() for binding in inputs])
                if (
                    waiting["binding_hash"] != fingerprint
                    or self._bindings(tx, operation_id) != inputs
                ):
                    raise ControlError("Frozen waiting inputs cannot be rebound")
                return operation_id
            attempted = tx.one(
                f"SELECT attempt_id FROM {tx.table('attempt')} WHERE operation_id=?",
                (operation_id,),
            )
            output = tx.one(
                f"SELECT output_id FROM {tx.table('output')} WHERE operation_id=?",
                (operation_id,),
            )
            if (
                op["status"] not in {"QUEUED", "BLOCKED_BY_DEPENDENCY"}
                or op["attempt_id"] is not None
                or op["fence"] != 0
                or attempted
                or output
                or self._bindings(tx, operation_id)
            ):
                raise ControlError("Waiting bindings require no previous attempt, binding or write")
            snapshot = self._snapshot(tx, op["release_version"])
            task = snapshot.task(op["task_id"])
            specified = {spec.dataset_id for spec in task.inputs}
            required = {spec.dataset_id for spec in task.inputs if spec.required}
            bound = {binding.dataset_id for binding in inputs}
            if bound - specified:
                raise ControlError("Unregistered task input binding")
            try:
                if required - bound:
                    raise DependencyBlocked("Required input bindings unresolved")
                inputs = self._validate_input_bindings(
                    tx,
                    snapshot,
                    op["task_id"],
                    op["environment"],
                    op["window_start"],
                    op["window_end"],
                    inputs,
                    kind=op["kind"],
                )
                fingerprint = digest_json([binding.to_dict() for binding in inputs])
                if self._blocked(tx, op["dataset_id"], op["environment"], op["scope"]):
                    raise DependencyBlocked("Output dataset is explicitly blocked")
                self._check_inputs(tx, op, resolved_inputs=inputs)
            except DependencyBlocked as error:
                blocked = error
                tx.update(
                    "operation",
                    "operation_id=?",
                    (operation_id,),
                    status="BLOCKED_BY_DEPENDENCY",
                    last_error=str(error),
                    updated_at=tx.now,
                )
                self._expected(tx, op, "BLOCKED_BY_DEPENDENCY")
                if op["last_error"] != str(error):
                    self._audit(tx, "waiting_binding_blocked", operation_id, {"reason": str(error)})
            if not blocked:
                for binding in inputs:
                    tx.insert("binding", operation_id=operation_id, **binding.to_dict())
                tx.update(
                    "waiting",
                    "operation_id=? AND bound_at IS NULL",
                    (operation_id,),
                    binding_hash=fingerprint,
                    bound_at=tx.now,
                    updated_at=tx.now,
                )
                tx.update(
                    "operation",
                    "operation_id=?",
                    (operation_id,),
                    status="QUEUED",
                    last_error=None,
                    updated_at=tx.now,
                )
                self._expected(tx, op, "QUEUED")
                self._audit(
                    tx,
                    "waiting_inputs_bound",
                    operation_id,
                    {
                        "release": op["release_version"],
                        "binding_hash": fingerprint,
                        "inputs": [binding.to_dict() for binding in inputs],
                    },
                )
        if blocked:
            raise blocked
        return operation_id

    @staticmethod
    def _blocked(tx: _Session, dataset_id: str, environment: str, scope: str) -> bool:
        return (
            tx.one(
                f"SELECT block_id FROM {tx.table('block')} WHERE dataset_id=? "
                "AND environment=? AND scope=? AND cleared_at IS NULL",
                (dataset_id, environment, scope),
            )
            is not None
        )

    def _check_inputs(
        self,
        tx: _Session,
        operation: Mapping[str, Any],
        *,
        resolved_inputs: tuple[InputBinding, ...] | None = None,
    ) -> None:
        snapshot = self._snapshot(tx, operation["release_version"])
        task = snapshot.task(operation["task_id"])
        specs = {i.dataset_id: i for i in task.inputs}
        if resolved_inputs is None:
            waiting = tx.one(
                f"SELECT bound_at FROM {tx.table('waiting')} WHERE operation_id=?",
                (operation["operation_id"],),
            )
            if waiting and waiting["bound_at"] is None:
                raise DependencyBlocked("Input bindings unresolved")
            resolved_inputs = self._bindings(tx, operation["operation_id"])
        if {spec.dataset_id for spec in task.inputs if spec.required} - {
            binding.dataset_id for binding in resolved_inputs
        }:
            raise DependencyBlocked("Required input bindings unresolved")
        for binding in resolved_inputs:
            if self._blocked(tx, binding.dataset_id, operation["environment"], operation["scope"]):
                raise DependencyBlocked(f"Corruption/descendant block: {binding.dataset_id}")
            spec = specs[binding.dataset_id]
            coverage = self._binding_source_coverage(tx, binding)
            if snapshot.dataset(binding.dataset_id).external and binding.output_id is None:
                if binding.source_snapshot_id:
                    source = tx.one(
                        f"SELECT retired_at FROM {tx.table('source')} WHERE source_snapshot_id=?",
                        (binding.source_snapshot_id,),
                    )
                    if not source or source["retired_at"]:
                        raise DependencyBlocked(
                            "Selected historical source snapshot is unavailable"
                        )
            else:
                ready = tx.one(
                    f"SELECT * FROM {tx.table('readiness')} "
                    "WHERE dataset_id=? AND environment=? AND scope=?",
                    (binding.dataset_id, operation["environment"], operation["scope"]),
                )
                if not ready or not ready["output_id"]:
                    raise DependencyBlocked(f"No validated output: {binding.dataset_id}")
                if ready["expected_status"] in {"FAILED", "UNCERTAIN", "CORRUPT"}:
                    raise DependencyBlocked(
                        f"Latest expected upstream failure: {binding.dataset_id}"
                    )
            age = (utc_datetime(tx.now) - utc_datetime(coverage[1])).total_seconds()
            freshness = (
                spec.freshness_seconds
                if spec.freshness_seconds is not None
                else snapshot.dataset(binding.dataset_id).freshness_seconds
            )
            if (
                age > freshness
                and not spec.allow_stale
                and operation["source_mode"] != "historical"
            ):
                raise DependencyBlocked(f"Stale committed coverage: {binding.dataset_id}")
        for parent_id in task.ordering_after:
            parent = snapshot.task(parent_id)
            ready = tx.one(
                f"SELECT * FROM {tx.table('readiness')} "
                "WHERE dataset_id=? AND environment=? AND scope=?",
                (parent.primary_output, operation["environment"], parent.scope),
            )
            if (
                not ready
                or not ready["progress_end"]
                or ready["progress_end"] < operation["window_end"]
                or ready["expected_status"] in {"FAILED", "UNCERTAIN", "CORRUPT"}
                or not ready["source_coverage_end"]
                or (
                    operation["source_mode"] != "historical"
                    and (
                        utc_datetime(tx.now) - utc_datetime(ready["source_coverage_end"])
                    ).total_seconds()
                    > snapshot.dataset(parent.primary_output).freshness_seconds
                )
                or self._blocked(tx, parent.primary_output, operation["environment"], parent.scope)
            ):
                raise DependencyBlocked(f"Exceptional ordering predecessor not ready: {parent_id}")

    def claim(self, operation_id: str, owner: str, lease_seconds: int = 300) -> Claim | None:
        if not owner or lease_seconds <= 0:
            raise ValueError("Claim owner and positive lease required")
        blocked: DependencyBlocked | None = None
        result = None
        with self.transaction() as tx:
            op = self._operation(tx, operation_id)
            if op["status"] in {"SUCCEEDED", "FAILED", "CANCELED", "UNCERTAIN"}:
                return None
            if op["lease_until"] and op["lease_until"] > tx.now:
                return None
            if self._blocked(tx, op["dataset_id"], op["environment"], op["scope"]):
                blocked = DependencyBlocked("Output dataset is explicitly blocked")
            try:
                if not blocked:
                    self._check_inputs(tx, op)
            except DependencyBlocked as error:
                blocked = error
            if blocked:
                tx.update(
                    "operation",
                    "operation_id=?",
                    (operation_id,),
                    status="BLOCKED_BY_DEPENDENCY",
                    last_error=str(blocked),
                    updated_at=tx.now,
                )
                self._expected(tx, op, "BLOCKED_BY_DEPENDENCY")
            else:
                conflicts = tx.all(
                    f"SELECT * FROM {tx.table('operation')} WHERE dataset_id=? AND environment=? "
                    "AND scope=? AND operation_id<>? AND window_start<? AND window_end>? "
                    "AND status NOT IN ('SUCCEEDED','FAILED','CANCELED')",
                    (
                        op["dataset_id"],
                        op["environment"],
                        op["scope"],
                        operation_id,
                        op["window_end"],
                        op["window_start"],
                    ),
                )
                for other in conflicts:
                    if (
                        other["status"] == "UNCERTAIN"
                        or other["status"] == "RUNNING"
                        or (other["lease_until"] and other["lease_until"] > tx.now)
                        or (op["kind"] != "daily" and other["kind"] == "daily")
                        or (
                            other["kind"] == op["kind"]
                            and (other["created_at"], other["operation_id"])
                            < (op["created_at"], operation_id)
                        )
                    ):
                        return None
                if op["attempt_id"]:
                    tx.update(
                        "attempt",
                        "attempt_id=?",
                        (op["attempt_id"],),
                        status="LEASE_EXPIRED",
                        completed_at=tx.now,
                    )
                attempt_id, fence = str(uuid.uuid4()), op["fence"] + 1
                until = utc_text(utc_datetime(tx.now) + timedelta(seconds=lease_seconds))
                tx.insert(
                    "attempt",
                    attempt_id=attempt_id,
                    operation_id=operation_id,
                    owner=owner,
                    fence=fence,
                    started_at=tx.now,
                    completed_at=None,
                    status="RUNNING",
                )
                tx.update(
                    "operation",
                    "operation_id=?",
                    (operation_id,),
                    status="RUNNING",
                    fence=fence,
                    owner=owner,
                    lease_until=until,
                    attempt_id=attempt_id,
                    updated_at=tx.now,
                    last_error=None,
                )
                self._audit(tx, "claimed", operation_id, {"attempt": attempt_id, "fence": fence})
                result = Claim(operation_id, attempt_id, owner, fence, until)
        if blocked:
            raise blocked
        return result

    @staticmethod
    def _fenced(tx: _Session, claim: Claim) -> dict[str, Any]:
        op = ControlStore._operation(tx, claim.operation_id)
        if (
            op["attempt_id"] != claim.attempt_id
            or op["fence"] != claim.fence
            or op["owner"] != claim.owner
            or not op["lease_until"]
            or op["lease_until"] <= tx.now
            or op["status"] != "RUNNING"
        ):
            raise LeaseLost("Attempt no longer owns an unexpired fence")
        return op

    def assert_fence(self, claim: Claim) -> None:
        """Check before writing; Delta also needs an idempotent operation token."""
        with self.transaction() as tx:
            self._fenced(tx, claim)

    def heartbeat(self, claim: Claim, lease_seconds: int = 300) -> Claim:
        if lease_seconds <= 0:
            raise ValueError("Positive heartbeat lease required")
        with self.transaction() as tx:
            self._fenced(tx, claim)
            until = utc_text(utc_datetime(tx.now) + timedelta(seconds=lease_seconds))
            tx.update(
                "operation",
                "operation_id=?",
                (claim.operation_id,),
                lease_until=until,
                updated_at=tx.now,
            )
            return Claim(claim.operation_id, claim.attempt_id, claim.owner, claim.fence, until)

    def _expected(self, tx: _Session, op: Mapping[str, Any], status: str) -> None:
        tx.update(
            "readiness",
            "dataset_id=? AND environment=? AND scope=? AND expected_operation_id=?",
            (op["dataset_id"], op["environment"], op["scope"], op["operation_id"]),
            expected_status=status,
            updated_at=tx.now,
        )

    def fail(self, claim: Claim, reason_code: str, *, uncertain: bool = False) -> None:
        """Never mark a possibly committed Delta write as routine FAILED."""
        with self.transaction() as tx:
            op = self._fenced(tx, claim)
            status = "UNCERTAIN" if uncertain else "FAILED"
            tx.update(
                "operation",
                "operation_id=?",
                (claim.operation_id,),
                status=status,
                lease_until=None,
                last_error=reason_code,
                updated_at=tx.now,
            )
            tx.update(
                "attempt", "attempt_id=?", (claim.attempt_id,), status=status, completed_at=tx.now
            )
            self._expected(tx, op, status)
            self._audit(tx, status.lower(), claim.operation_id, {"reason_code": reason_code})

    def retry_operation(self, operation_id: str, *, operator_approval: str | None = None) -> None:
        """Bounded scheduler retry reuses the operation/input token, never silently recaptures."""
        with self.transaction() as tx:
            op = self._operation(tx, operation_id)
            if op["status"] != "FAILED":
                raise ControlError("Only a routine failed operation may be retried")
            snapshot = self._snapshot(tx, op["release_version"])
            retries = (
                snapshot.effective_settings(op["task_id"]).get("scheduler", {}).get("retries", 0)
            )
            attempts = tx.all(
                f"SELECT attempt_id FROM {tx.table('attempt')} WHERE operation_id=?",
                (operation_id,),
            )
            if len(attempts) > retries and not operator_approval:
                raise ControlError(
                    "Scheduler retries exhausted; explicit operator intervention required"
                )
            tx.update(
                "operation",
                "operation_id=?",
                (operation_id,),
                status="QUEUED",
                owner=None,
                lease_until=None,
                updated_at=tx.now,
            )
            self._audit(tx, "retry_queued", operation_id, {"operator_approval": operator_approval})

    def _validate_evidence(
        self,
        tx: _Session,
        op: Mapping[str, Any],
        evidence: CommitEvidence,
    ) -> CommitEvidence:
        bindings = ControlStore._bindings(tx, op["operation_id"])
        expected_inputs = {binding.dataset_id: binding.version for binding in bindings}
        if (
            evidence.operation_id != op["operation_id"]
            or evidence.dataset_id != op["dataset_id"]
            or evidence.window_start != op["window_start"]
            or evidence.window_end != op["window_end"]
            or thaw(evidence.input_versions) != expected_inputs
            or evidence.commit_token != op["operation_id"]
            or not evidence.coverage_verified
        ):
            raise ControlError("Commit evidence does not match immutable operation/coverage/inputs")
        coverage = [self._binding_source_coverage(tx, binding) for binding in bindings]
        if not coverage:
            raise ControlError("Publication requires verified input source coverage")
        start, end = max(bounds[0] for bounds in coverage), min(bounds[1] for bounds in coverage)
        if start >= end:
            raise ControlError("Input source coverage has no common verified interval")
        if evidence.source_coverage_start is None:
            if not self.legacy_same_window_coverage or tx.sqlserver:
                raise ControlError("Publication requires explicit verified source coverage")
            evidence = replace(evidence, source_coverage_start=start, source_coverage_end=end)
        if evidence.source_coverage_start < start or evidence.source_coverage_end > end:
            raise ControlError(
                "Output source coverage is forged beyond authoritative input coverage"
            )
        return evidence

    def _publish(self, tx: _Session, op: Mapping[str, Any], evidence: CommitEvidence) -> str:
        evidence = self._validate_evidence(tx, op, evidence)
        evidence_hash = digest_json(evidence.to_dict())
        old = tx.one(
            f"SELECT * FROM {tx.table('output')} WHERE operation_id=?", (op["operation_id"],)
        )
        if old:
            if old["evidence_hash"] != evidence_hash:
                raise ControlError("Operation already published with different commit evidence")
            return old["output_id"]
        if self._blocked(tx, op["dataset_id"], op["environment"], op["scope"]):
            raise ControlError("Blocked output requires operator validation before publication")
        critical = tx.one(
            f"SELECT record_id FROM {tx.table('quality_outcome')} WHERE operation_id=? "
            "AND attempt_id=? AND severity='critical' AND status<>'PASS'",
            (op["operation_id"], op["attempt_id"]),
        )
        if critical:
            raise ControlError("Persisted critical/unavailable quality evidence blocks publication")
        output_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"healthcare-output:{op['operation_id']}"))
        tx.insert(
            "output",
            output_id=output_id,
            operation_id=op["operation_id"],
            dataset_id=op["dataset_id"],
            environment=op["environment"],
            scope=op["scope"],
            delta_version=evidence.delta_version,
            window_start=evidence.window_start,
            window_end=evidence.window_end,
            source_coverage_start=evidence.source_coverage_start,
            source_coverage_end=evidence.source_coverage_end,
            evidence_json=canonical_json(evidence.to_dict()),
            evidence_hash=evidence_hash,
            committed_at=tx.now,
            changed_rows=evidence.changed_rows,
        )
        for kind, reference, holder in (
            (
                "operation",
                op["operation_id"],
                f"committed-data:{digest_json(op['environment'])[:16]}",
            ),
            ("release", op["release_version"], f"committed-output:{output_id}"),
        ):
            hold_id = digest_json([kind, reference, holder])
            tx.insert(
                "hold",
                hold_id=hold_id,
                kind=kind,
                reference_id=reference,
                holder=holder,
                created_at=tx.now,
                released_at=None,
            )
        ready = tx.one(
            f"SELECT * FROM {tx.table('readiness')} WHERE dataset_id=? "
            "AND environment=? AND scope=?",
            (op["dataset_id"], op["environment"], op["scope"]),
        )
        if evidence.changed_rows == 0 and ready["output_id"]:
            previous = tx.one(
                f"SELECT delta_version FROM {tx.table('output')} WHERE output_id=?",
                (ready["output_id"],),
            )
            if previous["delta_version"] != evidence.delta_version:
                raise ControlError(
                    "Validated no-change must preserve the existing Delta data version"
                )
        if (
            not ready["source_coverage_end"]
            or evidence.source_coverage_end > ready["source_coverage_end"]
            or (
                evidence.source_coverage_end == ready["source_coverage_end"]
                and (
                    not ready["progress_end"]
                    or op["window_end"] > ready["progress_end"]
                    or (
                        op["window_end"] == ready["progress_end"]
                        and op["operation_id"] == ready["expected_operation_id"]
                    )
                )
            )
        ):
            tx.update(
                "readiness",
                "dataset_id=? AND environment=? AND scope=?",
                (op["dataset_id"], op["environment"], op["scope"]),
                output_id=output_id,
                source_coverage_start=evidence.source_coverage_start,
                source_coverage_end=evidence.source_coverage_end,
                updated_at=tx.now,
            )
        if not ready["progress_end"] or op["window_end"] > ready["progress_end"]:
            tx.update(
                "readiness",
                "dataset_id=? AND environment=? AND scope=?",
                (op["dataset_id"], op["environment"], op["scope"]),
                progress_end=op["window_end"],
                updated_at=tx.now,
            )
        self._expected(tx, op, "SUCCEEDED")
        tx.update(
            "operation",
            "operation_id=?",
            (op["operation_id"],),
            status="SUCCEEDED",
            lease_until=None,
            updated_at=tx.now,
            last_error=None,
        )
        if op["attempt_id"]:
            tx.update(
                "attempt",
                "attempt_id=?",
                (op["attempt_id"],),
                status="SUCCEEDED",
                completed_at=tx.now,
            )
        prior = tx.all(
            f"SELECT event_sequence FROM {tx.table('event')} WHERE dataset_id=? "
            "AND environment=? AND scope=?",
            (op["dataset_id"], op["environment"], op["scope"]),
        )
        sequence = max((r["event_sequence"] for r in prior), default=0) + 1
        tx.insert(
            "event",
            event_id=f"output:{output_id}",
            dataset_id=op["dataset_id"],
            environment=op["environment"],
            scope=op["scope"],
            output_id=output_id,
            event_sequence=sequence,
            progress_end=op["window_end"],
            created_at=tx.now,
            delivered_at=None,
            dispatch_attempts=0,
            next_retry_at=None,
            last_error=None,
        )
        self._audit(
            tx,
            "published",
            op["operation_id"],
            {"output": output_id, "evidence_hash": evidence_hash},
        )
        return output_id

    def publish(
        self,
        claim: Claim,
        evidence: CommitEvidence,
        verify_commit: Callable[[CommitEvidence], bool],
    ) -> str:
        """Verifier must read actual Delta transaction/validation evidence, not notebook status."""
        if not verify_commit(evidence):
            raise ControlError("Delta commit/coverage validation evidence could not be verified")
        with self.transaction() as tx:
            op = self._operation(tx, claim.operation_id)
            if op["status"] == "SUCCEEDED":
                return self._publish(tx, op, evidence)
            op = self._fenced(tx, claim)
            return self._publish(tx, op, evidence)

    def reconcile_commit(
        self,
        operation_id: str,
        evidence: CommitEvidence,
        verify_commit: Callable[[CommitEvidence], bool],
    ) -> str:
        """Repair post-Delta/pre-SQL uncertainty without executing or appending the batch again."""
        if not verify_commit(evidence):
            raise ControlError("Reconciliation could not verify durable Delta evidence")
        with self.transaction() as tx:
            op = self._operation(tx, operation_id)
            if op["status"] == "RUNNING" and op["lease_until"] > tx.now:
                raise ControlError(
                    "Live owner must publish; reconciliation cannot steal its commit"
                )
            if op["status"] not in {"RUNNING", "UNCERTAIN", "SUCCEEDED"}:
                raise ControlError("Operation is not an uncertain/completed write")
            output = self._publish(tx, op, evidence)
            self._audit(tx, "commit_reconciled", operation_id, {"output": output})
            return output

    def readiness(
        self, dataset_id: str, environment: str, scope: str = "default"
    ) -> dict[str, Any]:
        with self.transaction() as tx:
            row = tx.one(
                f"SELECT * FROM {tx.table('readiness')} WHERE dataset_id=? "
                "AND environment=? AND scope=?",
                (dataset_id, environment, scope),
            )
            if not row:
                return {"ready": False, "reason": "missing", "output_id": None}
            blocked = self._blocked(tx, dataset_id, environment, scope)
            active = tx.one(
                f"SELECT version FROM {tx.table('active')} WHERE environment=?", (environment,)
            )
            stale = False
            unknown_coverage = bool(row["output_id"]) and not row["source_coverage_end"]
            if active and row["source_coverage_end"]:
                dataset = self._snapshot(tx, active["version"]).dataset(dataset_id)
                age = (
                    utc_datetime(tx.now) - utc_datetime(row["source_coverage_end"])
                ).total_seconds()
                stale = age > dataset.freshness_seconds
            row["ready"] = (
                bool(row["output_id"])
                and not blocked
                and not stale
                and not unknown_coverage
                and row["expected_status"]
                not in {
                    "FAILED",
                    "UNCERTAIN",
                    "CORRUPT",
                }
            )
            row["reason"] = (
                "corruption"
                if blocked
                else "unverified_source_coverage"
                if unknown_coverage
                else "stale_coverage"
                if stale
                else row["expected_status"]
            )
            return row

    def output_history(self, dataset_id: str, environment: str) -> tuple[dict[str, Any], ...]:
        with self.transaction() as tx:
            return tuple(
                tx.all(
                    f"SELECT * FROM {tx.table('output')} "
                    "WHERE dataset_id=? AND environment=? ORDER BY window_end,committed_at",
                    (dataset_id, environment),
                )
            )

    def operation(self, operation_id: str) -> Mapping[str, Any]:
        with self.transaction() as tx:
            op = self._operation(tx, operation_id)
            waiting = tx.one(
                f"SELECT * FROM {tx.table('waiting')} WHERE operation_id=?",
                (operation_id,),
            )
            if waiting:
                op.update(
                    binding_state="BOUND" if waiting["bound_at"] is not None else "UNRESOLVED",
                    declared_inputs=json.loads(waiting["declared_inputs_json"]),
                    binding_hash=waiting["binding_hash"],
                    bound_at=waiting["bound_at"],
                )
            return freeze(op)

    def scheduled_operations(
        self,
        environment: str,
        window_start: str | datetime,
        window_end: str | datetime,
        limit: int = 1000,
    ) -> tuple[Mapping[str, Any], ...]:
        """Read all daily outcomes overlapping a UTC processing range, never dispatch-only."""
        if (
            not isinstance(environment, str)
            or not environment
            or len(environment) > 128
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
            or not isinstance(window_start, (str, datetime))
            or not isinstance(window_end, (str, datetime))
        ):
            raise ValueError("An environment and read budget in [1,1000] are required")
        start, end = utc_text(window_start), utc_text(window_end)
        if start >= end:
            raise ValueError("Schedule query requires a positive half-open UTC range")
        with self.transaction() as tx:
            prefix = f"TOP ({limit}) " if tx.sqlserver else ""
            suffix = "" if tx.sqlserver else " LIMIT ?"
            params = (environment, end, start) if tx.sqlserver else (environment, end, start, limit)
            rows = tx.all(
                f"SELECT {prefix}o.*,w.declared_inputs_json AS _declared_inputs_json,"
                "w.binding_hash AS _waiting_binding_hash,w.bound_at AS _waiting_bound_at,"
                "p.source_coverage_start,p.source_coverage_end,"
                f"CASE WHEN EXISTS (SELECT 1 FROM {tx.table('block')} b "
                "WHERE b.dataset_id=o.dataset_id AND b.environment=o.environment "
                "AND b.scope=o.scope AND b.cleared_at IS NULL) THEN 1 ELSE 0 END "
                "AS corruption_blocked "
                f"FROM {tx.table('operation')} o "
                f"LEFT JOIN {tx.table('waiting')} w ON w.operation_id=o.operation_id "
                f"LEFT JOIN {tx.table('output')} p ON p.operation_id=o.operation_id "
                "WHERE o.environment=? AND o.kind='daily' AND o.window_start<? AND o.window_end>? "
                "ORDER BY o.window_end,o.window_start,o.operation_id" + suffix,
                params,
            )
            result = []
            for row in rows:
                declared = row.pop("_declared_inputs_json")
                binding_hash = row.pop("_waiting_binding_hash")
                bound_at = row.pop("_waiting_bound_at")
                if declared is not None:
                    row.update(
                        binding_state="BOUND" if bound_at is not None else "UNRESOLVED",
                        declared_inputs=json.loads(declared),
                        binding_hash=binding_hash,
                        bound_at=bound_at,
                    )
                row["corruption_blocked"] = bool(row["corruption_blocked"])
                row["health_status"] = "CORRUPT" if row["corruption_blocked"] else row["status"]
                result.append(freeze(row))
            return tuple(result)

    def inputs(self, operation_id: str) -> tuple[InputBinding, ...]:
        with self.transaction() as tx:
            return self._bindings(tx, operation_id)

    def register_source_snapshot(
        self,
        dataset_id: str,
        environment: str,
        version: str,
        window_start: str | datetime,
        window_end: str | datetime,
        *,
        evidence_digest: str,
        artifact_ref: str,
        verify_snapshot: Callable[[], bool],
        scope: str = "default",
    ) -> str:
        """Register verified retained source coverage for current or historical input snapshots."""
        start, end = utc_text(window_start), utc_text(window_end)
        if start >= end or not evidence_digest or not artifact_ref or not verify_snapshot():
            raise ControlError(
                "A saved historical source snapshot needs verified retained evidence"
            )
        snapshot_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                canonical_json([dataset_id, environment, scope, version, start, end]),
            )
        )
        with self.transaction() as tx:
            dataset = tx.one(
                f"SELECT [external] FROM {tx.table('identity')} WHERE dataset_id=?", (dataset_id,)
            )
            if not dataset or not dataset["external"]:
                raise ControlError(
                    "Source snapshots reference a registered external logical dataset"
                )
            previous = tx.one(
                f"SELECT * FROM {tx.table('source')} WHERE source_snapshot_id=?", (snapshot_id,)
            )
            if previous:
                if (
                    previous["evidence_digest"] != evidence_digest
                    or previous["artifact_ref"] != artifact_ref
                    or previous["retired_at"]
                ):
                    raise ControlError("Source snapshot identity/evidence is immutable")
                return snapshot_id
            tx.insert(
                "source",
                source_snapshot_id=snapshot_id,
                dataset_id=dataset_id,
                environment=environment,
                scope=scope,
                version=version,
                window_start=start,
                window_end=end,
                evidence_digest=evidence_digest,
                artifact_ref=artifact_ref,
                created_at=tx.now,
                retired_at=None,
            )
            self._audit(
                tx,
                "source_snapshot_registered",
                snapshot_id,
                {"dataset": dataset_id, "version": version, "evidence": evidence_digest},
            )
            return snapshot_id

    def flag_corruption(
        self,
        dataset_id: str,
        environment: str,
        release_version: str,
        incident_id: str,
        *,
        scope: str = "default",
    ) -> tuple[str, ...]:
        with self.transaction() as tx:
            snapshot = self._snapshot(tx, release_version)
            snapshot.dataset(dataset_id)
            affected_set = set(snapshot.descendants(dataset_id))
            releases = tx.all(
                f"SELECT DISTINCT version FROM {tx.table('activation')} WHERE environment=?",
                (environment,),
            )
            lineage = tx.all(
                f"SELECT o.dataset_id,b.dataset_id AS input_id FROM {tx.table('operation')} o "
                f"JOIN {tx.table('binding')} b ON b.operation_id=o.operation_id "
                "WHERE o.environment=? AND o.scope=?",
                (environment, scope),
            )
            changed = True
            while changed:
                before = set(affected_set)
                for release in releases:
                    approved = self._snapshot(tx, release["version"])
                    registered = {d.dataset_id for d in approved.datasets}
                    for affected_id in tuple(affected_set & registered):
                        affected_set.update(approved.descendants(affected_id))
                affected_set.update(
                    edge["dataset_id"] for edge in lineage if edge["input_id"] in affected_set
                )
                changed = before != affected_set
            affected = tuple(sorted(affected_set))
            for affected_id in affected:
                block_id = f"{incident_id}:{environment}:{scope}:{affected_id}"
                if not tx.one(
                    f"SELECT block_id FROM {tx.table('block')} WHERE block_id=?", (block_id,)
                ):
                    tx.insert(
                        "block",
                        block_id=block_id,
                        incident_id=incident_id,
                        dataset_id=affected_id,
                        environment=environment,
                        scope=scope,
                        release_version=release_version,
                        created_at=tx.now,
                        cleared_at=None,
                        operator_approval=None,
                        validation_digest=None,
                    )
            self._audit(tx, "corruption_blocked", incident_id, {"datasets": affected})
            return affected

    def clear_corruption(
        self,
        incident_id: str,
        dataset_id: str,
        environment: str,
        *,
        operator_approval: str,
        validation_digest: str,
        scope: str = "default",
    ) -> None:
        if not operator_approval or not validation_digest:
            raise ControlError(
                "Confirmed corruption requires explicit operator approval and validation"
            )
        with self.transaction() as tx:
            row = tx.one(
                f"SELECT block_id FROM {tx.table('block')} WHERE incident_id=? "
                "AND dataset_id=? AND environment=? AND scope=? AND cleared_at IS NULL",
                (incident_id, dataset_id, environment, scope),
            )
            if not row:
                raise ControlError("No active corruption block")
            tx.update(
                "block",
                "block_id=?",
                (row["block_id"],),
                cleared_at=tx.now,
                operator_approval=operator_approval,
                validation_digest=validation_digest,
            )
            self._audit(
                tx,
                "corruption_cleared",
                incident_id,
                {
                    "dataset": dataset_id,
                    "approval": operator_approval,
                    "validation": validation_digest,
                },
            )

    def pending_events(self, *, coalesce: bool = True) -> tuple[dict[str, Any], ...]:
        with self.transaction() as tx:
            events = tx.all(
                f"SELECT * FROM {tx.table('event')} WHERE delivered_at IS NULL "
                "AND (next_retry_at IS NULL OR next_retry_at<=?) "
                "ORDER BY environment,scope,dataset_id,event_sequence",
                (tx.now,),
            )
            if not coalesce:
                return tuple(events)
            newest: dict[tuple[str, str, str], dict[str, Any]] = {}
            for event in events:
                key = (event["environment"], event["scope"], event["dataset_id"])
                old = newest.get(key)
                if old is None or (event["progress_end"], event["event_sequence"]) > (
                    old["progress_end"],
                    old["event_sequence"],
                ):
                    newest[key] = event
            return tuple(newest.values())

    def consume_event(self, event_id: str, consumer_id: str, *, process_each: bool = False) -> bool:
        """Deduplicate/order a wakeup; dispatch still MUST call claim to recheck every input."""
        with self.transaction() as tx:
            event = tx.one(f"SELECT * FROM {tx.table('event')} WHERE event_id=?", (event_id,))
            if not event:
                raise ControlError("Unknown readiness event")
            prior = tx.all(
                f"SELECT r.*,e.progress_end,e.event_sequence "
                f"FROM {tx.table('receipt')} r JOIN {tx.table('event')} e "
                "ON e.event_id=r.event_id WHERE r.consumer_id=? AND e.dataset_id=? "
                "AND e.environment=? AND e.scope=?",
                (consumer_id, event["dataset_id"], event["environment"], event["scope"]),
            )
            if any(p["event_id"] == event_id for p in prior):
                return False
            accepted = process_each or not any(
                (p["progress_end"], p["event_sequence"])
                >= (event["progress_end"], event["event_sequence"])
                for p in prior
                if p["accepted"]
            )
            tx.insert(
                "receipt",
                event_id=event_id,
                consumer_id=consumer_id,
                accepted=int(accepted),
                received_at=tx.now,
            )
            return accepted

    def acknowledge_event(self, event_id: str, *, coalesced: bool = False) -> None:
        with self.transaction() as tx:
            event = tx.one(f"SELECT * FROM {tx.table('event')} WHERE event_id=?", (event_id,))
            if not event:
                raise ControlError("Unknown event")
            if coalesced:
                tx.update(
                    "event",
                    "dataset_id=? AND environment=? AND scope=? AND progress_end<=?",
                    (
                        event["dataset_id"],
                        event["environment"],
                        event["scope"],
                        event["progress_end"],
                    ),
                    delivered_at=tx.now,
                )
            else:
                tx.update("event", "event_id=?", (event_id,), delivered_at=tx.now)

    def dispatch_events(
        self,
        deliver: Callable[[Mapping[str, Any]], None],
        *,
        coalesce: bool = True,
        max_attempts: int = 3,
        retry_delay_seconds: int = 30,
    ) -> tuple[str, ...]:
        """Stable at-least-once event transport; SQL reconciliation repairs lost delivery."""
        if max_attempts <= 0 or retry_delay_seconds <= 0:
            raise ValueError("Event delivery requires bounded retries and positive backoff")
        delivered = []
        for event in self.pending_events(coalesce=coalesce):
            with self.transaction() as tx:
                current = tx.one(
                    f"SELECT * FROM {tx.table('event')} WHERE event_id=?", (event["event_id"],)
                )
                if current["delivered_at"] or current["dispatch_attempts"] >= max_attempts:
                    continue
                attempt = current["dispatch_attempts"] + 1
                retry_at = utc_text(
                    utc_datetime(tx.now)
                    + timedelta(seconds=retry_delay_seconds * 2 ** (attempt - 1))
                )
                tx.update(
                    "event",
                    "event_id=?",
                    (event["event_id"],),
                    dispatch_attempts=attempt,
                    next_retry_at=retry_at,
                )
            try:
                deliver(freeze(event))
            except Exception:
                # A transport may have accepted the event before losing its acknowledgement.
                # Do not retain exception text, which could include credentials or patient values.
                with self.transaction() as tx:
                    tx.update(
                        "event", "event_id=?", (event["event_id"],), last_error="DELIVERY_UNCERTAIN"
                    )
                    if attempt == max_attempts:
                        self._audit(
                            tx,
                            "outlook_alert_required",
                            event["event_id"],
                            {"reason": "event_delivery_exhausted", "channel": "email"},
                        )
            else:
                self.acknowledge_event(event["event_id"], coalesced=coalesce)
                delivered.append(event["event_id"])
        return tuple(delivered)

    def begin_reconciliation(
        self,
        environment: str,
        owner: str,
        *,
        interval_seconds: int = 300,
        lease_seconds: int = 300,
        max_retries: int = 3,
    ) -> Mapping[str, Any] | None:
        if min(interval_seconds, lease_seconds) <= 0 or max_retries < 0:
            raise ValueError("Invalid bounded reconciliation policy")
        with self.transaction() as tx:
            rows = tx.all(
                f"SELECT * FROM {tx.table('reconcile')} WHERE environment=? "
                "ORDER BY started_at DESC",
                (environment,),
            )
            if rows:
                last = rows[0]
                if last["status"] == "RUNNING" and last["lease_until"] > tx.now:
                    return None
                elapsed = (utc_datetime(tx.now) - utc_datetime(last["started_at"])).total_seconds()
                if elapsed < interval_seconds:
                    return None
                if last["status"] == "RUNNING":
                    tx.update(
                        "reconcile",
                        "reconciliation_id=?",
                        (last["reconciliation_id"],),
                        status="LEASE_EXPIRED",
                        completed_at=tx.now,
                    )
            active = tx.one(
                f"SELECT version FROM {tx.table('active')} WHERE environment=?", (environment,)
            )
            if not active:
                raise ControlError("No active snapshot for reconciliation")
            snapshot = self._snapshot(tx, active["version"])
            until = utc_text(utc_datetime(tx.now) + timedelta(seconds=lease_seconds))
            result = dict(
                reconciliation_id=str(uuid.uuid4()),
                environment=environment,
                owner=owner,
                release_version=snapshot.version,
                snapshot_hash=snapshot.digest,
                snapshot_json=canonical_json(snapshot.to_dict()),
                started_at=tx.now,
                lease_until=until,
                completed_at=None,
                status="RUNNING",
                retry_count=0,
                max_retries=max_retries,
                next_retry_at=None,
                last_error=None,
            )
            tx.insert("reconcile", **result)
            return freeze(result)

    def reconciliation_operations(self, reconciliation_id: str, owner: str) -> tuple[str, ...]:
        with self.transaction() as tx:
            self._reconciliation_owner(tx, reconciliation_id, owner)
            run = tx.one(
                f"SELECT environment FROM {tx.table('reconcile')} WHERE reconciliation_id=?",
                (reconciliation_id,),
            )
            return tuple(
                r["operation_id"]
                for r in tx.all(
                    f"SELECT operation_id FROM {tx.table('operation')} WHERE environment=? "
                    "AND status IN ('QUEUED','BLOCKED_BY_DEPENDENCY','UNCERTAIN','RUNNING') "
                    "ORDER BY CASE WHEN kind='daily' THEN 0 ELSE 1 END,window_end,created_at",
                    (run["environment"],),
                )
            )

    @staticmethod
    def _reconciliation_owner(tx: _Session, reconciliation_id: str, owner: str) -> dict[str, Any]:
        row = tx.one(
            f"SELECT * FROM {tx.table('reconcile')} WHERE reconciliation_id=?", (reconciliation_id,)
        )
        if (
            not row
            or row["owner"] != owner
            or row["status"] != "RUNNING"
            or row["lease_until"] <= tx.now
        ):
            raise LeaseLost("Reconciliation owner expired or replaced")
        return row

    def finish_reconciliation(
        self,
        reconciliation_id: str,
        owner: str,
        *,
        error_code: str | None = None,
        retry_delay_seconds: int = 30,
    ) -> Mapping[str, Any]:
        if retry_delay_seconds <= 0:
            raise ValueError("Retry backoff must be positive")
        with self.transaction() as tx:
            row = self._reconciliation_owner(tx, reconciliation_id, owner)
            values: dict[str, Any]
            if error_code:
                if row["next_retry_at"] and row["next_retry_at"] > tx.now:
                    raise ControlError("Retry backoff has not elapsed")
                count = row["retry_count"] + 1
                exhausted = count > row["max_retries"]
                values = {
                    "retry_count": count,
                    "last_error": error_code,
                    "status": "FAILED" if exhausted else "RUNNING",
                    "completed_at": tx.now if exhausted else None,
                    "next_retry_at": utc_text(
                        utc_datetime(tx.now)
                        + timedelta(seconds=retry_delay_seconds * (2 ** min(count - 1, 10)))
                    ),
                }
                if exhausted:
                    self._audit(
                        tx,
                        "outlook_alert_required",
                        reconciliation_id,
                        {"reason": error_code, "notification_channel": "email"},
                    )
            else:
                values = {"status": "SUCCEEDED", "completed_at": tx.now, "next_retry_at": None}
            tx.update("reconcile", "reconciliation_id=?", (reconciliation_id,), **values)
            return freeze({**row, **values})

    def heartbeat_reconciliation(
        self,
        reconciliation_id: str,
        owner: str,
        lease_seconds: int = 300,
    ) -> str:
        if lease_seconds <= 0:
            raise ValueError("Positive reconciliation heartbeat lease required")
        with self.transaction() as tx:
            self._reconciliation_owner(tx, reconciliation_id, owner)
            until = utc_text(utc_datetime(tx.now) + timedelta(seconds=lease_seconds))
            tx.update("reconcile", "reconciliation_id=?", (reconciliation_id,), lease_until=until)
            return until

    def hold_reference(self, kind: str, reference_id: str, holder: str) -> None:
        """Protect evidence while active executions or approved recovery need it."""
        if kind not in {"delta", "output", "release", "operation", "artifact"} or not holder:
            raise ValueError("Invalid reference hold")
        with self.transaction() as tx:
            key = digest_json([kind, reference_id, holder])
            previous = tx.one(
                f"SELECT hold_id,released_at FROM {tx.table('hold')} WHERE hold_id=?", (key,)
            )
            if not previous:
                tx.insert(
                    "hold",
                    hold_id=key,
                    kind=kind,
                    reference_id=reference_id,
                    holder=holder,
                    created_at=tx.now,
                    released_at=None,
                )
            elif previous["released_at"] is not None:
                tx.update("hold", "hold_id=?", (key,), released_at=None)

    def release_reference(self, kind: str, reference_id: str, holder: str) -> None:
        with self.transaction() as tx:
            tx.update(
                "hold",
                "hold_id=?",
                (digest_json([kind, reference_id, holder]),),
                released_at=tx.now,
            )

    def protected_references(self, environment: str) -> Mapping[str, Any]:
        """Expose cleanup protections, without performing VACUUM or data deletion."""
        with self.transaction() as tx:
            bindings = tx.all(
                f"SELECT b.*,o.release_version FROM {tx.table('binding')} b "
                f"JOIN {tx.table('operation')} o ON o.operation_id=b.operation_id "
                "WHERE o.environment=? AND o.status NOT IN ('SUCCEEDED','FAILED','CANCELED')",
                (environment,),
            )
            holds = tx.all(f"SELECT * FROM {tx.table('hold')} WHERE released_at IS NULL")
            current = tx.all(
                f"SELECT dataset_id,scope,output_id FROM {tx.table('readiness')} "
                "WHERE environment=?",
                (environment,),
            )
            return freeze(
                {"active_inputs": bindings, "explicit_holds": holds, "current_outputs": current}
            )

    def can_cleanup_output(self, output_id: str, audit_years: int = 7) -> bool:
        """This authorizes evidence cleanup, NOT deletion/undo of Bronze or Silver data."""
        if audit_years < 7:
            raise ControlError("Execution/readiness audit target is at least seven years")
        with self.transaction() as tx:
            output = tx.one(f"SELECT * FROM {tx.table('output')} WHERE output_id=?", (output_id,))
            if not output:
                return False
            created = utc_datetime(output["committed_at"])
            now = utc_datetime(tx.now)
            try:
                expiry = created.replace(year=created.year + audit_years)
            except ValueError:
                expiry = created.replace(year=created.year + audit_years, day=28)
            if now < expiry:
                return False
            if tx.one(
                f"SELECT output_id FROM {tx.table('readiness')} WHERE output_id=?", (output_id,)
            ):
                return False
            if tx.one(
                f"SELECT output_id FROM {tx.table('binding')} WHERE output_id=?", (output_id,)
            ):
                return False
            if tx.one(
                f"SELECT hold_id FROM {tx.table('hold')} WHERE released_at IS NULL "
                "AND reference_id IN (?,?,?)",
                (output_id, output["delta_version"], output["operation_id"]),
            ):
                return False
            return True

    def source_snapshot_info(self, snapshot_id: str) -> Mapping[str, Any]:
        """Read the exact registered saved-source manifest; never resolve to current source."""
        with self.transaction() as tx:
            row = tx.one(
                f"SELECT * FROM {tx.table('source')} WHERE source_snapshot_id=?", (snapshot_id,)
            )
            if not row:
                raise ControlError("Registered historical source snapshot is unavailable")
            return freeze(row)

    def _prepare_operational_record(
        self,
        tx: _Session,
        kind: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        op = self._operation(tx, data["operation_id"])
        attempt = tx.one(
            f"SELECT operation_id FROM {tx.table('attempt')} WHERE attempt_id=?",
            (data["attempt_id"],),
        )
        if (
            not attempt
            or attempt["operation_id"] != op["operation_id"]
            or data["release_version"] != op["release_version"]
        ):
            raise ControlError(
                "Operational record attempt/operation/release lineage does not agree"
            )
        for key, value in tuple(data.items()):
            if key.endswith("_at") and value is not None:
                data[key] = utc_text(value)
        if data.get("started_at") and data.get("completed_at"):
            if data["completed_at"] < data["started_at"]:
                raise ControlError("Operational measurement ended before it started")
        if kind in {"benchmark_trial", "benchmark_step", "quarantine_manifest"}:
            actual = {b.dataset_id: b.version for b in self._bindings(tx, op["operation_id"])}
            if data["input_versions"] and data["input_versions"] != actual:
                raise ControlError("Operational record cannot substitute frozen input versions")
            data["input_versions"] = actual
        if kind in {"benchmark_trial", "benchmark_step"}:
            expected = {
                "release_version": op["release_version"],
                "snapshot_hash": op["snapshot_hash"],
                "input_versions": data["input_versions"],
            }
            context = data["snapshot_context"]
            if any(key in context and context[key] != value for key, value in expected.items()):
                raise ControlError("Benchmark frozen snapshot context is mismatched")
            data["snapshot_context"] = {**context, **expected}
            if data["artifact"] and "tables" in data["artifact"].replace("\\", "/").lower().split(
                "/"
            ):
                raise ControlError("Benchmark evidence must not write a production Tables path")
        if kind == "diagnostic_log":
            collection = tx.one(
                f"SELECT operation_id,attempt_id,release_version "
                f"FROM {tx.table('diagnostic_attempt')} WHERE record_id=?",
                (data["collection_id"],),
            )
            if not collection or any(
                collection[k] != data[k] for k in ("operation_id", "attempt_id", "release_version")
            ):
                raise ControlError("Diagnostic log must reference its own collection/attempt")
        if kind == "quarantine_manifest":
            quality = tx.one(
                f"SELECT operation_id,attempt_id,release_version,payload_json "
                f"FROM {tx.table('quality_outcome')} WHERE record_id=?",
                (data["quality_record_id"],),
            )
            if not quality or any(
                quality[k] != data[k] for k in ("operation_id", "attempt_id", "release_version")
            ):
                raise ControlError("Quarantine manifest must reference its own quality outcome")
            if json.loads(quality["payload_json"])["status"] != "FAIL":
                raise ControlError("Quarantine manifests require an actual failed quality check")
        if kind == "benchmark_step":
            task = self._snapshot(tx, op["release_version"]).task(op["task_id"])
            if data["ordinal"] >= len(task.functions):
                raise ControlError("Benchmark ordinal is outside the frozen function array")
            function = task.functions[data["ordinal"]]
            if (
                data["function"] != function.function
                or data["occurrence_id"] not in {None, function.occurrence_id}
                or (
                    data["parameters"] is not None
                    and data["parameters"] != thaw(function.parameters)
                )
            ):
                raise ControlError(
                    "Benchmark function/occurrence/parameters do not match its release"
                )
            data["occurrence_id"] = function.occurrence_id
            data["parameters"] = thaw(function.parameters)
            trial_data = {
                key: data[key]
                for key in (
                    "operation_id",
                    "attempt_id",
                    "release_version",
                    "run_id",
                    "trial",
                    "warmup",
                    "input_versions",
                    "snapshot_context",
                    "compute_context",
                )
            }
            trial_key = self._operational_key("benchmark_trial", trial_data)
            trial = tx.one(
                f"SELECT record_id,payload_json FROM {tx.table('benchmark_trial')} "
                "WHERE natural_key=?",
                (trial_key,),
            )
            if trial is None:
                trial_data.update(status="RUNNING", started_at=data["started_at"])
                trial_id = self._persist_operational(
                    tx, "benchmark_trial", normalize_record("benchmark_trial", trial_data)
                )
            else:
                trial_id = trial["record_id"]
                frozen_trial = json.loads(trial["payload_json"])
                for context_key in ("snapshot_context", "compute_context"):
                    if any(
                        key not in frozen_trial[context_key]
                        or frozen_trial[context_key][key] != value
                        for key, value in data[context_key].items()
                    ):
                        raise ControlError("Benchmark step changed its frozen trial context")
                    data[context_key] = frozen_trial[context_key]
            data["trial_record_id"] = trial_id
        return data

    @staticmethod
    def _operational_key(kind: str, data: Mapping[str, Any]) -> str:
        if kind == "spark_metric":
            return digest_json(
                [
                    kind,
                    *(
                        data[key]
                        for key in (
                            "workspace_id",
                            "livy_id",
                            "application_id",
                            "application_attempt_id",
                        )
                    ),
                ]
            )
        return digest_json(
            [
                kind,
                data["operation_id"],
                data["attempt_id"],
                data["release_version"],
                *(data[key] for key in RECORD_KEYS[kind]),
            ]
        )

    def _persist_operational(self, tx: _Session, kind: str, data: dict[str, Any]) -> str:
        data = self._prepare_operational_record(tx, kind, data)
        physical_metrics = metric_columns(data) if kind == "spark_metric" else {}
        natural_key = self._operational_key(kind, data)
        supplied_revision = data.pop("revision")
        supplied_id = data.pop("record_id")
        previous = tx.one(f"SELECT * FROM {tx.table(kind)} WHERE natural_key=?", (natural_key,))
        if previous and any(
            previous[key] != data[key] for key in ("operation_id", "attempt_id", "release_version")
        ):
            raise ControlError(
                "Application totals cannot be copied/re-attributed to another operation"
            )
        record_id = supplied_id or (previous["record_id"] if previous else natural_key)
        if previous and previous["record_id"] != record_id:
            raise ControlError("Operational natural identity was reused with another record ID")
        collision = tx.one(
            f"SELECT natural_key FROM {tx.table(kind)} WHERE record_id=?", (record_id,)
        )
        if collision and collision["natural_key"] != natural_key:
            raise ControlError("Operational record ID was reused with different immutable identity")
        payload_json = canonical_json(data)
        if len(payload_json.encode()) > 65536:
            raise ControlError("Resolved operational evidence exceeds the 64 KiB record budget")
        payload_hash = digest_json(data)
        if previous:
            if previous["payload_hash"] == payload_hash:
                return record_id
            historical = tx.one(
                f"SELECT revision FROM {tx.table('record_revision')} "
                "WHERE record_type=? AND record_id=? AND payload_hash=?",
                (kind, record_id, payload_hash),
            )
            if historical:
                return record_id
            if supplied_revision is not None and supplied_revision <= previous["revision"]:
                raise ControlError("Stale operational revision cannot overwrite newer evidence")
            terminal = {
                "SUCCEEDED",
                "COMPLETE",
                "FAILED",
                "CANCELED",
                "INTERRUPTED",
                "UNAVAILABLE",
                "SKIPPED",
                "PASS",
                "FAIL",
            }
            old = json.loads(previous["payload_json"])
            if kind in {"benchmark_trial", "benchmark_step"} and any(
                old[key] != data[key] for key in ("snapshot_context", "compute_context")
            ):
                raise ControlError("Benchmark evidence changed its frozen trial context")
            if kind == "spark_metric":
                identity_fields = (
                    "activity_run_id",
                    "workspace_id",
                    "item_id",
                    "item_type",
                    "livy_id",
                    "application_id",
                    "application_attempt_id",
                )
                if any(old[k] != data[k] for k in identity_fields):
                    raise ControlError(
                        "A metric snapshot cannot change its actual application scope"
                    )
                old_available = sum(m["value"] is not None for m in old["metrics"].values())
                new_available = sum(m["value"] is not None for m in data["metrics"].values())
                if supplied_revision is None and not (
                    new_available > old_available
                    and old["status"] in {"PENDING", "RUNNING", "PARTIAL", "UNAVAILABLE"}
                    or old["status"] in {"PENDING", "RUNNING"}
                    and data["status"] not in {"PENDING", "RUNNING"}
                ):
                    raise ControlError("Changed metric evidence requires a newer explicit revision")
            elif previous["status"] in terminal:
                raise ControlError(
                    "Terminal operational evidence is immutable; use a new attempt/key"
                )
            elif previous["status"] not in {"PENDING", "RUNNING", "PARTIAL"}:
                raise ControlError("Illegal operational evidence transition")
            elif data["status"] in {"PENDING", "RUNNING"} and data["status"] != previous["status"]:
                if previous["status"] != "PENDING":
                    raise ControlError("Operational evidence cannot regress to an earlier state")
        revision = supplied_revision or (previous["revision"] + 1 if previous else 1)
        columns = {
            "operation_id": data["operation_id"],
            "attempt_id": data["attempt_id"],
            "release_version": data["release_version"],
            "status": data["status"],
            "revision": revision,
            "payload_json": payload_json,
            "payload_hash": payload_hash,
            "updated_at": tx.now,
        }
        for key, value in data.items():
            if key in columns or key == "metrics":
                continue
            if key in JSON_COLUMNS:
                columns[JSON_COLUMNS[key]] = canonical_json(value)
            else:
                columns[key] = int(value) if isinstance(value, bool) else value
        columns.update(physical_metrics)
        if previous:
            tx.update(kind, "record_id=?", (record_id,), **columns)
        else:
            tx.insert(
                kind, record_id=record_id, natural_key=natural_key, created_at=tx.now, **columns
            )
        tx.insert(
            "record_revision",
            record_type=kind,
            record_id=record_id,
            revision=revision,
            operation_id=data["operation_id"],
            attempt_id=data["attempt_id"],
            release_version=data["release_version"],
            status=data["status"],
            payload_json=payload_json,
            payload_hash=payload_hash,
            created_at=tx.now,
        )
        self._audit(
            tx,
            "operational_record",
            record_id,
            {
                "kind": kind,
                "revision": revision,
                "status": data["status"],
                "payload_hash": payload_hash,
            },
        )
        if kind == "benchmark_step":
            task = self._snapshot(tx, data["release_version"]).task(
                self._operation(tx, data["operation_id"])["task_id"]
            )
            if data["status"] in {"FAILED", "CANCELED", "INTERRUPTED"} or (
                data["status"] == "SUCCEEDED" and data["ordinal"] == len(task.functions) - 1
            ):
                trial = tx.one(
                    f"SELECT payload_json FROM {tx.table('benchmark_trial')} WHERE record_id=?",
                    (data["trial_record_id"],),
                )
                trial_payload = json.loads(trial["payload_json"])
                trial_payload.update(status=data["status"], completed_at=data["completed_at"])
                self._persist_operational(
                    tx, "benchmark_trial", normalize_record("benchmark_trial", trial_payload)
                )
        return record_id

    def _record_operational(
        self,
        kind: str,
        record: OperationalRecord | Mapping[str, Any],
    ) -> str:
        try:
            data = normalize_record(kind, record)
            with self.transaction() as tx:
                return self._persist_operational(tx, kind, data)
        except ValueError as error:
            raise ControlError(str(error)) from error

    def record_diagnostic_attempt(
        self,
        record: DiagnosticAttemptRecord | Mapping[str, Any],
    ) -> str:
        return self._record_operational("diagnostic_attempt", record)

    def record_diagnostic_log(self, record: DiagnosticLogRecord | Mapping[str, Any]) -> str:
        return self._record_operational("diagnostic_log", record)

    def record_spark_metric(self, record: SparkMetricRecord | Mapping[str, Any]) -> str:
        return self._record_operational("spark_metric", record)

    def record_benchmark_trial(self, record: BenchmarkTrialRecord | Mapping[str, Any]) -> str:
        return self._record_operational("benchmark_trial", record)

    def record_benchmark_step(self, record: BenchmarkStepRecord | Mapping[str, Any]) -> str:
        return self._record_operational("benchmark_step", record)

    def record_quality_outcome(self, record: QualityOutcomeRecord | Mapping[str, Any]) -> str:
        return self._record_operational("quality_outcome", record)

    def record_quarantine_manifest(
        self,
        record: QuarantineManifestRecord | Mapping[str, Any],
    ) -> str:
        return self._record_operational("quarantine_manifest", record)

    def record_cleanup_outcome(self, record: CleanupOutcomeRecord | Mapping[str, Any]) -> str:
        return self._record_operational("cleanup_outcome", record)

    @staticmethod
    def _operational_read(row: Mapping[str, Any]) -> Mapping[str, Any]:
        return freeze(
            {
                **json.loads(row["payload_json"]),
                "record_id": row["record_id"],
                "revision": row["revision"],
                "created_at": row["created_at"],
                "updated_at": row.get("updated_at", row["created_at"]),
            }
        )

    def operational_record(self, kind: str, record_id: str) -> Mapping[str, Any]:
        if kind not in RECORD_TYPES:
            raise ControlError("Unknown operational record kind")
        with self.transaction() as tx:
            row = tx.one(f"SELECT * FROM {tx.table(kind)} WHERE record_id=?", (record_id,))
            if not row:
                raise ControlError("Operational record not found")
            return self._operational_read(row)

    def operational_records(
        self,
        kind: str,
        operation_id: str,
        *,
        attempt_id: str | None = None,
        limit: int = 100,
        after_record_id: str | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        if (
            kind not in RECORD_TYPES
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise ControlError("Known record kind and a read budget in [1,1000] are required")
        with self.transaction() as tx:
            predicates, params = ["operation_id=?"], [operation_id]
            if attempt_id is not None:
                predicates.append("attempt_id=?")
                params.append(attempt_id)
            if after_record_id is not None:
                predicates.append("record_id>?")
                params.append(after_record_id)
            prefix = f"TOP ({limit}) " if tx.sqlserver else ""
            suffix = "" if tx.sqlserver else f" LIMIT {limit}"
            rows = tx.all(
                f"SELECT {prefix}* FROM {tx.table(kind)} WHERE "
                + " AND ".join(predicates)
                + " ORDER BY record_id"
                + suffix,
                tuple(params),
            )
            return tuple(self._operational_read(row) for row in rows)

    def operational_record_revisions(
        self,
        kind: str,
        record_id: str,
        *,
        limit: int = 100,
        after_revision: int = 0,
    ) -> tuple[Mapping[str, Any], ...]:
        if (
            kind not in RECORD_TYPES
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise ControlError("Known record kind and a read budget in [1,1000] are required")
        if (
            not isinstance(after_revision, int)
            or isinstance(after_revision, bool)
            or not 0 <= after_revision <= 1_000_000
        ):
            raise ControlError("A bounded nonnegative revision cursor is required")
        with self.transaction() as tx:
            prefix = f"TOP ({limit}) " if tx.sqlserver else ""
            suffix = "" if tx.sqlserver else f" LIMIT {limit}"
            rows = tx.all(
                f"SELECT {prefix}* FROM {tx.table('record_revision')} "
                "WHERE record_type=? AND record_id=? AND revision>? ORDER BY revision" + suffix,
                (kind, record_id, after_revision),
            )
            return tuple(self._operational_read(row) for row in rows)


class SQLiteControlStore(ControlStore):
    """Durable local protocol reference, never the authoritative production metadata backend."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        legacy_same_window_coverage: bool = False,
    ):
        if str(path) == ":memory:":
            raise ValueError("Reference adapter requires a durable database file")
        if not isinstance(legacy_same_window_coverage, bool):
            raise ValueError("Legacy compatibility must be an explicit local-test boolean")
        self.path = str(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.legacy_same_window_coverage = legacy_same_window_coverage
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        # Packaged SQL is located independently of cwd when installed from this repository.
        schema = Path(__file__).resolve().parents[2] / "database" / "metadata" / "reference.sql"
        with contextlib.closing(self._connect()) as connection:
            connection.executescript(schema.read_text(encoding="utf-8"))
            connection.executescript(
                schema.with_name("reference_operations.sql").read_text(encoding="utf-8")
            )
            connection.executescript(
                schema.with_name("reference_waiting.sql").read_text(encoding="utf-8")
            )
            for table in ("ops_DatasetOutput", "ops_OperationInput", "ops_DatasetReadiness"):
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                for name in ("source_coverage_start", "source_coverage_end"):
                    if name not in columns:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} TEXT")
            connection.executescript(
                schema.with_name("reference_coverage.sql").read_text(encoding="utf-8")
            )

    @contextlib.contextmanager
    def transaction(self) -> Iterator[_Session]:
        connection = None
        try:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            tx = _Session(connection.cursor(), False, utc_text(self.clock()))
            yield tx
            connection.commit()
        except (sqlite3.OperationalError, sqlite3.InterfaceError) as error:
            if connection:
                connection.rollback()
            raise MetadataUnavailable("Local reference control database unavailable") from error
        except BaseException:
            if connection:
                connection.rollback()
            raise
        finally:
            if connection:
                connection.close()


class SqlServerControlStore(ControlStore):
    """Actual DB-API SQL Server/Fabric SQL adapter; never connects to analytics endpoints.

    The factory must return a new transactional DB-API connection, using a scoped identity
    and no embedded secrets. Each transition holds a transaction-owned application lock.
    This deliberately serializes short metadata transactions for the initial demo.
    """

    def __init__(self, connection_factory: Callable[[], Any], *, lock_timeout_ms: int = 30000):
        if lock_timeout_ms < 0:
            raise ValueError("Bounded SQL lock timeout required")
        self.connection_factory = connection_factory
        self.lock_timeout_ms = lock_timeout_ms

    @classmethod
    def from_pyodbc(cls, connection_string: str, **connect_kwargs: Any) -> SqlServerControlStore:
        """Lazy optional pyodbc import; credentials should use token/managed identity auth."""
        import pyodbc

        return cls(lambda: pyodbc.connect(connection_string, autocommit=False, **connect_kwargs))

    @contextlib.contextmanager
    def transaction(self) -> Iterator[_Session]:
        connection = None
        try:
            connection = self.connection_factory()
            connection.autocommit = False
            cursor = connection.cursor()
            cursor.execute(
                "SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; "
                "BEGIN TRANSACTION;"
            )
            cursor.execute(
                "DECLARE @result int; EXEC @result=sys.sp_getapplock "
                "@Resource=N'healthcare-ingestion-control',@LockMode=N'Exclusive',"
                "@LockOwner=N'Transaction',@LockTimeout=?; SELECT @result AS lock_result;",
                (self.lock_timeout_ms,),
            )
            while cursor.description is None and cursor.nextset():
                pass
            result = cursor.fetchone()
            if not result or result[0] < 0:
                raise MetadataUnavailable("Fabric SQL control-plane transaction lock unavailable")
            cursor.execute("SELECT SYSUTCDATETIME() AS now_utc")
            now = cursor.fetchone()[0]
            tx = _Session(cursor, True, utc_text(now.replace(tzinfo=UTC)))
            yield tx
            connection.commit()
        except ControlError:
            if connection:
                connection.rollback()
            raise
        except Exception as error:
            if connection:
                connection.rollback()
            if type(error).__module__.split(".")[0] in {"pyodbc", "pymssql"} or isinstance(
                error, (ConnectionError, TimeoutError, OSError)
            ):
                raise MetadataUnavailable("Fabric SQL metadata unavailable; fail closed") from error
            raise
        finally:
            if connection:
                connection.close()
