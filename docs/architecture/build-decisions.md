# Complete Build Decisions and Remaining Reviews

**Review checkpoint: November 20, 2026. All nine setup/operating groups B01-B09
are approved, and the updated cost estimate is accepted for planning. Exact physical
designs and the final costed Terraform plan are not yet approved.**

This is the complete review register for the decisions recorded in the source-model
approval, November 19-20 discussions, root design and deployment plan. Later explicit
approvals supersede older proposals. The A-series below records settled decisions;
the R-series lists every outstanding review area, including details previously
scattered across other documents. Inputs and engineering checks are separate.

It does not reopen approved choices or turn suggestions into defaults. The initial
delivery remains all-table Bronze plus Clarity Patient Silver 1, utilities, isolated
benchmarks, diagnostics, and alerts. Silver 2/Gold/streaming architecture does not
expand that delivery.

Local source SQL preparation already exists. Not every item below blocks that work:
the **Needed before** column identifies the affected build/deployment/activation gate.
Selected cloud targets/component names are recorded below. Cloud deployment and
exact revised framework schemas remain unapproved.

## How to Review This Register

| Record | Status / meaning |
| --- | --- |
| A01-A80 | **Settled direction or scope.** Preserve these choices. Approval of a direction is not approval of an unprepared physical implementation. |
| B01-B09 | **Approved setup batch.** Original approval groups retained for traceability; expanded in A01-A80. |
| R01-R53 | **Review required.** Existing direction/proposal and the exact remaining decision are stated. No new value in these rows is treated as approved. |
| I01-I08 | **Input required.** Concrete deployment values to resolve; these are not new architecture choices. Discover them from approved targets where possible. |
| V01-V14 | **Verification required.** Engineering checks and evidence, not requests for the user to invent implementation details. |
| F01-F08 | **Deferred / outside initial delivery.** Do not implement these merely because the model can accommodate them. |
| H01-H09 | **Superseded / excluded.** Historical proposals and incorrect interpretations that must not enter the current build. |
| D01-D12 | Existing gate/reference map, retained below. These are not twelve wholly undecided architecture choices. |

**Review packaging:** R01-R53 are details to resolve in three cohesive packages:
the revised framework/discovery/recovery/release design, the exact Patient Silver
contract, and the verified costed Terraform/deployment plan. They are not 53 separate
setup-question rounds. Engineering prepares concrete designs and validation evidence;
the user reviews those packages before their dependent implementation/deployment.

**Already prepared:** package/test tooling, approved source dictionaries/contracts,
local empty-database SQL baselines and review diagrams. **Not yet deployed:** SQL
sources, generator jobs, Fabric workspaces/items, revised control tables, ingestion,
Silver, release automation and alerts. The original 17-table / 261-column / 30-FK
metadata ERDs are a baseline, not the approved revised physical schema.

## Complete Settled-Decision Inventory

### Scope and Source Models

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A01 | Initial end-to-end delivery | All 13 Clarity and 15 Caboodle tables through Bronze; one Clarity Patient Silver flow; shared utilities, isolated transformation benchmarks, operational logging, Spark metrics/API diagnostics and centralized alerts. |
| A02 | Stop boundary | No Gold, semantic models, reports, additional Silver domains, cross-source patient consolidation, streaming implementation or enterprise rollout in this delivery. Silver 2 remains an architectural dependency requirement, not a new initial flow. |
| A03 | Approved source contracts | Preserve all 28 approved source models / 454 columns, including documented types, nullability, keys, relationships, audits and historical/event grains. Column dictionaries remain authoritative; this register does not replace them. |
| A04 | Source independence | Populate Clarity and Caboodle independently from shared deterministic synthetic identities. Caboodle does not query or derive its data from Clarity. |
| A05 | Source fidelity and reconciliation | Keep each source's own keys, audits, history and relationships. Reconcile each SQL source to its own Bronze publication, not Clarity row counts to Caboodle or current SQL counts to accumulated Bronze history. Exact check scopes remain R14. |
| A06 | Demo volume/history | 1,000 initial patients; 12 months of SQL source clinical history; about 500-1,000 combined daily source-row changes. The profile below includes about 5 new patients, 10 demographic updates, 25 encounters plus related rows, 3-5 corrections and 1-2 eligible soft deletes. |
| A07 | Workload priority | Low-cost, configurable, deterministic demo rather than hospital-volume simulation or maximum parallel throughput. Counts are targets, not per-table quotas, hard truncation limits or clinical prevalence guarantees. |

**All approved tables:**

| Source | Tables |
| --- | --- |
| Clarity | `Patient`, `Provider`, `Department`, `Encounter`, `Diagnosis`, `Procedure`, `MedicationOrder`, `MedicationAdministration`, `LaboratoryOrder`, `LaboratoryResult`, `VitalSign`, `Coverage`, `Appointment` |
| Caboodle | `DimPatient`, `DimProvider`, `DimDepartment`, `DimDate`, `DimDiagnosis`, `DimProcedure`, `DimMedication`, `DimCoverage`, `FactEncounter`, `FactDiagnosis`, `FactProcedure`, `FactMedicationOrder`, `FactMedicationAdministration`, `FactLabResult`, `FactAppointment` |

Source references: `docs\architecture\source-model-approval.md`,
`docs\clarity\data-dictionary.md`, `docs\caboodle\data-dictionary.md`,
`database\schema-contracts\clarity.json` and `database\schema-contracts\caboodle.json`.
The initial Caboodle patient table is `DimPatient`; earlier conversational
"PatientDim" wording refers to this table, not an additional model.

### Exact Targets and Resource Names

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A08 | Azure subscription | `ME-MngEnvMCAP372892-rharrington-1`, ID `910ebf13-1058-405d-b6cf-eda03e5288d1`. Selected existing subscription; not deployment authorization. |
| A09 | New Azure resource region | East US, `eastus`. This does not relocate existing Fabric capacity. |
| A10 | Azure resource group | `healthcare-data-ingestion-rg` for source SQL and generator/supporting Azure resources. |
| A11 | Fabric capacity | Existing `uswest3capacity`, discovered F32, West US 3; ID `ad343e36-f335-4ba3-b261-b739f7e950b0`. Reference it; do not create, resize or relocate capacity. |
| A12 | Metadata workspace | `healthcare-data-ingestion-metadata` on the selected existing capacity. |
| A13 | Data workspace | `healthcare-data-ingestion-data` on the same capacity, separate from metadata; not one workspace per source. |
| A14 | Clarity SQL source | Separate Azure SQL logical server `healthcare-data-ingestion-clarity-sql`, database `Clarity`; not a VM or Managed Instance. |
| A15 | Caboodle SQL source | Separate Azure SQL logical server `healthcare-data-ingestion-caboodle-sql`, database `Caboodle`. |
| A16 | Authoritative control database | Fabric SQL Database `healthcare-data-ingestion-metadata-db` in the metadata workspace for configuration, state and operational records; use its transactional connection, not its read-only analytics endpoint. No Azure SQL control database. |
| A17 | Bronze lakehouse | Schema-enabled `healthcare_data_ingestion_bronze` in the data workspace, shared by Clarity and Caboodle with `clarity` and `caboodle` schemas. |
| A18 | Silver lakehouse | Separate schema-enabled `healthcare_data_ingestion_silver` in the data workspace; initially Clarity Patient only. Exact Patient table/schema name remains R29. |
| A19 | Airflow host and DAG boundaries | New Fabric-managed Apache Airflow job in the data workspace on existing capacity. Clarity Bronze, Caboodle Bronze and Patient Silver logical DAGs with shared discovery; no monolithic framework DAG, reused existing Airflow instance or self-managed host. |
| A20 | Generator durable storage | `hcingestionstore`, Standard performance, Hot tier, LRS, East US, same resource group, anonymous access disabled. Population state, shared identities, exports and checkpoints persist across job runs. |
| A21 | Container registry | Basic Azure Container Registry `hcingestionacr`, East US, same resource group, for the Synthea/loader image. Builds and excess storage/transfer are separate cost contributors. |

### Deployment, Networking and Access

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A22 | Infrastructure ownership | Terraform manages Azure infrastructure and supported Fabric assets. Pin tested providers/APIs; report a specific provider gap and obtain approval before any repeatable non-Terraform exception. Never manage one resource through both paths. |
| A23 | Application/data operations | Container builds, SQL migrations and synthetic generation/loading are separate application/data operations; do not represent individual SQL data rows as Terraform-managed resources. |
| A24 | Environment and remaining names | One demo environment, no QA/prod rollout. Derive remaining valid names from the project prefix without changing approved names. Keep logical identities and environment-specific physical maps suitable for later isolated environments. |
| A25 | Terraform state | Restricted, isolated, non-expiring `terraform-state` container. Exclude it from generator permissions and cleanup. Bootstrap/migration/locking details remain R42. |
| A26 | Endpoint/authentication policy | Public authenticated endpoints for this synthetic demo, Microsoft Entra-only SQL, no anonymous Blob/registry access and no SQL administrator passwords. |
| A27 | SQL firewall policy | Azure-services firewall exception plus the approved human administrator client IP. The exception's cross-subscription/tenant network scope was disclosed and approved; it does not replace authentication or configure access by itself. |
| A28 | Human SQL administrator | The user's existing Microsoft Entra account initially administers both SQL servers. Resolve exact tenant/object IDs; do not execute scheduled workloads as that account. |
| A29 | Machine identity separation | Separate scoped machine identities, managed identities where supported/validated. Generator gets source-table read/write, its Blob containers and image pull; ingestion gets source read-only, target writes and scoped transactional state interfaces. Deployment/migration privileges remain separate; no runtime SQL administrator role. |
| A30 | Control-plane access | Airflow reads immutable orchestration snapshots. Framework/Spark write execution/readiness state through scoped interfaces, not unrestricted published configuration. Publication and privileged maintenance belong to authorized operations roles. |

