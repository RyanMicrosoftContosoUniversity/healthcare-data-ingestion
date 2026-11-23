# Deployment Plan

## Status

**Pipeline split: Ready for Validation. Workload: Not Ready for Deployment.**
The approved ownership refactor is implemented; validate the independent roots,
publisher, saved-plan helpers and ADO definitions. This is not authorization for
Azure/Fabric applies, and no live Terraform plan is validated by local checks.

Development and infrastructure preparation are authorized by
`discussions\discussed-changes-03.md` and the November 20 instruction to consolidate
the decisions and perform the development work. Architectural directions are
approved; concrete implementation specifications and validation evidence must now
be produced. No infrastructure deployment is approved until the actual target
configuration and costed Terraform plan are reviewed.

Preserve the 28-source Bronze and Clarity Patient Silver scope. Use Outlook/email,
five-minute single-owner reconciliation, seven-year execution/readiness audit target,
native Fabric SQL backup/restore, PR/code-review-governed releases and protected
reference-aware retention. Do not add Teams, custom backup infrastructure, an
isolated migration-test database, detailed cost attribution or a new task-by-task
approval loop. Unverified schemas, provider support and test results are not
implicitly complete; cloud creation/apply and activation remain separate.

## Azure DevOps Pipeline Delivery

### 7. Validation Proof: independent pipeline split

Local checks on November 23, 2026:

| Check | Command/evidence | Result |
| --- | --- | --- |
| All validation checks pass: tools/authentication | Terraform 1.13.4; Azure CLI; `az account show` | Approved subscription/tenant confirmed |
| Initialize, format, syntax | `terraform init -backend=false -input=false -lockfile=readonly`, `terraform fmt -check -recursive`, `terraform validate` for bootstrap/Azure/Fabric | Passed; existing AzureRM storage-property deprecation only |
| Build and native behavior | `scripts\Test-Project.ps1` | Lint/format, 209 native tests and source/wheel builds passed; two Windows Spark skips |
| Final publisher changes | `pytest tests\test_cicd_delivery.py tests\test_runtime_artifacts.py -q` | 51 passed, including unmanifested inputs and 200/202 operation polling |
| Immutable declarations | `python -m healthcare_ingestion.build_artifacts` with actual built wheel | New scratch bundle compiled, including hashed Fabric declarations; no historical bundle overwritten |
| Pipeline/helper syntax | PyYAML across eight YAML files; PowerShell AST across delivery scripts | Passed |
| Plan preview and remote state backend | Actual Secure File inputs and reviewed live Terraform plan | Not run: live inputs/approval remain outstanding |
| Azure Policy validation | Target-resource policy evaluation | Not yet run; required before a live apply |
| AZD template resolution | Not an AZD recipe; direct Terraform inputs | Not applicable |

Static role review preserves container-scoped Blob Data Contributor for generator
and recovery writers, Blob Data Reader for source-reader/Fabric reads, ACR-scoped
AcrPull, DCR-scoped Monitoring Metrics Publisher and separately owned Fabric
workspace assignments. Actual Fabric identity grants remain optional until the
Fabric root emits its real principal; certificate-backed runtime principals are
not replaced with workspace/managed identities. SQL runtime grants remain migrations.

The pipeline refactor has local validation evidence, not a validated cloud plan.
Do not set the workload status to Validated or invoke Azure deployment: backend,
policy, actual inputs, live plan review and activation gates remain incomplete.

### Approved independent pipeline boundaries

The November 23 clarification approves three independent delivery pipelines:
Azure resources managed by Terraform, Fabric infrastructure managed by Terraform,
and CI/CD for Fabric artifacts such as notebooks and data pipelines.
Azure scope: resource group,
protected Terraform backend, Azure SQL infrastructure, storage, registry, Container
Apps, Azure identities/RBAC, budgets and monitoring. Exclude Fabric workspaces/items,
SQL schema/data migrations and application publication.

