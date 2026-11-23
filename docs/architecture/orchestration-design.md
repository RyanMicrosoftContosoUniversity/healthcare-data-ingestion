# Metadata-Driven Orchestration and Release Design

**Status: handoff03 approves remaining recommended directions and authorizes
development; concrete specifications/testing are required, not assumed complete.
Infrastructure deployment still requires the actual reviewed costed Terraform plan.**

`discussions\discussed-changes-03.md` supersedes contradictory earlier open-choice
labels below. Use five-minute single-owner snapshot-pinned reconciliation, fixed
input/output/window evidence, original-version reruns, queued/running pinning,
order-aware events and fenced claims; no silent historical-input substitution.
Critical quality blocks publication and confirmed corruption requires operator
clearance of affected lineage; unrelated work continues. Backfills are explicit,
checkpointed and subordinate to conflicting daily work. Metadata outage blocks new
starts until safe in-flight commit reconciliation. Configuration/hotfixes require PR
code review, with pinned published environments and safe technical rollback for new
runs. Outlook/email only; seven-year audit target/reference holds and native backups.

Reconciled from `discussions\discussed-changes.md` (November 19, 2026) and
`discussions\discussion-02.md` (November 20, 2026). Both records remain unchanged.
The second record supersedes conflicting earlier proposals. Approved logical entities
and behavior are not deployed tables or blanket approval of exact physical schemas.

Remaining user choices and review gates are consolidated in
`docs\architecture\build-decisions.md`; target model reconciliation is in
`docs\ingestion\task-dataset-design.md`.

## Approval and Build Boundaries

| Area | Status | Work allowed now |
| --- | --- | --- |
| Synthetic Clarity/Caboodle source models | Previously approved | Local source SQL definition generation and tests; no target-dependent deployment. |
| Append-only Bronze and eight technical columns | Previously approved | Preserve the contract; publication implementation still requires framework review. |
| Independent Bronze and Silver 1; dependency-gated Silver 2 | Behavior approved | Document execution/readiness requirements; no unreviewed runtime/state schemas. |
| Freshness, separate availability SLA, and recovery after missed deadlines | Behavior approved | Document policy-versus-observation requirements and acceptance cases. |
| Metadata-generated Airflow DAGs and sequential versioned releases | Behavior approved | Document lifecycle and technical checks; no invented deployment/queue schema. |
| Single source-discovery pass and prompt dependent dispatch | Agreed in principle | Revise the design; do not require a second live-source pass. |
| Airflow macro dependencies; PySpark ordered function composition | Approved | One independently executable task record; ordered function JSON array with validated parameters; reconcile legacy step identities before removal. |
| Logical metadata revision | Approved direction | Separate mapping, task, dataset, and normalized task-input roles; detailed columns/keys and operational-table reuse still need review. |
| Workflow shape and recovery | Approved | New Fabric-managed Apache Airflow job, smaller domain/workflow DAGs, metadata-authoritative readiness, events primary and reconciliation fallback. Deployment inputs and event transport remain open. |
| Candidate activation and incident rollback | Approved behavior | Candidate version before CI; activate after tests/deployment/Airflow recognition. Roll back technical health failures under defined rules; data-quality/clinical concerns need operator approval. |
| Strict schema drift policy | Approved | Block every ingestion-relevant contract difference, including nullable additions/type widening, pending review/approved revision; only the affected table stops. No allowlist or automatic contract/target evolution. |
| Discovery failure handling/recheck, SLA calendars, physical release mechanics, Airflow deployment inputs | Open | Finalize remaining mechanics without reopening Strict or Fabric-managed hosting. |
| Azure/Fabric targets and spend | Unconfirmed | No cloud provisioning. |

Existing approval covers local source preparation, not new infrastructure. The first
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

The November 20 follow-up sets the initial default parent-workflow start to **daily at
10:00 AM Eastern local time, observing daylight-saving changes**. This supersedes the
earlier ambiguous "Eastern Standard Time" wording; do not use fixed UTC-05:00 year-round.
The 11:00 AM availability deadline follows the same local time zone.
Discovery starts with the workflow; eligible ingestion follows
without another fixed start-time gate. Freshness limits and delivery deadlines remain
separate decisions. No running schedule has been created.

