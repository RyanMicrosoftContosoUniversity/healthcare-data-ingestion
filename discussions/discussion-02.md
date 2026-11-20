Healthcare Data Ingestion Framework — Consolidated Architecture Decision Record

Date: November 20, 2026
Repository: https://github.com/RyanMicrosoftContosoUniversity/healthcare-data-ingestion
Status: Discussion decisions approved in conversation; implementation/schema changes not yet applied.

Scope and reference baseline

This record consolidates the November 19–20 architecture conversations and compares the intended design with the repository’s documented baseline. Relevant existing documentation:

• docs/architecture/orchestration-design.md
• docs/ingestion/metadata-design.md

The repository’s metadata baseline describes cfg.PipelineDefinition, cfg.PipelineObject, cfg.TransformationStep, ops.IngestionRun, ops.IngestionTableRun, and other state/telemetry tables. The proposals below are not claims that those changes are implemented.

Approved architectural decisions

1. Ingestion and medallion execution

• Phase one supports scheduled batch ingestion from Epic Clarity and Caboodle. The architecture remains extensible to additional databases and real-time/streaming sources.
• Schema discovery/validation precedes batch ingestion; streaming validation may occur at startup or schema changes rather than on every event.
• Schema drift blocks the affected table, not unrelated Bronze ingestion.
• Independent Bronze and Silver 1 processing continues when another table fails; Silver 2 joins wait for all required inputs.
• Distinguish source/table existence from committed, eligible data. Blocked dependencies are not classified as transformation failures.
• Different upstream datasets can have different refresh schedules and freshness limits.

2. Freshness, deadlines and readiness

• Freshness requirements and delivery/availability SLAs are separate policies.
• Default freshness belongs to the logical dataset, with optional per-consuming-task input overrides.
• Evaluate freshness using appropriate source data currency/watermark evidence, not just job completion time.
• A failed latest expected upstream execution blocks downstream work by default, even when an older committed version remains within its age threshold.
• Successful task completion alone is insufficient: the required data must be committed, fresh, and compatible with any required processing window.
• A missed SLA does not prevent late execution; run as soon as dependencies recover.

3. Orchestration and transformation functions

• Airflow orchestrates processing tasks and inter-dataset dependencies; PySpark handles ordered transformations inside a task.
• Transformation functions are registered, reusable DataFrame-to-DataFrame functions applied in the configured order (e.g., using DataFrame.transform()).
• Store each task’s ordered function sequence as a single JSON array/configuration column, including validated per-function parameters where needed.
• One configuration record per independently executable processing task.
• Generic notebooks by processing stage are the default; specialized notebooks are permitted when justified.
• Multiple smaller Airflow DAGs organized by logical workflow/domain, not one monolithic framework DAG.
• Cross-DAG coordination is hybrid: Airflow executes/schedules; the metadata control plane authoritatively evaluates readiness and initiates eligible downstream runs.

4. Metadata model

• Preserve a normalized model where it adds integrity, particularly many-to-many relationships; avoid separate lookup tables for trivial attributes.
• Keep cfg.PipelineObject as a source-to-target mapping, separate from a proposed cfg.ProcessingTask for executable work.
• ProcessingTask.PipelineObjectID is optional; lineage and input/output identification remain mandatory.
• Introduce a logical cfg.Dataset registry for Bronze, Silver 1, Silver 2, and Gold, with stable logical identifiers across dev/QA/prod.
• Introduce normalized cfg.TaskInput records, one per consumed dataset, referencing Dataset rather than physical Fabric table IDs.
• Record the primary output dataset on ProcessingTask.
• Derive task graph edges from task inputs and dataset producers whenever unambiguous; reserve explicit task dependencies for exceptional ordering constraints.
• Preserve explicit relational dependency records where necessary and validate the resulting graph for cycles, missing inputs, and ambiguous producers.
• Remove InputLayer/OutputLayer from cfg.PipelineDefinition in the proposed revision; infer data movement from task inputs and output dataset.
• Keep PipelineDefinition focused on shared pipeline/stage configuration and a default execution policy, with optional task overrides.
• Reconcile the existing cfg.TransformationStep one-row-per-function baseline with the approved ordered-array model before deleting anything; preserve parameters, auxiliary inputs, validation, and profiling needs.
• Keep task execution history separate from current dataset readiness. Reuse existing operational tables when their grain and semantics fit.

5. Execution and Fabric resources

• Support framework defaults, stage defaults, and task-specific overrides.
• Distinguish Airflow retry/timeout settings from Spark/Fabric runtime configuration.
• Separate Fabric environment selection from compute-sizing/profile decisions.
• Use logical notebook, environment, and compute references resolved to deployment-specific resources.
• Use distinct stage-oriented Fabric environments, with task-level exceptions and right-sizing; a Fabric environment is not itself a dedicated compute pool.
• A wider task configuration table is acceptable for per-task overrides; normalize shared policies only when useful.

6. Automatic recovery and idempotency

• When an upstream dataset becomes ready, reevaluate blocked downstream work and execute immediately, including after a missed deadline.
• Event-driven readiness notifications are primary; periodic reconciliation is a fallback for missed events.
• Recheck all dependencies before dispatch; events alone do not authorize execution.
• Centralize idempotency in the framework: stable logical operation IDs, distinct attempt IDs, concurrency controls, idempotent writes, and recoverable commit tracking.
• Individual transformation functions should be deterministic and side-effect-free where practical; generic notebook/framework controls persistence.
• Delta commits and Fabric SQL metadata updates are not a shared atomic transaction; design reconciliation for commits that succeed before metadata confirmation.