The implementation separates the mixed configuration into `infrastructure\terraform\azure`
and `infrastructure\terraform\fabric`, with independent backend keys and the existing
bootstrap root. Preserve existing resource names, approved subscription,
regions, identity boundaries and disabled runtime/alert activation. Keep backend
bootstrap separate from recurring workload updates. Exchange only explicit output
bindings; handle Fabric-identity-dependent Azure role assignments after the actual
Fabric identities exist, without circular state ownership or placeholder IDs.

The dedicated Azure and Fabric pipelines perform validate, saved plan, existing plan
review and exact-plan apply without downloading the ingestion wheel/notebook bundle
or requiring a successful application release. Application CI remains independent.
Keep PR/merged-main governance and scoped federated authentication. Register and
server-validate the revised definitions after the boundary is approved; do not apply
Azure changes as part of this pipeline refactoring.

The user confirmed **all Azure resources**, not just the group/backend bootstrap.
Implement the separation without applying cloud resources. Preserve the existing
approved subscription/regions and actual-plan review gate. Fabric artifact content
has only one deployment owner: the Fabric artifact pipeline. It provisions the
versioned environment/notebook and Airflow artifact items and publishes content.
Fabric Terraform owns durable workspaces, capacity attachment, access assignments,
lakehouses and the metadata SQL database, not notebook/library/DAG content.

The original pipeline IDs/history below describe the first delivery; the current
three-lane design and bootstrap/grant ordering supersede its combined ownership.
See `docs\ingestion\azure-devops-delivery.md` for current definitions and inputs.

The subsequent request to construct and deploy CI/CD targets
**Contoso-University / Fabric**. Definitions are registered in
`\healthcare-data-ingestion`: **33** `healthcare-ingestion-ci`, **34**
`healthcare-ingestion-infrastructure`, **35** `healthcare-ingestion-release`.
Delivery definitions reference CI 33; release references infrastructure 34.
Only the new relevant definitions were added to existing connection permissions.

The implementation is pushed to `build/healthcare-ado-delivery` with GitHub PR **#1**.
Actual hosted CI run **1127** **succeeded**, including native/package/bundle, real
Spark/Delta and Terraform jobs; its `validated-release` artifact is published.
Server-side compilation of all three YAML definitions passed. These are deployed
**ADO definitions**, not deployed
Azure/Fabric workloads. Initial infrastructure delivery requires successful CI for
the exact reviewed main commit, actual Secure File inputs and saved-plan review.
No fabricated review, runtime identity or activation evidence is permitted.

Initial foundation apply creates no generator job; after the actual image exists,
an explicitly provisioned job is manual until live schedule activation is accepted.
The pipeline order, state ownership, migration and asset-publication boundaries are
documented in `docs\ingestion\azure-devops-delivery.md`. This does not change the
**Not Ready for Deployment** status of the Azure/Fabric workload or mark a live
Terraform plan as validated.

## Scope

Two Entra-only Azure SQL source servers/databases, synthetic source data, a dedicated
Fabric metadata workspace/SQL database, separate data workspace, all-table Bronze,
Patient Silver, utilities and observability. Handoff03 authorizes local implementation;
the actual infrastructure plan and live activation remain unapproved.

## Prepared Implementation and Remaining Live Gates

Local implementation includes the 28/454 source contracts, independent generator,
versioned source/metadata migrations, waiting bindings, real source coverage, fenced
capture/publication recovery, Patient transformations, quarantine evidence, isolated
benchmarks, diagnostic collectors and immutable notebook/DAG release preparation.
The logical workflows remain Clarity Bronze, Caboodle Bronze and Patient Silver;
the five-minute reconciliation DAG is maintenance, not another business domain.

Terraform prepares per-release environments and notebooks with actual lakehouse/environment
tokens, scoped generator container roles, required job environment variables, $8/$10
generator budget notifications and disabled-by-default operational alerts. Bootstrap
owns the resource group/state storage; the workload configuration reads that resource
group rather than managing it twice. State bootstrap must be reviewed separately,
and its local initial state retained securely until migrated to the protected backend.