### Generator and Source Operating Profile

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A31 | Generator/loader technology | Synthea plus versioned mappings and executable independent SQL loaders, hosted in Consumption Container Apps Jobs. Mapping files alone are not loaders. |
| A32 | Clinical/demographic profile | Massachusetts/default Synthea mix and mixed ages, not a custom prevalence or hospital-representativeness model. Supplemental fields/mutations require documented mapping coverage. |
| A33 | Population continuity | Advance the same cohort, retaining stable shared identities, current snapshots and checkpoints. Pin generator, mapping, image and release versions. |
| A34 | SQL evaluation size | Standard S0, 10 DTU, per source database. This is a baseline requiring measured seed/extraction checks, not a throughput guarantee. |
| A35 | Generator execution limits | Evaluate at 2 vCPUs/4 GiB; one worker/execution at a time; serialized SQL loaders; 45-minute per-attempt timeout; one transient-failure retry. Do not apply these limits automatically to Fabric tasks or enlarge the initial seed without measured/costed review. |
| A36 | Generator schedule | Daily 12:00 UTC: 7:00 AM Eastern standard time / 8:00 AM Eastern daylight time, before the daily Fabric workflow. |
| A37 | Source publication/recovery | Full seed then checkpoint-based incrementals; prevent overlapping writes. Failed/missing required committed checkpoints block and alert affected consumers only; useful late recovery continues. Exports alone do not establish successful SQL publication. |
| A38 | Scenario profiles | Normal change mix in A06, verified zero-change increments and an on-demand approximately 5,000-row spike. Preserve relationships/history; do not force equal Clarity/Caboodle counts or daily changes in reference tables. |

### Discovery, Bronze and Readiness

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A39 | Fabric cadence and availability | Daily workflow/discovery starts 10:00 AM Eastern local time; required Bronze and Patient Silver available by 11:00 AM Eastern. Both observe daylight saving; the one-hour target is not yet demonstrated. |
| A40 | Freshness policy | At most 24 elapsed hours since committed source coverage/checkpoint, inclusive at exactly 24 hours; not row age, completion time or a local calendar day. Dataset defaults and consumer overrides are supported, but no initial differing values/calendar exceptions/optional Patient inputs are selected. |
| A41 | Latest failure and late recovery | Latest expected upstream failure blocks consumers even if older successful data is recent. An availability miss alerts but does not cancel useful recovery; retain the violation and time to recovery. |
| A42 | Dependency isolation/status | Healthy Bronze and Silver 1 continue independently. Dependent joins require all explicit committed/fresh/window-compatible inputs. Persist and notify `BLOCKED_BY_DEPENDENCY`; waiting is not a failed/executed transformation. |
| A43 | Schema drift policy | Strict: all ingestion-relevant differences, including nullable additions and widening, block only that table until approved revision or source correction. No allowlist, auto-promotion or target evolution. Physical column order alone is observational with explicit name-based projection; primary-key order remains significant. |
| A44 | Discovery placement and staging | Reusable live-source discovery before eligible fresh extraction, one full source pass, then prompt eligible dispatch and independent staged mapped-schema validation. Freeze contracts; no mandatory duplicate full scan. Additional lightweight recheck and unavailable-evidence mechanics remain R17-R18. |
| A45 | Bronze publication semantics | Append-only raw observations. Publish each captured batch once; preserve repeated business keys and identical payloads across distinct batches. Neither business keys nor row hashes suppress distinct-batch observations. |
| A46 | Bronze technical columns | Seven required `_ingest_` columns plus optional row hash, enumerated below. Use readable `_ingest_source_name`, not a numeric per-row source-object ID; internal metadata keys remain. |
| A47 | Source/capture fidelity | Preserve source columns, identifiers, audits and soft-delete status. Reserve `_ingest_` names and reject collisions. Freeze source name/extraction identity with a saved batch; writer IDs identify the successful append attempt. Hash source values only; exact canonicalization/precision is reviewed, not invented. |
| A48 | Empty/no-change acceptance | Initial Clarity `Patient` / Caboodle `DimPatient` must be nonempty. Other legitimately empty tables need reviewed expectations. Verified zero-change increments succeed, preserve data and require schema/readiness/coverage checks; zero count alone does not authorize state advancement. |

**Accepted Bronze row-column contract** (Spark/Delta types, not control-store SQL types):

| Column | Type | Nullable | Recorded meaning |
| --- | --- | --- | --- |
| `_ingest_batch_id` | `STRING` | No | Stable captured-batch UUID reused during replay. |
| `_ingest_run_id` | `STRING` | No | Run that successfully published the observation. |
| `_ingest_table_run_id` | `STRING` | No | Table execution attempt that successfully published it. |
| `_ingest_source_name` | `STRING` | No | Frozen readable identity, for example `Clarity.dbo.Patient`. |
| `_ingest_extracted_at_utc` | `TIMESTAMP` | No | Batch capture time, retained on replay. |
| `_ingest_landed_at_utc` | `TIMESTAMP` | No | Successful write-attempt time; exact Delta commit evidence is separate. |
| `_ingest_capture_mode` | `STRING` | No | `FULL` or `WATERMARK`, not inferred INSERT/UPDATE operation type. |
| `_ingest_row_hash` | `STRING` | Yes | Optional SHA-256 of canonical source values, excluding ingestion metadata. |

### Patient Silver and Reusable Metadata/Functions

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A49 | Patient-only Silver grain | First Silver flow reads Clarity Patient Bronze; one logical row per `PatientID`. Do not collapse Caboodle Type 2 versions or create a cross-source patient model. Exact schema/merge rules remain R29-R33. |
| A50 | Allowed Patient normalization | Trim surrounding name whitespace; preserve identifiers, source audits, soft-delete flags and nulls. Do not invent clinical values or silently rewrite source modification times. |
| A51 | Conflicting Patient ties | Fail conflicting key/time payload ties rather than select an arbitrary survivor. Exact duplicates and source-precision-safe ordering need the reviewed contract; a quarantine artifact is not permission to treat a conflicting load as successful. |
| A52 | Silver versus Bronze writes | Latest-state business-key deduplication/merge belongs in Silver, not Bronze. Writes/replays must be idempotent; exact deletion representation, ordering and write protocol remain for review. |
| A53 | Mapping versus executable task | Retain `PipelineObject` as source-target mapping; separate `ProcessingTask` for one independently executable operation. Mapping FK is optional, but lineage, input/output identification and primary output dataset are mandatory. |
| A54 | Logical datasets | Register logical dataset identities, stable across deployment environments. The model can represent Bronze/Silver/Gold without authorizing additional initial flows. Current readiness is separate from task-attempt history. |
| A55 | Normalized task inputs | One `TaskInput` per consumed logical dataset, with alias, required flag and supported consumer freshness override. Reference datasets, not physical Fabric table IDs; hidden untracked auxiliary inputs are not permitted. |
| A56 | Dependency graph | Derive edges through unambiguous dataset producers. Reserve explicit relational task dependencies for exceptional ordering; reject cycles, missing required inputs and ambiguous producers. |
| A57 | Shared pipeline revision | Keep `PipelineDefinition` for shared pipeline/stage policy; remove its baseline input/output layer attributes in the revision and infer movement from task datasets. |
| A58 | Function storage/history | One ordered JSON function array/configuration column per task, including validated parameters. Preserve repeated occurrences, auxiliary inputs, validation and profiling attribution before retiring baseline `TransformationStep` references. |
| A59 | Function dispatch and utilities | Registered versioned packaged callables; focused DataFrame-in/DataFrame-out functions, applied in order through `DataFrame.transform`. No metadata `eval`/`exec`, arbitrary import paths or pickled callables. Framework utilities own I/O/state/logging, not business functions. An empty function list is pass-through. |
| A60 | Notebook/resource configuration | Generic stage notebooks by default, justified specializations allowed. Framework/stage defaults and task overrides; logical notebook/environment/compute maps. Environment is not a dedicated compute pool; scheduler retries/timeouts remain distinct from runtime/startup settings. Exact precedence and versions remain review items. |

### Recovery, Releases and Ownership

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A61 | Coordination/wakeup | Metadata is authoritative for readiness and eligible dispatch; Airflow schedules/executes. Events are primary, periodic reconciliation fallback; every dispatch rechecks all dependencies. Recover eligible blocked work without waiting for the next daily cycle. |
| A62 | Idempotency/state boundary | Stable logical operation IDs, distinct attempts, atomic claims and recoverable commit tracking. SQL control-state and Delta writes are not a distributed transaction; reconcile target success before SQL confirmation without blindly repeating effects. |
| A63 | Publication/release relationship | Human review before authoritative configuration publication. Approved publication automatically starts technical validation/DAG generation/deployment without a redundant manual publication gate. Complete immutable snapshots and framework/DAG artifacts share a semantic version. |
| A64 | Release sequencing/activation/pinning | Candidate version before CI; sequential builds; failed candidates preserve last-good active deployment and allow newer valid releases. Activate after tests/deployment/Airflow recognition. New runs bind active version; in-flight runs stay pinned. Fix forward rather than activate an obsolete repaired candidate over a newer active version. |
| A65 | Incident rollback | Defined technical-health failures may automatically reactivate known-good code/configuration. Data-quality/clinical remediation requires operator approval. Rollback is auditable, does not reverse Delta data and does not silently cancel in-flight runs. |
| A66 | Human operations ownership | The user is reviewer, publisher, emergency operator and owner of email notifications. Confirm the delivery address before activation; no scheduled personal-user execution. |

### Retention, Benchmarking, Diagnostics and Cost

