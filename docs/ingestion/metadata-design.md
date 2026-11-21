# Metadata-Driven Framework: Control-Table Design

**Status: proposed, awaiting user review.** This document specifies tables; it does not
deploy them. No source configuration records, control-store migrations, or Bronze
pipelines should be implemented until this design is approved.

**Discussion reconciliation:** `discussions\discussion-02.md` consolidates and extends
`discussions\discussed-changes.md`. The approved logical revision is specified in
`docs\ingestion\task-dataset-design.md`; lifecycle behavior is in
`docs\architecture\orchestration-design.md`. The 17 dictionaries below remain the
**original baseline**, not a current finalized target schema. Do not implement them
unchanged: revise task/dataset/input/function-array and operational/release roles,
then review exact physical definitions. Remaining user decisions are consolidated in
`docs\architecture\build-decisions.md`.

## Accepted Decision: Dedicated Fabric Metadata Workspace

**Latest approval: `discussions\discussed-changes-03.md`.** Remaining recommended
architectural directions are approved for development; concrete revised SQL,
migrations/interfaces and tests are engineering deliverables, not another approval
loop. Original dictionaries below remain baseline, not the revised deployed schema.
Use output history separate from readiness/attempts, window-aware fenced progress,
five-minute reconciliation/outbox, compatible pre-activation migrations and pinned
release resources. Audit target is seven years with active/reference holds;
temporary artifacts retain their distinct policies. Native Fabric SQL backup/restore
only; no custom backup system or isolated migration-test database. Terraform apply
and code-review-governed publication remain separate.

The control store will be a **Fabric SQL Database in a dedicated metadata workspace**,
separate from the data/ingestion workspace containing the pipelines, notebooks, and
Bronze/Silver lakehouses. This supersedes the earlier Azure SQL control-database proposal.
The Clarity and Caboodle simulation databases remain in Azure SQL.

- Store all authoritative `cfg` and `ops` tables here: configuration, state/watermarks,
  run history, reconciliation, schema changes, benchmark results, Spark metrics, and
  diagnostic/alert metadata. Large raw evidence remains in protected artifact storage;
  its manifests and references remain in the control database.
- Use the transactional database connection for authoritative configuration/state reads,
  writes, leases, and transition routines, not the read-only SQL analytics endpoint.
- Supply the control-store workspace/database identities, database connection details,
  and authentication reference through deployment settings so the framework can connect
  before reading its own configuration. Do not derive connection endpoints from names.
- Validate the data workspace's pipeline/notebook and diagnostic-worker identities
  against the metadata workspace/database permissions. Workspace separation must not
  depend on implicit same-workspace access.
- Confirm the workspace name, SQL database item name, existing capacity assignment,
  region, and deployment/runtime permissions before creation. Names are **not assigned**;
  the user can provide the metadata workspace name when creation is prepared.
- Reuse approved existing capacity; this decision does not authorize a new capacity.

The backend and workspace-separation decisions are accepted. The 17 table definitions,
processing semantics, runtime integration, and deployment targets remain subject to
their existing review gates; this is not blanket framework/deployment approval.

**Connection references:** `https://learn.microsoft.com/en-us/fabric/database/sql/connect`
and `https://learn.microsoft.com/en-us/fabric/database/sql/sql-analytics-endpoint`.

## Review Decisions

| Decision | Accepted Direction / Remaining Proposal |
| --- | --- |
| Control store | Accepted: Fabric SQL Database in a dedicated metadata workspace; no additional Azure SQL control database. |
| Workspace separation | Accepted: metadata workspace is separate from the data/ingestion workspace. Workspace/database names, existing capacity assignment, and cross-workspace permissions must be confirmed before creation. |
| Bronze | Accepted: append-only raw Delta observations, retaining source fields, `IsDeleted`, and source audits. Publish each captured batch once; preserve repeated keys/observations across distinct batches. Silver owns latest-state deduplication/merges. The eight technical row columns below are accepted, with a readable source name instead of a source-object ID. November 20 retention approval: retain ingested Fabric data indefinitely, with no automatic age-based purge. This does not imply indefinite temporary staging or Delta historical versions. Publication/recovery details and staging cleanup remain under review. |
| Schema discovery | Required before eligible fresh extraction. **Strict approved:** all ingestion-relevant contract differences, including nullable additions/widening, block only the affected table pending review/approved revision; no allowlist or auto-evolution. One source pass and staged validation remain; unavailable-evidence/scheduling/concurrency policy and optional lightweight recheck remain open. |
| Layer dependencies | Approved behavior: independent Bronze and Silver 1; Silver 2 waits for explicit committed, sufficiently fresh upstream datasets. `BLOCKED_BY_DEPENDENCY` is waiting, not a failed transformation. Persistence schemas remain unapproved. |
| Freshness and SLA | Approved defaults: committed source-coverage age at most 24 elapsed hours, daily start 10:00 AM Eastern local time, required Bronze and initial Patient Silver available by 11:00 AM Eastern local time. Both clock times observe daylight saving; freshness remains elapsed time, not a local calendar day. One-hour feasibility is not yet demonstrated. Per-input overrides remain supported; latest expected failure still blocks despite recent older success. Calendar exceptions, override values and window rules remain open. Deadline breach alerts but does not stop useful late recovery. |
| Zero-change runs | Successful incremental runs with zero changed records count as successful with verified source-window coverage and normal validation/readiness checks; preserve existing data. Zero rows alone do not prove coverage or justify advancing state. Empty initial/full-load acceptance and exact state protocol remain under review. |
| Tasks and inputs | Approved logical `ProcessingTask`, `Dataset`, normalized `TaskInput`, and exceptional-only explicit ordering. Retain `PipelineObject` mapping; task mapping FK optional but lineage/output identification mandatory. Physical keys/types still need review. |
| Function storage | Approved: one ordered JSON function array/configuration column per task, with validated parameters. Reconcile auxiliary inputs, step identity/profiling/history and baseline `TransformationStep` references before retiring it. |
| Execution settings | Framework/stage defaults and task overrides, generic stage notebooks with justified exceptions, logical notebook/environment/compute refs, separate scheduler/runtime policy and environment/compute sizing. Exact field precedence/resources remain open. |
| Recovery | Approved: primary readiness events and periodic reconciliation fallback; recheck all dependencies before dispatch. Stable logical operation IDs, distinct attempts, claims and idempotent writes; preserve SLA/recovery evidence. Transport/physical queue/claim protocol remains open. |
| Orchestration and releases | Fabric SQL is authoritative; generate Airflow DAG artifacts after approved configuration publication, with the same framework/DAG semver and sequential release processing. Preserve last-good active deployment on failure and permit newer queued releases. Manifest/queue/active-pointer schemas are not approved. |
| DAG shape and access | Smaller workflow/domain DAGs; metadata evaluates readiness and initiates eligible runs. Airflow reads immutable snapshots; scoped Spark/framework interfaces write ops state, not unrestricted published configuration. |
| Activation and rollback | Candidate semver before CI; activate only after required tests/deployment/Airflow recognition. New runs use active version; in-flight runs stay pinned. Defined technical failures allow automatic known-good reactivation; data-quality/clinical concerns need operator approval. Rollback does not undo Delta data. |
| Incremental consistency | Synthea plus mapping configuration is selected for source population through independent SQL loaders. Generation runs well before Fabric ingestion, targeting completion before the 10:00 AM Eastern local time start; do not assume a continuously running generator requiring a pause. Hosting, mapping coverage and population continuity remain under review. Completion/committed-checkpoint evidence must cover SQL loading, not just Synthea exports; unintended-overlap protection and late/failed generation handling need review. Earlier scheduling alone does not establish a safe extraction boundary; watermarks alone do not guarantee capture of arbitrary late commits. |
| Silver | One row per Clarity `PatientID`; normalize approved text fields, deduplicate deterministically, preserve deletion status, and merge idempotently. Do not collapse Caboodle Type 2 versions into this table. |
| Benchmarking | Separate, explicitly enabled benchmark invocations using frozen Delta inputs and full-column materialization between functions. No production publishing or watermark advancement. |
| Deployment | Terraform where supported; documented supported API automation otherwise. No new Fabric capacity. |