**Not Ready for Deployment:** no reviewed actual Terraform plan, confirmed email/admin
IP, immutable published registry image, resolved runtime certificate principals/delivery
or live acceptance evidence exists. Certificate-backed SQL identities must be real Entra
service principals with reviewed database/Blob/Fabric permissions; the Terraform-created
UAIs/workspace identities are not automatically interchangeable with certificate credentials.
Do not invent identity IDs, use personal-token fallback or place private keys in state.

Live checks include SQL migration/locking/negative permissions, ODBC18 availability in
both driver environments, Fabric capacity headroom, API/library publication/Airflow
recognition, source expected-slot binding, all-28-table reconciliation, the 1,000-patient
seed/one-hour daily target, consumption acknowledgement/cleanup and real email delivery.
Retained history missing its protected manifest/data fails explicitly; no current substitution.
Some Airflow file/environment APIs remain beta. Stable environment library upload/publish
requests are prepared separately from Terraform's infrastructure ownership.

## Authoritative References

- Approved implementation roadmap: retained in the local Copilot session; versioned decisions and progress are recorded here.
- Detailed local design: repository-root `plan.md` (intentionally ignored by Git).
- Versioned source-model approval: `docs\architecture\source-model-approval.md`.
- Source dictionaries: `docs\clarity\data-dictionary.md` and `docs\caboodle\data-dictionary.md`.
- Proposed framework tables: `docs\ingestion\metadata-design.md`.
- Required schema-discovery process review: `docs\ingestion\schema-discovery-design.md`.
- Reconciled approval record: `discussions\discussed-changes.md`.
- Later consolidated decisions: `discussions\discussion-02.md` (supersedes conflicting earlier proposals).
- Latest approval/development handoff: `discussions\discussed-changes-03.md`; later explicit decisions supersede conflicting earlier proposals.
- Orchestration/release design and open schema assessment: `docs\architecture\orchestration-design.md`.
- Logical task/dataset revision: `docs\ingestion\task-dataset-design.md`.
- Consolidated remaining decisions and gates: `docs\architecture\build-decisions.md`.

## Confirmed Decisions

The detailed bullets below preserve the November 20 setup checkpoint. References
there to pending physical-schema implementation/review are historical and superseded
by Handoff 03 and the prepared implementation above. They are not new user decisions
or vetoes on local development. Actual costed-plan review and live activation remain gated.

