# Concrete metadata/control-plane implementation

These are local development artifacts, **not deployed Fabric SQL or verified live
permissions/transactions**. The production backend is the dedicated Fabric SQL Database
transactional endpoint. SQLite is only a durable local protocol reference in a checkout.
No infrastructure creation, migration-test database, custom backup service or Delta undo
is included. Metadata backup/restore uses native Fabric SQL facilities.

## Physical schema and deployment

Apply reviewed `migrations\0001_configuration.sql`, `0002_control.sql`,
`0003_legacy_preservation.sql`, `0004_operational_records.sql`,
`0005_waiting_operations.sql`, `0006_source_coverage.sql` in order. The scripts are additive, transaction-bounded,
ledger-guarded and contain no client-only `GO`. `metadata_migrations.apply_migrations`
uses a real `SqlServerControlStore` connection and records/checks immutable script hashes.
Never edit an applied migration; halt failed deployment and publish a controlled
corrective migration. Do not assume arbitrary future DDL can be automatically reversed.
Activate dependent framework code only after backward-compatible migration and technical
checks; retain this schema and baseline tables through the rollback compatibility window.

`COLUMN_DICTIONARY.md` lists every exact column, type and nullability. Named keys,
composite correlation FKs, uniqueness, JSON checks and indexes are in the SQL. Application
validation additionally enforces the graph, function parameter schemas, immutable bindings
and legal state transitions. Coverage uses normalized UTC `varchar(27)` with seven
fractional digits to preserve source `datetime2(7)` precision through DB-API. Operational
clock/lease/audit columns are UTC `datetime2(7)`.

`cfg.PipelineObjectMapping` bridges release-local source/target mapping to optional baseline
IDs; `cfg.ProcessingTask` is the executable grain, with optional mapping FK and mandatory
inputs/primary output. `cfg.PipelineDefinitionRelease` retains shared/stage policy without
baseline InputLayer/OutputLayer fields. Existing baseline `PipelineDefinition`,
`PipelineObject`, `TransformationStep`, `Ingestion*`, benchmarks and profiling data are
not dropped or rewritten. `LegacyStepAttribution` stores reviewed old-step to stable JSON
occurrence attribution; baseline `IngestionTransformationRun.TransformationStepID` remains
authoritative. The optional archive view is read-only, not a copied/custom backup.

## Transactions, concurrency and recovery

`SqlServerControlStore(connection_factory)` uses actual DB-API SQL, transactions,
serializable isolation and a bounded transaction-owned `sys.sp_getapplock`. A global
short-transaction lock intentionally favors demonstrable safety over metadata throughput
for this demo. No Spark, HTTP, event transport or other external work is done while that
lock is held. Production time comes from `SYSUTCDATETIME`, not worker clock guesses.
Connections must use scoped identity authentication and the transactional endpoint.
`from_pyodbc` imports the optional dependency lazily; the ODBC driver/authentication and
exact permissions must be validated on the reviewed target before deployment.

`queue_operation` permanently freezes the request hash, framework/DAG snapshot, processing
window and exact source/Delta input versions. Claims are exclusive for overlapping
dataset/environment/scope windows, monotonic-fenced and leased. Expired attempts of the
same operation can be taken over; other overlapping operations wait for uncertain/expired
writes to reconcile. Daily queued work has priority over conflicting backfills; disjoint
windows can proceed. No preemption of an already running daily/backfill write is invented.
Heartbeats or commits from replaced/expired attempts are rejected.

The runner must read only these pinned inputs and use the **logical operation ID** as the
Delta idempotency/commit token across retries. `assert_fence` is required immediately before
writing but SQL cannot atomically fence an external Delta commit. In particular a delayed
old writer must be made harmless by Delta's idempotent token/transaction protocol; a SQL
lease alone is not a distributed write lock. The runner's commit verifier must inspect
actual durable Delta transaction/version and normal schema/quality/coverage evidence,
not trust notebook status or a row count. Conflicting key/time Patient ties remain fatal.

`publish` atomically records immutable output evidence, completes its attempt, protects
newest logical progress and writes the outbox. A zero-change increment with verified
coverage preserves the previous data version; empty initial loads remain subject to the
approved source/output expectations enforced by the verifier. The current output pointer
is independent of latest expected outcome: a newer failure/uncertainty blocks consumers
while retaining the last valid output. Completion time never outranks logical coverage.