Synthetic data generation is a separate earlier activity: run it well before the daily
Fabric ingestion, targeting completed source preparation before 10:00 AM Eastern local
time. The normal sequence is **generate data -> finish source preparation -> run Fabric
ingestion**, not start generation at 10:00 AM or assume continuous synthetic writes
that ingestion must pause. Exact generator start time, completion/checkpoint evidence,
late/failed generation handling, and unintended-overlap protection remain under D05
review. This sequencing does not by itself prove a consistent extraction boundary or
approve a runtime checkpoint/pause implementation.

Synthea plus versioned mapping configuration is selected for source population.
Execution hosting is selected: **Azure Container Apps Jobs on Consumption**, with an
approximately $10/month generation planning target, not a fixed fee or enforced cap.
Synthea and executable mapping/loaders run externally, not on Fabric compute or
Airflow workers. Runtime sizing, durable storage, exact early schedule, triggering and
completion protocol remain open; host selection does not approve provisioning.
The approved demo profile, initial S0 evaluation baseline and cost assumptions are
recorded in the decision register.
A proposed execution shape is
generation -> durable exports/population state -> mapping/validation -> independently
controlled SQL loaders -> completion evidence -> normal Fabric ingestion. Export/state
storage and this exact execution/state protocol remain design proposals. Generation
parallelism must not automatically become the same number of simultaneous SQL writers.
Keep source generation separate from the 10:00 AM ingestion workload; whether the
existing Fabric Airflow job submits earlier generation work is a separate integration
choice, not a new hosting decision for Airflow.

November 20 follow-up: **Strict schema comparison** is selected. Any ingestion-relevant
contract difference, including new nullable columns and type widening, blocks fresh
extraction for that table pending review and approved revision or source correction.
Record/alert drift; do not advance its watermark or auto-change the contract/target.
Other tables continue. Canonical name-based comparison still treats physical column
order alone as an observation, not an ingestion-significant difference.

| Stage | Dependency boundary | Isolation |
| --- | --- | --- |
| Bronze | Its own source/schema/extraction authorization | No dependency on unrelated source tables. |
| Silver 1 | Its own required committed Bronze input | Healthy tables continue independently. |
| Silver 2 | All explicitly required upstream datasets | Gate joins on compatible committed versions and required freshness/coverage. |

Readiness is not physical table existence, a green notebook, or any historical row.
Evidence must identify producer run/attempt, committed Delta version, source checkpoint
or event-time coverage, and the consuming operation's requirements.

By default, failure of the latest expected upstream execution blocks its consumers
even if an older committed version is still within its freshness limit. Readiness
requires committed data, source currency, compatible processing-window coverage, and
the applicable latest-expected-execution outcome. Different source cadences remain valid;
how to identify the expected execution/window must be specified, not inferred from the
most recently completed successful run.

Persist `BLOCKED_BY_DEPENDENCY`, the missing/stale dependency reason, and a notification
when a consumer cannot run. This is not a failed transformation and must not fabricate
an executed function record. The current baseline status columns are not automatically
extended by this requirement; the persistence/state model remains under review.

## Freshness and Availability

Default freshness belongs to the logical `cfg.Dataset`; a consuming task can impose a
dependency-specific override through its `cfg.TaskInput`.
Different datasets need not share one ingestion cycle if their applicable requirements
are met. Use source coverage/checkpoints where available, not only completion time.
Keep desired policies in `cfg`; measured coverage, commits, and outcomes belong in `ops`.

The November 20 follow-up approves a **24-hour default freshness limit**, measured as
elapsed time since committed source coverage/checkpoint at dependency evaluation.
Coverage older than 24 hours blocks the consumer; age of exactly 24 hours is within
the limit. Do not substitute notebook completion time or the most recent row's
modification timestamp. Preserve the independent rule that the latest expected
upstream failure blocks even when older coverage is younger than 24 hours.