- All nine setup/operating groups B01-B09 approved November 20 by the user's "I approve all." The complete approved settings are in `docs\architecture\build-decisions.md`. This closes routine setup choices, not the remaining physical framework/Patient Silver contract or infrastructure/Terraform-plan review gates.
- Approved batch deployment settings: demo only; Airflow in `healthcare-data-ingestion-data` on `uswest3capacity`, with Clarity Bronze, Caboodle Bronze and Patient Silver logical DAGs. Derive remaining valid names from the project prefix. Isolate non-expiring `terraform-state` storage from generator access and cleanup.
- Approved network/identity policy: public authenticated endpoints, Entra-only SQL, no anonymous Blob/registry access, SQL's Azure-services firewall exception plus the administrator's approved client IP. The exception's cross-subscription/tenant scope was explicitly disclosed and approved. Use separate scoped machine identities, managed identities where supported/validated; generator source read/write, ingestion source read-only, scoped target/control-store writes, and separate deployment/migration permissions. Actual identities, tenant, client IP, policy compliance and connectivity still need verification before configuration.
- Approved evaluation limits: generator 2 vCPUs/4 GiB, one worker/execution at a time, serialized loaders, 45-minute per-attempt timeout and one transient-failure retry; supported existing Fabric/Airflow defaults without automatic capacity expansion. Generator spend alerts at $8/$10 are notifications, not an enforced cap. Benchmarks: one warm-up, three measured trials, 30-minute case limit. The prior cost illustration assumed 30-minute daily runs, not every timeout/retry being exhausted; refresh measured/total costs before apply and separately review initial-seed/runtime changes.
- Approved operations: Massachusetts/default Synthea profile with mixed ages and continuing cohort; pin generator/mapping/image/releases. Initial Patient/PatientDim loads must be nonempty; other empty tables require reviewed expectations. Patient Silver trims surrounding name whitespace, preserves IDs/audits/soft-delete flags and fails conflicting key/time ties; exact schema/write protocol remains gated. The user owns review/publication/emergency operations and email alerts, with the delivery address pending. Diagnostic/benchmark artifacts: 30 days; completed Fabric staging: five days after confirmed publication/recovery checks; commit evidence/releases/images retained while referenced. Approved metadata publication still triggers automation; automatic rollback is restricted to reviewed technical-health failures, not automatic data remediation.
- Container registry approved November 20: Basic Azure Container Registry named `hcingestionacr`, in East US (`eastus`) under `healthcare-data-ingestion-rg`, provisioned through Terraform, for the Synthea/SQL-loader container image. Name availability is unchecked; review any necessary replacement before deployment. The approximately $5 base fee for 30 days was already included in the approximately $10/month generator planning estimate, not an additional guaranteed total. Image builds, extra storage and transfer may add charges. Registry identity/network configuration and deployment still require review.
- Generator durable storage approved November 20: Terraform-managed Azure Blob Storage, Standard performance, Hot access tier and locally redundant storage (LRS), in East US (`eastus`) under `healthcare-data-ingestion-rg`, with anonymous access disabled. Storage account name approved: `hcingestionstore`; global availability has not been checked, and any necessary replacement requires review before deployment. Retain synthetic population snapshots, shared identity maps, exports and generation checkpoints between job runs. Container names, cleanup implementation, runtime permissions, network access and checkpoint/recovery protocols remain to be confirmed; this does not approve provisioning.
- Retention approved November 20: keep completed generator exports and run manifests for five days, with cleanup subject to confirmed Fabric ingestion and protection of files still needed by unfinished/recovery runs. Keep current population snapshots, shared identity maps and the latest successful checkpoint until verified replacements exist. Retain ingested Fabric data indefinitely, without automatic age-based purge; preserve append-only Bronze and existing Silver business-key merge/delete semantics. This does not require archiving generator files in Fabric or indefinite retention of temporary staging, diagnostics or Delta historical versions. The 12-month source clinical-history profile is unchanged. Cleanup mechanics remain under review; no cleanup or deployment has been executed.
- SQL Microsoft Entra administrator approved November 20: the user's existing Microsoft Entra account is the initial administrator for both `healthcare-data-ingestion-clarity-sql` and `healthcare-data-ingestion-caboodle-sql`. Resolve and verify that account's tenant/object identifiers in deployment settings before Terraform configures the administrator. Do not create SQL administrator passwords or grant administrator access to generator/Fabric runtime identities. This records the administrator choice; no access has been assigned.
- Azure SQL source names approved November 20: logical server `healthcare-data-ingestion-clarity-sql` with database `Clarity`, and separate logical server `healthcare-data-ingestion-caboodle-sql` with database `Caboodle`. Both target `healthcare-data-ingestion-rg` in East US (`eastus`) and remain Terraform-managed, Entra-only sources using the accepted S0 evaluation baseline. Server-name availability has not been checked; review any required name change before deployment. Naming approval does not create resources or select the SQL Entra administrator.
- Lakehouse names approved November 20 in `healthcare-data-ingestion-data`: `healthcare_data_ingestion_bronze` for shared append-only Clarity/Caboodle Bronze with `clarity` and `caboodle` schemas, and `healthcare_data_ingestion_silver` for separate Silver, initially the Clarity Patient flow. Both use the selected workspace capacity `uswest3capacity`. Naming does not create items or authorize additional Silver domains.
- Fabric SQL metadata/control database name approved November 20: `healthcare-data-ingestion-metadata-db`, in `healthcare-data-ingestion-metadata` on existing `uswest3capacity`. It will hold authoritative framework configuration, execution state and operational logs. Name approval does not approve the physical framework schema or create the database.
- Fabric workspace names approved November 20: `healthcare-data-ingestion-metadata` for the Fabric SQL metadata/control database, and `healthcare-data-ingestion-data` for pipelines, notebooks, Bronze and Silver. Both target the selected existing `uswest3capacity` in West US 3. Naming approval does not create workspaces, assign capacity or approve the remaining framework design.
- Azure deployment region selected November 20: East US (`eastus`) for the resource group and new regional Azure resources, including the SQL sources and Container Apps Jobs infrastructure. This does not relocate the selected existing Fabric capacity in West US 3. Service availability, quota, networking and the infrastructure plan still require validation/review before deployment.
- Azure subscription selected November 20: `ME-MngEnvMCAP372892-rharrington-1` (`910ebf13-1058-405d-b6cf-eda03e5288d1`). The user chose their sole subscription; read-only Azure CLI discovery found exactly one enabled subscription, also the default. This confirms the subscription target, not resource deployment.
- November 20 deployment requirement: Terraform owns project Azure infrastructure, including the resource group, source SQL infrastructure, Container Apps environment/Jobs, registry, durable storage, identities/role assignments and monitoring resources when those components are approved. Do not create these manually or through a separate resource-creation script.
- Separate Azure SQL logical servers and databases for Clarity and Caboodle.
- Thirteen Clarity tables and fifteen Caboodle tables are approved.
- Independently generated synthetic sources share consistent identities.
- Synthea plus versioned mapping configuration is selected for source population, retaining independent Clarity/Caboodle SQL loaders. Mapping files need an executable, reviewed loader for identities, relationships, audit/history changes and validation. November 20 generator-host decision: Azure Container Apps Jobs on the Consumption plan, not Fabric-native generation or Azure Batch.
- Low generation cost is the stated priority, with approximately $10/month as the generation planning target, not a fixed fee, enforced cap or whole-platform budget. The prior East US estimate assumes 30 runs/month at 30 minutes/run with 2 vCPUs and 4 GiB, plus a Basic registry and small storage/logging allowances; runtime and resource sizing are unmeasured. SQL databases, normal Fabric ingestion, initial historical seed, private networking and taxes are excluded. Validate actual runtime/memory, free-grant availability and supporting-service costs before deployment. No runtime upgrade, capacity change, execution or resource creation is authorized by this host selection.
- Demo profile approved November 20: 1,000 initial patients, 12 months retained history and approximately 500-1,000 combined daily source-row inserts/updates. About 5 new patients, 10 demographic updates and 25 new encounters plus related rows are components of that total, as are 3-5 corrections and 1-2 eligible soft deletes. On-demand zero-change and approximately 5,000-row spike scenarios are included. Standard S0 (10 DTU) per source is the accepted initial SQL evaluation baseline, subject to initial-load/extraction checks and deployment gates; the earlier GP_Gen5_4 proposal is superseded as the demo baseline. Existing schemas, observability and isolated benchmarks remain in scope. No throughput guarantee or deployment approval is implied.
- Synthetic generation is approved daily at 12:00 UTC (7:00 AM Eastern in standard time, 8:00 AM in daylight time), before the unchanged 10:00 AM Eastern ingestion. Use full seed then checkpoint-based incrementals, prevent overlapping writes, and block/alert only affected consumers when required checkpoints fail or are missing; late recovery continues. Exact checkpoint/capture implementation remains under review; no schedule has been deployed.
- Fabric capacity selected November 20 for both the metadata and data/ingestion workspaces: `uswest3capacity`, ID `ad343e36-f335-4ba3-b261-b739f7e950b0`, discovered SKU F32, region West US 3. Reference this existing capacity in Terraform rather than creating, resizing or relocating it. Selection does not assign workspaces or establish available compute headroom.
- Use Fabric SQL Database in a dedicated metadata workspace for all authoritative framework configuration/state/logging tables.
- Keep that workspace separate from the data/ingestion workspace; do not provision an Azure SQL control database.
- Full observability and isolated benchmarks are in scope.
- Bronze retains append-only raw observations; batch retry protection is distinct from Silver business-key deduplication/merge.
- The seven standard Bronze metadata columns plus optional row hash are accepted. Use `_ingest_source_name` as a `STRING` such as `Clarity.dbo.Patient`; keep internal control-store source-object IDs unchanged. The full row contract is in `docs\ingestion\metadata-design.md`.
- Reusable schema validation precedes eligible fresh extraction. Strict is approved: all ingestion-relevant contract differences, including nullable additions/widening, block only the affected table pending review/approved revision or source correction. No allowlist or auto-evolution. One source pass and staged validation remain; optional lightweight recheck, unavailable-evidence handling, scheduling and concurrency are still open.
- Independent Bronze/Silver 1, dependency-gated Silver 2, committed/fresh readiness, blocked-work notification, and automatic recovery after missed availability deadlines are approved behaviors; schemas/runtime details remain gated.
- Fabric SQL is authoritative for generated Airflow workflow definitions. Approved configuration publication automatically initiates sequential, same-semver framework/DAG releases; failed releases preserve the active last-good version and do not prevent newer queued versions.
- One `ProcessingTask` per independently executable operation, optional source mapping FK but mandatory lineage/input/output identity, logical `Dataset`, normalized `TaskInput`, and limited exceptional task ordering. Ordered function storage is one JSON array/configuration column per task; reconcile legacy step/profiling history before removal.
- Smaller logical-workflow/domain DAGs with hybrid metadata-authoritative readiness/dispatch. Events are primary, periodic reconciliation fallback; every dispatch rechecks all dependencies. Latest expected upstream failure blocks consumers by default despite recent historical success.
- November 20 Airflow decisions: a new Fabric-managed Apache Airflow job in `healthcare-data-ingestion-data` on existing `uswest3capacity`, with Clarity Bronze, Caboodle Bronze and Patient Silver logical DAGs. The user owns operations; derive the item name from the project prefix. Validate supported defaults, service integration, headroom, permissions and connectivity before provisioning; no deployment is authorized by these choices alone.
- Framework/stage defaults and task overrides; generic stage notebooks with justified exceptions; logical notebook/environment/compute refs. Separate scheduler retry/timeouts from runtime settings and environment selection from compute sizing.
- Candidate semver before CI; activation only after required tests/deployment/Airflow recognition. In-flight runs remain pinned. Post-activation technical health failures may trigger defined automatic known-good rollback; data-quality/clinical concerns need operator approval. Rollback does not undo Delta data.
- Airflow reads immutable snapshots; scoped framework/Spark interfaces write execution/readiness state. Preserve deployment environment isolation and logical-to-physical resource maps.
- Stop at the patient Silver slice; no additional Silver domains or downstream analytics.
- Default parent-workflow cadence: daily at 10:00 AM Eastern local time, observing daylight-saving changes; not fixed EST/UTC-05:00 year-round. The 11:00 AM deadline follows the same local time zone. Discovery precedes eligible ingestion. No schedule is deployed.
- Approved default freshness: maximum committed source-coverage/checkpoint age 24 elapsed hours when evaluating dependencies; not row age or notebook completion. Latest expected upstream failure still blocks consumers despite recent older success. No calendar exceptions, freshness overrides or optional Patient inputs initially; physical processing-window/coverage rules remain for review.
- Approved daily availability deadline: 11:00 AM Eastern local time for required Bronze and initial Patient Silver outputs, after the 10:00 AM start. Both times observe daylight saving; the freshness limit remains 24 elapsed hours, not a local calendar day. This is a one-hour end-to-end target, not verified throughput. Benchmark representative full/incremental runs including discovery, waits and required validation before claiming it is met. Misses alert without stopping useful late processing.
- Successful zero-change incremental runs are approved as successful with verified source-window coverage and normal validation/readiness checks; preserve existing data. Initial Patient/PatientDim loads must be nonempty; other empty tables need reviewed expectations. Exact state protocol remains for review. Future processed-record limits use UCL = historical mean + 2 standard deviations and LCL = historical mean - 2 standard deviations. Implementation is deferred; baseline/metric definition, minimum history, negative-LCL handling and breach response need design before activation. This does not authorize a new failure/readiness gate.

