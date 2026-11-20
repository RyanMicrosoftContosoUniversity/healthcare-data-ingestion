# Metadata-Driven Orchestration and Release Design

**Status: approved directions and open design decisions, not implementation approval.**

Reconciled from `discussions\discussed-changes.md`. That discussion record is preserved
unchanged. Its explicit approvals supersede earlier conflicting proposals; statements
marked agreed in principle, recommended, or open do not approve schemas or runtime code.

## Approval and Build Boundaries

| Area | Status | Work allowed now |
| --- | --- | --- |
| Synthetic Clarity/Caboodle source models | Previously approved | Local source SQL definition generation and tests; no target-dependent deployment. |
| Append-only Bronze and eight technical columns | Previously approved | Preserve the contract; publication implementation still requires framework review. |
| Independent Bronze and Silver 1; dependency-gated Silver 2 | Behavior approved | Document execution/readiness requirements; no unreviewed runtime/state schemas. |
| Freshness, separate availability SLA, and recovery after missed deadlines | Behavior approved | Document policy-versus-observation requirements and acceptance cases. |
| Metadata-generated Airflow DAGs and sequential versioned releases | Behavior approved | Document lifecycle and technical checks; no invented deployment/queue schema. |
| Single source-discovery pass and prompt dependent dispatch | Agreed in principle | Revise the design; do not require a second live-source pass. |
| Airflow macro dependencies; PySpark ordered function composition | Agreed in principle | Keep the layers separate; do not choose a new step storage format. |
| Existing 17 metadata tables and suggested additions | Not blanket-approved | Assess gaps; no migrations or 28 source configuration records. |
| Drift tolerance, recheck, SLA calendars, release mechanics, Airflow hosting | Open | Keep decisions explicit; no implementation that assumes an answer. |
| Azure/Fabric targets and spend | Unconfirmed | No cloud provisioning. |

This request authorizes approved local development, not new infrastructure. The first
working data slice remains all-table Bronze plus Clarity Patient Silver 1. Silver 2 is
an architectural requirement, not authorization to implement new joins/business domains.
Gold, reporting, streaming implementation, and cross-source patient consolidation remain
outside the current build.

## Processing and Dependencies

Schedule the parent workflow, discover the selected source schemas once, and start
eligible ingestion when discovery results permit it. Do not insert an arbitrary fixed
ingestion start time or duplicate a full catalog pass for each processing phase.
Discovery scheduling, concurrency, timeout, and optional lightweight rechecks need review.
Validate staged schema before Bronze publication independently of source discovery.

| Stage | Dependency boundary | Isolation |
| --- | --- | --- |
| Bronze | Its own source/schema/extraction authorization | No dependency on unrelated source tables. |
| Silver 1 | Its own required committed Bronze input | Healthy tables continue independently. |
| Silver 2 | All explicitly required upstream datasets | Gate joins on compatible committed versions and required freshness/coverage. |

Readiness is not physical table existence, a green notebook, or any historical row.
Evidence must identify producer run/attempt, committed Delta version, source checkpoint
or event-time coverage, and the consuming operation's requirements.

Persist `BLOCKED_BY_DEPENDENCY`, the missing/stale dependency reason, and a notification
when a consumer cannot run. This is not a failed transformation and must not fabricate
an executed function record. The current baseline status columns are not automatically
extended by this requirement; the persistence/state model remains under review.

## Freshness and Availability

Per-dataset freshness is configuration; a consumer may require stricter freshness.
Different datasets need not share one ingestion cycle if their applicable requirements
are met. Use source coverage/checkpoints where available, not only completion time.
Keep desired policies in `cfg`; measured coverage, commits, and outcomes belong in `ops`.

Availability SLA is a separate business deadline for monitoring/reporting/alerting.
An SLA miss does not itself make useful late processing ineligible. Preserve the
original violation, actual availability time, and time to recovery.

Duration versus calendar semantics, time zones/holidays, precedence, full-load/streaming
coverage, and exact policy storage are open. **Recommendation, not approval:** do not
automatically fail a legitimately empty successful upstream result. Its acceptance and
readiness rules still require confirmation.

## Automatic Recovery and Idempotency

When a dependency becomes ready, reevaluate and automatically dispatch eligible blocked
consumers promptly, without waiting for the next scheduled cycle. Do so after an SLA
miss as well; do not clear the historical violation after recovery.

Use durable state, atomic claims, and idempotent writes across discovery, Bronze,
Silver 1/2, generated releases, and recovery. A retry of the same captured Bronze batch
must not append it twice; distinct batches retain repeated business observations.
SQL state and Delta commits are not a distributed transaction.

