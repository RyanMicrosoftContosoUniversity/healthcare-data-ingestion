# Operational persistence public contract

Local development implementation only: migration 0004 and its permissions have not been
deployed or verified against live Fabric SQL. The production adapter executes real
transactional DB-API SQL; SQLite is a durable protocol/reference test backend only.
No new backup service, deployment, migration-test database or cloud resource is included.

## Imports and exact signatures

```python
from healthcare_ingestion.control_store import SqlServerControlStore, SQLiteControlStore
from healthcare_ingestion.operational_records import (
    DiagnosticAttemptRecord, DiagnosticLogRecord, SparkMetricRecord,
    BenchmarkTrialRecord, BenchmarkStepRecord, QualityOutcomeRecord,
    QuarantineManifestRecord, CleanupOutcomeRecord, SPARK_METRIC_TYPES, record_schema,
)

SqlServerControlStore(connection_factory, *, lock_timeout_ms=30000)
SqlServerControlStore.from_pyodbc(connection_string, **connect_kwargs)
SQLiteControlStore(path, *, clock=None)

store.source_snapshot_info(snapshot_id: str) -> Mapping[str, Any]
store.record_diagnostic_attempt(record: DiagnosticAttemptRecord | Mapping[str, Any]) -> str
store.record_diagnostic_log(record: DiagnosticLogRecord | Mapping[str, Any]) -> str
store.record_spark_metric(record: SparkMetricRecord | Mapping[str, Any]) -> str
store.record_benchmark_trial(record: BenchmarkTrialRecord | Mapping[str, Any]) -> str
store.record_benchmark_step(record: BenchmarkStepRecord | Mapping[str, Any]) -> str
store.record_quality_outcome(record: QualityOutcomeRecord | Mapping[str, Any]) -> str
store.record_quarantine_manifest(record: QuarantineManifestRecord | Mapping[str, Any]) -> str
store.record_cleanup_outcome(record: CleanupOutcomeRecord | Mapping[str, Any]) -> str

store.operational_record(kind: str, record_id: str) -> Mapping[str, Any]
store.operational_records(
    kind: str, operation_id: str, *, attempt_id: str | None = None,
    limit: int = 100, after_record_id: str | None = None,
) -> tuple[Mapping[str, Any], ...]
store.operational_record_revisions(
    kind: str, record_id: str, *, limit: int = 100, after_revision: int = 0,
) -> tuple[Mapping[str, Any], ...]
record_schema(kind: str) -> Mapping[str, Any]
```

Writers return the stable record ID. Reads return immutable decoded payload mappings plus
`record_id`, `revision`, `created_at`, `updated_at`; step reads also include `trial_record_id`.
Read budgets are integers 1–1000, not booleans. List cursors are exclusive and ordered by
record ID; revision cursors are exclusive, ordered by revision and bounded 0–1,000,000.
These paginated reads are not an immutable multi-call read snapshot.

`record_schema(kind)` exposes exact field types, required flags, JSON-compatible defaults
and, for Spark metrics, all 50 physical column types. Kinds are exactly
`diagnostic_attempt`, `diagnostic_log`, `spark_metric`, `benchmark_trial`, `benchmark_step`,
`quality_outcome`, `quarantine_manifest`, `cleanup_outcome`.

`source_snapshot_info` returns the exact registered `source_snapshot_id`, `dataset_id`,
`environment`, `scope`, `version`, `window_start`, `window_end`, `evidence_digest`,
`artifact_ref`, `created_at`, `retired_at`. Missing registration raises `ControlError`.
It does not assert retained bytes still exist or replace missing history with current
source. The runner verifies the selected protected manifest/content and retirement policy.

## Exact record dictionary

All dataclasses are frozen and **keyword-only**. Their common required fields are
`operation_id: str`, `attempt_id: str`, `release_version: str`, `status: str`; common optional
fields are `record_id: str | None = None`, `revision: int | None = None`.
Lineage must refer to the actual registered operation, SQL attempt and pinned release.
The SQL task `attempt_id` is not the Spark application attempt ID.

`{}` below means an independent dictionary default; optional timestamps/references are
strings or null. Timestamps normalize to UTC with seven fractional digits.