Dataset/consumer overrides remain supported, but no differing values are selected.
This freshness limit does not fix extraction-window boundaries, require each captured
batch to span exactly 24 hours, or choose an availability deadline.

Availability SLA is a separate business deadline for monitoring/reporting/alerting.
An SLA miss does not itself make useful late processing ineligible. Preserve the
original violation, actual availability time, and time to recovery.

The November 20 follow-up sets **11:00 AM Eastern daily** as the shared availability
deadline for required Bronze data and the initial Patient Silver output. With the
10:00 AM workflow start, the one-hour window includes discovery, source extraction,
staging checks, required Bronze publication/reconciliation and Patient Silver commit/
readiness. Do not equate notebook success with available data or declare the full
delivery met while a required table remains blocked.

The deadline is approved policy, but its achievability is unverified: source scale,
throughput, concurrency, startup and capacity contention are not yet benchmarked.
Measure representative full and normal incremental runs on approved resources,
including wait time and required validation, before claiming the one-hour target is
demonstrated. Do not silently relax the deadline or exclude slow required tables.
Missing it records/alerts the breach without canceling healthy work; recover as soon
as dependencies permit. Both times follow Eastern local time with daylight saving.

Availability calendar exceptions/holidays, override precedence, full-load/streaming
coverage, window alignment, and exact policy storage remain open. The default freshness
limit remains 24 elapsed hours, not a local calendar-day policy; verify coverage/window
behavior across daylight-saving transitions without silently relaxing that limit.

### Successful Zero-Change Runs and Future Volume Monitoring

The November 20 follow-up approves a successful incremental extraction with **zero
changed records** as a successful no-change run. Preserve existing data, record the
zero processed count, and require verified source-window/checkpoint coverage plus the
normal schema, validation and readiness checks. Zero rows alone do not prove coverage,
justify advancing a watermark, or bypass the latest-expected-failure rule. Retain the
existing committed data version and record no-change coverage evidence; the exact
SQL/Delta state protocol remains subject to D01/D05 review. Empty initial/full loads
and optional-input semantics are separate unresolved policies.

The user also selected future statistical monitoring of processed-record counts:

- **Upper Control Limit (UCL) = historical mean + 2 standard deviations.**
- **Lower Control Limit (LCL) = historical mean - 2 standard deviations.**

Implementation is deferred and is not required to accept a verified zero-change run.
Define the processed-record metric/grain, comparable baseline population, lookback,
minimum history, standard-deviation calculation, and handling of a negative LCL before
activation. Whether a breach only alerts or also changes run/readiness status remains
unapproved; do not silently make these limits a new failure/dependency gate.

## Automatic Recovery and Idempotency

When a dependency becomes ready, reevaluate and automatically dispatch eligible blocked
consumers promptly, without waiting for the next scheduled cycle. Do so after an SLA
miss as well; do not clear the historical violation after recovery.

Use durable state, atomic claims, and idempotent writes across discovery, Bronze,
Silver 1/2, generated releases, and recovery. A retry of the same captured Bronze batch
must not append it twice; distinct batches retain repeated business observations.
SQL state and Delta commits are not a distributed transaction.

Event-driven readiness notification is primary, with periodic reconciliation as a
fallback for lost/missed events. Every dispatch reevaluates **all** dependencies;
an event is a wakeup, never permission to execute. The metadata plane authoritatively
evaluates readiness and initiates eligible downstream runs; Airflow schedules/executes.

Stable logical operation IDs distinguish intended work from attempt IDs. Central
framework/notebook code owns claims, persistence, idempotent writes, and recoverable
commit tracking. Transformation functions remain deterministic and side-effect-free
where practical. Reconcile a Delta commit that succeeds before SQL confirmation;
do not rerun effects blindly.

Event transport/outbox, claims/leases, the recovery queue, retry/backoff, cross-DAG
trigger mechanics, reprocessing/window ordering, and notification routes remain open.
"Immediate" is a dispatch requirement, not a chosen event-bus technology or zero-latency
guarantee.

## Macro Order versus Micro Order