Review the table model, runtime access, Bronze/incremental semantics, and Silver
contract before approving the remaining framework design. The 28 source-table configuration records come **after**
this review; only structural examples appear here.

## Baseline Table Inventory and Approved Revision

The approved logical revision retains shared `PipelineDefinition` configuration and
`PipelineObject` mappings, adds task/dataset/input roles, and replaces normalized
function-step storage with the ordered task JSON array. Remove `InputLayer`/`OutputLayer`
from `PipelineDefinition` in that revision, inferring movement through datasets.
Normalize many-to-many input/dependency edges, derive graph edges from producers when
unambiguous, and validate cycles, missing inputs, and ambiguous producers.

Keep task-attempt history separate from current readiness. Reuse existing ops tables
where grain fits; do not assume an ingestion table attempt represents every join or
general task. Exact revised table count, SQL types/keys, step/history migration,
release/snapshot relationships and reliable event/state routines are not finalized.
See `docs\ingestion\task-dataset-design.md` and the separate
`data-models\framework\09-task-dataset-logical.mmd` / `.svg`.

| Schema | Tables | Responsibility |
| --- | --- | --- |
| `cfg` | `ProcessingDomain`, `SourceSystem`, `SourceObject`, `PipelineDefinition`, `PipelineObject`, `TransformationStep` | Validated reusable configuration |
| `ops` | `IngestionRun`, `IngestionTableRun`, `IngestionWatermark`, `IngestionError`, `SchemaChangeLog`, `ReconciliationResult`, `IngestionTransformationRun` | Run history, concurrency, progress, and benchmarks |
| `ops` | `SparkApplicationRunMetric`, `DiagnosticCollection`, `DiagnosticArtifact`, `AlertEvent` | Spark telemetry, diagnostic evidence, and notifications |

There are 17 proposed tables. Focused native Mermaid sources and SVG previews are in
`data-models\framework`. Simple bidirectional relationship lists are in
`data-models\framework\relationships.md`.

The complete relationship overview is `data-models\framework\00-overview.mmd`, with
a zoomable preview at `data-models\framework\00-overview.svg`. It shows all 17 tables,
their PK/FK columns, and all 30 distinct FKs, including cross-area relationships.
The four focused diagrams remain available for less crowded review. Entity names are
unqualified in the diagrams: the six configuration entities use `cfg`; the other
eleven use `ops`, as listed above. These are control tables, not Bronze row columns.

For complete column-level review, use `data-models\framework\05-full-schema.mmd`
or its zoomable `05-full-schema.svg` preview. This separate diagram includes all
261 columns across the 17 tables, including the four shared columns on every `cfg`
table and all 50 Spark metric extension fields. It preserves all 30 FK relationships,
marks nullability, and displays SQL decimal precision/scale in column comments.
The keys-only overview and table definitions are unchanged.

These ERDs describe the original baseline only, including superseded layer/step
proposals. The task/dataset roles and array choice are now approved logically, but
exact physical tables/columns remain under review. Updated behavior diagrams
`06-orchestration`, `07-release-lifecycle`, `08-transformation-order`, and the separate
`09-task-dataset-logical` revision must not be mistaken for migrated physical schemas.

## Conventions and Invariants

- Control-table dictionary types describe Fabric SQL Database; the explicitly labeled
  Bronze row contract uses Spark/Delta types.
  Validate the DDL, constraints, and concurrency primitives against Fabric SQL Database
  before implementing migrations.
- `No` means `NOT NULL`; a nullable FK represents a genuinely optional attribution.
- Configuration IDs are stable; runtime IDs are generated once per logical execution.
- Control-store timestamps are UTC `datetime2(7)`. Durations are decimal seconds measured with a
  monotonic clock. `rowversion` is an optimistic concurrency token, not a date.
- JSON columns must pass `ISJSON` plus application/schema validation. JSON references
  and column-name arrays are not physical FKs.
- Each `cfg` table additionally contains the common columns below. Configuration edits
  are validated, and each run stores an immutable resolved configuration snapshot/hash.
- Never store secrets, bearer tokens, connection strings containing credentials, patient
  records, raw exception payloads, or signed download URLs in configuration/logging.
- FKs do not cascade-delete execution history. Disable configuration instead of deleting
  referenced objects; retention cleanup operates on explicitly selected run-owned records.
- Correlated IDs must agree, not merely exist: use composite parent keys/FKs where
  possible and restrict writes to validating state-transition routines. A step-linked
  error must also identify its table/run; table/application-linked alerts must identify
  their run. Reject cross-run or cross-mapping associations.

### Common Columns on Every `cfg` Table

| Column | Type | Null | Purpose |
| --- | --- | --- | --- |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation time |
| `ModifiedAtUtc` | `datetime2(7)` | No | Last accepted configuration edit |
| `ConfigRevision` | `bigint` | No | Monotonically increasing revision for this record |
| `RowVersion` | `rowversion` | No | Compare-and-swap protection against conflicting edits |

## Accepted Bronze Row Metadata