Event/outbox versus polling, claims/leases, the recovery queue, retry/backoff,
cross-DAG wakeups, reprocessing scope, and notification routes remain open.
"Immediate" is a dispatch requirement, not a chosen event-bus technology or zero-latency
guarantee.

## Macro Order versus Micro Order

The agreed direction is Airflow for task/dataset dependencies, with authoritative
definitions/readiness in Fabric SQL. Inside a task, a generic PySpark notebook resolves
registered utility functions and applies them in order using `DataFrame.transform()`.
Business functions take/return DataFrames and contain no framework logging or I/O.

The ordered function list is not the graph of upstream datasets. Keep the existing
`cfg.TransformationStep` proposal until the user chooses normalized step rows versus an
ordered JSON array. Airflow hosting, supported integration, DAG granularity, and dynamic
mapping are not selected.

## Configuration Publication and DAG Releases

Required human/governance approvals happen before configuration is published into the
authoritative metadata plane. Successful publication automatically initiates generation
and deployment; there is no second manual configuration-release approval gate.
This does not waive initial design, environment, identity, or infrastructure approvals.

Process approved releases sequentially. Every release uses its own complete immutable
configuration snapshot and corresponding code revision; never patch from the preceding
generated DAG artifact. Validate missing references, cycles, function registrations,
task definitions, and artifacts before activation.

The framework release and corresponding DAG artifact release use the same semantic
version. Track snapshot hash, code revision, artifact hash, deployment outcome, active
pointer, and execution IDs separately. Publication is not activation: a failed version
has history/evidence but is not reported as successfully deployed.

Keep the last known good active deployment on generation/deployment failure. Record and
alert the failure, then allow the next approved queued version to proceed. For example
only: active `1.1.0`, failed `1.1.1`, active `1.2.0`; fix on top as `1.2.1` rather than
automatically deploying an older repaired version over a newer active release.
No actual release numbers or deployment states are assigned by these examples.

Existing executions should remain pinned to their starting snapshot/code; the mechanism
to retain/import those artifacts and safely activate a newer deployment still needs review.
Immutable generation artifacts rather than live SQL queries during every scheduler
parse are the supported direction, not an implemented mechanism.

## Baseline Metadata Assessment

The existing ERDs remain a **17-table baseline**, not a complete approved model for the
new requirements. They already cover source/pipeline/step configuration, runs, table
attempts, watermarks/leases, checks/errors, profiling, diagnostics, and alerts.

| Required capability | Baseline coverage / unresolved gap |
| --- | --- |
| Dataset/consumer policy | `PipelineObject` and policy JSON are candidates; explicit upstream edges and override semantics are not defined. |
| Committed readiness | `IngestionTableRun.TargetVersion` and checkpoints are partial evidence; compatible multi-producer coverage/readiness needs a design. |
| Blocked work and wakeup | Existing failure/run records are not a reviewed blocked-task or durable dispatch queue. |
| Freshness versus SLA | Existing policy JSON/alerts are candidates; policy and independent measurements need review. |
| Release manifest and publication | Configuration revisions/run snapshots do not supply a reviewed semver publication manifest. |
| Sequential deployment and active pointer | No reviewed release queue, activation pointer, or deployment-attempt history exists. |
| Ordered functions | `TransformationStep` is proposed; JSON-array preference is not finalized. |

Do not silently overload unrelated telemetry tables or add unapproved physical tables
to make these gaps appear implemented. Review normalized additions versus existing
columns/validated JSON, recording keys, types, grains, constraints, relationships, and
state transitions before migrations, DAG generation, or runtime development.

## Review Diagrams and Acceptance Requirements

- `data-models\framework\06-orchestration.mmd` / `.svg`: isolation, readiness, and recovery.
- `data-models\framework\07-release-lifecycle.mmd` / `.svg`: publication through activation.
- `data-models\framework\08-transformation-order.mmd` / `.svg`: task versus function order.
- Existing `00-overview` and `05-full-schema` remain the baseline relationships/columns.

Later acceptance must prove table isolation, committed/fresh dependency gating,
blocked-not-failed reporting, recovery after missed deadlines without clearing SLA
evidence, duplicate-dispatch/write protection, one discovery pass, invalid release
rejection, sequential releases, failure followed by newer activation, last-good
preservation, and pinned in-flight execution behavior. Do not implement these tests
against invented runtime schemas before their review.

**Primary references:** `https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html`
and `https://semver.org/`. These support engineering research; the discussion record
defines this project's approvals. No Airflow/runtime version is pinned yet.