| ID | Decision | Recorded choice |
| --- | --- | --- |
| A67 | Generator retention/holds | Completed exports/manifests: five days, only with confirmed ingestion and no unfinished/recovery dependency. Protect current population, identity map and latest successful checkpoint until verified replacements exist. |
| A68 | Ingested Fabric retention | Keep ingested Bronze/Silver data indefinitely without automatic age purge. This does not require archiving every generator file or indefinitely keeping temporary staging, diagnostics or all Delta historical versions. |
| A69 | Staging and diagnostic retention | Completed Fabric staging: five days after publication/recovery checks. Diagnostic and benchmark artifacts: 30 days. Do not apply these durations to indefinite ingested data or protected referenced evidence. |
| A70 | Referenced control/release evidence | Retain commit/idempotency evidence, immutable releases and images while data/runs reference them. Terraform state is separately non-expiring. Exact safe cleanup/reference rules remain R51-R52. |
| A71 | Isolated profiling protocol | Explicit separate benchmark invocation with frozen input/reference snapshots; initial materialization outside timing; full-column Delta materialization and versioned re-read between functions. No production publication/watermark advance. Disabled profiling introduces no profiling actions; DEBUG does not enable it. |
| A72 | Benchmark limits | One warm-up, three measured trials, 30-minute per-case limit. Warm-ups/failures are not successful measured samples; generator attempt limits are separate. |
| A73 | Benchmark evidence/interpretation | Keep distinct run/trial/step/attempt and repeated-function identities, code/configuration/input/compute versions, UTC times and monotonic plan/materialization/elapsed seconds. Measurements include I/O and optimization-boundary effects; confirm changes in normal end-to-end runs. Exact storage/schema remains reviewed. |
| A74 | Spark metric/diagnostic scope | Preserve the planned 50-field comparison contract and separate application/attempt grain. Unsupported/unavailable values are null with reasons, not invented zeroes/anomaly predictions; no UI scraping or attribution of application totals to every function/table. |
| A75 | Shared logging and central route | Shared correlated sanitized logging, supported driver bridge/emitter/API collection and filtered events/metrics to Log Analytics through supported Log Ingestion configuration. No patient rows/secrets in logs or Spark actions solely for logging. Console output alone is not proof of ingestion; exact logger/emitter design remains R44-R47. |
| A76 | Alert scope | Failures including pre-Spark/Copy-only failures, dependency blocks, missed availability, freshness, telemetry gaps, comparable duration regression and sustained memory pressure. Separate diagnostic retries from ingestion outcome; initial failure notification need not wait for evidence collection. Exact rules/thresholds/cardinality remain R48-R49. |
| A77 | Future volume monitoring | UCL = historical mean + 2 standard deviations; LCL = historical mean - 2 standard deviations. Implementation and baseline/breach semantics are deferred; no new zero-change failure/readiness gate. |
| A78 | Accepted whole-demo estimate | Accepted for planning: normal USD/30-day additional spend $46.33-$55.49 ($51.87-$55.49 without unused job/log allowances); recommend $60/month. Existing F32 bill excluded; conditional $0 extra Fabric compute assumes unchanged paid uptime/size/headroom and no paid on-demand/autoscale. Initial seed/taxes/paid CI excluded; retention grows storage. This is not a hard cap or final Terraform-plan approval. |
| A79 | Generator spend controls | Approximately $10/month generator-only planning target with $8/$10 notifications, not shutdown, a fixed fee or the whole-platform budget. Registry was already included in the generation illustration; free grants are conditional, not guaranteed. |
| A80 | Release acceptance | Local tests/lint/build plus applicable live SQL/catalog, Terraform and deployed Fabric checks; prove full/incremental/replay correctness, source-to-Bronze reconciliation, Patient Silver, benchmark isolation and alert delivery. Re-deployment must be non-destructive. Stop at A01-A02. |

## All Remaining Review Decisions

Every R-series row is **review required**, even where the existing proposal is
specific. Directions already approved in A/B are not reopened. A physical design
must supply the details below before that review can approve implementation;
listing the requirement here does not pretend the design already exists.

### Revised Physical Metadata and Configuration

| ID | Decision to review | Existing direction/proposal and exact remaining question | Gates |
| --- | --- | --- | --- |
| R01 | Complete revised physical dictionaries | Supply every table/column's purpose, SQL type/precision, nullability, PK/FK/UQ, index, grain and lifecycle for task/dataset/input, configuration, history, readiness/events and releases. Reconcile the baseline; do not claim its 17-table count is final. | D01 |
| R02 | Operational reuse and relational integrity | Decide which existing ops tables fit general tasks and which need adaptation/new roles; retain ingestion batch/watermark lineage, cross-run/mapping consistency, stable IDs and protected history. Review correlated/composite constraints and no cascading loss of referenced evidence. | D01 |
| R03 | Dataset producer/output identity | Define one authoritative producer per applicable release/window, multiple-output and metadata-only task treatment, producer uniqueness, missing/ambiguous input rejection and exceptional ordering edges. | D01, D04 |
| R04 | Function JSON and legacy step migration | Define JSON field/parameter schemas, stable step occurrence identity, repeated ordinals, auxiliary dataset aliases/frozen references and evolving-schema validation. Preserve old step/error/profiling FKs/history before retiring `TransformationStep`. | D01, D06 |
| R05 | Effective-setting precedence | Define field-by-field framework/stage/pipeline/domain/task/permitted-run precedence, null/override semantics and allowed settings. Separate startup-only runtime configuration, compute and scheduler retry/timeout policy. | D01, D09 |
| R06 | Status/history/readiness schema | Define transitions for queued/running/blocked/failed/committed/no-change/abandoned work, attempts versus logical operations, current readiness versus history, expected execution and protected older/newer-window ordering. Status names beyond recorded requirements are not approved here. | D01, D04-D05 |
| R07 | Frozen configuration and publication transactions | Define snapshot/revision/hash relationships, atomic reviewed publication, immutable run binding and resource/code identity. Prevent mixed revisions or runtime configuration edits; approve the corresponding SQL interfaces. | D01, D10 |

### Source Schemas, Mapping and Capture

| ID | Decision to review | Existing direction/proposal and exact remaining question | Gates |
| --- | --- | --- | --- |
| R08 | Synthea export/mapping coverage | Compare CSV/FHIR coverage and supply executable mappings for all approved fields, units, nulls, relationships and controlled mutations. Identify supplemental operational/test rules explicitly; do not change dictionaries silently. | D05, D09 |
| R09 | Stable keys and source histories | Define deterministic seed/key allocation, shared identity manifest, dependency-ordered loaders, source-specific audits/soft deletes, Type 2 expirations/non-overlap and fact/dimension consistency. Prove independent restart without cross-source ETL. | D05 |
| R10 | Repeatable SQL migrations/write paths | Complete filtered/composite/temporal integrity, indexes, audit mutation and upgrade scripts recorded in `database\README.md`. Empty-database baselines are not repeatable upgrade migrations or proof of live catalog integrity. | D05, D07 |
| R11 | Partial generator/loader recovery | Define per-source transactions/checkpoints, manifest states, failure/retry classification and restart/idempotency. Separate exported files, validated mapped records and successfully committed SQL publication. | D05 |
| R12 | Cross-source checkpoint coordination | Define which source checkpoints are complete/eligible, shared-manifest consistency and protection against overlap/catch-up races. Keep missing/failed checkpoint impact limited to affected consumers; serial loading alone is not a completion protocol. | D04-D05 |
| R13 | Incremental extraction boundary | Review the proposed inclusive-lower/exclusive-upper interval, overlap amount, exact SQL timestamp/tie handling and retained bounds. Define safe committed-source evidence/concurrent-write assumptions; timestamp watermarks alone do not capture arbitrary late commits or physical deletes. | D01, D05 |
| R14 | Reconciliation scope and tolerance | Specify initial/full, captured incremental batch and committed target check scopes; counts/hashes/rejects/keys and permitted tolerances. Compare a source to its own publication, not total accumulated Bronze; define what must pass before state advances. | D01, D05-D06 |
| R15 | Legitimately empty and rejected input | List empty-table expectations beyond nonempty initial Patient/DimPatient, validation/rejection disposition, restart behavior and whether rejected records prevent publication. Conflicting Patient ties still fail under A51. | D04-D06 |

### Discovery and Evidence

| ID | Decision to review | Existing direction/proposal and exact remaining question | Gates |
| --- | --- | --- | --- |
| R16 | Discovery integration/concurrency/retries | Define shared child workflow, selected-table scheduling, parallelism, timeouts, bounded transient retries and prompt per-table dispatch. One full pass is settled; deterministic drift is not a transient retry. | D02-D03 |
| R17 | Unavailable/unpersisted evidence | Proposed fail-closed: missing metadata access, failed connection or evidence persistence cannot authorize extraction. Review actual PASS/FAIL/UNAVAILABLE persistence, attempt status, retry/fatal scope and notification behavior; Strict approval alone did not approve this protocol. | D01, D03 |
| R18 | Discovery-to-extraction DDL gap | Choose and document exact controlled-DDL/capture assumptions and staged checks. Decide whether a lightweight extra live check is necessary; no duplicate full discovery scan or unsupported claim that Spark types prove exact SQL catalog properties. | D03, D05 |
| R19 | Schema fingerprint/comparison implementation | Define canonical SQL identifier, type, byte/character length, `max`, nullability, precision and ordered-key handling, approved projections and `_ingest_` collision checks. Freeze/hash exact source contracts before Spark conversion. | D01, D03 |
| R20 | Discovery check evidence | Review success/failure records, metadata-only snapshots/differences, correlation, check names/phases and schema/configuration revisions. Require current persisted evidence, not a previous attempt's PASS; decide retention without losing referenced capture/replay evidence. | D01, D03, D12 |
| R21 | Saved-batch compatibility | Define replay checks against captured schema/contract and approved target mapping, without requiring today's SQL schema/source access to match a saved batch. Fresh extraction always creates a new capture with fresh discovery. | D01, D03, D05 |

### Bronze Publication, Readiness and Recovery

| ID | Decision to review | Existing direction/proposal and exact remaining question | Gates |
| --- | --- | --- | --- |
| R22 | Batch-idempotent Delta publication | Select and validate the actual append/commit-evidence mechanism, stable batch identity, target-version recording and already-published handling. Preserve writer versus capture IDs; do not deduplicate business keys or reappend to relabel a retry. | D01, D05 |
| R23 | Post-Delta/pre-SQL failure recovery | Specify durable publication evidence, verification and fenced repair of SQL progress after target success. No distributed transaction/exactly-once atomicity claim; prevent duplicate append and older windows overwriting newer progress. | D01, D05 |
| R24 | Expected windows and committed readiness | Define applicable expected producer/window, committed source checkpoint/currency, compatibility and exact 24-hour/DST evaluation. Support differing cadences without one universal cycle ID; latest expected failure still blocks. No initial calendar/freshness override is being proposed. | D01, D04 |
| R25 | Zero-change commit protocol | Define how a successful no-change attempt retains data/Delta version but records verified coverage/progress/readiness. Zero count alone is insufficient; discovery and validation still apply. | D01, D04-D05 |
| R26 | Event/outbox and blocked-work persistence | Select reliable event delivery/outbox or equivalent, blocked-task state and dispatch transport. Define atomic event production, deduplication and complete readiness recheck; no event-bus product is selected by this register. | D01, D02, D11 |
| R27 | Claims, fencing and retry ownership | Define lease scope, owner/fencing token, expiry/heartbeat, takeover and release; reject stale writers. Assign scheduler/framework/SDK retries and timeouts without multiplying attempts or borrowing generator limits for all tasks. | D01-D03, D05 |
| R28 | Reconciliation fallback and recovery operations | Set reconciliation cadence, backoff/throttling, duplicate/lost-event repair, exhausted-work handling and scoped manual replay. Preserve SLA violation/availability/recovery times and new-versus-replayed batch identity. | D01, D04-D05, D11 |