The user accepts the seven standard columns plus the optional hash below.
Use `_ingest_source_name` as a readable string instead of a per-row numeric
source-object ID. This is a Bronze-column decision only: preserve the internal
`cfg.SourceObject.SourceObjectID` key and its control-table relationships unchanged.

**Types in this table are Spark/Delta types, not Fabric SQL Database types.**

| Column | Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `_ingest_batch_id` | `STRING` | No | Stable UUID for one captured extraction batch; reuse when replaying that same saved batch. |
| `_ingest_run_id` | `STRING` | No | UUID of the ingestion run that successfully appended the observation. |
| `_ingest_table_run_id` | `STRING` | No | UUID of the table execution attempt that successfully appended the observation. |
| `_ingest_source_name` | `STRING` | No | Human-readable source identity, such as `Clarity.dbo.Patient` or `Caboodle.dbo.DimPatient`. |
| `_ingest_extracted_at_utc` | `TIMESTAMP` | No | Batch extraction timestamp, captured once and retained during replay. |
| `_ingest_landed_at_utc` | `TIMESTAMP` | No | Timestamp assigned to the successful Bronze write attempt; exact Delta commit time/version is separate control evidence. |
| `_ingest_capture_mode` | `STRING` | No | `FULL` or `WATERMARK` for this release; not an inferred source INSERT/UPDATE operation. |
| `_ingest_row_hash` | `STRING` | Yes | Optional SHA-256 fingerprint of canonical source values only, excluding ingestion metadata, for downstream comparison; null when not calculated. |

Build the readable source name from the approved source-system name, source schema,
and source table. Freeze it with the captured batch and preserve it on replay; do not
relabel historical observations after configuration/source-name changes. Internal
source IDs remain available through table-attempt/mapping lineage when needed.

Preserve original source columns unchanged. Reserve the `_ingest_` namespace and
reject source-column collisions rather than silently overwrite or rename source data.
Use UTC for both technical timestamps. All rows in one batch share its capture metadata;
record-level source modification timestamps remain separate.

The run/table-run IDs identify the writer, while batch identity and the extraction
timestamp identify the captured data. Earlier extraction/failed-attempt history stays
in the control store. An already published batch must not be appended or rewritten just
to assign a retry's IDs; the framework must enforce publication idempotency.

Keep repeated business keys and identical payloads from distinct batches in raw Bronze.
Neither a source key nor `_ingest_row_hash` suppresses those observations. Keep exact
extraction bounds, schema/hash-algorithm revisions, file references, commit evidence,
and compute/logging details in the control records rather than repeating them per row.
The hash's canonicalization and publication implementation remain framework review work;
approval of this column set does not approve the remaining framework or deployment.

## Configuration Tables

### cfg.ProcessingDomain

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `DomainID` | `bigint` | No | PK |
| `DomainName` | `nvarchar(64)` | No | Unique domain, for example `patient` |
| `DefaultLoggingLevel` | `varchar(8)` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `DefaultProfileTransformations` | `bit` | No | Explicit benchmark default; initially false |
| `IsActive` | `bit` | No | Enable domain scheduling |

### cfg.SourceSystem

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `SourceSystemID` | `smallint` | No | PK |
| `SourceSystemName` | `varchar(30)` | No | Unique source name |
| `ConnectionRef` | `nvarchar(256)` | No | Approved connection/identity reference, not credentials |
| `IsActive` | `bit` | No | Enable source selection |

### cfg.SourceObject

One record identifies a physical source table and its source-column contract. It does
not describe a particular target or duplicate source metadata for each downstream flow.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `SourceObjectID` | `bigint` | No | PK |
| `SourceSystemID` | `smallint` | No | FK to `SourceSystem` |
| `SourceSchema` | `nvarchar(128)` | No | Validated source schema |
| `SourceTable` | `nvarchar(128)` | No | Validated table identifier |
| `PrimaryKeyColumnsJson` | `nvarchar(max)` | No | Ordered, validated non-null key-column names |
| `WatermarkColumn` | `nvarchar(128)` | Yes | Approved modification column; required for watermark strategy |
| `WatermarkSqlType` | `varchar(40)` | Yes | Exact type; initial contract is `datetime2(7)` |
| `SchemaContractJson` | `nvarchar(max)` | No | Approved source names, SQL types/lengths/precision/scale, nullability, and contract revision; compare with ordered PK/watermark configuration during discovery |
| `IsActive` | `bit` | No | Enable object selection |

Unique `(SourceSystemID, SourceSchema, SourceTable)`. Validate identifiers against the
registered schema and quote them; SQL values remain parameters, not string interpolation.

### cfg.PipelineDefinition

**Baseline only:** remove `InputLayer`/`OutputLayer` in the revision. Keep shared
pipeline/stage settings/default execution policy with optional task overrides.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `PipelineID` | `uniqueidentifier` | No | PK |
| `DomainID` | `bigint` | No | FK to `ProcessingDomain` |
| `PipelineName` | `nvarchar(128)` | No | Unique logical flow name |
| `InputLayer` | `varchar(16)` | No | `SOURCE` or `BRONZE` for this release |
| `OutputLayer` | `varchar(16)` | No | `BRONZE` or `SILVER` |
| `LoggingLevel` | `varchar(8)` | Yes | Override domain logging level |
| `ProfileTransformations` | `bit` | Yes | Override domain benchmark setting |
| `ProfilingOptionsJson` | `nvarchar(max)` | Yes | Validated trial/scale/materialization/retention limits |
| `ExecutionPolicyJson` | `nvarchar(max)` | No | Validated retry, concurrency, schema-validation, reconciliation, and freshness policies |
| `IsActive` | `bit` | No | Enable scheduling |

### cfg.PipelineObject

Map one registered source object to one pipeline's target. Retain this mapping role;
it is not the revised unit of arbitrary executable work. A `ProcessingTask` may omit
its mapping FK but cannot omit lineage and input/output identification. The baseline
Silver mapping below is not a requirement to invent a source mapping for every join.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `PipelineObjectID` | `bigint` | No | PK |
| `PipelineID` | `uniqueidentifier` | No | FK to `PipelineDefinition` |
| `SourceObjectID` | `bigint` | No | FK to `SourceObject` |
| `InputLocationRef` | `nvarchar(256)` | No | Approved source/bronze location reference |
| `TargetLakehouseRef` | `nvarchar(256)` | No | Resolved target identity without credentials |
| `TargetSchema` | `nvarchar(128)` | No | Validated target schema |
| `TargetTable` | `nvarchar(128)` | No | Validated target table |
| `LoadStrategy` | `varchar(24)` | No | `FULL`, `WATERMARK`, or `BRONZE_MERGE`; reject unimplemented strategies |
| `WatermarkOverlapSeconds` | `int` | No | Nonnegative replay overlap; does not replace commit-consistency protocol |
| `DeletePolicy` | `varchar(24)` | No | Initially preserve soft-delete indicator; no inferred physical deletes |
| `ColumnMappingJson` | `nvarchar(max)` | Yes | Explicit approved type/name mappings |
| `PolicyOverridesJson` | `nvarchar(max)` | Yes | Validated object-specific policy overrides |
| `IsActive` | `bit` | No | Enable this mapping |