## Required Target Confirmation

- Azure tenant; subscription and Azure deployment region are selected above.
- Validate assignment permissions and workload headroom on the selected `uswest3capacity` for both the metadata and data/ingestion workspaces. Capacity identity and West US 3 region are selected; actual workspace assignment remains undeployed. Validate connectivity and transfer-cost assumptions between East US Azure resources and West US 3 Fabric before deployment.
- Fabric SQL Database and workspace names are approved above. Validate name availability, creation/assignment permissions, cross-workspace transactional access and service support before deployment; the physical framework review remains pending.
- Validate the approved Airflow data-workspace/existing-capacity placement and derive/verify its item name; do not create another capacity.
- Cross-workspace runtime identities and database permissions, using the transactional database connection for state/configuration access.
- Resolve the selected SQL Entra administrator's account identifiers; confirm deployment/runtime identities and their separate required permissions.
- Resource-group name approved November 20: `healthcare-data-ingestion-rg`, containing both source SQL infrastructures and the generator/supporting Azure resources, managed through Terraform. Other resource names, policy constraints, connectivity and permissions remain to be confirmed; name approval does not authorize deployment.
- Benchmark the approved source/demo/generator evaluation settings and supported Fabric defaults; validate initial-seed runtime, costs and notification thresholds before apply.
- For the selected Consumption Container Apps Jobs host: validate approved compute/retry/concurrency settings and Basic registry availability/access; derive valid remaining container names; prepare cleanup, scoped permissions/connectivity and completion/checkpoint/partial-failure protocols for review. Refresh total costs against the approximately $10/month generator target before apply. See `docs\architecture\build-decisions.md`.
- Confirm the user's email alert delivery address before activation; prepare/test approved retention and alert delivery without enabling unreviewed cleanup.