7. Governance, releases, CI/CD and rollback

• Required human review/approval occurs before configuration enters authoritative published metadata tables.
• Approved publication automatically initiates technical validation, DAG generation and deployment; no redundant manual approval gate.
• Immutable complete configuration snapshot per release; corresponding versioned DAG artifact(s) with a one-to-one release mapping.
• Use semantic versioning; queue release builds sequentially. A failed older release may be superseded by a newer independently valid snapshot.
• Preserve failed releases in history; normally fix forward in a new patch of the latest line rather than retroactively changing an old release.
• Assign a traceable candidate version before CI/CD testing; only activate the version after all required tests, deployment and Airflow recognition checks pass.
• New executions use the latest successfully activated version; in-flight executions retain their original version and configuration.
• Production incident example: if 1.3.0 fails after activation, reactivate last known good 1.2.3 for new executions; develop 1.3.1, validate through CI/CD, then activate it.
• Rollback of framework code/configuration does not itself reverse Delta data changes.
• Automatic rollback for clearly defined deployment/technical health failures; operator approval for suspected data-quality/clinical issues.
• Keep rollback and release transitions auditable; avoid silently canceling in-flight runs except through an explicit emergency mechanism.

8. Access and security

• Airflow receives read-only access to immutable configuration snapshots needed for orchestration.
• Spark/framework components write readiness and execution state through tightly scoped permissions, ideally via controlled interfaces; avoid unrestricted writes to configuration.
• Preserve deployment environment isolation and logical-to-physical resource mapping.

Proposed logical entities and relationships

|Entity                                                |Responsibility                                                             |Status                        |
|------------------------------------------------------|---------------------------------------------------------------------------|------------------------------|
|`cfg.PipelineDefinition`                              |Shared pipeline/stage configuration and default execution policy           |Existing; revise              |
|`cfg.PipelineObject`                                  |Source-to-target mapping                                                   |Existing; retain              |
|`cfg.ProcessingTask`                                  |Independently executable operation; notebook, transforms, output, overrides|Proposed                      |
|`cfg.Dataset`                                         |Logical Bronze/Silver/Gold dataset registry                                |Proposed                      |
|`cfg.TaskInput`                                       |Task-to-input dataset edges, alias, required flag, freshness override      |Proposed                      |
|`cfg.TaskDependency`                                  |Explicit non-inferable task ordering edges                                 |Proposed, limited use         |
|`ops.TaskExecution` or adapted `ops.IngestionTableRun`|Attempt history, framework version, outcome                                |Reconcile existing grain      |
|`ops.DatasetReadiness`                                |Current committed evidence, watermark, eligibility                         |Proposed logical role         |
|Release manifest/snapshot/activation state            |Immutable version graph, artifact mapping, status and active pointer       |Proposed; physical design open|

Remaining implementation design and reconciliation tasks

1. Compare proposed logical entities to the repository’s actual DDL and 17-table baseline; avoid duplicate tables and preserve existing ingestion-specific state.
2. Define exact columns, keys, unique constraints, indexes, immutable-snapshot foreign keys, and the effective configuration resolution order.
3. Resolve the existing cfg.TransformationStep table’s profiling and per-step parameter needs when adopting a JSON array.
4. Define how to identify one authoritative producer per dataset per applicable release/window and when explicit dependencies are necessary.
5. Define freshness source-watermark semantics for full loads, incremental loads, and streams, plus compatible-window rules.
6. Define operational status transitions (BLOCKED_BY_DEPENDENCY, stale, failed, ready), retry/attempt grain, and transactional outbox or equivalent reliable event delivery.
7. Specify the Delta commit reconciliation protocol, lock scope, replay keys, and safeguards against older windows overwriting newer data.
8. Specify Fabric environment/compute mapping and which settings can be applied before Spark session startup.
9. Implement DAG build-time checks, activation gate, rollback authorization rules, audit trail, and emergency cancellation.
10. Reconcile prior approved Bronze row metadata, schema discovery and Patient Silver contracts rather than silently superseding them.

Example end-to-end workflow

1. Publish reviewed framework release 1.3.0 and immutable snapshot.
2. CI/CD validates tasks, function registry, datasets, graph, resource mappings and generated DAGs; deploys and verifies Airflow parsing.
3. Activate 1.3.0. New tasks bind to it; older in-flight runs retain their original versions.
4. Patient and Encounter independently ingest to Bronze and transform to Silver 1.
5. If Encounter’s latest expected run fails, Patient continues independently; PatientEncounter Silver 2 is blocked, with reason recorded.
6. Encounter retry commits safely; operational readiness updates and an event triggers reevaluation.
7. All dependencies pass commit/freshness/window checks; Silver 2 executes immediately, even after its deadline, under a stable idempotency key.
8. A duplicate event cannot duplicate output; periodic reconciliation repairs missing notifications.
9. If a production defect is detected, restore the last known good active release for new runs and fix forward with a validated patch.

Change control

This is a discussion record, not a database migration or a claim that CI/CD, DAG generation, or recovery automation is deployed. No GitHub repository files were changed in preparing this record.