Unique `(PipelineID, SourceObjectID)` and unique target identity across mappings in this
release. Do not allow two active mapping owners to write the same target under separate locks.

### cfg.TransformationStep

**Superseded storage proposal, retained for baseline comparison:** the approved target
is one ordered JSON function array per processing task. Reconcile parameter/auxiliary
input validation, repeated-step identity, and profiling/history FKs before removing
this definition; do not implement new normalized step rows as the target model.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `TransformationStepID` | `bigint` | No | PK |
| `PipelineObjectID` | `bigint` | No | FK to `PipelineObject` |
| `StepOrdinal` | `int` | No | Positive execution order; unique within mapping |
| `RegistryFunctionName` | `nvarchar(128)` | No | Approved package registry key; never executable code/import paths |
| `ParametersJson` | `nvarchar(max)` | No | Validated JSON arguments |
| `ReferenceInputsJson` | `nvarchar(max)` | Yes | Approved auxiliary input references and snapshot rules |
| `IsActive` | `bit` | No | Enable step without deleting its identity |

The same function may appear at several ordinals. Resolve actual callables in the
notebook; an empty step sequence is pass-through. Validate the entire sequence before
writes, then validate each evolving DataFrame schema as the plan is composed.

## Execution and State Tables

### ops.IngestionRun

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `RunID` | `uniqueidentifier` | No | PK |
| `PipelineID` | `uniqueidentifier` | No | FK to `PipelineDefinition` |
| `RunType` | `varchar(16)` | No | `INGESTION` or `BENCHMARK` |
| `Status` | `varchar(24)` | No | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, or `INTERRUPTED` |
| `StartedAtUtc` | `datetime2(7)` | Yes | Actual start |
| `EndedAtUtc` | `datetime2(7)` | Yes | Terminal transition |
| `ConfigurationSnapshotJson` | `nvarchar(max)` | No | Immutable resolved configuration, revisions, and sanitized run overrides |
| `ConfigurationHash` | `binary(32)` | No | SHA-256 of canonical configuration snapshot |
| `CodeRevision` | `nvarchar(128)` | No | Deployed package/source revision |
| `ExecutionContextJson` | `nvarchar(max)` | No | Available Fabric run/item/workspace identifiers and effective environment/compute |
| `LastHeartbeatAtUtc` | `datetime2(7)` | Yes | Recovery evidence, not proof Spark is terminated |
| `RowVersion` | `rowversion` | No | Concurrency protection |

Baseline run settings resolve framework defaults -> domain -> pipeline -> explicit run
override. The revision must incorporate approved stage defaults and task overrides and
finalize field-level precedence/null semantics; the baseline chain is not complete.
Changing the log level does not suppress required result records.
Require explicit benchmark invocation for profiling. Reject incompatible
`RunType`/profiling settings instead of silently turning a scheduled ingestion run
into a benchmark or introducing materialization into normal processing.

### ops.IngestionTableRun

Grain: one run, configured mapping, and actual execution attempt. Unique
`(RunID, PipelineObjectID, AttemptNumber)`; retrying persistence is not a new execution attempt.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `TableRunID` | `uniqueidentifier` | No | PK |
| `RunID` | `uniqueidentifier` | No | FK to `IngestionRun` |
| `PipelineObjectID` | `bigint` | No | FK to `PipelineObject` |
| `AttemptNumber` | `int` | No | Positive execution attempt |
| `Status` | `varchar(24)` | No | Execution state with validated transitions |
| `StartedAtUtc` | `datetime2(7)` | Yes | Start |
| `EndedAtUtc` | `datetime2(7)` | Yes | End |
| `WindowStartUtc` | `datetime2(7)` | Yes | Exact SQL-precision lower extraction bound |
| `WindowEndUtc` | `datetime2(7)` | Yes | Fixed, exclusive upper extraction bound |
| `SourceCheckpointRef` | `nvarchar(256)` | Yes | Committed generator epoch/snapshot evidence |
| `StagingRef` | `nvarchar(2048)` | Yes | Run-owned extraction location |
| `TargetVersion` | `bigint` | Yes | Committed target Delta version when known |
| `LastCompletedPhase` | `varchar(32)` | Yes | `SCHEMA_DISCOVERY`, `SCHEMA_RECHECK`, `EXTRACT`, `VALIDATE`, `APPLY`, or `COMMIT_STATE` |
| `RowCountsJson` | `nvarchar(max)` | Yes | Named source/extracted/loaded/rejected/duplicate counts and their scope |
| `RowVersion` | `rowversion` | No | Concurrency protection |

### ops.IngestionWatermark

One state/lease row per mapping. Initialize a row before scheduling that mapping.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `PipelineObjectID` | `bigint` | No | PK and FK to `PipelineObject` |
| `CommittedWatermarkUtc` | `datetime2(7)` | Yes | Last successfully committed source boundary |
| `LastSuccessfulTableRunID` | `uniqueidentifier` | Yes | FK to `IngestionTableRun`; must match this mapping |
| `LeaseOwnerRunID` | `uniqueidentifier` | Yes | FK to `IngestionRun`; current write owner |
| `LeaseExpiresAtUtc` | `datetime2(7)` | Yes | Detect suspect owners, not automatic takeover authorization |
| `FencingToken` | `bigint` | No | Monotonically increasing lease generation |
| `ModifiedAtUtc` | `datetime2(7)` | No | Last accepted state change |
| `RowVersion` | `rowversion` | No | Conditional state updates |

Only the current owner/token may commit state. An expired heartbeat/lease does not
prove an old Spark writer stopped: confirm cancellation/terminal execution before
reassigning write ownership. Never use a SQL lease to claim atomicity with Delta.

### ops.IngestionError

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `ErrorID` | `uniqueidentifier` | No | PK |
| `RunID` | `uniqueidentifier` | No | FK to `IngestionRun` |
| `TableRunID` | `uniqueidentifier` | Yes | FK to `IngestionTableRun` |
| `StepExecutionID` | `uniqueidentifier` | Yes | FK to `IngestionTransformationRun` |
| `OccurredAtUtc` | `datetime2(7)` | No | Error time |
| `FailurePhase` | `varchar(32)` | No | Where execution failed |
| `ErrorCode` | `nvarchar(128)` | No | Stable sanitized classification |
| `Message` | `nvarchar(2048)` | No | Controlled diagnostic message |
| `IsRetryable` | `bit` | No | Policy classification |
| `EvidenceRef` | `nvarchar(2048)` | Yes | Restricted sanitized stack-trace/evidence location |