## Current Cost Estimate: November 20, 2026

Public retail estimate, USD/30 days, East US Azure resources and West US 3 Fabric
storage: **$46.33-$55.49 additional normal spend; recommend $60/month for planning**.
Without unused job/log allowances, the modeled normal range is $51.87-$55.49.
This is not an actual bill, approved spending cap or deployment approval.

The user accepted this planning estimate on November 20. Routine setup decisions
are complete; exact framework/state and Patient Silver designs, concrete identity/
notification inputs, engineering checks and final costed Terraform-plan review
remain before end-to-end deployment.

The model includes two S0 SQL sources ($29.03), job compute ($0-$4.86), Basic ACR
($5), Blob/state ($0.26), Fabric storage ($0.54), 1 GB Analytics logs ($0-$2.30),
seven five-minute alert time series ($10.50) and a $1-$3 incidental allowance.
Assumed averages: 10 GB Blob, 10 GB Hot OneLake, 1 GB billable Fabric SQL data and
1 GB excess billable backups. Quantities are illustrative/unmeasured, not extra
approved resource settings. Full daily retry consumption gives about $60.35 before
allowances under the same quantities, not a guaranteed maximum.

The existing F32 bill is separate. Additional Fabric compute is $0 only with
unchanged paid capacity/uptime and sufficient headroom, without paid on-demand/
autoscale. Indefinite retention grows storage costs. Initial seed runtime, taxes,
paid CI licenses, private networking and material capacity/usage changes are excluded.
Detailed rates/assumptions: `docs\architecture\build-decisions.md`; query/calculation
audit: session `retail-prices-2026-11-20.json`. Final costed Terraform-plan review
remains required; existing $8/$10 generator alerts are not changed.