### Exact Patient Silver Contract

| ID | Decision to review | Existing direction/proposal and exact remaining question | Gates |
| --- | --- | --- | --- |
| R29 | Target name and output dictionary | Confirm exact Silver schema/table and `patient_bronze_silver` mapping; enumerate every output column/type/nullability, source-field and Bronze-lineage treatment. One row per Clarity `PatientID`, not a consolidated Caboodle model. | D06 |
| R30 | Normalization/type precision | Specify the approved name fields to trim, null handling and exact SQL-to-Spark output mappings, especially `datetime2(7)` versus Spark timestamp precision. Preserve IDs/audits; no extra case folding, identifier trimming or clinical imputation is selected. | D06 |
| R31 | Deterministic ordering and duplicates | Existing proposal: newest source `ModifiedAtUtc` per `PatientID`, collapse exact duplicates, fail conflicting key/time payload ties. Review precision-safe comparison/order and any explicitly justified source tie-breaker; never choose an arbitrary survivor. | D06 |
| R32 | Merge/delete/replay semantics | Review one-row-per-key upsert, retained `IsDeleted` representation, incremental/full behavior, concurrent/out-of-order replay and commit evidence. Do not infer physical deletion from a missing incremental row. | D01, D06 |
| R33 | Patient validation/acceptance | Define casts/invalid inputs, schema/key/null checks, affected-row/reject reconciliation, idempotent reruns and failure behavior during Spark actions. Review test fixtures including exact/conflicting ties, source precision and deleted records. | D06, D12 |

### Fabric Execution, Releases and Infrastructure

| ID | Decision to review | Existing direction/proposal and exact remaining question | Gates |
| --- | --- | --- | --- |
| R34 | Logical-to-physical execution maps | Define notebook, pipeline/Copy, stage environment and compute references, same/cross-workspace transactional paths and source/target connections. Preserve logical IDs and approved workspace/capacity placement. | D01-D02, D07-D09 |
| R35 | Pinned runtimes and startup settings | Select tested compatible package, Spark/Fabric environment, Airflow and generator Java/image versions; define startup-only versus per-task settings, concurrency/session isolation and compute defaults. No automatic runtime/capacity upgrade. | D02, D09 |
| R36 | DAG task/operator generation | Specify three logical DAGs, shared discovery, dynamic/static task integration, dependency-driven dispatch, Airflow API/operator definitions and deployment recognition. Metadata remains dependency authority; do not embed a second handwritten graph. | D01-D02 |
| R37 | Release manifest/version contract | Define candidate semver, complete immutable snapshot, code/package/image/DAG/resource hashes and one-to-one framework/artifact release mapping. Validate graph, registry, parameters and maps before activation. | D01, D10 |
| R38 | Release queue and activation transactions | Define publication/build/validation/deployment/recognition outcomes, sequential claims/retries, last-good active pointer and atomic activation. Failed candidates remain historical and do not block newer valid snapshots. | D01-D02, D10 |
| R39 | In-flight artifact pinning | Prove older runs can execute their bound snapshot/code/notebook/package/image while a newer release activates. Define retained artifact/import/resource resolution rather than silently reading the latest live definition. | D01-D02, D10, D12 |
| R40 | Technical activation/health checks | Supply exact CI/local/deployed tests, recognition probes, failure signals, health thresholds and required evidence. Publication is not successful activation; a failed candidate cannot become active. | D10, D12 |
| R41 | Rollback/emergency procedures | Define known-good selection, compatibility, technical auto-rollback signals/thresholds, authorized operator data remediation/cancellation and audit trail. No automatic Delta undo or silent in-flight cancellation. | D01, D10, D12 |
| R42 | Terraform provider/state bootstrap plan | Pin per-resource providers/APIs, remote-state bootstrap/migration/locking, outputs and separate deployment credentials/roles. Document specific unsupported Fabric resources before requesting an alternative; state remains isolated/non-expiring. | D07-D08, D10 |
| R43 | Final costed infrastructure plan | Present actual Terraform changes, resolved names/identities, quota/policy/provider checks and resource/monitor quantities with refreshed cost/headroom evidence. Accepted $60 planning estimate is not apply approval, an enforced cap or approval of paid exceptions. | D07-D10 |

### Logging, Alerts, Benchmarks and Retention

| ID | Decision to review | Existing direction/proposal and exact remaining question | Gates |
| --- | --- | --- | --- |
| R44 | Shared logger/event contract | Review proposed standard-library logging, INFO/default and targeted DEBUG, idempotent handlers, scoped context, newline JSON and driver-only JVM bridge/severity mapping. Define sanitization/error fallback; logging failures must not mask original failures or alter authoritative state. | D01, D11 |
| R45 | Metric source/field matrix | Map each planned comparison field to a supported collection source, unit/type, application/attempt grain and availability reason. Define final/partial/retried snapshots and avoid fabricated anomalies or application-wide totals attributed to each step. | D01, D11 |
| R46 | API diagnostic collection | Define triggers, actual session-owning item/application/attempt/container/file attribution, pagination/offset/size/rotation/truncation handling, delayed evidence/backoff and protected/sanitized manifests. Separate collector retries/outcome from ingestion. | D01, D08, D11 |
| R47 | Emitter/DCR/DCE/table implementation | Review supported Log Ingestion emitter, filtered driver/event/metric categories, destination table/schema mappings, identities and retention/ingestion limits. Include queryable run-state/expected-schedule signals for pre-Spark, Copy-only and never-started failures. | D07-D09, D11 |
| R48 | Actual alert rules and baselines | Specify KQL, scopes, severity, evaluation/lookback, minimum history, regression multiplier/absolute increase, sustained memory thresholds and telemetry delays. Seven five-minute single-series alerts are cost assumptions, not approved final rule definitions/cardinality. | D09, D11 |
| R49 | Notification/incident lifecycle | Define email action groups, delivery/retry/deduplication, acknowledgments, escalation/recovery messages, runbooks and evidence enrichment. Send initial failure promptly; other channels/connectors are not automatically selected. | D08, D11 |
| R50 | Benchmark schema/execution details | Reconcile run/trial/step occurrence/attempt and history FKs, effective settings, snapshot/partition/cache options, timers/job attribution, interrupted records and persistence failure. Enforce frozen full-column materialization/isolation and the approved 1/3/30-minute limits. | D01, D06, D09, D12 |
| R51 | Safe staging/version/control cleanup | Define concrete containers/paths and reference-aware holds, protected current state, abandoned-run resolution, Delta historical-version/maintenance rules and control/snapshot parent retention. Indefinite data retention is not indefinite temporary or every-version retention; do not erase needed replay evidence. | D01, D05, D12 |
| R52 | Evidence/image retention and access | Define raw versus sanitized evidence, diagnostic/support permissions, image/release/reference reachability and any rejection/quarantine artifact lifecycle. Reconcile 30-day artifact retention with longer required control/replay references before deletion. | D08, D10-D12 |
| R53 | Final acceptance and handoff contract | Specify live schema/integrity/redeploy checks; full/incremental/no-change/spike, drift/isolation, interruption/replay, Patient correctness, deadline feasibility, benchmark isolation and alert delivery evidence. Provide operator runbooks and the explicit stop boundary; do not waive failed checks. | D03-D12 |

## All Concrete Inputs Still to Resolve

**Status: input required.** Resolve known selections through engineering discovery
and deployment outputs where possible. Request user input only when the authorized
value cannot be determined; no credentials, tokens or secret-bearing URLs belong here.

| ID | Input | Existing selection and remaining value |
| --- | --- | --- |
| I01 | Azure/Microsoft Entra tenant | Approved subscription is known; resolve its actual tenant and verify Fabric/SQL identity alignment. |
| I02 | Human SQL administrator identifiers | User's existing Entra account is selected; resolve and verify its object ID/tenant for both servers. |
| I03 | Deployment/migration principal | Identify the authorized execution principal and required separate permissions/authentication path; never substitute a runtime administrator grant. |
| I04 | Machine identities and role mappings | Resolve actual generator, ingestion/framework and diagnostic principal IDs/connection paths, using approved separate identities and managed identity where supported. Provisioned IDs should come from reviewed deployment outputs. |
| I05 | Administrator client firewall IP | Determine/confirm the authorized human client IP or range before applying the approved firewall policy. |
| I06 | Alert email destination | Confirm the user's actual authorized delivery address before activation; ownership does not imply a discovered address is approved for delivery. |
| I07 | Derived names, IDs and required tags | Derive remaining Airflow/environment/pipeline/notebook/container/monitoring names, resolve required tag values, validate approved-name availability and capture created workspace/item/database IDs from deployment outputs. No new names are silently replacing approved names. |
| I08 | Build/deployment execution locations | Resolve image/build publication, versioned artifact locations, Terraform backend and local/CI runner/auth paths under the approved user-owned release model; no paid runner/CI license is assumed approved. |

## All Engineering Checks Before Deployment or Activation

**Status: verification required.** These are execution/evidence tasks, not unsettled
routine user choices. Check only dependencies needed by the relevant operation.

