# Pre-Ingestion Schema Discovery: Design Review

**Status: proposed, awaiting explicit user review.**

Reconciled with `discussions\discussed-changes.md` and the later
`discussions\discussion-02.md`. Discovery before batch ingestion and blocking only the
affected table on drift are approved. The November 20 follow-up selects **Strict**:
every ingestion-relevant contract difference blocks, including nullable additions and
type widening, until review/approved revision. Preserve one full source pass and staged
validation; scheduling/concurrency, unavailable-evidence handling and any lightweight
second check remain open. No duplicate full scan or compatibility allowlist is approved.

This is a required pre-build review document for the schema-discovery and Bronze
ingestion framework. Creating this document does not approve or implement the process.
Review it alongside `docs\ingestion\metadata-design.md` before implementing control
storage, source configuration records, schema-discovery pipelines, or Bronze flows.
Existing source-model approvals and cloud-target gates remain unchanged.

## Purpose and Current State

Detect differences between live source schemas and approved ingestion contracts
before copying source records or appending them to Bronze.

The current Python validator checks the local JSON source contracts, not live SQL
schemas. Discovery, its control tables, and the ingestion gate are not implemented.
The framework table definitions remain in `docs\ingestion\metadata-design.md`; this
document is the standalone process and behavior review.

The approved task/dataset logical revision is in `docs\ingestion\task-dataset-design.md`.
Bind discovery evidence to its ingestion mapping, immutable release/snapshot, and
operation/attempt identity without replacing the accepted Bronze IDs. Exact adaptation
of existing ops records remains a physical-design task. Schema validation is reusable;
future streaming may validate at startup/schema change, not necessarily every event.
Streaming implementation is outside the first batch build.

## Where Discovery Runs

The dependency-driven parent workflow invokes reusable discovery before eligible fresh
extraction. Inspect each selected source table once per cycle, persist its result, and
start eligible ingestion promptly instead of waiting for an arbitrary fixed start time.
Do not add another full catalog scan. Airflow/Fabric integration, exact barriers,
chunking, concurrency, timeout, and optional lightweight rechecks remain for review.

```text
Start ingestion run; create selected table-attempt records
  -> Freeze approved configuration and source contracts
  -> Run schema_discovery for all selected source tables
  -> Persist each table's PASS / FAIL / UNAVAILABLE result
  -> For each eligible table:
       Acquire the mapping's write lease
       Establish fixed extraction boundaries and source checkpoint
       Extract records into immutable batch staging
       Validate staged schema against the approved type mapping
       Append the batch to Bronze with batch-publication retry protection
       Reconcile and commit state only after successful validation/publication
  -> Finalize the overall ingestion run
```

Only attempts with acceptable persisted evidence for their frozen configuration may
proceed. Complete applicable discovery before dependent extraction; whether results
arrive as a complete pass or eligible groups is still a scheduling decision.

The discovery activity uses the existing ingestion `RunID` and pre-created
`TableRunID` values for control records. Record the native child-pipeline execution IDs
as trace context; they do not require a separate framework run type.

## Inputs and Expected-Schema Ownership

| Input | Purpose |
| --- | --- |
| Selected active source objects and pipeline mappings | Limit discovery to the tables this invocation intends to ingest. |
| Approved source connection/identity references | Read source catalog metadata without embedding credentials in configuration. |
| `cfg.SourceObject.SchemaContractJson` | Approved column names, SQL types and attributes, nullability, and contract revision. |
| Primary-key and watermark declarations | Verify record identity and extraction-boundary columns. |
| Approved column/type mappings and schema policies | Define the expected SQL-to-Delta conversion and allowed behavior. |
| Frozen run configuration and table-attempt IDs | Bind the check to the exact configuration and attempt it authorizes. |

Discovery must not make its latest observation the new expected schema. Contract
changes require review and a new approved revision; they cannot modify an in-flight
run's frozen configuration. Discovering an unregistered table does not enroll it.

## What Is Compared

Read source catalog metadata using `sys.schemas`, `sys.tables`, `sys.columns`,
`sys.types`, `sys.indexes`, and `sys.index_columns`. Discovery does not read patient
records. Validate the runtime identity's metadata visibility and source access.