## Approved Setup and Operating Decision Batch

The setup and operating choices are consolidated into **nine approved
groups, B01-B09**, in `docs\architecture\build-decisions.md`. They cover rollout and
placement, networking, identities, scheduling/recovery, sizing/limits, synthetic
profile, data-quality policy, operations/retention and release ownership.

The user approved **all nine groups on November 20**. Final physical framework/state-protocol and
Patient Silver contract reviews, plus the infrastructure/Terraform-plan review,
remain separate gates. Provider/policy/capacity exceptions require specific approval;
the nine-group count is not a guarantee that validation will reveal no additional
choices. No target, permission, schedule or compute change is deployed by this batch.

## Review Gates

1. Implementation plan: approved.
2. Cloud targets and infrastructure plan: pending; no provisioning yet.
3. Framework/control-table and standalone schema-discovery process review: pending; no control-store schema, source configuration records, schema-discovery pipeline, or Bronze orchestration yet. Explicitly review both `docs\ingestion\metadata-design.md` and `docs\ingestion\schema-discovery-design.md`.
4. Review the revised physical model/protocol from `docs\ingestion\task-dataset-design.md` and lifecycle requirements in `docs\architecture\orchestration-design.md`; no migrations, DAG generator, or recovery/release runtime before review. Existing 17-table ERDs are the original baseline, not the revised target.
5. Resolve applicable D01-D12 items in `docs\architecture\build-decisions.md` at their stated implementation/provisioning/activation gate, rather than treating all production choices as blockers for independent local source work.