| ID | Check | Required evidence |
| --- | --- | --- |
| V01 | Target/name availability | Validate SQL server, registry, storage and Fabric workspace/item names; review necessary replacements before deployment. |
| V02 | Regional service/feature support and quota | Verify selected Azure/Fabric services/SKUs/features/providers in East US and West US 3, plus relevant quotas and tenant settings. |
| V03 | Existing capacity assignment/headroom | Verify access to the selected capacity, workspace assignment rights and concurrent workload headroom; no capacity creation/resize/relocation. |
| V04 | Provider/API coverage | Test/pin actual per-resource Terraform/API/auth capabilities, including schemas-enabled lakehouses and Airflow/control SQL. Report specific gaps before any exception. |
| V05 | Deployment/admin/runtime permissions | Verify the exact Entra administrator and separate deployment/migration/generator/ingestion/collector permission paths, including transactional control SQL access. |
| V06 | Network/policy/cross-region connectivity | Test approved public authenticated SQL/Blob/registry and Fabric paths and applicable organizational policy; validate East US-to-West US 3 transfer assumptions. Private-policy exceptions require revised costed approval. |
| V07 | State/bootstrap protection | Verify remote-state isolation, locking/bootstrap recovery, no generator access and exemption from all generator cleanup. |
| V08 | Source catalog/integrity/redeployment | Compare deployed catalogs to all approved dictionaries; exercise constraints, audits/histories, deterministic load/restart and non-destructive repeat migrations. |
| V09 | Generator image/runtime/performance | Test pinned Synthea/mappings/loaders, memory/cold start and normal/initial/spike runtime on the approved pilot; review changes before exceeding approved sizing/limits. |
| V10 | Capture/readiness/publication recovery | Prove checkpoint completeness, drift evidence, exclusive/fenced writes, no-change coverage, batch replay, post-Delta/pre-SQL repair and old-window protection. |
| V11 | Fabric resource/session compatibility | Test actual Copy/notebook/Airflow identities, environment/package/runtime settings, namespace/resource mapping and concurrent-session isolation. |
| V12 | Availability/benchmark feasibility | Measure discovery, waits, extraction, validation, publication and Patient Silver against the 10-to-11 AM target; prove isolated full-column benchmarks and supported attribution without production state changes. |
| V13 | Monitoring and notification delivery | Prove structured events/metrics reach intended tables, supported API evidence attribution, pre-Spark failure coverage, bounded collector retry, deduplication, actual email delivery and recovery escalation. |
| V14 | Final measured usage/cost and plan | Refresh job duration, free-grant eligibility, storage/log/rule/cardinality/build/transfer assumptions; review Terraform changes/costs and deployed release/rollback acceptance before apply/activation. |

## Deferred Decisions and Explicit Non-Scope

| ID | Area | Current decision and later work |
| --- | --- | --- |
| F01 | Additional Silver and consolidated patients | Do not implement further Silver 1/2 domains or cross-source patient consolidation now; require separate domain/input/output contracts later. |
| F02 | Gold and analytics | Gold, semantic models, dashboards and reporting are outside this delivery despite future-compatible dataset registration. |
| F03 | Streaming and external change capture | Future streaming schema/checkpoint rules, CDC/Change Tracking, physical-delete capture and capture of every intermediate mutation need separate designs; source checkpoints cover this controlled simulator only. |
| F04 | Production volume/environments | Hospital-scale volumes and QA/prod/enterprise rollout are not prerequisites for the demo; later scale/isolation/policy/cost review is separate. |
| F05 | Processed-record statistical monitoring | Formula is settled; metric grain/comparable population, lookback, minimum samples, deviation calculation, negative LCL and breach response remain deferred. No new failure/readiness gate. |
| F06 | Extra calendar/consumer policies | Framework supports differing cadences/freshness overrides; none are selected initially. Review holidays/optional inputs/override values only if later scope needs them. |
| F07 | Optional performance/maintenance features | Native acceleration, cache/session sharing, compaction/file layout/V-order and VACUUM settings require compatible measured review; no mandatory runtime upgrade, blind tuning or unsafe replay cleanup. |
| F08 | Extra paid/preview/platform services | No private-networking redesign, extra capacity, paid on-demand/autoscale, paid CI license, additional notification channel or mandatory preview collector is approved by the existing cost estimate. Review specific exceptions if needed. |

## Superseded or Explicitly Excluded Patterns

These include historical proposals and excluded interpretations; not every row was
a user request. Preserve the current replacement rather than infer broader approval.

| ID | Earlier proposal / excluded interpretation | Current replacement |
| --- | --- | --- |
| H01 | Clarity-to-Caboodle population ETL | Independent loaders sharing stable synthetic identities. |
| H02 | Azure SQL control database | Fabric SQL Database in the dedicated metadata workspace. |
| H03 | Source-specific Fabric workspaces/lakehouses | Shared Clarity/Caboodle Bronze lakehouse; separate metadata/data workspaces and separate Silver lakehouse. |
| H04 | 100,000-patient / 50,000-daily-change / larger source-SQL baseline | Approved 1,000-patient / 500-1,000-combined-change demo and S0 per source. |
| H05 | Business-key merge or payload deduplication in Bronze | Append observations across distinct batches; publication idempotency per captured batch; latest-state work in Silver. |
| H06 | One normalized `TransformationStep` target row per function and pipeline input/output layers | Task JSON function array; task/dataset/input revision; preserve historical attribution before migration. |
| H07 | Monolithic DAG, live SQL dependency definitions on every parse, redundant publication approval | Smaller domain DAGs, immutable snapshots and automatic release processing after reviewed publication. |
| H08 | Fixed EST year-round, arbitrary extra ingestion start gate or mandatory second full discovery scan | DST-aware 10 AM/11 AM Eastern policy, prompt eligible dispatch and one full source pass. |
| H09 | Approximately $10 as a guaranteed bill/whole-platform budget or unrestricted rollback | Generator-only planning target; accepted whole-demo estimate is separate. Technical code/config rollback is bounded/audited; data remediation remains operator-owned. |

## Review Source of Truth and Change Control

Source records remain unchanged:
`discussions\discussed-changes.md` and `discussions\discussion-02.md`.
Current choices also come from `docs\architecture\source-model-approval.md`,
`.azure\deployment-plan.md` and the intentionally ignored root `plan.md`.
Physical review requirements are reconciled from
`docs\ingestion\metadata-design.md`, `docs\ingestion\schema-discovery-design.md`,
`docs\ingestion\task-dataset-design.md`, `docs\architecture\orchestration-design.md`
and `database\README.md`.

Record future approvals against the applicable R/I/V IDs and corresponding concrete
artifacts; revise their status only after explicit approval or actual verification.
Do not infer permission to migrate, publish, create resources, apply Terraform or
activate alerts from the presence of this register. Existing D/B IDs below remain
stable for references elsewhere in the repository.

## User Choices and Review Gates

| ID | Decision / review area | Approved direction and remaining review / verification | Needed before |
| --- | --- | --- | --- |
| D01 | Revised framework schema and state-protocol approval | Review the revised task/dataset/input/function-array model, operational-table reuse, keys/constraints, release snapshots, readiness/events, and SQL/Delta recovery protocol once their physical design is prepared. The original 17-table dictionary alone is no longer sufficient. | Framework/control-store and dependent runtime implementation |
| D02 | Airflow hosting and workflow boundaries | **Approved B01:** a new Fabric-managed Airflow job in `healthcare-data-ingestion-data` on existing `uswest3capacity`, with Clarity Bronze, Caboodle Bronze and Patient Silver logical DAGs/shared discovery. User-owned operations and project-prefix name derivation are selected. Exact integration/resource mappings and supported defaults need engineering verification/design review; no provisioning yet. | Airflow integration/infrastructure implementation |
| D03 | Schema compatibility and discovery consistency | **Strict remains approved:** affected-table isolation, no allowlist/auto-evolution and no duplicate full discovery pass. **B04-B05 approved** for missing required checkpoint blocking and generator execution/retry limits; do not misapply the generator's 45-minute timeout to every Fabric task. Exact discovery concurrency/timeouts, unavailable-evidence persistence and optional lightweight recheck/DDL consistency belong to engineering design review, not a new routine setup question. | Discovery runtime |
| D04 | Cadence, source currency, and dependency windows | **Approved:** daily 10:00 AM Eastern ingestion, 11:00 AM deadline, both daylight-saving-aware; 24 elapsed-hour committed-coverage freshness; verified zero-change incrementals succeed. **B04/B07 approved:** no initial calendar exceptions, freshness overrides or optional Patient inputs; initial Patient/PatientDim loads nonempty, other empty tables need reviewed expectations. Latest expected upstream failure blocks affected consumers; deadline misses alert but late recovery continues. Exact window/coverage/state rules and one-hour feasibility need design/benchmarks. | Readiness policy/configuration and first scheduled flows |
| D05 | Source capture and mutation consistency | **B04/B06 approved:** daily generation at 12:00 UTC (7:00 AM Eastern standard / 8:00 AM daylight time), continuing cohort with pinned versions, full seed then checkpoint-based incrementals, no overlapping writes, and affected-consumer blocking/alerts for failed or missing required checkpoints. Late recovery continues. Exact commit/capture boundaries, partial-load recovery, replay evidence and lease/checkpoint mechanisms require physical design review; stronger capture/scope changes need specific approval. | Generator change scenarios and extraction runtime |
| D06 | Patient Silver contract | **B07 approved:** trim surrounding name whitespace, preserve identifiers/audits/soft-delete flags, and fail conflicting key/time ties rather than choose arbitrary payloads. **Exact output schema, timestamp precision, deduplication/write/delete implementation still require contract review.** No cross-source patient consolidation or extra Silver domains. | Patient transformation/write implementation |
| D07 | Azure/Fabric targets and environment rollout | **Resource-group name approved November 20: `healthcare-data-ingestion-rg`** for both source SQL infrastructures and generator/supporting Azure resources. **Subscription selected: `ME-MngEnvMCAP372892-rharrington-1`**, the user's sole enabled subscription, verified read-only; its ID is recorded in `.azure\deployment-plan.md`. **Azure region selected November 20: East US (`eastus`)** for the resource group and new regional Azure resources. **Existing Fabric capacity selected November 20 for both metadata and data/ingestion workspaces: `uswest3capacity`, discovered F32, West US 3**; ID recorded in the deployment plan. **Workspace names approved November 20: `healthcare-data-ingestion-metadata` for metadata/control, and `healthcare-data-ingestion-data` for pipelines, notebooks, Bronze and Silver. Fabric SQL database name approved: `healthcare-data-ingestion-metadata-db` in the metadata workspace. Lakehouse names approved: `healthcare_data_ingestion_bronze` and `healthcare_data_ingestion_silver`, both in the data workspace. Azure SQL names approved: `healthcare-data-ingestion-clarity-sql` / `Clarity` and `healthcare-data-ingestion-caboodle-sql` / `Caboodle`.** Preserve shared Clarity/Caboodle Bronze and the initial Clarity Patient-only Silver scope. Do not create, resize or relocate capacity. Confirm tenant, name availability and assignment permissions/headroom. B01 approves demo-only rollout, Airflow in the data workspace on existing capacity, project-prefix derivation of remaining names and isolated non-expiring Terraform state. Server-name availability remains unchecked; review any necessary name change before deployment. Validate cross-region connectivity/cost assumptions before deployment. Terraform owns Azure infrastructure; report provider gaps and obtain approval before non-Terraform exceptions. Naming does not approve the physical framework schema or SQL administrator; target selection does not authorize deployment or perform workspace assignment. Logical IDs stay stable regardless. | Infrastructure generation/deployment for those targets |
| D08 | Identities, connectivity, and constraints | **B02-B03 approved:** public authenticated endpoints, Entra-only SQL, no anonymous Blob/registry access, SQL's Azure-services firewall exception plus approved administrator client IP; its cross-subscription/tenant scope was disclosed. Use separate scoped machine identities, managed identities where supported/validated: generator source read/write, ingestion source read-only, target/control-store writes and separate deployment/migration permissions. The user is human SQL administrator, not the runtime identity. Actual tenant/principals/client IP, permission paths and policy/connectivity checks remain engineering inputs; policy-required private networking needs revised costed approval. No access assigned. | Identity/network integration and provisioning |
| D09 | Scale, compute, and spend bounds | **B05-B06 approved**, retaining 1,000 patients, 12-month source history, 500-1,000 combined daily changes and S0 evaluation baseline. Consumption generator pilot: 2 vCPUs/4 GiB, one worker/execution, serialized loaders, 45-minute attempt timeout, one transient retry; Massachusetts/default mixed-age profile and continuing cohort. Existing supported Fabric/Airflow defaults, no automatic resizing. Generator alerts at $8/$10 are not a hard cap or total-platform budget. Initial-seed performance, supported defaults, benchmarks and refreshed total cost require verification/review before apply. | Sized infrastructure, seed execution, and Spark deployment |
| D10 | CI/CD ownership, activation, and rollback rules | **B09 approved:** the user reviews, publishes and handles emergency operations; existing/local and deployed acceptance/health checks precede activation; pin images/releases and retain referenced images. Approved metadata publication still triggers automation without a second publication gate. Review Terraform plans before apply. Automatic rollback is limited to reviewed technical-health failures; data-quality/clinical remediation is operator-owned. Exact health checks/triggers/thresholds remain part of physical design review. | CI/CD/rollback implementation and activation |
| D11 | Notifications and operational ownership | **B08 approved:** user-owned email alerts for failures, dependency blocks, missed deadlines, freshness and telemetry gaps; confirm delivery address in deployment settings before activation. Events remain primary with reconciliation fallback; exact delivery/retry/escalation mechanics need engineering review/testing. Future processed-record UCL/LCL (mean plus/minus 2 standard deviations) remains deferred; baseline/history/LCL/breach details belong to its later activation, not new initial-demo choices. | Recovery/alert routing and scheduled activation |
| D12 | Retention, replay, and acceptance limits | **B05/B08-B09 approved:** generator exports/manifests five days with ingestion/recovery holds; current generator state protected until verified replacement; ingested Fabric data indefinite, preserving Bronze append and Silver merge/delete semantics. Completed Fabric staging: five days after confirmed publication/recovery checks. Diagnostic/benchmark artifacts: 30 days. Keep commit/idempotency evidence, release artifacts/images while referenced. Benchmarks: one warm-up, three measured trials, 30-minute case limit. Exact cleanup/replay/state evidence and technical-health checks need review; operator-owned data remediation does not automatically reverse Delta changes. | Cleanup, benchmark/monitor activation, and final acceptance |