| Record | Additional required fields | Additional fields and defaults |
|---|---|---|
| DiagnosticAttemptRecord | `scope_key: str` | `collection_attempt=0`, `max_attempts=3`, `availability=None`, `reason=None`, `spark={}`, `started_at=None`, `completed_at=None` |
| DiagnosticLogRecord | `collection_id: str`, `kind: str`, `filename: str`, `source_identity: str` | `artifact=None`, `bytes=None`, `sha256=None`, `complete=True`, `availability=None`, `reason=None`, `source_modified_at=None`, `collected_at=None`, `retrieval_context={}` |
| SparkMetricRecord | `activity_run_id: str`, `workspace_id: str`, `item_id: str`, `item_type: str`, `livy_id: str`, `application_id: str`, `application_attempt_id: str` | `metrics={}`, `collected_at=None`, `execution_evidence={}` |
| BenchmarkTrialRecord | `run_id: str`, `trial: int` | `warmup=False`, `input_versions={}`, `snapshot_context={}`, `compute_context={}`, `artifact=None`, `started_at=None`, `completed_at=None` |
| BenchmarkStepRecord | All trial fields plus `ordinal: int`, `function: str` | All trial defaults plus `occurrence_id=None`, `parameters=None`, `attempt_number=1`, `plan_seconds=None`, `materialization_seconds=None`, `reread_seconds=None`, `total_seconds=None`, `rows=None`, `exception_type=None`, `execution_metrics={}`, `collection_status="UNAVAILABLE"` |
| QualityOutcomeRecord | `check: str`, `evidence_digest: str` | `severity="critical"`, `reason=None`, `expected_value=None`, `actual_value=None`, `artifact=None`, `details={}` |
| QuarantineManifestRecord | `quality_record_id: str`, `artifact: str`, `reason_code: str`, `row_count: int`, `schema_digest: str` | `identifiers_manifest_ref=None`, `input_versions={}` |
| CleanupOutcomeRecord | `artifact_id: str` | `artifact=None`, `artifact_kind=None`, `attempt_number=1`, `reason=None`, `proof_digest=None`, `started_at=None`, `completed_at=None` |

Counts/indices are bounded integers; flags are booleans. Durations and quality numeric
values accept numeric values, Decimal or canonical strings and normalize to fixed-scale
decimal strings in JSON. SQL keeps authoritative decimal types; the SQLite reference uses
TEXT for these exact values. Durations are nonnegative and ≤1,800 seconds; quality values
permit signed decimal(38,6). No measurements are fabricated from zero/null defaults.

Records accept only the declared fields, not arbitrary callback dictionaries. A supplied
`framework_version` alias must equal `release_version` and is removed. Metadata is bounded
to 64 KiB per resolved record. String limits match the physical dictionary. Nested JSON
must be metadata-only; secrets/signed URLs, raw bodies and patient identifiers are rejected.
Use restricted artifact/identifier-manifest references, sanitized reason codes and
exception **type**, never raw exception/log/patient bodies. This is defensive validation,
not a substitute for caller redaction and artifact access controls.

## States, identities and ordering

Ordinary records accept `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELED`,
`INTERRUPTED`, `PARTIAL`, `COMPLETE`, `UNAVAILABLE`, `SKIPPED`.
Quality outcomes accept only `PASS`, `FAIL`, `UNAVAILABLE`; Spark metric records accept
`PENDING`, `RUNNING`, `PARTIAL`, `COMPLETE`, `UNAVAILABLE`.
Aliases normalize `COLLECTED`, `RECORDED`, `QUARANTINED` to `SUCCEEDED`, and `AVAILABLE`
to `COMPLETE`. Failed/unavailable quality and unavailable diagnostics require reason codes;
failed cleanup requires a reason. Unavailable diagnostics never become successful evidence.

Natural identities include operation/attempt/release plus:

| Kind | Additional identity |
|---|---|
| diagnostic_attempt | scope_key, collection_attempt |
| diagnostic_log | collection_id, source_identity |
| benchmark_trial | run_id, trial |
| benchmark_step | run_id, trial, ordinal, attempt_number |
| quality_outcome | check |
| quarantine_manifest | quality_record_id, artifact |
| cleanup_outcome | artifact_id, attempt_number |

**Exception:** Spark metric identity is the actual workspace/Livy/application/application
attempt, anchored to one operation/SQL attempt/release. Changed activity/item/operation
anchors are rejected; shared application totals cannot be copied into every task/step.
`application_attempt_id="latest"` is rejected. Put actual Spark identities in the explicit
metric fields and diagnostic `spark`/retrieval context, not the SQL `attempt_id`.