The Fabric SQL backend and dedicated metadata workspace are accepted architectural
decisions, not approval of the remaining table definitions or permission to create
unnamed/unconfirmed cloud assets.

## Deployment Ownership

Terraform owns the Azure infrastructure above and is the required first path for Fabric
infrastructure. Verify and pin provider/API coverage before implementation. If an
asset cannot be managed through Terraform, report the specific gap and obtain approval
before introducing a non-Terraform deployment exception; do not silently substitute
portal steps or scripts. Never manage the same resource through both paths.

SQL migrations, container image builds and synthetic generation/loading are separate
application/data operations, not claims that Terraform manages individual SQL rows.

## Validation

Run local checks, source-schema tests, Terraform validation/plan, and relevant Azure/Fabric validation before deployment. Record actual verification evidence here as work progresses; preparation is not deployment.

## Preparation Evidence

- Python project, source-contract validation, development lockfile, and test/build entry point exist.
- Approved source exports contain 13 Clarity tables / 183 columns and 15 Caboodle tables / 271 columns.
- Eighteen source-contract tests passed; lint/format checks and wheel/source-distribution builds passed.
- Framework review artifacts define 17 proposed tables, 30 FKs, and 50 nullable Spark metric fields, with four focused Mermaid previews plus the complete `data-models\framework\00-overview.mmd` / `.svg` relationship overview.
- A separate `data-models\framework\05-full-schema.mmd` / `.svg` shows every column: 261 across all 17 tables, including shared configuration audit/revision fields and all 50 metric extensions. Table definitions and existing diagram artifacts are unchanged.
- The discovery design uses one-pass source discovery plus staged validation and the subsequently approved Strict drift policy. Optional lightweight live rechecks, unavailable-evidence/scheduling/concurrency and DDL consistency remain open. No discovery runtime has been implemented.
- Reconciled the discussion across the plans, metadata/discovery review, and new orchestration design. Added three behavior-only Mermaid/SVG views; the 17-table baseline ERDs are unchanged.
- Reconciled `discussion-02.md`: JSON task functions, logical task/dataset/input separation, latest-expected-failure readiness, hybrid/event-primary recovery, stage resource configuration, candidate activation, and incident rollback. Added a logical revision review and consolidated decision register; exact physical schemas and cloud targets remain pending.
- Prepared local source SQL baselines for all 28 tables / 454 columns, with PKs, 59 explicit intra-source FKs, and eight single-column UQs. Generator tests pass. Remaining filtered/composite/temporal integrity, audit/write paths, non-destructive migrations, and live SQL validation are documented in `database\README.md`; no databases were deployed.
- Azure account and Fabric capacity discovery succeeded read-only. Their suggested/default choices were not confirmed by the user.
- No SQL servers/databases, Fabric workspaces/lakehouses, control tables, pipelines, or cloud monitoring resources have been created.
- Terraform/cloud validation remains pending because deployment targets and infrastructure have not been approved/prepared.

## Next Required Approvals

Use `docs\architecture\build-decisions.md` as the consolidated D01-D12 register.
Prepare/review revised physical metadata and state/recovery/release protocols, then
obtain the first-flow policies and actual Airflow/Azure/Fabric inputs at their relevant
gates. Baseline ERDs alone cannot approve the now-revised design. No second manual
configuration-release approval gate is added after approved publication.

Do not treat user unavailability or suggested form defaults as approval. Source configuration records and framework implementation remain gated.