Record environment-specific values in the appropriate deployment settings, not as
credentials in this document. No suggested value is selected on your behalf.

## Consolidated Setup Decisions: Approved Batch

The user approved **all nine setup/operating groups B01-B09 on November 20** with
"I approve all." This closes routine initial-demo setup choices rather than
requiring one question per resource name or implementation parameter.
The detailed D01-D12 register remains the gate/reference map, not twelve wholly
undecided architectural choices.

Final revised framework/state-protocol and exact Patient Silver schema reviews,
plus final infrastructure/Terraform-plan approval, remain separate. Account/tenant
resolution, name availability, provider coverage, service support, permissions,
capacity headroom and benchmarks are engineering checks, not requests to reapprove
known selections. Any exception or material cost/scope change discovered by those
checks needs specific approval.

| Batch ID | Decision group | Approved direction for the initial demo | Related gates |
| --- | --- | --- | --- |
| B01 | Rollout, placement and remaining names | One demo environment, no QA/prod rollout. Put the new Airflow job in `healthcare-data-ingestion-data` on existing `uswest3capacity`; use Clarity Bronze, Caboodle Bronze and Patient Silver logical DAGs with shared discovery. Derive remaining valid names from the project prefix without changing approved names. Keep Terraform state in an isolated, restricted, non-expiring `terraform-state` container, outside generator cleanup and runtime access. | D02, D07 |
| B02 | Network policy | Public authenticated endpoints for this synthetic demo, retaining Entra-only SQL and no anonymous storage/registry access, are approved. SQL's Azure-services firewall exception plus the human administrator's approved client IP is approved with its disclosed cross-subscription/tenant network scope; authentication remains separate. This policy approval does not configure the rule or authorize deployment. If organization policy requires private networking, stop for a revised costed design, not an automatic SKU/network change. | D07-D08 |
| B03 | Runtime permissions | Separate machine identities, preferring managed identities where supported and validated. Generator: scoped read/write on source tables, its own Blob containers and registry image pull. Fabric ingestion: source read-only, target writes and scoped transactional control-store interfaces. Keep deployment/migration permissions separate; never run scheduled workloads as the user's administrator account or grant runtime SQL administrator access. | D08 |
| B04 | Schedule, readiness and capture recovery | Generate daily at 12:00 UTC, which is 7:00 AM Eastern in standard time and 8:00 AM in daylight time; preserve the approved 10:00 AM Eastern ingestion and 11:00 AM deadline. Preserve the cohort, full seed then checkpoint-based incrementals, and prevent overlapping writes. Missing/failed required checkpoints block only affected consumers and alert; useful recovery continues. No calendar exceptions, freshness overrides or optional Patient inputs initially. Exact capture/state mechanics remain for review. | D03-D05, D11 |
| B05 | Compute, retries, budgets and benchmark limits | Evaluate the generator at 2 vCPUs/4 GiB, one worker, one execution at a time, a 45-minute per-attempt timeout and one transient-failure retry; serialize source-loader work. Use supported Fabric/Airflow defaults on existing capacity, then benchmark rather than resize automatically. Warn at $8/$10 monthly generator spend, not a shutdown or whole-platform cap; refresh total costs before apply. Isolated benchmarks: one warm-up, three measured trials and a 30-minute per-case limit. Initial seed/runtime changes require a separate measured/costed review. | D03, D09, D11-D12 |
| B06 | Synthetic clinical profile and continuity | Use Synthea's Massachusetts/default demographic and clinical mix, including mixed ages, rather than a custom prevalence model. Keep and advance the same cohort with the already approved new-patient/mutation scenarios and stable shared identities. Preserve independently populated sources; pin generator/mapping versions. This is demo data, not a claim of hospital/clinical representativeness. | D05, D09 |
| B07 | Empty-load and Patient Silver policy | Initial core Patient/PatientDim loads must be nonempty; other legitimately empty tables need a reviewed expectation. Keep approved zero-change incremental success and Strict drift behavior. For Patient Silver, trim surrounding name whitespace, preserve identifiers/audits and soft-delete flags, and fail conflicting key/time ties instead of choosing an arbitrary payload. Exact output columns, timestamp precision and write/deduplication rules require the separate contract review. | D03-D04, D06 |
| B08 | Operations, notifications and remaining retention | The user owns email alerts; obtain/confirm the delivery address in deployment settings before activation. Retain diagnostic/benchmark artifacts for 30 days. Keep completed Fabric extraction staging for five days only after confirmed publication and recovery checks; do not apply this to indefinite Bronze/Silver data retention. Keep commit/idempotency evidence and released artifacts while retained data/runs reference them. Alert on failures, dependency blocks, missed deadlines, freshness and telemetry gaps; future volume UCL/LCL activation remains deferred. | D11-D12 |
| B09 | Publication, deployment and rollback ownership | The user is reviewer, publisher and emergency operator. Require existing local checks plus relevant deployed acceptance/health checks, pin images/releases, and retain referenced images for rollback. Approved metadata publication still launches automated release processing without a second manual publication gate. Review Terraform plans before apply. Automatic rollback is limited to reviewed technical-health failures; data-quality/clinical remediation or cancellation remains an operator decision. Exact checks/triggers are part of the separate design review. | D10, D12 |

Reference checks for the approved batch: Container Apps Jobs schedules use UTC, and their
retry/timeout/parallelism settings are distinct from application checkpoint recovery;
SQL's Azure-services firewall exception is not subscription-scoped; Synthea's default
demographics use Massachusetts Census data. These checks do not prove tenant-specific
connectivity, permission paths, worker performance or deployment readiness.

## Synthea Generation: Chosen Direction and Remaining Decisions

November 20: **Synthea plus versioned mapping configuration to load the approved
Azure SQL models is selected.** Preserve independent source loaders and shared stable
identities; this is not Clarity-to-Caboodle ETL. A mapping file is configuration for an
executable loader, not a standalone SQL loading mechanism. Mapping coverage, loader
design and supporting infrastructure still need review.

The user prioritizes **low generation cost**, not maximum parallel throughput.
November 20 follow-up selects **Azure Container Apps Jobs on Consumption** for Synthea
and the independent SQL loaders, with **approximately $10/month as the generation
planning target**. This is not a fixed subscription fee, an enforced spending cap or
the total platform budget. Include compute, storage, image registry, logging and
networking when validating actual cost; subscription-shared free grants do not
guarantee free compute. Host selection does not authorize provisioning.

The latest scope clarification is **demo-first, not actual hospital-volume simulation**.
Keep correctness, recovery and the approved observability/isolated benchmark scope;
do not make production-scale data volume a prerequisite for the demo.

