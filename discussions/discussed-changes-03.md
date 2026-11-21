Healthcare Data Ingestion — Consolidated Decisions and Approval Handoff

Date: 2026-11-20
Repository: https://github.com/RyanMicrosoftContosoUniversity/healthcare-data-ingestion
Authoritative baseline: docs/architecture/build-decisions.md (A01–A80 settled; R01–R53 review areas)
Purpose: Repo-ready record of the user’s approvals in the continued architecture conversation, including blanket approval of recommended directions for remaining items. Not an infrastructure deployment authorization.

Interpretation and precedence

1. Preserve all A01–A80 decisions in the existing register unless a later explicit user decision conflicts. This document records subsequent approvals and is intended to be merged into that register, not replace its source contracts or implementation specifications.
2. The user explicitly approved the assistant’s recommendations for the remaining decisions near the end of the session. This is approval of recommended architectural direction, not evidence that all 53 R-items have complete physical designs, tested SQL, working Fabric operators, exact provider support, or final deployment plans.
3. Where a conversation recommendation is broader than the initial demo, preserve the demo scope: 13 Clarity and 15 Caboodle tables to Bronze, Clarity Patient to Silver 1, utilities, diagnostics, benchmarks, and alerts. Do not add Silver 2, Gold, streaming, regional DR, or additional domains to initial delivery.
4. Specific later user decisions override generic earlier suggestions. In particular: Outlook/email rather than Teams; no custom metadata backup system; no additional isolated migration-test database for now; no bypass of code review for hotfixes.
5. The user asked to prepare a definitive list for repo handoff. This document does not claim that any GitHub file was modified or any Fabric/Azure resource was deployed.

Explicit approvals — metadata and orchestration

• One ProcessingTask record per independently executable step; preserve PipelineObject as source-to-target mapping, with optional mapping FK on tasks.
• Introduce logical Dataset identities for Bronze, Silver and modeled future layers; immutable IDs, changeable names, centralized environment-specific logical-to-physical Fabric mappings.
• One authoritative producing task per logical dataset within an active release/applicable processing scope. Primary output dataset on task; normalized relational TaskInput records for all inputs, including multiple inputs.
• Derive dependency edges from known producers and task inputs; explicit relational dependency records only for exceptional ordering. Reject missing, ambiguous, or cyclic dependencies.
• Store ordered transformation functions with validated parameters in a task-level JSON array, preserving occurrence identity, history and profiling references before removing legacy TransformationStep links.
• Generic notebooks per stage by default; specialized notebooks only when needed. Logical notebook, environment, compute profile references; stage defaults with task overrides.
• Keep PipelineDefinition for shared/stage policy, remove baseline input/output layer fields; execution policy default on pipeline/stage with optional task overrides. Distinguish ingestion strategy, Airflow retry/timeout policy, and Spark startup/runtime settings.
• Dataset-level current readiness plus historical committed output instances; execution history and individual attempts separate from readiness. Preserve the last valid output when a newer attempt fails.
• Compare authoritative outputs by logical processing watermark/window, not completion time; reject stale progress updates. Dataset freshness defaults, with per-task-input overrides; default downstream behavior is block on stale or invalid inputs, with explicit approved exceptions.
• Publish readiness events on committed validated output, with periodic reconciliation as fallback; independently re-evaluate all inputs for each consumer. Event handling is idempotent and order-aware; coalesce rapid updates by default when semantically safe, configurable exception to process each update.
• Reconciliation interval: five minutes by default, configurable; one active reconciliation run at a time; bounded retries/backoff, next-run catch-up and persistent-failure Outlook alerts. Each reconciliation run uses an immutable configuration snapshot.
• Immutable configuration and DAG binding: queued and running tasks keep their original DAG-run framework version; new releases apply to new runs. Manual reruns default to original approved framework version with explicit option for another approved version.
• If original historical input snapshots are unavailable, do not silently substitute current data; require explicit authorization and record the substituted source version.
• Concurrent duplicate/conflicting reruns of the same dataset/window are prevented or queued; nonconflicting windows may run concurrently.
• Each transformation reads fixed Delta input versions for its execution; retain referenced versions while active executions or approved recovery need them.

Explicit approvals — recovery, data quality, and schema