Duplicate callbacks and exact historical replays return the existing ID without erasing
newer evidence. Changed ordinary terminal evidence requires a new attempt/key. Supplied
record IDs cannot be reused for another natural identity. Every persisted revision also
writes immutable `OperationalRecordRevision` and `ControlAudit`.
Metric snapshots can automatically improve missing evidence or use an explicitly higher
`revision`; stale changed revisions are rejected. Exact prior payload acknowledgements
are harmless even when they arrive late.

## Collector, benchmark and quality integration

Diagnostic collection attempt indices are 0 through `max_attempts` inclusive; the latter
is bounded 1–6. A retry uses a new `collection_attempt`. Logs reference their same-context
collection ID. Kinds are `driver`, `rolling_driver`, `executor`, `event`, `livy`, `evidence`.
`source_identity` must distinguish the actual provider file/revision, not only its name.
Collected/partial logs require an artifact reference; SHA-256, when present, must be hex.
`complete=False` changes an otherwise successful log to `PARTIAL`.

Each `metrics` entry has this shape:

```python
{
    "CPUTime": {
        "value": "1.123456",
        "availability": "AVAILABLE",
        "source": "verified:provider-field",
        "unit": "seconds",
    },
    "ReadRows": {"value": None, "availability": "UNAVAILABLE", "reason": "NOT_EXPOSED"},
}
```

All 50 baseline names/types are preserved as nullable physical fields and listed in
`SPARK_METRIC_TYPES`/`COLUMN_DICTIONARY.md`. A nonnull value requires AVAILABLE/source.
A null value requires UNAVAILABLE/NOT_APPLICABLE/DELAYED plus a reason; omitted fields
become null with UNAVAILABLE/NOT_COLLECTED. Attribution descriptors are bounded strings.
Available zeros are valid measured zeros. Executor min≤max and percentages≤100 are checked.
PotentialCausesJson is an array, not a stringified or raw log body.

Benchmark trial 0 is warmup (`warmup=True`); measured trials 1–3 use `warmup=False`.
Step ordinals are zero-based and must match the frozen registered function array.
Occurrences/parameters derive from that release when omitted; supplied values must match.
Trial/step/quarantine input versions derive from operation bindings; replacements fail.
Snapshot context adds the pinned release/hash/inputs. Trial compute/snapshot context
freezes on creation; subsequent step omissions inherit it and conflicting context fails.
Record the actual compute context on trial creation or its first auto-creating step.
Step retries use a new `attempt_number` (1–6). A step auto-creates its parent trial;
the final successful step or a failed/canceled/interrupted step finishes that trial.
The executor remains responsible for correct function execution order/completion proof.
Empty execution metrics explicitly mean UNAVAILABLE/NOT_ATTRIBUTABLE, not copied app totals.
Benchmark artifacts cannot target a production `Tables` path.

Quarantine manifests require an existing same-context FAIL quality record. They store
only protected manifest references, row count, schema/cause and pinned input versions.
Current-attempt critical FAIL/UNAVAILABLE quality evidence blocks publication;
warning outcomes do not. Corrected quality evidence belongs to a new execution attempt,
not a rewritten failed terminal record. Corruption approval/descendant blocks remain
the existing separate operator protocol.

Diagnostic, benchmark and cleanup status writes **never mutate operation/readiness state**.
Cleanup retries use a new `attempt_number` (1–6); eligibility/reference hold decisions are
separate existing APIs. Callers isolate these observational failures from ingestion and
preserve post-commit evidence for reconciliation if metadata becomes unavailable.

## Physical tables and acceptance boundary

Migration 0004 adds `ops.TaskDiagnosticAttempt`, `TaskDiagnosticLog`, `TaskSparkMetric`,
`TransformationBenchmarkTrial`, `TransformationBenchmarkStep`, `TaskQualityOutcome`,
`TaskQuarantineManifest`, `ArtifactCleanupOutcome`, `OperationalRecordRevision`, plus
operation/release composite uniqueness and audited parent/lineage FKs. Baseline tables
and historical TransformationStep attribution are not modified.

SQLite uses matching `reference_operations.sql` columns/relations. Operational revisions
and audit records retain the existing seven-year execution-audit target and active/reference
holds; these APIs implement no age-based deletion or custom backup.

New runtime operational write grants in `permissions.sql` are an unexecuted reviewed-role
starting point, not an arbitrary-direct-SQL security boundary. Live Fabric SQL migration,
transaction/constraint behavior, scoped identity/negative permissions, native backup/restore
and actual collection/benchmarking still require reviewed live acceptance checks.