| Choice | Current position / approval and remaining work | Related gate |
| --- | --- | --- |
| Execution host | **Selected November 20: Azure Container Apps Jobs on Consumption.** Package Synthea, a compatible Java runtime and executable mapping/loaders as a run-to-completion job. Fabric-native generation and Batch are retained below as comparison context, not active host-selection questions. Fabric Airflow hosting is a separate decision. | D07-D09 |
| Container registry | **Approved November 20:** Basic Azure Container Registry `hcingestionacr`, Terraform-managed in East US under `healthcare-data-ingestion-rg`, for the generator/loader image. Name availability and identity/network details remain unchecked. Approximately $5 base fee for 30 days was included in the earlier approximately $10 generator planning target; builds, extra storage and transfer may add charges. No provisioning is approved. | D07-D09 |
| Population and daily workload | **Approved:** 1,000 initial patients, 12 months retained history and approximately 500-1,000 combined daily source-row changes with the controlled profile below. These are demo targets, not exact Synthea counts or hard row limits. They supersede the earlier 100,000-patient / 50,000-daily-change recommendation. | D09 |
| Clinical profile | **B06 approved:** Massachusetts/default Synthea profile, mixed ages, no custom prevalence model, retaining the 12-month source-history profile. Source-field supplements and controlled mutation mappings still need engineering review. | D05, D09 |
| Population continuity | **B06 approved:** retain and advance the same cohort with stable identities, approved additions/mutations and pinned versions. Prepare deterministic seed/catch-up/checkpoint mechanics for review. | D05 |
| Early schedule and late completion | **B04 approved:** 12:00 UTC daily generation; failed/missing required checkpoints block/alert affected consumers, prevent overlap and continue useful recovery. The 10:00 AM Eastern ingestion/11:00 AM deadline remain daylight-saving-aware. Actual completion feasibility and checkpoint protocol still need verification/review. | D04-D05, D11 |
| Durable state and retention | **Approved:** Standard/Hot/LRS Blob Storage `hcingestionstore`, Terraform-managed in East US under `healthcare-data-ingestion-rg`, anonymous access disabled. Generator exports/manifests: five days with confirmed-ingestion/recovery holds; current population/identity/checkpoint state until verified replacement; ingested Fabric data indefinite. **B01-B08 approve name derivation, access and remaining retention policies.** Actual names/availability, cleanup and checkpoint implementation require engineering verification/review; no resources deployed. | D07-D08, D12 |
| Compute and spending | **B05 approved:** 2-vCPU/4-GiB generator pilot, one worker/execution, serialized loaders, 45-minute attempts, one transient retry and $8/$10 generator alerts, not shutdown. S0 remains the SQL evaluation baseline. Measure runtime/cold starts/supporting costs and review initial-seed changes/refreshed costs before apply; no throughput or approximately $10 fixed-bill guarantee. | D08-D09 |

### Approved Demo Profile: November 20

| Measure | Approved demo target |
| --- | --- |
| Initial population | 1,000 patients |
| Retained clinical history | 12 months; measure actual exported/source size |
| New patients per normal day | About 5 |
| Existing patient demographic updates per normal day | About 10 |
| New encounters per normal day | About 25 |
| Total inserted/updated source rows per normal day | Approximately 500-1,000 across both databases, including related clinical rows, dimension-history changes and the patient/encounter components above; not per table or per database |
| Deliberate recovery/data-change examples | Around 3-5 corrections and 1-2 eligible soft deletes within the total; preserve relationships and source audit/history rules |
| On-demand scenario profiles | Verified zero-change run and approximately 5,000-row spike, separate from the normal profile |

These are controlled demo-workload targets, not clinical prevalence estimates, native
Synthea output guarantees or hard truncation limits. Use Synthea for patient histories
and reviewed supplemental rules for deterministic demo mutations and missing source
fields. Natural activity and newly introduced patient history may change row counts;
measure and tune the profile rather than discard required history to meet a quota.
Reference tables may legitimately have no daily changes. Preserve common identities,
but do not require equal Clarity/Caboodle row counts.

Engineering deliverables, not extra low-level choices for the user: compare CSV/FHIR
coverage, prepare versioned mapping files and controlled SQL loaders, stable key
allocation, dependency-ordered loads, source-specific audit/history/delete handling,
per-source restart/idempotency and validation evidence. Review missing source fields and
supplemental generation explicitly. Neither a saved Synthea population nor exported
files alone prove successful SQL publication.

### Selected Generation Host and Planning Cost: November 20

Use **Azure Container Apps Jobs on Consumption**. The user selected this host after
the three-way cost comparison. The approximately **$10/month** target refers to normal
daily generation and loading plus the estimated supporting services, not Azure SQL
or Fabric ingestion costs.

The prior East US/USD estimate assumed 30 runs/month, 30 minutes/run, 2 vCPUs and
4 GiB, with a new Basic container registry and small storage/logging allowances.
It estimated $6-$10/month depending on available subscription-shared free grants.
These are unmeasured runtime/resource assumptions and planning allowances, not a
deployment quote or guaranteed bill. The initial historical seed, private networking
and taxes were excluded. East US (`eastus`) is now the selected Azure region. Basic
registry `hcingestionacr` is approved; its name availability/access configuration,
concrete storage/identity resolution and implementation still need verification.
B01-B09 now approve the 2-vCPU/4-GiB evaluation profile, 45-minute attempt limit,
one transient retry, serialized loading and $8/$10 generator alerts. The prior
30-minute estimate is retained as historical context, not current deployment approval.

### Updated Whole-Demo Cost Estimate: November 20, 2026

**Recommend $60/month of additional spending for planning**, with an illustrative
normal range of **$46.33-$55.49 per 30 days**. Without unused job/log free allowances,
normal 30-45-minute daily executions give approximately **$51.87-$55.49**.
The user accepted this estimate for planning on November 20.
This is a public retail calculation, not an actual bill, negotiated quote, approved
whole-platform spending cap or approval to deploy.

Azure resources are priced in East US; Fabric storage uses West US 3, matching the
selected existing capacity. The existing F32 capacity bill is excluded. Airflow,
Spark, Copy and metadata SQL compute add **$0 to the capacity bill only if existing
paid capacity/headroom suffices without more uptime, resizing or separately billed
on-demand/autoscale usage**. They still consume capacity.

| Component | Quantity / assumption | Additional USD / 30 days |
| --- | --- | --- |
| Clarity and Caboodle source SQL | Two continuously provisioned S0 databases at $0.4839/database/day | $29.03 |
| Container Apps Jobs compute | 30 executions at 2 vCPUs/4 GiB, averaging 30-45 minutes; free allowances conditional | $0.00-$4.86 |
| Basic ACR | One registry at $0.1666/day; image builds/extra storage separate | $5.00 |
| Generator Blob storage / Terraform state | Average 10 GB Hot LRS; 10K write/list operations and 10K reads | $0.26 |
| Fabric data / metadata storage | Average 10 GB Hot OneLake, 1 GB billable SQL data and 1 GB billable excess backups | $0.54 |
| Analytics log ingestion | 1 GB/month; $2.30/GB paid tier, unused free allowance conditional | $0.00-$2.30 |
| Log-alert evaluation | Seven alert time series at five-minute frequency, $1.50/month each; no extra dimension splitting | $10.50 |
| Builds / additional transactions / cross-region transfer | Planning allowance, not a validated usage quantity or guaranteed maximum | $1.00-$3.00 |
| Existing Fabric compute | Existing F32 bill and capacity changes excluded; conditional $0 incremental as above | $0.00 |
| **Illustrative normal total** | Calculated using unrounded rates | **$46.33-$55.49** |

**Rate verification and arithmetic:** Public Azure Retail Prices API checked
November 20, USD/Consumption, with all pages retrieved. S0 uses the primary S0 SKU,
not cheaper secondary replicas; Blob uses non-hierarchical General Block Blob v2
Hot LRS. Regional records with `isPrimaryMeterRegion=false` were not discarded,
since doing so hid applicable SQL/registry rates. Queries, returned meters and
calculations are retained in session artifact `retail-prices-2026-11-20.json`.

- Active job rates: $0.000024/vCPU-second and $0.000003/GiB-second. At 2 vCPUs/4 GiB,
  that is $0.216/worker-hour: $3.24 for 30 half-hour runs, or $4.86 for 30
  45-minute runs, before allowances. Available subscription-shared job allowances
  have not been checked; do not rely on them.
- If all 30 executions each consume two full 45-minute attempts, job compute is
  $9.72 before allowances. With the other modeled charges and $3 incidental allowance,
  the total is **$60.35**, about $61. This is a retry scenario, not a monthly upper
  bound: manual runs, higher log/storage usage or more alert time series add cost.
- Hot Blob storage: $0.0208/GB-month; write/list $0.05/10K and reads $0.004/10K.
  Average byte footprints are unmeasured; five-day export retention alone does not
  determine stored GB, and current population/identity/state remains protected.
- West US 3 storage: Hot OneLake $0.023/GB-month, Fabric SQL data $0.22115/GB-month,
  and billable excess SQL backups $0.088462/GB-month. Backup storage up to 100% of
  allocated SQL database size is included; the modeled 1 GB is **excess** billable
  storage, not a charge for the first 1 GB of backups. Additional 100 GB of Hot
  OneLake adds approximately $2.30/month; indefinite retention makes this line grow.
- Seven alerts model failure, blocked dependency, availability deadline, freshness,
  telemetry gaps, duration regression and memory pressure. Exact queries, time-series
  cardinality and evaluation settings still need physical design/validation; this
  estimate does not deploy or approve unreviewed alert definitions. Thirty-day
  Analytics retention is within included retention. Email is assumed within the
  first 1,000 monthly notifications; other channels/escalation are not priced.
- The initial historical seed has not been benchmarked. Its job compute scales at
  $0.216/worker-hour before allowances; do not present this as a known total seed
  cost or bypass the approved timeout/sizing review.

Excluded: the existing F32 bill, additional capacity uptime/size, paid on-demand/
autoscale usage, initial-seed runtime, taxes, paid CI/runner licenses and private
networking. Extra registry storage/builds, monitoring dimensions, optional storage
resilience and excess source-SQL storage/backups need repricing if applicable.
The $1-$3 incidental allowance is not evidence that every such charge is covered.
The approved $8/$10 **generator** alerts remain unchanged; $60 is a new planning
recommendation for the whole demo and still needs final costed-plan review.