The agreed direction is Airflow for task/dataset dependencies, with authoritative
definitions/readiness in Fabric SQL. Inside a task, a generic PySpark notebook resolves
registered utility functions and applies them in order using `DataFrame.transform()`.
Business functions take/return DataFrames and contain no framework logging or I/O.

The ordered function list is not the graph of upstream datasets. The approved target
stores a task's ordered function sequence in **one JSON array/configuration column**,
including validated per-function parameters. Reconcile auxiliary inputs, repeated
functions, step-level validation/profiling, and legacy step FKs before retiring the
baseline `cfg.TransformationStep`. Physical JSON shape and step identity need design.

Use multiple smaller Airflow DAGs by logical workflow/domain, not one monolithic DAG.
Generic notebooks by processing stage are the default, with justified specialized
notebooks allowed. The November 20 follow-up selects a **new Fabric-managed Apache
Airflow job for this project**, not an existing instance or a self-managed deployment.
Workspace/item/capacity assignment, ownership, connectivity, sizing, exact grouping
boundaries, dynamic task mapping and integration details remain to be finalized.
No environment has been provisioned.

Official Fabric item terminology: **Apache Airflow job**.
Reference: `https://learn.microsoft.com/en-us/fabric/data-factory/create-apache-airflow-jobs`.

## Execution Configuration and Access

Support framework defaults, stage defaults, and per-task overrides; finalize field-level
resolution, validation, and null semantics in the revised schema. Keep Airflow
retry/timeout policy separate from Spark/Fabric runtime settings.

Logical notebook, Fabric environment, and compute-profile references resolve to
deployment-specific resources. Environment selection and compute sizing are separate;
a Fabric environment is not a dedicated compute pool. Use distinct stage-oriented
environments, task-level exceptions, and right-sizing. Exact resource maps, runtime
versions, startup-only settings, and exception limits remain design/deployment inputs.

Airflow reads immutable orchestration snapshots with read-only permissions. Spark and
framework components write execution/readiness state through tightly scoped interfaces;
they do not receive unrestricted authoritative-configuration writes. Preserve
dev/QA/prod isolation while logical dataset identities remain stable across environments.

## Configuration Publication and DAG Releases

Required human/governance approvals happen before configuration is published into the
authoritative metadata plane. Successful publication automatically initiates generation
and deployment; there is no second manual configuration-release approval gate.
This does not waive initial design, environment, identity, or infrastructure approvals.

Assign a traceable candidate semantic version before CI/CD testing. Process approved
releases sequentially. Every release uses its own complete immutable
configuration snapshot and corresponding code revision; never patch from the preceding
generated DAG artifact. Validate missing references, cycles, function registrations,
task definitions, resource maps, and artifacts before activation. Activate only after
required tests, deployment, and Airflow recognition/parsing checks succeed. New
executions use the latest successfully activated revision.

The framework release and corresponding DAG artifact release use the same semantic
version. Track snapshot hash, code revision, artifact hash, deployment outcome, active
pointer, and execution IDs separately. Publication is not activation: a failed version
has history/evidence but is not reported as successfully deployed.

Keep the last known good active deployment on generation/deployment failure. Record and
alert the failure, then allow the next approved queued version to proceed. For example
only: active `1.1.0`, failed `1.1.1`, active `1.2.0`; fix on top as `1.2.1` rather than
automatically deploying an older repaired version over a newer active release.
No actual release numbers or deployment states are assigned by these examples.

In-flight executions retain their starting version/snapshot/code. The mechanism to
retain/import those artifacts and safely activate a newer deployment still needs review.
Immutable generation artifacts rather than live SQL queries during every scheduler
parse are the supported direction, not an implemented mechanism.

### Failed Candidate versus Post-Activation Incident

A failed candidate must not replace the active revision; later valid snapshots may
still proceed. This is different from an incident in a version already activated.
For example only, if active `1.3.0` is defective, reactivate last known good `1.2.3`
for **new** executions, then validate/activate fix-forward `1.3.1`.