After Delta commit but before SQL acknowledgement, retain the durable evidence outside
SQL. Mark `UNCERTAIN` if possible. While metadata is unavailable no new starts/readiness
publication occur. Let safe in-flight work finish, then `reconcile_commit` independently
verifies its fixed token/input/window and records it once, without reappending. Do not
declare uncertain output ready or run a conflicting replay until reconciliation succeeds.

Corruption flags conservatively follow approved release graphs and recorded lineage;
dataset-level blocks cover descendants across pinned releases. Technical release rollback
does not clear them or undo Delta. Each confirmed-corruption block requires explicit
operator approval and validation evidence to clear; descendants are not silently cleared.
Routine latest-failed blocking can clear after the same/later expected window is corrected.

## Events, reconciliation, backfills and retention

Outbox rows are written in the publication transaction. Stable event IDs, receipt PKs and
logical-progress ordering deduplicate/reject obsolete wakeups. Coalescing is default and
configurable; `process_each=True` preserves intentional every-update delivery semantics.
Every consumer still rechecks **all** inputs in `claim`. `dispatch_events` supplies bounded
at-least-once delivery/backoff and emits an Outlook-email-required audit on exhaustion.
It never assumes transport acknowledgement proves exactly-once execution.

Reconciliation defaults to five minutes, one leased owner per environment, immutable
snapshot, bounded retries/backoff, owner heartbeat and next-run catch-up after exhaustion.
It scans persisted queued/blocked/uncertain/expired operations independently of lost events.
Persistent failures record an Outlook/email alert request; parent operational wiring must
deliver that notification to the configured recipient.

### Read-only schedule-health query

```python
store.scheduled_operations(
    environment: str, window_start: str | datetime, window_end: str | datetime,
    limit: int = 1000,
) -> tuple[Mapping[str, Any], ...]

rows = store.scheduled_operations(
    "demo", "2026-11-20T00:00:00Z", "2026-11-21T00:00:00Z", limit=1000,
)
```

Both SQL and SQLite return existing **daily** operations whose half-open processing windows
overlap the requested UTC range (`operation.start < range.end` and `operation.end > range.start`).
Offset timestamps normalize to UTC. Ordering is processing end, processing start, operation ID.
The actual stored kind names are `daily` (default scheduled/deferred daily work), `backfill`,
and `rerun`; there is no stored `scheduled` kind. This query selects `daily` only and applies
**no status filter**, unlike dispatch/reconciliation candidates: queued, blocked, running,
uncertain, failed, succeeded and canceled daily outcomes remain visible.

Mappings retain public operation/task/release/status/window fields and deferred binding
declarations where applicable. Additional `source_coverage_start/end` are from the operation's
committed output, or null if no verified output coverage exists—not processing/publication
time or last-good coverage from another operation. `corruption_blocked` reflects an existing
active dataset/environment/scope block. `health_status` is `CORRUPT` when blocked, otherwise
the original status; original `status` is never overwritten (CORRUPT is not a TaskOperation
storage-state enum). The blocked storage name is `BLOCKED_BY_DEPENDENCY`.

Environment/range values are bound parameters and `limit` is an integer 1–1000, not boolean.
A result reaching its limit might be truncated: narrow/split the range rather than declaring
a partial result healthy. The query creates no operations, audit rows, retries, tables or
business/deadline/freshness policies. It cannot report expected work the scheduler never
recorded; parent monitoring still compares against its schedule and independently checks
source freshness/latest failure. No live Fabric SQL query/permission validation is claimed.

Backfills are explicitly queued windows, not triggered by transform releases. Current
corrected source is default. Available historical source snapshots can be registered with
verified retained evidence and pinned with `InputBinding.source_snapshot_id`; historical
Delta inputs use exact `output_id`. Unavailable/different historical sources never silently
fall back. An explicit recorded approval can authorize substitution; the actual versions
remain in immutable operation inputs. Manual reruns default to the original approved
release, with explicit choice of another previously activated release.