### ops.SchemaChangeLog

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `SchemaChangeID` | `uniqueidentifier` | No | PK |
| `RunID` | `uniqueidentifier` | No | FK to `IngestionRun` |
| `TableRunID` | `uniqueidentifier` | No | FK to `IngestionTableRun` |
| `DetectedAtUtc` | `datetime2(7)` | No | Detection time |
| `ExpectedSchemaJson` | `nvarchar(max)` | No | Approved contract |
| `ObservedSchemaJson` | `nvarchar(max)` | No | Observed names/types/nullability; no row values |
| `ChangeSummaryJson` | `nvarchar(max)` | No | Add/drop/rename/type differences |
| `Disposition` | `varchar(24)` | No | `BLOCKED` or explicitly `ALLOWED_BY_POLICY`; never implicit contract/DDL approval |

Schema drift records reference the pre-created table attempt even when no extraction
has started. Successful discovery checks also require durable evidence; they are not
represented by the absence of a `SchemaChangeLog` entry.

### ops.ReconciliationResult

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `ReconciliationID` | `uniqueidentifier` | No | PK |
| `RunID` | `uniqueidentifier` | No | FK to `IngestionRun` |
| `TableRunID` | `uniqueidentifier` | No | FK to `IngestionTableRun` |
| `CheckName` | `nvarchar(128)` | No | Registered check identifier |
| `ScopeJson` | `nvarchar(max)` | No | Fixed window, filters, and source/target versions |
| `ExpectedValue` | `decimal(38,6)` | Yes | Numeric expectation when applicable |
| `ActualValue` | `decimal(38,6)` | Yes | Observed value |
| `Status` | `varchar(16)` | No | `PASS`, `FAIL`, or `UNAVAILABLE` |
| `DetailsJson` | `nvarchar(max)` | Yes | Reason/aggregate evidence, never rejected record bodies |
| `CheckedAtUtc` | `datetime2(7)` | No | Check time |

Unique `(TableRunID, CheckName)` for this release; updates are idempotent.

For schema checks, numeric values may remain null. `ScopeJson` identifies the source,
frozen contract/configuration revisions and canonical expected/observed schema hashes;
`DetailsJson` retains metadata-only schema snapshots and comparison details.
Use separate check names `SOURCE_SCHEMA_PREFLIGHT`, `SOURCE_SCHEMA_BEFORE_EXTRACT`,
and `EXTRACTED_SCHEMA_CONTRACT` so separate phases do not overwrite each other's
evidence. On immutable-batch replay, use `REPLAY_SCHEMA_CONTRACT` for the saved input
and approved target mapping rather than inventing a new live-source check.

### ops.IngestionTransformationRun

Grain: benchmark run, table-run, trial, ordered step, and step attempt. This table is
for explicitly enabled benchmark records, not fabricated production per-function CPU timings.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `StepExecutionID` | `uniqueidentifier` | No | PK; stable across result persistence retries |
| `RunID` | `uniqueidentifier` | No | FK to `IngestionRun`; must be `BENCHMARK` |
| `TableRunID` | `uniqueidentifier` | No | FK to `IngestionTableRun` |
| `TransformationStepID` | `bigint` | No | FK to `TransformationStep` |
| `TrialNumber` | `int` | No | Positive trial |
| `StepOrdinal` | `int` | No | Snapshotted execution order |
| `AttemptNumber` | `int` | No | Actual execution retry |
| `IsWarmup` | `bit` | No | Exclude from measured aggregates |
| `FunctionName` | `nvarchar(128)` | No | Resolved registry name snapshot |
| `ParametersJson` | `nvarchar(max)` | No | Sanitized resolved arguments |
| `Status` | `varchar(24)` | No | Started/succeeded/failed/cancelled/interrupted |
| `StartedAtUtc` | `datetime2(7)` | Yes | Measured interval start |
| `EndedAtUtc` | `datetime2(7)` | Yes | Measured interval end |
| `PlanBuildDurationSeconds` | `decimal(20,6)` | Yes | Python plan construction |
| `MaterializeDurationSeconds` | `decimal(20,6)` | Yes | Completed output action, including I/O/commit |
| `StepElapsedSeconds` | `decimal(20,6)` | Yes | Full measured interval, not result-store overhead |
| `SnapshotContextJson` | `nvarchar(max)` | No | Frozen input/reference versions and output snapshot |
| `ComputeContextJson` | `nvarchar(max)` | No | Runtime, code revision, compute/cache/layout and profiling protocol |
| `ExecutionMetricsJson` | `nvarchar(max)` | Yes | Attributable counts/bytes, job/stage references, CPU/shuffle/spill/GC/skew and availability |
| `CollectionStatus` | `varchar(16)` | No | `PENDING`, `COMPLETE`, `PARTIAL`, or `UNAVAILABLE` |
| `RowVersion` | `rowversion` | No | Idempotent finalization |

Unique `(TableRunID, TrialNumber, StepOrdinal, AttemptNumber)`. Validate that configured
step, table mapping, run, and frozen snapshots agree; FK existence alone is insufficient.

## Telemetry and Notification Tables

### ops.SparkApplicationRunMetric

Grain: run, pipeline activity, Spark application, and actual application attempt.
Never copy one application's totals into every table/step it touched.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `SparkMetricID` | `uniqueidentifier` | No | PK |
| `RunID` | `uniqueidentifier` | No | FK to `IngestionRun` |
| `TableRunID` | `uniqueidentifier` | Yes | FK to `IngestionTableRun` only when attributable |
| `ActivityRunID` | `nvarchar(128)` | No | Actual activity identity; distinguish invocation/retry |
| `WorkspaceID` | `uniqueidentifier` | No | Fabric workspace |
| `SessionOwnerItemID` | `uniqueidentifier` | No | Actual session-owning item, including shared sessions |
| `SessionOwnerItemType` | `varchar(32)` | No | Validated API item route |
| `LivySessionID` | `nvarchar(128)` | No | Actual session identity |
| `ApplicationID` | `nvarchar(128)` | No | Spark application |
| `ApplicationAttemptID` | `nvarchar(64)` | No | Explicit attempt, never silently "latest" |
| `ApplicationStatus` | `varchar(32)` | No | Provider execution status |
| `StartedAtUtc` | `datetime2(7)` | Yes | Application start |
| `EndedAtUtc` | `datetime2(7)` | Yes | Application end |
| `CollectedAtUtc` | `datetime2(7)` | Yes | Snapshot collection |
| `CollectionStatus` | `varchar(16)` | No | `PENDING`, `COMPLETE`, `PARTIAL`, or `UNAVAILABLE` |
| `SourceMappingJson` | `nvarchar(max)` | No | Per-field supported source, unit conversion, availability/reason and contract version |
| `ExecutionEvidenceJson` | `nvarchar(max)` | Yes | Code/configuration/baseline/Advisor references |

