# Deployment Plan

## Status

Preparation paused at explicit review gates. No deployment is approved until the target configuration and the corresponding infrastructure plan are reviewed.

Local development may proceed only for already-approved source models. The November 19
discussion approves architecture behaviors, not the remaining metadata schemas or
deployment inputs. Author/test local source SQL definitions; do not deploy them yet.

## Scope

Two Entra-only Azure SQL source servers/databases, synthetic source data, and, after framework-design approval, a dedicated Fabric metadata workspace/SQL database plus the separate Fabric ingestion workspace, Bronze platform, patient Silver slice, utilities, and observability.

## Authoritative References

- Approved implementation roadmap: retained in the local Copilot session; versioned decisions and progress are recorded here.
- Detailed local design: repository-root `plan.md` (intentionally ignored by Git).
- Versioned source-model approval: `docs\architecture\source-model-approval.md`.
- Source dictionaries: `docs\clarity\data-dictionary.md` and `docs\caboodle\data-dictionary.md`.
- Proposed framework tables: `docs\ingestion\metadata-design.md`.
- Required schema-discovery process review: `docs\ingestion\schema-discovery-design.md`.
- Reconciled approval record: `discussions\discussed-changes.md`.
- Orchestration/release design and open schema assessment: `docs\architecture\orchestration-design.md`.

## Confirmed Decisions

- Separate Azure SQL logical servers and databases for Clarity and Caboodle.
- Thirteen Clarity tables and fifteen Caboodle tables are approved.
- Independently generated synthetic sources share consistent identities.
- Reuse an existing Fabric capacity; do not create one.
- Use Fabric SQL Database in a dedicated metadata workspace for all authoritative framework configuration/state/logging tables.
- Keep that workspace separate from the data/ingestion workspace; do not provision an Azure SQL control database.
- Full observability and isolated benchmarks are in scope.
- Bronze retains append-only raw observations; batch retry protection is distinct from Silver business-key deduplication/merge.
- The seven standard Bronze metadata columns plus optional row hash are accepted. Use `_ingest_source_name` as a `STRING` such as `Clarity.dbo.Patient`; keep internal control-store source-object IDs unchanged. The full row contract is in `docs\ingestion\metadata-design.md`.
- Reusable source-schema validation precedes eligible fresh extraction, with one full discovery pass per selected source table/cycle as the agreed direction. A second live-source recheck, exact drift tolerance, scheduling, and concurrency remain unapproved. Keep staged-schema validation.
- Independent Bronze/Silver 1, dependency-gated Silver 2, committed/fresh readiness, blocked-work notification, and automatic recovery after missed availability deadlines are approved behaviors; schemas/runtime details remain gated.
- Fabric SQL is authoritative for generated Airflow workflow definitions. Approved configuration publication automatically initiates sequential, same-semver framework/DAG releases; failed releases preserve the active last-good version and do not prevent newer queued versions.
- Stop at the patient Silver slice; no additional Silver domains or downstream analytics.

## Required Target Confirmation

- Azure tenant/subscription and region.
- Existing Fabric capacity assignment and region for both the metadata and data/ingestion workspaces.
- Metadata workspace name and Fabric SQL Database item name; unassigned until the user confirms them before creation.
- Cross-workspace runtime identities and database permissions, using the transactional database connection for state/configuration access.
- Entra administrator and deployment/runtime identities.
- Resource naming, policy constraints, connectivity, and permissions.
- Performance sizing, seed-volume limits, and budget.
- Notification destinations and monitoring retention.

## Review Gates

1. Implementation plan: approved.
2. Cloud targets and infrastructure plan: pending; no provisioning yet.
3. Framework/control-table and standalone schema-discovery process review: pending; no control-store schema, source configuration records, schema-discovery pipeline, or Bronze orchestration yet. Explicitly review both `docs\ingestion\metadata-design.md` and `docs\ingestion\schema-discovery-design.md`.
4. Review the dependency/readiness/freshness/SLA and release-state schema gaps in `docs\architecture\orchestration-design.md`; no migrations, Airflow DAG generator, or recovery/deployment runtime before that review. The existing ERDs are a baseline, not a completed expansion.

The Fabric SQL backend and dedicated metadata workspace are accepted architectural
decisions, not approval of the remaining table definitions or permission to create
unnamed/unconfirmed cloud assets.

## Deployment Ownership

Terraform will own supported resources. Document supported API/script alternatives for any demonstrated Fabric provider gaps before implementation. Never manage the same resource through both paths.

## Validation

Run local checks, source-schema tests, Terraform validation/plan, and relevant Azure/Fabric validation before deployment. Record actual verification evidence here as work progresses; preparation is not deployment.

## Preparation Evidence

- Python project, source-contract validation, development lockfile, and test/build entry point exist.
- Approved source exports contain 13 Clarity tables / 183 columns and 15 Caboodle tables / 271 columns.
- Eighteen source-contract tests passed; lint/format checks and wheel/source-distribution builds passed.
- Framework review artifacts define 17 proposed tables, 30 FKs, and 50 nullable Spark metric fields, with four focused Mermaid previews plus the complete `data-models\framework\00-overview.mmd` / `.svg` relationship overview.
- A separate `data-models\framework\05-full-schema.mmd` / `.svg` shows every column: 261 across all 17 tables, including shared configuration audit/revision fields and all 50 metric extensions. Table definitions and existing diagram artifacts are unchanged.
- The discovery design is reconciled to one-pass source discovery plus staged-schema validation; second live-source checks and drift tolerance remain open. No discovery pipeline or live-schema comparison has been implemented.
- Reconciled the discussion across the plans, metadata/discovery review, and new orchestration design. Added three behavior-only Mermaid/SVG views; the 17-table baseline ERDs are unchanged.
- Prepared local source SQL baselines for all 28 tables / 454 columns, with PKs, 59 explicit intra-source FKs, and eight single-column UQs. Generator tests pass. Remaining filtered/composite/temporal integrity, audit/write paths, non-destructive migrations, and live SQL validation are documented in `database\README.md`; no databases were deployed.
- Azure account and Fabric capacity discovery succeeded read-only. Their suggested/default choices were not confirmed by the user.
- No SQL servers/databases, Fabric workspaces/lakehouses, control tables, pipelines, or cloud monitoring resources have been created.
- Terraform/cloud validation remains pending because deployment targets and infrastructure have not been approved/prepared.

## Next Required Approvals

1. Confirm actual Azure/Fabric targets, administrator/connectivity, sizing, and spend limits.
2. Review `docs\ingestion\metadata-design.md` and its relationship diagrams.
3. Review `docs\ingestion\schema-discovery-design.md` before the dependent framework/discovery/Bronze build. Document creation is not process approval.

Do not treat user unavailability or suggested form defaults as approval. Source configuration records and framework implementation remain gated.