Official pricing references: Azure Retail Prices API overview, Azure SQL single
database pricing, Container Apps pricing/billing, Container Registry pricing,
Blob Storage pricing, Azure Monitor pricing, Microsoft Fabric pricing and Fabric
SQL usage-reporting/backup billing documentation.

### Generation Host Comparison: Retained Decision Context

This comparison informed the selected Consumption Container Apps Jobs host; it is
retained for context, not as an unresolved host decision. It is for the approved small
demo, not a new hospital-scale benchmark.
"Fabric" here means executing generation in a Fabric notebook/job, not just using
Fabric Airflow to submit an external job, which would still incur its own compute cost.

| Option | Execution and cost model | Fit for this demo / condition |
| --- | --- | --- |
| Azure Batch | Schedule Synthea/loader tasks on VM pool workers. Batch has no separate service fee, but VMs, storage and supporting resources cost money. Pool lifecycle and capacity planning remain operational work. | Strong parallel-cohort/growth option; more pool/task machinery than this small default workload appears to need. Not inherently the most expensive option; compare measured total cost if retained. |
| Container Apps Jobs, Consumption | Package a compatible Java runtime, Synthea and loader dependencies in a run-to-completion container. CPU/memory consumption is billed while executions run, with no idle job compute charges. Free grants are subscription-shared; storage, image registry, logging and networking may still cost. | **Selected host.** Explicit runtime control and isolation from Fabric compute. Validate runtime/memory and total supporting-service cost before sizing. |
| Fabric-native notebook/job | Run on approved existing capacity and persist generation artifacts in a reviewed OneLake location. Shared capacity usage is not free/unlimited; Spark Autoscale Billing, if enabled, uses separately billed compute. OneLake storage is billed separately. | Potential lowest additional cash spend if suitable capacity is already running with headroom, without extending uptime, upgrading capacity or enabling separate autoscale billing. Validate Java execution, state recovery, SQL authentication/connectivity and capacity consumption before selection. |

Synthea's current source requires Java JDK 17 or newer. Microsoft's runtime matrix
lists Java 21 for Fabric Spark Runtime 2.0 and Java 11 for Runtime 1.3. Runtime 2.0
therefore meets that version prerequisite, but this is not evidence that the Synthea
artifact, dependencies, scheduled execution, snapshots and SQL loaders have been tested
there. Do not silently upgrade existing workspace runtimes or claim compatibility
solely from a version comparison.

Fabric also has non-Spark Python notebooks, which can suit small mapping/loading work.
Do not assume that a Python kernel includes a supported Java execution environment for
Synthea or that starting Spark automatically distributes its Java simulation.

**Selection supersedes the earlier evaluation recommendation:** proceed with the
Consumption Container Apps Jobs design rather than a Fabric-native prototype or Batch
pool. The Fabric runtime notes above describe an alternative, not a requirement to
change this project's Fabric runtime. No hosted prototype, resource changes, capacity
upgrades or autoscale enablement have been performed.

Measure initial seed and normal incremental execution separately: end-to-end runtime,
peak memory, exported/source bytes, retries, SQL loading time/concurrency and full
generation-plus-loader cost. For Fabric, include CU consumption and effects on other
workloads; for external jobs include startup and supporting-service costs. Synthea
simulation work is not determined solely by the number of SQL rows changed that day.
All hosts still require durable state, retry-safe independent source loading and
completion evidence before ingestion; host choice does not bypass D05.

Official references checked November 20, 2026:

- Batch cost model: `https://learn.microsoft.com/en-us/azure/batch/plan-to-manage-costs`
- Container Apps job billing: `https://learn.microsoft.com/en-us/azure/container-apps/billing`
- Fabric Spark capacity and autoscale billing: `https://learn.microsoft.com/en-us/fabric/data-engineering/billing-capacity-management-for-spark`
- Fabric capacity/storage billing: `https://learn.microsoft.com/en-us/fabric/enterprise/azure-billing`
- Fabric runtime matrix: `https://learn.microsoft.com/en-us/fabric/data-engineering/runtime`
- Non-Spark Python notebooks: `https://learn.microsoft.com/en-us/fabric/data-engineering/using-python-experience-on-notebook`
- Synthea requirements and snapshot options: `https://github.com/synthetichealth/synthea`

## Engineering Design Work, Not Extra Questions for You to Solve

These are deliverables to prepare for review, not requests for you to invent SQL types
or implementation algorithms.

| Design deliverable | Unresolved details to produce and validate | Related decisions |
| --- | --- | --- |
| Revised physical metadata model | Exact columns/keys/indexes/release-scoped FKs; retain mapping versus optional task mapping; primary outputs/non-data tasks; stable dataset identities; task-input/exceptional dependency relationships; avoid duplicate ops tables. | D01 |
| Ordered function and profiling contract | JSON schema/parameter validation; repeated-function and stable step occurrence IDs; auxiliary datasets/snapshots; preserve legacy step profiling/history and existing Bronze IDs. | D01, D06 |
| Effective configuration resolver | Framework/stage/pipeline/task precedence, existing domain and permitted run overrides, null semantics, allowed fields; scheduler policy distinct from runtime/session-start configuration. | D01, D09 |
| Producer/readiness/window protocol | Unambiguous producer per release/window, expected-execution identity, committed version/source-currency coverage, statuses, concurrent state transitions, and dataset-versus-attempt history. | D01, D04 |
| Reliable dispatch and commit recovery | Event/outbox or equivalent delivery, periodic reconciliation, atomic claims/leases, stable operation versus attempt keys, duplicate handling, SQL/Delta reconciliation, and old-window write protection. | D01, D05, D11 |
| Release artifact and activation design | Candidate version/snapshot/hash, corresponding DAG artifacts, sequential processing, CI/Airflow recognition, pinned in-flight runs, activation/rollback audit and compatibility, emergency/data-remediation procedures. | D01, D02, D10, D12 |
| Resource and verification matrix | Supported Airflow/Fabric integration, pinned tested runtime/providers/APIs, environment/compute mapping and startup settings, least-privilege permission paths, and executable acceptance cases. | D02, D07-D10 |

The source SQL baseline still needs the already documented business integrity,
audit/write-path, upgrade-migration, synthetic population, and live catalog work in
`database\README.md`. These are unfinished engineering tasks, not new source-model
approval questions.

## Already Decided: Do Not Reopen as Build Questions

- Basic Azure Container Registry `hcingestionacr`, Terraform-managed in East US
  under `healthcare-data-ingestion-rg`, is approved. Validate name availability and
  identity/network configuration; no registry has been created.
- Separate Azure SQL Clarity/Caboodle sources; approved 28 source models, independently
  populated with consistent synthetic identities.
- Use Synthea plus mapping configuration for source population, hosted in Azure
  Container Apps Jobs on Consumption with an approximately $10/month generation
  planning target, not a fixed fee or enforced cap. Mapping coverage/loader details,
  B01-B09 now approve evaluation sizing, name derivation, access and spend policies;
  concrete resource resolution, mapping/loader/state design and measured costs remain
  for engineering verification/review.
- Generator durable storage is approved: Terraform-managed Standard/Hot/LRS Azure
  Blob Storage in East US under `healthcare-data-ingestion-rg`, with anonymous access
  disabled. Account name `hcingestionstore` is approved, subject to availability checks.
  Completed exports/manifests have five-day retention with confirmed-ingestion and
  recovery holds; current generator state remains protected. Ingested Fabric data
  has indefinite retention. B01-B08 now approve remaining naming/access/retention
  policies. Concrete names, cleanup and checkpoint implementation need engineering
  verification/review; storage selection does not authorize provisioning.
- The demo workload above is approved, including the normal change mix and on-demand
  zero-change/spike scenarios. Standard S0 per database is the initial evaluation
  baseline. B05 approves the 2-vCPU/4-GiB generator pilot, execution/retry limits,
  $8/$10 alerts (not hard caps) and bounded benchmark settings. Initial-seed sizing
  and refreshed total cost still need measured/costed review before apply.
- B04 approves daily 12:00 UTC generation, before 10:00 AM Eastern ingestion.
  Required checkpoint failures/missing coverage block and alert affected consumers;
  no overlapping writes and useful late recovery. Exact implementation remains gated.
- Dedicated Fabric SQL metadata workspace, separate ingestion workspace, existing
  capacity, append-only Bronze, and the accepted technical columns including
  `_ingest_source_name`.
- Independent Bronze/Silver 1, committed/fresh/window-compatible dependency readiness,
  latest-expected-failure blocking, separate SLA monitoring, and useful late recovery.
- One task record per independently executable operation; retained `PipelineObject`
  mapping; logical datasets and normalized task inputs; limited exceptional ordering.
- Ordered function JSON array, generic stage notebooks by default with justified
  exceptions, and framework/stage/task configuration support.
- Smaller logical-workflow/domain DAGs, hybrid readiness coordination, primary events
  with reconciliation fallback, and framework-owned idempotency.
- A new Fabric-managed Apache Airflow job for this project, rather than reuse of an
  existing instance or a self-managed deployment. B01 selects the data workspace,
  existing capacity and three logical DAGs; the user owns operations/publication.
  Integration, concrete names and supported defaults need engineering verification.
- Strict schema drift policy: additions, widening and all other ingestion-relevant
  contract differences block only the affected table pending review/approved revision.
  No compatibility allowlist, automatic contract promotion or target evolution.
- Initial default cadence is daily at 10:00 AM Eastern local time, observing daylight saving;
  default maximum age of committed source coverage is 24 elapsed hours. The separately
  approved daily availability deadline is 11:00 AM Eastern for required Bronze and
  initial Patient Silver outputs, also observing daylight saving. The freshness limit
  remains elapsed time rather than a local calendar day. Neither freshness nor a deadline miss authorizes
  fallback after the latest expected run fails.
- Immutable complete same-semver framework/DAG releases, sequential builds, no redundant
  post-publication manual gate, candidate testing/recognition before activation,
  pinned in-flight runs, and audited incident rollback with the approved authorization split.
- A successfully validated incremental run with zero changes is successful; preserve
  existing data and verify source coverage and all other readiness requirements.
  Future processed-record UCL/LCL use the historical mean plus/minus two standard
  deviations. Their implementation and breach-response policy are deferred.

**Next review package:** D01's physical model/protocol and D03-D06's initial flow policies,
alongside D02/D07-D09's environment inputs. Answer remaining items at their stated gates;
do not block independent approved local source work on unrelated production settings.
