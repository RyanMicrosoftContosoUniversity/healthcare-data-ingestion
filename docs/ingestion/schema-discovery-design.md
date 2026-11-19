# Pre-Ingestion Schema Discovery: Design Review

**Status: proposed, awaiting explicit user review.**

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

## Where Discovery Runs

The ingestion parent pipeline invokes one reusable `schema_discovery` child pipeline
before the fresh-extraction loop starts. The child inspects every selected source table
and persists a result for each table attempt.

```text
Start ingestion run; create selected table-attempt records
  -> Freeze approved configuration and source contracts
  -> Run schema_discovery for all selected source tables
  -> Persist each table's PASS / FAIL / UNAVAILABLE result
  -> For each eligible table:
       Acquire the mapping's write lease
       Establish fixed extraction boundaries and source checkpoint
       Recheck source schema immediately before extraction
       Extract records into immutable batch staging
       Validate staged schema against the approved type mapping
       Append the batch to Bronze with batch-publication retry protection
       Reconcile and commit state only after successful validation/publication
  -> Finalize the overall ingestion run
```

Only attempts with matching, persisted evidence for their frozen configuration may
proceed. Complete the discovery pass before starting fresh extraction.

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

**Strict comparison is the proposed default.** Even nullable additions and type widening
block until reviewed contract/mapping revisions or a separately approved bounded
compatibility policy permits them. Discovery never changes source/target DDL, silently
updates configuration, or approves schema drift.

Preserve table-level failure isolation: matching tables may continue after the discovery
pass; blocked tables do not. If a required table is blocked, the overall ingestion run
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
| `ops.IngestionError` | Sanitized discovery/recheck failures, retry classification, and correlated run/table-attempt IDs. |
| `ops.IngestionTableRun` | Attempt status and completed discovery/recheck phases. |
| Planned centralized alert route | Discovery failures must be visible even when no Copy activity or Spark application starts. |

Use distinct check names so phases retain their own evidence:

| Check name | Scope |
| --- | --- |
| `SOURCE_SCHEMA_PREFLIGHT` | Live source versus frozen contract before the extraction loop. |
| `SOURCE_SCHEMA_BEFORE_EXTRACT` | Live source recheck immediately before that table's fresh extraction. |
| `EXTRACTED_SCHEMA_CONTRACT` | Staged input versus approved mapped schema before Bronze publication. |
| `REPLAY_SCHEMA_CONTRACT` | Saved batch/capture contract and approved target compatibility during recovery. |

Require evidence for the current attempt/configuration, not an earlier run's PASS.
Do not store patient values, credentials, or raw exception payloads in schema evidence.

## Mid-Run Changes and Saved-Batch Recovery

A preflight check does not lock the source schema for the entire execution. Recheck
before extraction, coordinate source DDL changes, and validate staging before append.
Abort on read/conversion/schema failures without advancing state. These checks do not
claim an atomic guarantee against arbitrary concurrent source DDL.

When recovering an already captured immutable batch, validate its saved schema,
capture-contract revision, and compatibility with the approved target mapping. Do not
query SQL again just to identify the same batch, silently apply a new contract, or
require today's live source schema to equal that historical extraction. A genuinely
fresh extraction always requires fresh live-source discovery.

## Review Decisions Required Before Build

| Decision to review | Current proposal |
| --- | --- |
| Pipeline placement | Mandatory reusable child pipeline before fresh extraction, plus per-table recheck and staged-schema validation. |
| Default drift policy | Strict blocking, including additions/widening, unless explicitly approved. |
| Failure scope | Block affected tables; allow matching tables; overall run is not fully successful if required tables fail. |
| Expected-schema ownership | Reviewed, revisioned configuration; discovery never auto-promotes observations. |
| Evidence model | Reuse the existing framework tables and retain successful as well as failed check evidence. |
| Recovery behavior | Validate saved batches against their capture contract and approved target compatibility without requiring fresh source access. |

All process proposals above remain pending review. The Bronze row-column set is
approved separately, including the readable `_ingest_source_name`. Approval of this
process does not approve the other framework table definitions, deployment targets,
or cloud provisioning.

## Acceptance Cases for the Later Implementation

- Matching schemas permit extraction only after a persisted matching result.
- Added/missing/renamed columns and type, length, precision, nullability, key, or
  watermark differences follow the approved policy.
- Permission/connectivity failures, absent/stale PASS evidence, and evidence-store
  failures cannot authorize ingestion.
- Drift after preflight and staged-schema mismatch cannot publish an invalid batch.
- With one valid and one blocked table, only the valid table proceeds; the blocked
  table performs no source-data copy, Bronze append, or watermark advance.
- Saved-batch replay validates its captured schema and target compatibility without
  silently extracting new data.

SQL catalog references and full control-table column definitions are in
`docs\ingestion\metadata-design.md`.