Additionally includes **all 50 nullable metric columns** defined in
`docs\ingestion\spark-metric-columns.md`, including the two allocated-executor bounds.
Preserve counts/bytes, decimal seconds, anomaly flags, and cause JSON as declared there.
Unsupported, not-applicable, and delayed values are null with a reason, never zero.

Unique `(RunID, ActivityRunID, ApplicationID, ApplicationAttemptID)`. Delayed collection
updates the canonical snapshot idempotently; keep archived raw evidence separately.

### ops.DiagnosticCollection

One request for one diagnostic scope. Status/retry state is independent of ingestion.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `CollectionID` | `uniqueidentifier` | No | PK |
| `RunID` | `uniqueidentifier` | No | FK to `IngestionRun` |
| `SparkMetricID` | `uniqueidentifier` | Yes | FK to `SparkApplicationRunMetric`; null for pre-application evidence |
| `ScopeKey` | `nvarchar(256)` | No | Stable sanitized session/application/attempt/scope key |
| `Status` | `varchar(16)` | No | Pending/running/complete/partial/unavailable |
| `AttemptCount` | `int` | No | Bounded collector retries |
| `RequestedAtUtc` | `datetime2(7)` | No | Enqueue time |
| `NextAttemptAtUtc` | `datetime2(7)` | Yes | Backoff scheduling |
| `CompletedAtUtc` | `datetime2(7)` | Yes | Terminal collection time |
| `UnavailableReason` | `nvarchar(2048)` | Yes | Expiry, permission, unsupported scope, missing logs, or other controlled reason |
| `RowVersion` | `rowversion` | No | Concurrent worker protection |

Unique `(RunID, ScopeKey)`. Collect promptly before provider retention expires; a
missing startup log does not convert an ingestion failure into success.

### ops.DiagnosticArtifact

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `ArtifactID` | `uniqueidentifier` | No | PK |
| `CollectionID` | `uniqueidentifier` | No | FK to `DiagnosticCollection` |
| `ArtifactType` | `varchar(32)` | No | Driver, rolling driver, executor, event, Livy, or sanitized evidence |
| `SourceIdentity` | `nvarchar(512)` | No | Container/file identity and revision discriminator, not filename alone |
| `SourceModifiedAtUtc` | `datetime2(7)` | Yes | Provider file revision |
| `CollectedAtUtc` | `datetime2(7)` | No | Retrieval time |
| `ByteCount` | `bigint` | Yes | Bytes actually archived |
| `Sha256` | `binary(32)` | Yes | Integrity check of archived bytes |
| `IsComplete` | `bit` | No | False when partial/truncated |
| `RetrievalContextJson` | `nvarchar(max)` | No | Scope, offsets, limits, content type, attribution, and truncation reason |
| `StorageRef` | `nvarchar(2048)` | No | Protected artifact location without embedded credentials |
| `IsSanitizedCopy` | `bit` | No | Distinguish support copy from restricted raw evidence |
| `ExpiresAtUtc` | `datetime2(7)` | Yes | Approved retention/cleanup boundary |

Unique collection/source-revision/snapshot identity, using a fixed-length canonical
hash if required by SQL index limits. Do not overwrite growing/rotated evidence.
Shared-session raw logs retain restricted support access; do not expose other workloads
through developer copies.

### ops.AlertEvent

Includes alerts for expected runs that never started, so a run FK can be null.

| Column | Type | Null | Key / Purpose |
| --- | --- | --- | --- |
| `AlertEventID` | `uniqueidentifier` | No | PK |
| `PipelineID` | `uniqueidentifier` | Yes | FK to `PipelineDefinition` when attributable |
| `RunID` | `uniqueidentifier` | Yes | FK to `IngestionRun` |
| `TableRunID` | `uniqueidentifier` | Yes | FK to `IngestionTableRun` |
| `SparkMetricID` | `uniqueidentifier` | Yes | FK to `SparkApplicationRunMetric` |
| `ProviderAlertID` | `nvarchar(256)` | No | Provider identity for deduplicating repeated callbacks |
| `RuleName` | `nvarchar(128)` | No | Versioned alert rule |
| `Severity` | `varchar(16)` | No | Operational severity |
| `Status` | `varchar(24)` | No | Fired/acknowledged/resolved/delivery-failed |
| `OccurredAtUtc` | `datetime2(7)` | No | Provider event time |
| `DeliveryContextJson` | `nvarchar(max)` | No | Route reference, delivery status, incident reference; no secrets |
| `EvidenceJson` | `nvarchar(max)` | Yes | Observed value, threshold/baseline, scope, runbook, and artifact references |
| `AcknowledgedAtUtc` | `datetime2(7)` | Yes | Acknowledgment |
| `ResolvedAtUtc` | `datetime2(7)` | Yes | Recovery/resolution |

Unique `(ProviderAlertID, Status, OccurredAtUtc)` to retain transitions without duplicate
callbacks. Route details/credentials remain in infrastructure/approved secret storage.

## Required Schema Discovery Before Bronze Ingestion

**Separate required review:** `docs\ingestion\schema-discovery-design.md` presents this
process, policies, evidence, and recovery behavior as a standalone review document.
Obtain explicit approval of that document as well as this framework design before
beginning the dependent build; the requirement to perform discovery is not approval
of its proposed implementation policies.

**Current implementation:** the versioned source JSON files describe approved columns
and primary keys. `source_contracts.py` validates those files' structure, identifiers,
supported type declarations, and key usability; it does not connect to live SQL or
compare deployed schemas. `SchemaContractJson` and `SchemaChangeLog` are proposed
framework definitions, not an implemented discovery service.

The dependency-driven parent workflow should invoke reusable schema discovery and
start eligible ingestion promptly when applicable results are ready, without a
fixed ingestion-start delay. One full discovery pass per selected source table/cycle
is the agreed direction. Airflow/Fabric integration, exact scheduling/concurrency,
result granularity, and any lightweight extra live-source check still need review:

```text
Create ingestion run and selected table attempts; freeze approved configuration
  -> schema_discovery: inspect live SQL metadata for every selected source table
  -> persist PASS / FAIL / UNAVAILABLE evidence and schema differences
  -> extraction loop receives only mappings with a matching persisted PASS
  -> copy to staging, validate mapped extracted schema, append batch to Bronze
```

### Discovery Inputs and Comparison

- Discover only enabled, selected source objects. Newly found SQL tables are not
  automatically registered, ingested, or approved.
- Read `sys.schemas`, `sys.tables`, `sys.columns`, and `sys.types`; use
  `sys.indexes`/`sys.index_columns` for primary-key membership and key order.
  Inspect metadata only, not patient rows. Verify the executing source identity has
  the required read and metadata visibility permissions.
- Compare against the approved `cfg.SourceObject.SchemaContractJson`, ordered
  `PrimaryKeyColumnsJson`, watermark declaration, and the selected mapping's approved
  type/column mappings, all resolved from the run's immutable configuration snapshot.
  The latest discovery result is evidence, never the expected-schema baseline.
- Compare source/table existence; column additions/removals; names; exact SQL types,
  character lengths, numeric precision/scale, timestamp precision, and nullability;
  ordered primary keys; and presence/type of configured watermark and soft-delete
  columns. Reject unsupported types or collisions with configured technical columns.
- Canonicalize ingestion-significant properties before hashing. Account for SQL catalog
  byte lengths versus declared character lengths, `max`, and identifier comparison
  rules. Physical column order alone is not blocking when the approved extraction uses
  explicit name-based projections; primary-key order remains part of the contract.
- Compare SQL metadata before Spark conversion. Separately validate the staged Spark/
  Delta schema against the approved SQL-to-Delta mapping; a Spark string column alone
  cannot prove an exact SQL character-length match. Never use `SELECT *`, automatic
  Delta schema evolution, or inference as a substitute for the approved contract.

### Proposed Gate Behavior

| Result | Disposition before source extraction |
| --- | --- |
| Approved contract matches | Persist `PASS`; authorize only that table attempt and frozen configuration. |
| Added/removed/renamed column, changed type/length/precision/nullability, or changed key/watermark | Approved Strict policy: persist differences, block the affected table and alert, including nullable additions/type widening. Resume after review/approved contract revision or source correction. Do not copy, append or advance state; unrelated tables continue. |
| Source query fails, permissions are insufficient, or evidence cannot be persisted | Fail closed; do not copy, append, or advance the affected table's watermark. Record `UNAVAILABLE` where possible and a sanitized error; failure to record evidence cannot authorize ingestion. |
| Only physical column order differs | Record observation; permit if explicit mappings and all ingestion-significant properties match. |

Strict, table-isolated blocking is approved; there is no compatible-change allowlist.
Physical column order alone is still non-blocking under explicit name-based projection
when ingestion-significant properties match. Discovery cannot approve contracts, edit
metadata/DDL, or change a run's frozen snapshot. Approval/publication mechanics and
unavailable-evidence handling remain design-review work. Do not retry deterministic
drift as a transient connection error.

Use the existing 17-table model: write every check to `ops.ReconciliationResult`,
differences to `ops.SchemaChangeLog`, and failures to `ops.IngestionError` with
`FailurePhase = SCHEMA_DISCOVERY`. Track `SCHEMA_DISCOVERY` in table-attempt phase
progress; `SCHEMA_RECHECK` applies only if an optional second check is later approved.
Correlate the child workflow's native execution IDs in
the parent run's execution context; no new run type is required for this child activity.
Emit pre-Spark alerts through the planned centralized failure route.

Complete applicable discovery before its dependent source extraction and preserve
table-level isolation. Exact discovery barrier/chunking/concurrency and result-delivery
mechanics remain open. An execution with blocked required tables cannot be reported as
fully successful; a fatal discovery failure cannot authorize tables without their own
persisted acceptable result. Dependency-blocked downstream work is not a transformation
failure; see the separate orchestration design.

A discovery pass does not lock source DDL. Keep staged-schema validation before
publication and abort on read/conversion/schema failures without advancing state.
Do not add another full source scan; a lightweight live recheck is explicitly unapproved.
Source DDL/write consistency and the validation-to-use gap need design review rather
than an implicit extra scan.

For recovery using an already captured immutable batch, validate its saved schema,
capture-contract revision, and compatibility with the approved target mapping before
append. Do not query SQL again merely to relabel an existing batch, silently apply a
new contract to it, or require the current live source schema to equal historical data.
Fresh extraction always requires fresh live-source discovery.

Acceptance cases must cover a matching schema; extra/missing/renamed columns; SQL
length/decimal/timestamp precision and nullability differences; PK and watermark
changes; unsupported types; metadata permission/connectivity failures; absent or stale
PASS evidence; drift between preflight and extraction; staged-schema mismatch; batch
replay; and one blocked table alongside valid tables. Prove blocked attempts perform no
source-data copy, Bronze append, or watermark advance.

**SQL catalog references:** `https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-columns-transact-sql`
and `https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/querying-the-sql-server-system-catalog-faq`.
Metadata visibility: `https://learn.microsoft.com/en-us/sql/relational-databases/security/metadata-visibility-configuration`.

## Orchestration and State Protocol

1. Select active domain/pipeline/mappings. Validate source/target contracts, all steps,
   registered names and parameters, supported policies, and runtime permissions.
2. Resolve and freeze configuration and code/runtime identity. Insert the run and its
   table attempts with stable persistence IDs.
3. For fresh captures, execute the required live schema-discovery pass and persist its
   results before the extraction loop. Replay attempts instead require the saved-input/
   target compatibility check above. Block failed/unavailable attempts in either path.
4. Acquire each eligible mapping's exclusive write lease through an atomic conditional operation;
   verify run type and owner/token before writes and before state commits.
5. For source loads, verify the earlier generation's completion/committed checkpoint
   under the reviewed D05 protocol and establish the fixed extraction interval. Do not
   assume generation starts with ingestion or that a generator-pause mechanism is approved.
   Use parameterized inclusive lower/exclusive upper bounds with approved
   overlap. Use the applicable discovery evidence; keep exact SQL timestamp values
   outside Spark precision-loss paths. Replay saved batches under the schema rules above.
6. Copy to immutable batch-owned staging, validate its mapped schema, and append the
   captured observations to Bronze with enforced batch-publication idempotency.
   Record successful target version. Preserve source audits and soft deletes; do not
   deduplicate distinct batches or apply business-key updates in Bronze.
7. Reconcile the defined batch/source/target scope, not current source counts against
   all accumulated Bronze history. Only then commit the new watermark
   and successful attempt together in the control database under the current owner/token.
8. Release the lease and finalize the run. Independent table failures remain isolated.
   Benchmark runs use separate artifacts/results and never execute step 7's state advance.
