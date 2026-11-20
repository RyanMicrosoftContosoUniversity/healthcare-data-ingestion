# Processing Tasks and Datasets: Metadata Revision

**Status: logical direction approved in `discussions\discussion-02.md`;
physical schemas and runtime implementation remain under review.**

This supersedes conflicting task/step proposals in the original 17-table dictionary.
It is a revision specification, not DDL, a migration, or a claim that new tables exist.
The original dictionaries and `00`-`05` ERDs remain labeled baseline review artifacts.

## Approved Logical Responsibilities

| Entity / role | Responsibility and relationships |
| --- | --- |
| `cfg.PipelineDefinition` | Shared pipeline/stage configuration and default execution policy. Remove baseline `InputLayer`/`OutputLayer` in the revision; infer movement from task inputs/output. |
| `cfg.PipelineObject` | Retained source-to-target mapping, not the unit of arbitrary executable work. Preserve source extraction/watermark identity. |
| `cfg.ProcessingTask` | One record per independently executable operation. Optional `PipelineObjectID`, mandatory input/output identification and lineage, primary output dataset, logical notebook/environment/compute references, ordered function JSON, and task overrides. |
| `cfg.Dataset` | Logical Bronze, Silver 1, Silver 2, or Gold dataset identity, stable across dev/QA/prod; default freshness and environment-specific physical resolution. Gold registration is future-compatible design, not approval to build Gold. |
| `cfg.TaskInput` | Normalized task-to-dataset consumption edge; input alias, required flag, and optional consumer freshness override. Reference logical datasets, not physical Fabric table IDs. |
| `cfg.TaskDependency` | Explicit relational ordering only where producer/input derivation cannot express the requirement. Do not duplicate every inferred edge. |
| Task execution history | Stable logical operation identity and distinct attempts, release/snapshot, outcome, and commit evidence. Reuse/adapt existing tables only when their grain fits. |
| Current dataset readiness | Current committed version, source currency/checkpoint, window compatibility, latest expected outcome, and eligibility; separate from historical task attempts. |
| Release/snapshot/activation roles | Candidate semver, immutable complete snapshot, code/artifact mapping, CI/deployment/recognition outcomes, active pointer, rollback audit. Physical tables remain to be designed. |

Normalize many-to-many consumption/dependency relationships where that adds integrity.
Do not introduce a separate lookup table for every trivial attribute.

## Graph and Readiness

Derive producer-to-consumer task edges through datasets where unambiguous. Define the
authoritative producer per dataset for the applicable release/window and reject missing
or ambiguous producers, unresolved required inputs, and cycles, including cycles formed
by explicit ordering edges. Multiple smaller domain/workflow DAGs share this authoritative
graph; cross-DAG events do not become a second source of dependency truth.

Tasks without an ingestion mapping still require explicit lineage and input/output
identification. Source extraction identifies its SQL source through the retained
mapping/source contract; it must not invent a physical Fabric ID as a logical dataset.
Exact treatment of metadata-only tasks and multiple outputs needs physical design.

Consumer readiness requires committed compatible data, appropriate source-currency
evidence, freshness, and required processing-window coverage. Failure of the latest
expected upstream execution blocks by default even if an older success remains recent.
Different cadences do not imply one global ingestion-cycle identifier.

`BLOCKED_BY_DEPENDENCY` records waiting and its reason, not a transformation failure.
A missed availability SLA does not block useful late execution. A successful incremental
run with zero changed records counts as successful when source-window coverage and
normal validation/readiness checks are verified. Preserve existing data; a zero count
alone does not establish coverage or justify advancing a watermark. The exact no-change
state protocol, empty initial/full-load acceptance and optional-input behavior remain
under review. Future processed-record UCL/LCL monitoring (historical mean plus/minus
two standard deviations) is deferred; no breach-based readiness gate is approved.

## Ordered Function Array and Baseline Reconciliation

The storage choice is now settled: **one ordered JSON array/configuration column per
task**, with registered function identifiers and validated per-function parameters.
Do not ask again whether to use one normalized row per function as the target model.

Before removing the baseline `cfg.TransformationStep`, design and review:

| Baseline concern | Requirement in the revision |
| --- | --- |
| `StepOrdinal` and repeated functions | Preserve explicit array order and distinguish repeated occurrences. |
| `RegistryFunctionName`, `ParametersJson` | Keep registered callables and parameter-schema validation; never permit arbitrary executable code/imports. |
| `ReferenceInputsJson` | Preserve auxiliary input aliases, dependency registration, and frozen snapshot/version rules; no hidden untracked reads. |
| Step input/output validation | Validate the entire sequence and evolving schemas before publication. |
| `ops.IngestionTransformationRun.TransformationStepID` | Preserve historical profiling attribution and define release/task/step occurrence identity before changing the FK. |
| Existing error/run correlation | Keep accurate task/attempt/step evidence without pretending JSON references are SQL FKs. |
| Historical configurations | Retain immutable snapshots and do not rewrite old benchmark or execution history. |

The exact JSON field names/schema, stable step identifiers, and physical FK migration
are not chosen here. No `TransformationStep` table has been implemented or deleted.
The original diagram's step edges remain baseline, not the target storage model.

## Execution Configuration

Framework defaults, stage defaults, and task overrides are supported. Shared pipeline
policy remains available; resolve its interaction with existing domain/run/profiling
settings field by field. Publish the exact precedence, allowed overrides, validation,
and null semantics rather than carrying forward the old precedence as complete.

Keep scheduler retries/timeouts separate from Spark/Fabric session/runtime settings.
Use logical notebook, environment, and compute-profile references; resolve physical
resources per deployment. Stage-specific environments have task exceptions and do not
themselves represent dedicated compute pools. Decide which settings must be established
before session startup. A wider task record is acceptable; normalize shared policies
only where useful.

## Operational State, Events, and Access

Evaluate `ops.IngestionRun`, `ops.IngestionTableRun`, `ops.IngestionWatermark`, and
profiling/diagnostic history against the new task grain before proposing parallel
tables. An ingestion table attempt is not automatically suitable for a join with no
source mapping. Keep ingestion batch/watermark lineage and the accepted Bronze row
contract intact when adding general task operation/attempt identities.

Readiness changes emit reliable events; periodic reconciliation repairs missed
notifications. The metadata plane reevaluates every dependency before dispatch and
initiates eligible runs. Stable operation IDs, distinct attempts, concurrency control,
idempotent writes, and recoverable SQL/Delta commit tracking are central framework work.
Define event delivery/outbox, lease scope, replay keys, duplicate-event handling, and
protection against older windows overwriting newer results before implementing them.

Airflow reads immutable orchestration snapshots. Scoped framework/Spark interfaces
write readiness/history; configuration publication belongs to authorized deployment
roles, not unrestricted task identities. Preserve environment isolation.

## Physical Design Still Required

Produce revised dictionaries with exact columns/types/nullability, keys/uniqueness,
indexes, snapshot/release FKs, and state-transition routines. Reconcile operational
reuse, dataset producers/windows, array-step attribution, override precedence,
reliable events, activation/pinning/rollback, and deployment resource maps together.
Review the resulting complete physical model before migrations, runtime code, or the
28 source configuration records. Do not label the revision as a finalized table count.

The separate `data-models\framework\09-task-dataset-logical.mmd` / `.svg` illustrates
logical roles and associations only. See `docs\architecture\build-decisions.md` for
remaining user choices versus engineering design deliverables.