• Framework rollback reactivates the last-known-good release for new executions, leaving in-flight work intact unless explicitly canceled. Example: 1.3.0 issue → 1.2.3 active → tested 1.3.1 later becomes active.
• Technical deployment-health failures can trigger automatic rollback; suspected data-quality corruption/remediation requires operator authorization.
• Framework rollback does not itself undo Delta data. Flag potentially corrupted outputs, use lineage to identify potentially affected descendants, and block affected downstream consumption until validated or corrected. Unaffected work continues.
• Routine failures may automatically clear after validation; confirmed corruption requires operator approval to unblock.
• Severity-based quality rules: critical violations block publication; noncritical violations warn. Quarantine invalid records with centrally configurable thresholds; critical dataset-level failures still reject publication. Conflicting Patient key/time ties must still fail, not silently become acceptable quarantine.
• Support targeted replay of quarantined records, with full reprocessing fallback; preserve original identifiers, causes and attempt lineage; rerun normal validations and idempotent writes.
• Strict source schema drift: compare the approved source contract before each ingestion, with caching only where it does not replace the live validation. Block only the affected source table and its dependent consumers, not unrelated tables. No automatic schema evolution.
• Validate intentional curated-output schema changes against downstream contracts during CI/CD; reject incompatible changes unless dependent tasks are migrated in the same release.
• If a metadata schema migration fails, halt deployment and use a controlled corrective migration; use transactional operations where supported, never assume arbitrary DDL can always be automatically reversed.
• Apply backward-compatible metadata schema migrations before activating dependent framework code; preserve a rollback compatibility window.
• Task-level partial success: successful committed datasets remain available while unrelated failed tasks are retried. Exhausted retries stop and require explicit intervention.
• If Fabric SQL metadata control is unavailable, block new task starts; allow in-flight work to finish safely and reconcile commits/status before publishing readiness.
• Backfills are explicit, not automatic on transformation changes. Allow backfills and daily ingestion concurrently with coordinated conflicting writes; daily runs take priority. Checkpoint backfill by processing window and resume failed windows.
• Backfill source choice: support current corrected source data (default) and available historical snapshots; record the actual source versions used.
• Prevent new dependencies on retired datasets; retire tasks and datasets logically, preserve historical data, execution records and lineage subject to retention.
• Missed 11 a.m. availability deadline: continue useful processing, log SLA violation and alert; recurring violations escalate with configurable thresholds. Deadline is not execution timeout.

Explicit approvals — release, Fabric, security and operations

• Approved configuration changes go through GitHub branch/PR, code review, CI/CD and versioned deployment. No direct production metadata edits or hotfix bypass.
• Human-reviewed configuration publication triggers DAG generation and technical deployment automatically; validate graph, resources, metadata and CI/CD checks before activation. No additional manual approval after technical checks pass.
• Multiple smaller logical DAGs (Clarity Bronze, Caboodle Bronze, Patient Silver), not one monolithic DAG; hybrid cross-DAG metadata readiness and Airflow execution.
• Candidate semantic version is assigned before tests; active version advances only after validation, Fabric publication and Airflow recognition. Preserve last-known-good on failure.
• Pin transformation package, Python dependencies, notebooks and Fabric environment configurations to framework release. Version Spark settings through CI/CD, do not modify active environments in place. New release activation requires its Fabric environment to publish successfully; rollback restores the matching approved environment configuration for new executions.
• Distinguish Fabric environments from dedicated compute pools. Centrally define workload/compute-profile concurrency limits, with task overrides; use Fabric native throttling and proactive Airflow scheduling. Automatic compute escalation for confirmed resource failures is allowed only where supported by Fabric and within configured limits.
• Keep logical connection references in metadata; credentials stay in Fabric connections or approved secret store. Use scoped service identities, not personal accounts for scheduled workloads.
• Audit/operational history: user approved a seven-year target for execution/readiness audit records and read-only role-controlled access through Fabric. Reconcile this target with baseline A67–A70, which specify different retention for generator files, staging, diagnostics, data and referenced control evidence. Do not interpret seven years as indefinite retention of every temporary artifact.
• Centrally managed configurable artifact retention and automated cleanup, protecting references and active recovery. Cleanup failures have separate retries/alerts and do not halt ingestion except critical operational/compliance conditions.
• Use Fabric SQL Database native backup/restore; no custom backup system. Rely on Fabric native resilience for this demo; defer cross-region DR.
• Alert delivery is Outlook/email, not Teams. The user explicitly has no Teams account connected to the Fabric tenant. Keep notification delivery simple; exact recipient must be confirmed before activation.
• Task-level metrics and exact cost attribution were explicitly deprioritized; preserve existing minimum operational logging, diagnostics and alerts in A74–A76 without expanding scope.
• Transient notebook retry discussion was deferred, not a license to disable the already approved bounded retry/timeout policies.
• Isolated migration-test database was deferred; do not provision a third source/test database for this purpose. Note that architecture still calls for a separate Fabric SQL metadata database in addition to the two Azure SQL source databases.
• Access-review cadence was deferred; do not infer permission to weaken the scoped access model.
• Retain task outputs and audit lineage when task retired. Renames preserve immutable logical IDs; physical location mapping changes remain CI/CD governed.

Blanket-approved recommended direction for remaining review areas

The user said: “Let’s just approve whatever your recommendations are for the rest of the decisions.” Apply the following recommended engineering principles to still-unresolved R-items, without fabricating physical implementation specifics:

|Register area                          |Approved direction / engineering action                                                                                                                                                                     |Still requires concrete implementation evidence                                                                             |
|---------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
|R01–R07 Metadata physical design       |Separate task/dataset/input/dependency/readiness/history/release concerns, preserve baseline history, use immutable versions and validated function JSON.                                                   |Full SQL column dictionaries, constraints, migration plan, state transitions, interfaces and tests.                         |
|R08–R15 Generator/source/reconciliation|Preserve approved 28 source models, deterministic identities, independent Clarity/Caboodle loads, committed checkpoints, exact source-to-Bronze reconciliation, empty/no-change handling and bounded replay.|Executable field mappings, exact incremental boundary, key/temporal integrity, checkpoint and reconciliation tests.         |
|R16–R21 Discovery and drift            |Strict pre-extraction live-source discovery, fail closed on unavailable evidence, freeze approved contracts and capture evidence, isolate affected tables.                                                  |Canonical SQL schema fingerprints, DDL race strategy, actual PASS/FAIL/UNAVAILABLE persistence and saved-batch replay tests.|
|R22–R28 Commit, readiness and events   |Idempotent batch Delta publication; reconcile post-Delta/pre-SQL uncertainty; version-aware readiness; event plus five-minute reconciliation, fenced claims and deduplicated dispatch.                      |Concrete Delta commit evidence, SQL transaction/outbox design, claim fencing, exact windows and DST test cases.             |
|R29–R33 Patient Silver                 |Only Clarity Patient Silver 1; preserve PatientID grain, audits, deletes, precision and approved name trimming; fail conflicting ties.                                                                      |Final output dictionary, deterministic order/merge/delete logic and acceptance fixtures.                                    |
|R34–R41 Fabric and releases            |Logical physical maps, pinned Fabric environments, three logical DAGs, immutable release manifests, validated activation and safe rollback.                                                                 |Supported operator/API selection, deployment recognition, artifact pinning and health-check evidence.                       |
|R42–R43 Terraform/cost                 |Keep selected infrastructure targets and Terraform ownership; no deploy without explicit review of exact plan and costs.                                                                                    |Provider/API feasibility, state/bootstrap and costed Terraform plan.                                                        |
|R44–R49 Diagnostics and alerts         |Preserve existing logging/metric/alert scope; Outlook email notifications only; do not expand to Teams or detailed cost attribution.                                                                        |Actual Log Ingestion/DCR schemas, supported metric sources, KQL alert rules, recipient and delivery test.                   |
|R50–R52 Benchmarks/retention           |Preserve isolated benchmark contract and protected retention; protect referenced Delta versions and evidence before cleanup.                                                                                |Benchmark FK/schema/test details and exact reference-aware cleanup rules.                                                   |
|R53 Final acceptance                   |Require source, Bronze, Patient Silver, replay, drift, isolation, release and alert evidence before declaring build complete.                                                                               |Live acceptance results, runbooks and explicit final signoff.                                                               |

Explicitly deferred or excluded (do not turn into build requirements)

• Additional Silver/Gold/streaming pipelines, production-scale regional resilience, extra test database for migration testing, Teams integration, custom backup infrastructure, detailed capacity-cost attribution, quarterly access-review workflow, and a new per-task approval loop.
• Do not treat the suggested 7-year audit retention as a regulatory fact; it is a user-approved target subject to applicable requirements and feasibility.
• Do not claim every R01–R53 item is physically implemented or that all exact values are approved. Blanket architectural approval does not supply missing resource IDs, schemas, test results or Terraform authorization.

Ready-to-build sequence

1. Merge this decision handoff into the existing docs/architecture/build-decisions.md, marking each R-item as direction approved / implementation specification pending, explicitly deferred, or fully settled with evidence. Keep A01–A80 and existing source dictionaries authoritative.
2. Prepare concrete physical metadata SQL definitions and migration scripts for R01–R07, R22–R28 and R34–R41, including testable constraints, run-state machine, immutable release manifest, and Fabric-specific execution maps.
3. Finish the executable source generators and independent SQL loaders (R08–R15), strict discovery and Bronze append/idempotency path (R16–R28), and Patient Silver contract (R29–R33).
4. Produce Fabric/Airflow deployment artifacts, diagnostic and email alert wiring, and the actual Terraform plan. Obtain separate approval before applying infrastructure changes.
5. Execute R53 acceptance tests against the approved demo scope; capture reproducible results and operator runbooks.

Provenance

• Current repository register reviewed on November 20, 2026: https://github.com/RyanMicrosoftContosoUniversity/healthcare-data-ingestion/blob/main/docs/architecture/build-decisions.md
• User’s explicit approvals and deferrals in the November 20 continued conversation provided in this chat.
• This document is a consolidation for repository handoff, not a claim that the register has been edited, a PR opened, or the build deployed.