9. Recover post-target/pre-watermark failures by verifying the saved batch's publication
   evidence and repairing state without appending that batch twice. A fresh extraction
   is a new batch, even for the same window. Validate the selected Delta commit/replay
   mechanism and evidence-retention limits before implementation; do not claim a
   distributed transaction between the control database and Delta.

Source checkpoints are part of the simulator's controlled consistency protocol, not
proof that timestamp-only extraction is safe for arbitrary external SQL applications.
CDC/Change Tracking, physical-delete capture, capture of every intermediate source mutation, and
cross-source patient consolidation require later designs.

### Approved Dependency and Release Behaviors Still Needing Physical Schemas

The protocol above is a proposed ingestion baseline, not a complete Airflow or
Silver 2 scheduler. See `docs\architecture\orchestration-design.md` for the required
committed/fresh readiness gates, `BLOCKED_BY_DEPENDENCY` semantics, separate
availability SLA, automatic late recovery, ordered configuration releases, activation
checks, and incident rollback. Apply the approved logical task/dataset/input/function
revision while reviewing exact columns/keys, operational reuse, latest-expected-outcome
and window semantics, event/commit recovery, and active-version audit before migrations.
Preserve the current Patient-only first Silver scope.

## Patient Silver Contract Proposed for Approval

- Read Clarity Patient Bronze only, at a recorded version.
- Preserve `PatientID`, all approved source fields/audits, and `IsDeleted`; do not
  discard deleted rows or rewrite source modification times.
- Trim configured string fields only; preserve nulls and do not invent clinical values.
- Deduplicate by `PatientID`, newest `ModifiedAtUtc` first. Exact duplicates collapse;
  conflicting rows with identical key/time fail or quarantine rather than choose an
  arbitrary survivor. Agree on any additional source tie-breaker before enabling it.
- Upsert one row per patient; reruns are idempotent. Validate precision/type mappings
  and do not infer physical deletion from a missing incremental row.
- Use `patient_bronze_silver` and an approved target name. Do not seed this pipeline's
  actual configuration until this document is approved.

## Profiling, Diagnostics, and Alerts

- Follow the isolated protocol in the approved design: frozen input/reference snapshots,
  initial setup outside timing, full-column Delta output per function, and snapshot
  re-read before the next function. Record plan, materialization, and full-step durations.
- Persist required results regardless of diagnostic verbosity. No profiling actions
  on the disabled path. Warm-ups and failed trials are not successful measured samples.
- Explain that materialization timings include I/O and optimizer-boundary effects;
  validate code/compute changes using normal end-to-end runs.
- Diagnostic collection covers supported driver/rolling/executor/event/Livy APIs,
  pagination, size/offset limits, retries, actual session ownership, and attempts.
- Centralize filtered application events/metrics through the supported Fabric Log
  Ingestion/DCR route. Configure versioned KQL/action groups with actual destination
  schemas; Python console output alone is not evidence that an event was ingested.
- Alert on failures including pre-Spark/Copy-only failures, comparable duration
  regressions, sustained memory pressure, freshness breaches, and telemetry gaps.
  Baseline absence and unsupported signals remain explicit.
- Confirm notification targets, scheduling mechanism, identities, metric/API
  permissions, retention, and spend limits before activation.
- Future processed-record monitoring uses UCL = historical mean + 2 standard deviations
  and LCL = historical mean - 2 standard deviations, as selected November 20.
  Implementation is deferred. Metric grain, comparable samples/lookback, minimum
  history, standard-deviation calculation, negative-LCL handling and breach response
  remain to be designed; no automatic failure/readiness gate is approved.

## Approval Checklist

- Revised physical task/dataset/input/function-array and operational/release schemas, reconciled with the original 17-table baseline and accepted Fabric SQL backend; do not approve the baseline unchanged.
- Configuration hierarchy, constraints, relationships, and recording grains.
- Append-only Bronze batch publication, staging retention/cleanup separate from approved indefinite ingested Fabric data retention, and the committed-source checkpoint protocol. The Bronze row-column set above is already accepted. Generator exports/manifests have a separate five-day retention target, subject to confirmed ingestion and unfinished/recovery-run holds; current generator identity/population/checkpoint state remains protected until verified replacement.
- Explicit review of `docs\ingestion\schema-discovery-design.md`: implement the approved Strict policy and one-pass direction; finalize unavailable-evidence/scheduling/concurrency, optional recheck/DDL consistency, and retained evidence details without reopening tolerance.
- Review `docs\ingestion\task-dataset-design.md` and the readiness/recovery/release/rollback protocols in `docs\architecture\orchestration-design.md`; logical approval does not finalize columns, keys, or statuses.
- Lease recovery, retry ownership, and post-target/pre-state replay semantics.
- Patient Silver schema/deletion/deduplication contract.
- Benchmark and telemetry isolation, evidence access, and retention.

After approval: implement migrations/routines and platform resources, then prepare
and review source configurations for all 28 physical tables before enabling ingestion.

## Index, Retention, and Access Plan

The index examples below describe the baseline. Revise them for task/dataset/input
keys, snapshot/release scope, current readiness, event dispatch, and JSON-step
attribution; do not create an obsolete physical step table to satisfy an old index.

- Configuration PKs and declared unique constraints support direct resolution. Index
  mapping selection by `(PipelineID, IsActive)` and step lookup by
  `(PipelineObjectID, StepOrdinal)`; FK indexes are explicit deployment work.
- Index run history by pipeline/start time and table history by mapping/start time.
  Index error/schema/reconciliation records by their parent table-run and occurrence/check time.
- Keep watermark lease acquisition as a conditional PK lookup, never a scan followed
  by an unconditional update.
- Index benchmark history by function/start time, including table-run/trial/outcome
  and duration columns. Join the frozen run configuration for code/compute comparisons;
  add validated computed JSON projections only for demonstrated query needs.
- Index Spark snapshots by their declared recording grain and ingestion run. Index
  pending diagnostic work by `(Status, NextAttemptAtUtc)` and artifacts by collection.
  Index alert history by pipeline/event time in addition to callback deduplication.
- Separate restricted raw evidence from sanitized support copies. Use approved
  identities with read-only diagnostic access; do not make a lakehouse path public.
- Agree on independent retention for configuration snapshots, run/control history,
  staging, benchmark snapshots, diagnostic files, and alert history before cleanup
  is enabled. Preserve parent records while retained child evidence references them.
- Grant ingestion identities only the approved configuration reads and transition
  routines; diagnostic workers cannot modify watermarks. Restrict configuration edits,
  lease takeover, and retention deletion to their respective authorized operations.