| Check | Expected behavior |
| --- | --- |
| Source schema/table and column names | Detect missing tables and added/removed columns. Treat apparent renames as add/drop unless explicitly approved and mapped. |
| SQL types and attributes | Compare character lengths, numeric precision/scale, timestamp precision, and supported types. |
| Nullability | Compare each column's approved nullable/not-null declaration. |
| Primary keys | Compare membership and key order with the approved key configuration. |
| Watermark and soft-delete columns | Verify required columns exist and have the approved types. |
| Technical-column compatibility | Reject collisions with the accepted `_ingest_` Bronze metadata contract, including `_ingest_source_name`; see `docs\ingestion\metadata-design.md`. |
| Extracted schema | Before Bronze publication, validate the staged Spark/Delta schema against the approved SQL-to-Delta mapping. |

Canonicalize ingestion-significant properties before calculating schema hashes.
Account for SQL catalog byte lengths versus declared character lengths, `max`, and
identifier comparison rules. Record physical column order, but do not block solely on
it when extraction uses explicit name-based projections; primary-key order still matters.

Compare exact SQL types before Spark conversion. Do not treat a Spark string type as
proof that a source `nvarchar` length matches. Do not substitute `SELECT *`, inferred
schemas, or automatic target schema evolution for approved contracts.

## Proposed Results and Failure Policy

| Result | Action |
| --- | --- |
| `PASS` | Persist the match and allow this table attempt to proceed. |
| `FAIL` | Persist the differences, fail the affected attempt, and alert. Do not extract data, append to Bronze, or advance that table's watermark. |
| `UNAVAILABLE` | Block the affected attempt when discovery cannot establish a match, such as a connection or permission failure. |
| Evidence cannot be persisted | Block ingestion even if the in-memory comparison matched; missing evidence is never authorization. |

**Strict comparison is approved.** Added columns (including nullable), removed/renamed
columns, type widening/narrowing, changed lengths/precision/nullability, ordered keys,
and required ingestion-column differences block the affected table. Persist differences
and alert; do not copy source records, publish Bronze, or advance its watermark.
Other eligible tables continue. There is no compatible-change allowlist.

Resume fresh extraction only after review and an approved contract/mapping revision
or correction of the source back to its approved contract. Never mutate the current
run's frozen snapshot. Discovery does not change source/target DDL, silently update
configuration, or approve its own observations. Fail-closed handling of unavailable/
unpersisted evidence remains a separate process-review item, not an inferred approval
from selecting Strict.

Preserve table-level failure isolation: eligible tables may continue independently;
blocked tables do not. If a required table is blocked, the overall ingestion run
must not report full success. A fatal discovery failure blocks every table without its
own persisted matching result.

Bounded retries may handle transient discovery failures. Deterministic contract
differences require correction/review rather than repeated connection retries.

## Evidence and Operational Visibility

Reuse the proposed framework tables; no additional control table is introduced.

| Control record | Evidence |
| --- | --- |
| `ops.ReconciliationResult` | Every check, including successful checks, with status, source/attempt identity, configuration revisions, schema hashes, metadata-only snapshots, and check time. Numeric expected/actual fields may be null. |
| `ops.SchemaChangeLog` | Expected/observed schemas, differences, and blocked or explicitly allowed disposition. |
| `ops.IngestionError` | Sanitized discovery failures, retry classification, and correlated run/table-attempt IDs. |
| `ops.IngestionTableRun` | Attempt status and completed discovery/staging validation phases. |
| Planned centralized alert route | Discovery failures must be visible even when no Copy activity or Spark application starts. |

Use distinct check names so phases retain their own evidence:

| Check name | Scope |
| --- | --- |
| `SOURCE_SCHEMA_PREFLIGHT` | Live source versus frozen contract before the extraction loop. |
| `SOURCE_SCHEMA_BEFORE_EXTRACT` | Reserved proposal only if a lightweight second live-source check is later approved; not a required second pass. |
| `EXTRACTED_SCHEMA_CONTRACT` | Staged input versus approved mapped schema before Bronze publication. |
| `REPLAY_SCHEMA_CONTRACT` | Saved batch/capture contract and approved target compatibility during recovery. |

