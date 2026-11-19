Healthcare Data Ingestion Framework — Architecture Discussion Record

Date: November 19, 2026
Repository: https://github.com/RyanMicrosoftContosoUniversity/healthcare-data-ingestion
Purpose: Reconcile approved design direction against repository documents, diagrams, metadata schemas, orchestration and implementation.
Scope: Discussion record only; no repository changes performed.

Status conventions

• Approved in discussion: User explicitly agreed or directed the design.
• Agreed in principle: Direction supported; implementation details remain open.
• Recommended / not yet approved: Assistant proposal requiring further decision.
• Existing repository decision: Previously documented approval, not newly decided today.

1. Existing repository decisions carried forward

• Bronze append-only (existing): preserve raw source observations and repeated keys across distinct captured batches; Silver owns deduplication and merges. Publishing the same captured batch twice must be prevented.
• Bronze technical metadata (existing): _ingest_batch_id, _ingest_run_id, _ingest_table_run_id, _ingest_source_name, _ingest_extracted_at_utc, _ingest_landed_at_utc, _ingest_capture_mode, optional _ingest_row_hash. Human-readable source name was explicitly chosen over numeric source-object ID per row.
• Control plane (existing): Fabric SQL Database in a dedicated metadata workspace, separate from the data/ingestion workspace. The existing 17-table model remains proposed and is not blanket-approved.
• Schema discovery (existing requirement): compare source schema to approved contracts before fresh extraction; detailed drift policy and implementation still require review.

2. Schema discovery and batch orchestration

Agreed in principle:

• Phase 1 supports scheduled batch ingestion of simulated Epic Clarity and Caboodle sources. The framework should be extensible to additional databases and potentially streaming sources later, without requiring all sources to use the same execution engine.
• Favor a dependency-driven orchestration: schedule a parent workflow, perform source schema discovery, then start eligible ingestion promptly when discovery completes; do not enforce an arbitrary fixed 4 a.m. ingestion start.
• Optimize for data availability by downstream business-use deadlines, rather than fixed ingestion start times.
• Avoid duplicate full source-schema discovery passes across ~1,000 tables; the user explicitly objected to scanning/querying the source twice per cycle.
• Keep the schema-validation capability logically reusable, not permanently tied to batch-only processing.
• Validate staged/extracted schema before Bronze publication as an independent safeguard.
• Table-level isolation: schema drift or unavailability for one table blocks that table, not unrelated Bronze tables.

Still open:

• Precise discovery scheduling, concurrency, timeout and failure policy.
• Whether to perform any additional lightweight live-source recheck; this was discussed but not approved. A single discovery pass minimizes duplicate checks but leaves a possible time-of-check/time-of-use gap.
• Exact drift policy for additions, widening, missing columns, incompatible types, and contract promotion.
• Source-consistency guarantees under concurrent source DDL and writes.
• How future streaming sources validate schema and maintain checkpoints.

3. Processing layers and failure isolation

Approved in discussion:

• Bronze: each source table ingests independently, with no cross-table dependency requirement.
• Silver 1: independent per-table operations (validation, normalization, deduplication, other transformations) continue for a healthy table even when another table fails.
• Silver 2: cross-table transformations/joins execute only when all required upstream datasets are ready.
• Readiness means required data is successfully processed and persisted/committed, not merely that a physical table exists.
• A downstream operation waiting on an upstream dataset is BLOCKED_BY_DEPENDENCY, not a failed transformation. Persist the reason and generate notification.
• Existing historical data is not automatically sufficient: readiness must account for required data coverage/freshness.
• An upstream successful run producing legitimately zero rows should not automatically be considered a failure (assistant implementation recommendation; confirm during detailed design).

Design implications:

• Record producer execution IDs, committed Delta versions, checkpoints/coverage, and downstream dependency readiness.
• Represent required upstream datasets explicitly; ensure joins consume a compatible set of committed versions.

4. Freshness versus availability SLA

Approved in discussion:

• Define per-dataset freshness policies in configuration; a downstream consumer may impose a stricter dependency-specific requirement.
• Define availability deadlines / SLAs separately from freshness.
• Freshness controls whether a dependency is eligible for downstream processing.
• Availability SLA governs deadline monitoring, reporting and alerting; missing an SLA does not automatically prohibit useful processing.
• Keep desired policy in cfg and observed processing/checkpoint/commit state in ops.
• Do not require unrelated sources with different refresh cadences to share one ingestion cycle if they meet their applicable readiness/freshness requirements.
• Freshness should reflect actual source checkpoint or event-time coverage where available, not just notebook completion time.

Open implementation choices: duration versus schedule/calendar semantics; time zones and holidays; policy override precedence; how to represent freshness for full loads and streaming sources; whether existing cfg.PipelineObject / policy JSON is sufficient.

5. Automatic recovery and idempotency

Approved in discussion:

• When a missing dependency becomes ready, automatically reevaluate and dispatch the previously blocked downstream transformation immediately, rather than waiting for the next scheduled cycle.
• If the original SLA was already missed, still process as soon as possible. Preserve the SLA violation and measure time to recovery. Rationale: restore part of the business day rather than lose the whole day.
• The end-to-end framework must be idempotent across discovery, Bronze batch publication, Silver processing, downstream joins and recovery.
• Prevent duplicate execution effects with durable state, atomic claims/concurrency control and idempotent writes.
• Bronze idempotency is per captured batch, not deduplication of identical business rows across different batches.

Open implementation choices: event/outbox versus polling, claim/lease details, recovery queue, retry/backoff, exactly-once publication protocol, reprocessing scope and notification channels.

6. Transformation functions and workflow dependencies

User-directed architecture, agreed in principle:

• Use generic PySpark notebooks with ordered, registered transformation functions from version-controlled Python utility modules.
• Each function takes and returns a DataFrame; execute in configured order using DataFrame.transform() within a loop.
• User envisions an ordered array of transformation identifiers in a configuration record; in Fabric SQL Database, a validated JSON array is one possible representation.
• Airflow owns task-to-task / dataset dependency orchestration (macro order).
• PySpark owns function order inside a processing task (micro order).
• Fabric SQL metadata owns authoritative dependency definitions and readiness state.
• Distinguish an ordered list of functions from a graph of required upstream datasets.

Reconciliation note: repository currently proposes cfg.TransformationStep as an ordered registry. Do not silently replace it with a JSON array until the user chooses between normalized step rows and an array stored in one record. The user described an array preference; exact schema is not finalized.

7. Metadata-driven Airflow DAG generation

Approved in discussion:

• The Fabric SQL metadata plane is the single source of truth for workflow definitions and dependencies; avoid separately hand-maintained Airflow dependency graphs.
• A generator reads approved metadata and automatically generates corresponding Airflow DAGs.
• Governance and required personnel approvals happen before configuration enters authoritative tables.
• Successful publication of approved configuration automatically triggers DAG generation and deployment; there is no second manual approval gate.
• Technical integrity checks still apply (cycles, missing references, unknown transformation registrations, invalid task definitions).
• Track approved configuration publication separately from successful DAG deployment; a published revision is not necessarily active.
• Prefer immutable, versioned snapshots/artifacts rather than querying live SQL on every Airflow scheduler parse (assistant recommendation supported in discussion).
• Preserve the last known good active deployment if generation/deployment fails; log and alert.

Open implementation choices: number/granularity of DAGs; publication trigger/outbox mechanism; DAG artifact storage and promotion; Airflow/Fabric integration; cross-DAG recovery; how task graph generation relates to dynamic task mapping.

8. Semantic versioning, release queue and failure handling

Approved in discussion:

• Every effective framework release has a corresponding DAG library/artifact release with the same semantic version, e.g. 1.1.1 ↔ 1.1.1, 1.2.0 ↔ 1.2.0.
• Generate/process releases sequentially, so a newer approved release queues while the prior release is still being generated/deployed.
• Each release is built from its own complete immutable configuration snapshot, not as a patch applied to previously generated DAG artifacts.
• Failed releases do not block newer approved releases: record failure and allow subsequent releases to proceed.
• Example: 1.1.0 active → 1.1.1 fails → 1.2.0 successfully deploys.
• Normally fix an issue from the failed older release on top of the latest active version, e.g. 1.2.1, rather than deploying repaired 1.1.1 after 1.2.0.
• Keep historical failed releases and diagnostic records; allow deliberate investigation/retry where worthwhile, but never automatically roll active deployment backward.
• Distinguish framework/DAG release version, configuration snapshot, code/artifact hash, active release, and individual execution IDs.
• Existing running executions should retain their pinned configuration/code revision rather than unexpectedly switching mid-run (assistant recommendation accepted in principle; verify execution-isolation mechanics).

Clarification: “One-to-one” means each framework release has a corresponding versioned DAG release record/artifact relationship; a failed release may not produce a successfully deployed DAG. Do not misreport a failed version as deployed.

9. Suggested control-plane additions / revisions (NOT yet approved)

Evaluate existing 17-table schema before introducing new tables:

• Approved configuration release manifest: semver, immutable snapshot/hash, code commit, DAG artifact/hash, created/approved/published times.
• Release deployment queue/state: QUEUED, GENERATING, VALIDATING, DEPLOYING, ACTIVE, FAILED, SUPERSEDED, with retry history.
• Active release pointer with concurrency-safe updates.
• Dataset dependency edges: producer output identity, consumer task, required readiness/coverage, freshness override.
• Dataset state: latest committed Delta version, checkpoint/coverage, success status, run/attempt lineage.
• Blocked task state and reevaluation/dispatch queue.
• Freshness policy and availability SLA policy, with independent actual measurements.
• Transformation registry and ordered step configuration, reconciled with cfg.TransformationStep.
• Notifications and audit trail for drift, dependency blocking, SLA violations, recovery and release failures.

10. Reconciliation checklist for repository/design diagrams

1. docs/ingestion/metadata-design.md: retain previously accepted Bronze/control-store decisions; mark discussion approvals; reconcile cfg/ops design with readiness, freshness, SLA, DAG generation and versioning.
2. docs/ingestion/schema-discovery-design.md: revisit original mandatory centralized discovery + per-table source recheck. Reflect the discussed one-pass, discovery-before-ingestion direction, but leave exact recheck and drift policy open.
3. Airflow/orchestration diagrams: parent discovery → eligible Bronze → independent Silver 1 → dependency-gated Silver 2; blocked-task recovery; generator/publisher flow.
4. Transformation diagrams: metadata-selected ordered function chain using DataFrame.transform(), distinct from DAG dependency graph.
5. Control-plane ERDs: explicit dataset dependency/readiness state, policy-versus-observation separation, release-to-DAG mapping and deployment statuses; assess whether 17 existing tables suffice.
6. Release diagrams: approved config publication → event/queue → sequential DAG generation/validation/deployment → active pointer; failed releases can be superseded by later releases.
7. Operational diagrams: per-table isolation, stale-data checks, BLOCKED_BY_DEPENDENCY, immediate recovery dispatch, immutable SLA violation and end-to-end idempotency.
8. Future-proofing: batch implemented in Phase 1; control-plane abstractions permit other source types and streaming later.

11. Decisions intentionally deferred

• Precise schema drift tolerance and behavior.
• Whether a second source-catalog recheck is justified; handling time-of-check/time-of-use.
• Detailed metadata table/column schemas and relationship model.
• DAG generation granularity and runtime dynamic mapping strategy.
• Airflow trigger and cross-run recovery implementation.
• Transformation step JSON array versus normalized registry table.
• Release artifact pinning, rollback and retry mechanics.
• Exact SLA calendar and freshness semantics.
• Future streaming implementation.

12. Design principles established

• Metadata plane is authoritative; Airflow and Spark are execution mechanisms.
• Approve configuration before publication; deployment automation follows publication.
• Avoid duplicate configuration definitions and duplicate source scans without benefit.
• Isolate independent work; gate dependent work on committed, sufficiently current data.
• Recover immediately when safe, even after a missed deadline.
• Idempotency and immutable versioned evidence across the entire lifecycle.
• Distinguish approved direction from unresolved implementation proposals.