Execution/readiness audit target is seven years, with current-output, historical lineage,
active-run and explicit approved-recovery/reference holds overriding cleanup eligibility.
`protected_references` exposes the protections for artifact/Delta-version cleanup.
`can_cleanup_output` authorizes only evidence cleanup, never automatic age-purge of
indefinitely retained Bronze/Silver data. Referenced releases/images/evidence remain held;
no custom backup/restore pipeline or cross-region DR is introduced.
Each publication automatically holds its operation's idempotency evidence and its release
while committed data refers to them. Only an authorized cleanup/operator path with proof
that the data/reference no longer exists may release those holds. Historical SQL output
records do not alone prove an old Delta version is still readable: the runner must confirm
selected snapshots still exist, fail closed if unavailable, and never substitute current.

## Deferred daily requests

`WAITING_OPERATIONS.md` documents `queue_waiting_operation` and `bind_waiting_operation`.
Daily downstream intent can persist before any upstream Delta version exists: it pins
the DAG-run release, task/window and declared input identities, with no OperationInput
rows or invented placeholder version. Migration 0005 adds the durable resolution guard.
Complete validated inputs freeze atomically once, before any attempt/write; unresolved
claims remain BLOCKED_BY_DEPENDENCY. Original request hashes, release versions and fixed
explicit/manual input bindings are never rewritten. Parent-owned event/reconciliation
resolvers select compatible actual commits using the operation's originally pinned snapshot.

## Verified source coverage

`SOURCE_COVERAGE.md` documents the appended InputBinding/CommitEvidence source-coverage
fields and strict provenance rules. Processing windows and logical `progress_end` remain
independent; freshness uses only verified `source_coverage_end`. Source snapshot bounds
are generator/capture coverage, not an implied historical processing interval. Current
backfills may read fresh real full snapshots for older processing windows; historical
requests still require retained selected originals and never substitute silently.
Migration 0006 preserves unknown legacy coverage as NULL rather than fabricating freshness.
Production never falls back to processing/publication time; local legacy protocol fixtures
must explicitly opt in to same-window compatibility.

## Operational persistence

`OPERATIONAL_RECORDS.md` is the exact public writer/read contract and record dictionary.
Migration 0004 adds task-grain diagnostics, all 50 nullable Spark measurements, benchmark
trials/steps, quality outcomes, quarantine manifests, cleanup outcomes and immutable revision
history without rewriting any baseline diagnostic/profiling data. The SQLite reference
initializes `reference_operations.sql`; it is not a replacement production schema.
Diagnostics, benchmark and cleanup records do not change readiness or execution status.
Publication rejects a persisted critical FAIL/UNAVAILABLE quality outcome for its own
current attempt. Protected artifact content and actual collection/execution remain runner
responsibilities; recording a supplied status is not a successful live acceptance check.

## Access boundary and evidence still required

Deployment configuration publication is branch/PR/review/CI-governed. Runtime operators
must not have unrestricted `cfg` write rights or bypass this boundary for metadata hotfixes.
Airflow uses immutable snapshots; Spark/framework transitions are scoped operational writes.
Operator approval identity is supplied by an authenticated administrative caller, not a
worker's arbitrary string. The Python adapter enforces transitions but is not a database
security boundary against arbitrary direct SQL: final deployment must review database roles,
grant only the necessary service identities and verify each denied-write/read-only path.
`permissions.sql` provides unexecuted runtime/publisher/operator/read-only role definitions,
including column-scoped operational updates, runtime configuration DML denial and operator-only
corruption clear/reference release. It creates no principals, memberships or credentials.
Migration DDL permissions are separately held by the reviewed deployment identity. Do not combine
runtime/publisher/operator memberships to circumvent the separation. These grants constrain
identities but do not replace the trusted transition service: arbitrary direct INSERT can still
fabricate evidence, so runners access the authenticated framework interfaces only.

Local tests verify protocol behavior and schema/reference-column alignment. They do **not**
prove live Fabric SQL DDL support, isolation/lock contention, ODBC availability, native
backup/restore, deployed credentials/permissions, Delta commit integration, Fabric publication,
Airflow recognition or Outlook delivery. Those are mandatory reviewed live acceptance checks.

Offline artifact check (no deployment):

```powershell
uv run python database\metadata\inspect_metadata.py --check
uv run pytest tests\test_configuration.py tests\test_control_store.py tests\test_release.py tests\test_metadata_migrations.py
```