Require evidence for the current attempt/configuration, not an earlier run's PASS.
Do not store patient values, credentials, or raw exception payloads in schema evidence.

## Mid-Run Changes and Saved-Batch Recovery

A single discovery pass leaves a time-of-check/time-of-use gap; it does not lock source
DDL. Staged validation remains required, and read/conversion/schema failures must not
publish invalid data or advance state. Coordinated DDL windows or another consistency
protocol require review. Do not silently add an unapproved live recheck as the solution,
or claim staged Spark types prove exact source SQL lengths/nullability at extraction.

When recovering an already captured immutable batch, validate its saved schema,
capture-contract revision, and compatibility with the approved target mapping. Do not
query SQL again just to identify the same batch, silently apply a new contract, or
require today's live source schema to equal that historical extraction. A genuinely
fresh extraction always requires fresh live-source discovery.

## Review Decisions Required Before Build

| Decision to review | Current proposal |
| --- | --- |
| Workflow placement | Reusable discovery before eligible fresh extraction, then prompt dependency-driven dispatch. One full pass is the agreed direction; integration/scheduling/concurrency are open. |
| Drift policy | **Approved: Strict.** All ingestion-relevant contract differences block that table pending review/approved revision or source correction; no allowlist or automatic evolution. |
| Unavailable evidence | Connection/permission failure or inability to persist results: proposed fail-closed behavior still needs process review. |
| Live-source recheck | Not approved. Decide whether a lightweight extra check is needed without duplicating full discovery. |
| Staged validation / DDL consistency | Keep independent mapped-schema validation; choose explicit protection/assumptions for the discovery-to-extraction gap. |
| Failure scope | Block affected tables; allow matching tables; overall run is not fully successful if required tables fail. |
| Expected-schema ownership | Reviewed, revisioned configuration; discovery never auto-promotes observations. |
| Evidence model | Reuse the existing framework tables and retain successful as well as failed check evidence. |
| Recovery behavior | Validate saved batches against their capture contract and approved target compatibility without requiring fresh source access. |

The approved behaviors above do not finalize physical evidence/state schemas or the
remaining policies. The Bronze row-column set remains approved, including readable
`_ingest_source_name`. No process approval is permission to provision unconfirmed
cloud targets or implement unreconciled baseline tables.

For the approved independent Bronze/Silver 1, dependency-gated Silver 2, freshness
versus SLA, and recovery/release requirements, review
`docs\architecture\orchestration-design.md`. A consumer waiting for a blocked upstream
dataset is `BLOCKED_BY_DEPENDENCY`, not a failed transformation. Persistence/state
schema remains under review. The subsequent November 20 decision accepts successful
zero-change incremental runs with verified source-window coverage and normal validation/
readiness checks; zero rows alone do not prove coverage. Empty initial/full-load
acceptance remains separate. Discovery and staged-schema checks still apply to no-change
runs; the detailed state protocol remains gated.

Failure of the latest expected source/producer execution blocks dependent consumers
by default, even if an older committed output is still recent. A schema/drift event is
not authorization to run downstream work: the metadata plane rechecks commit,
freshness, processing-window, and latest-expected-outcome requirements before dispatch.
Readiness events are primary; periodic reconciliation repairs missed notifications.

## Acceptance Cases for the Later Implementation

- Matching schemas permit extraction only after a persisted matching result.
- Added/missing/renamed columns and type, length, precision, nullability, key, or
  watermark differences block under Strict, including nullable additions and widening.
  Physical column order alone remains non-blocking under explicit name-based projections.
- Permission/connectivity failures, absent/stale PASS evidence, and evidence-store
  failures cannot authorize ingestion.
- Drift after preflight and staged-schema mismatch cannot publish an invalid batch.
- With one valid and one blocked table, only the valid table proceeds; the blocked
  table performs no source-data copy, Bronze append, or watermark advance.
- Saved-batch replay validates its captured schema and target compatibility without
  silently extracting new data.
- Prove one full source discovery pass per selected table/cycle; do not smuggle in a
  second scan. Exercise the reviewed mid-run-DDL behavior and prompt eligible dispatch.

SQL catalog references and full control-table column definitions are in
`docs\ingestion\metadata-design.md`.