Automatic rollback is approved for clearly defined deployment/technical-health
failures; suspected data-quality/clinical issues require operator approval. Define
signals, thresholds, authorization, compatibility, and audit evidence before enabling
either path. Rollback reactivates immutable known-good code/configuration; it does not
repair/rewrite older releases, reverse Delta data changes, or silently cancel in-flight
runs. Emergency cancellation and any data remediation need explicit procedures.

The earlier prohibition on automatically deploying a repaired obsolete failed release
does not prohibit this deliberate, auditable incident rollback.

## Baseline Metadata Assessment

The existing ERDs remain a **17-table baseline**, not a complete approved model for the
new requirements. They already cover source/pipeline/step configuration, runs, table
attempts, watermarks/leases, checks/errors, profiling, diagnostics, and alerts.

| Required capability | Baseline coverage / unresolved gap |
| --- | --- |
| Dataset/consumer policy | Approved logical `Dataset` plus normalized `TaskInput`; dataset defaults and per-input overrides need physical design. |
| Executable task versus mapping | Retain `PipelineObject` as mapping; add logical `ProcessingTask`, optional mapping FK, mandatory lineage, primary output, ordered JSON sequence, and task overrides. |
| Pipeline/stage configuration | Remove `PipelineDefinition.InputLayer/OutputLayer` in the revision; infer movement from dataset inputs/output and retain shared configuration/default policy. |
| Committed readiness | `IngestionTableRun.TargetVersion` and checkpoints are partial evidence; compatible multi-producer coverage/readiness needs a design. |
| Blocked work and wakeup | Existing failure/run records are not a reviewed blocked-task or durable dispatch queue. |
| Freshness versus SLA | Existing policy JSON/alerts are candidates; policy and independent measurements need review. |
| Release manifest and publication | Configuration revisions/run snapshots do not supply a reviewed semver publication manifest. |
| Sequential deployment and active pointer | No reviewed release queue, activation pointer, or deployment-attempt history exists. |
| Ordered functions | JSON array is approved; reconcile legacy step references, parameters, auxiliary inputs, validation, and profiling before removal. |

Derive graph edges from `TaskInput` and dataset producers when unambiguous. Limit
explicit relational `TaskDependency` edges to ordering that cannot be inferred. Validate
cycles, missing inputs, and ambiguous producers within the applicable release/window.
Avoid lookup tables for trivial attributes; preserve normalization where it adds integrity.

Separate task-attempt history from current dataset readiness. Reuse operational tables
only where their grain and meaning fit; `ops.TaskExecution` versus adapting ingestion
history, readiness storage, and release/event schemas remain physical design questions.
`docs\ingestion\task-dataset-design.md` and the separate `09-task-dataset-logical`
diagram show the revision without pretending the baseline ERDs were migrated.

## Review Diagrams and Acceptance Requirements

- `data-models\framework\06-orchestration.mmd` / `.svg`: isolation, readiness, and recovery.
- `data-models\framework\07-release-lifecycle.mmd` / `.svg`: publication through activation.
- `data-models\framework\08-transformation-order.mmd` / `.svg`: task versus function order.
- `data-models\framework\09-task-dataset-logical.mmd` / `.svg`: approved logical revision, not physical column/FK definitions.
- Existing `00-overview` and `05-full-schema` remain the baseline relationships/columns.

Later acceptance must prove table isolation, committed/fresh dependency gating,
blocked-not-failed reporting, recovery after missed deadlines without clearing SLA
evidence, duplicate-dispatch/write protection, one discovery pass, invalid release
rejection, sequential releases, failure followed by newer activation, last-good
preservation, latest-expected failure blocking despite a recent historical success,
event loss/duplication with full readiness recheck, activation/Airflow recognition,
audited technical versus operator-authorized rollback, and pinned in-flight execution.
Do not implement these tests against invented runtime schemas before their review.

**Primary references:** `https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html`
and `https://semver.org/`. These support engineering research; the discussion record
defines this project's approvals. No Airflow/runtime version is pinned yet.

Availability feasibility references:
`https://learn.microsoft.com/en-us/fabric/data-engineering/spark-job-concurrency-and-queueing`
and `https://learn.microsoft.com/en-us/fabric/data-factory/copy-activity-performance-and-scalability-guide`.
