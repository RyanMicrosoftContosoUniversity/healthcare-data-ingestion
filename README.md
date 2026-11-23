# Synthetic Healthcare Data Ingestion

Build synthetic Clarity/Caboodle sources and a metadata-driven Microsoft Fabric ingestion
framework. These models are representative simulations, not proprietary Epic schemas.

## Implementation Boundary

**Current authorization:** `discussions\discussed-changes-03.md` approves remaining
recommended architectural directions and the user has requested development.
Concrete implementation and evidence are being produced; older "decisions still
needed" statements below are historical and do not require another choice loop.
Cloud resources/apply remain gated by the actual reviewed costed Terraform plan.
Latest policies include five-minute reconciliation, fixed-version/window-aware
recovery, PR-reviewed pinned releases/environments, critical-quality/corruption
blocking, explicit daily-priority backfills, seven-year execution/readiness audit
target, Outlook/email-only notifications and native Fabric SQL backup/restore.

The approved release ends at all-table Bronze ingestion and a working Clarity Patient
Silver flow, with reusable Python utilities, isolated benchmarks, diagnostics, and alerts.
No Gold, reporting, or additional Silver domains are included.

Local source, metadata/control, discovery, Bronze and Patient Silver implementation
is authorized. Cloud deployment is not. Local tests and prepared artifacts do not
establish live SQL/Fabric connectivity, permissions, throughput or alert delivery.

The accepted control store is a **Fabric SQL Database in a dedicated metadata workspace**,
separate from the data/ingestion workspace. It holds the authoritative framework
configuration, runtime state, and logging metadata. Approved names are
`healthcare-data-ingestion-metadata` / `healthcare-data-ingestion-metadata-db`;
actual IDs and runtime permissions still require live validation. The two simulated
source databases remain in Azure SQL.

The Bronze metadata column set is accepted, with `_ingest_source_name` as a readable
string such as `Clarity.dbo.Patient`. The complete eight-column contract is under
**Accepted Bronze Row Metadata** in `docs\ingestion\metadata-design.md`; internal
control-store source-object IDs remain unchanged.

`discussions\discussion-02.md` consolidates the earlier record and is reconciled in
`docs\architecture\orchestration-design.md`. Approved directions now include task JSON
function arrays, logical datasets/normalized inputs, smaller domain DAGs, hybrid
readiness coordination, event-primary recovery with reconciliation fallback, candidate
activation, and audited incident rollback. Latest expected upstream failure blocks
consumers by default even if an older success is recent.

Airflow hosting is selected: a **new Fabric-managed Apache Airflow job** for this
project in `healthcare-data-ingestion-data` on the existing F32 capacity;
no separate self-managed Airflow host is planned.

**Synthea plus versioned mapping configuration** is selected for source generation and
loading into the approved Azure SQL models through independent source loaders.
**Azure Container Apps Jobs on Consumption** is selected for generation, with
**approximately $10/month as the generation planning target**, not a fixed fee or
enforced cap. That estimate excludes SQL databases, normal Fabric ingestion and the
initial historical seed. The approved evaluation profile is 2 vCPUs/4 GiB, one
worker, serial loaders, 45-minute attempts and one transient retry; no resources
have been deployed.

The workload is **demo-first and cost-conscious**, not hospital-volume simulation.
The approved profile is 1,000 initial patients with 12 months retained history and
about 500-1,000 daily source-row changes across both databases, including controlled
corrections/soft deletes and on-demand zero-change/spike scenarios. Standard S0 (10 DTU)
per SQL database is the accepted initial evaluation baseline, not a deployment approval
or throughput guarantee. Correctness, recovery and isolated benchmarks remain in scope.

Synthetic data generation runs well before daily Fabric ingestion, with source data
intended to be ready before the 10:00 AM start. Generation is scheduled at 12:00 UTC.
Missing/failed expected checkpoints block affected consumers, never silently selecting
an older success; independently committed source work remains useful.

Initial defaults are daily runs at **10:00 AM Eastern local time, observing daylight
saving**, and a **24-elapsed-hour maximum age of committed source coverage** for downstream
eligibility. Required Bronze and initial Patient Silver outputs have a separate
**11:00 AM Eastern local time daily availability deadline**, also observing daylight
saving; one-hour feasibility still needs
benchmarking. Misses alert but allow useful late recovery, and recent older data does
not bypass the rule blocking consumers after a latest expected upstream failure.

Successful incremental runs with zero changed records count as successful when source
coverage and normal validation/readiness checks are verified; preserve existing data.
Future processed-record monitoring will use historical mean plus/minus two standard
deviations for UCL/LCL. Implementation, baseline details and breach response are deferred.

Review the logical revision in `docs\ingestion\task-dataset-design.md`.
`docs\architecture\build-decisions.md` preserves decisions and the engineering checklist;
handoff03 closes the remaining architectural-choice loop.
The original 17-table diagrams are baseline, not finalized revised physical schemas.
These decisions do not expand the first Patient-only Silver build or authorize cloud
creation. **Strict schema comparison is approved**: nullable additions, widening and
other ingestion-relevant contract differences block only the affected table pending
review/approved revision, without automatic contract/target evolution. One source pass
remains the direction. One shared source transaction and catalog pass protects captures;
staged validation and immutable replay do not substitute today's live schema for history.

## Local Development

Use Python 3.11-3.13 and `uv`. Spark validation uses Linux, Spark 4.1/Delta 4.2,
Python 3.13 and Java 21, matching Fabric Runtime 2.0. Airflow's documented profile is
2.10.5/Python 3.12; live item configuration and ODBC18 availability still require acceptance.

```powershell
uv sync --group dev --python 3.11
.\scripts\Test-Project.ps1
```

`uv.lock` records dependencies; `cloud` and `spark` extras pin the runtime SDKs.
Native Windows checks skip actual Spark tests, which run in the bounded Linux container.
See `docs\ingestion\runtime-operations.md` for release preparation and live prerequisites.
`.github\workflows\validate.yml` prepares native builds/bundles, real Spark checks
and backend-disabled Terraform validation on reviewed changes. It does not deploy,
activate releases or enable alerts; hosted CI execution still requires a pushed PR.

## Source Models

- Approval and population decisions: `docs\architecture\source-model-approval.md`
- Column dictionaries: `docs\clarity\data-dictionary.md` and `docs\caboodle\data-dictionary.md`
- Typed column/primary-key snapshots: `database\schema-contracts\`
- Reviewable relationships and diagrams: `data-models\`

The JSON snapshots describe columns and primary keys; they do not replace the documented
FKs, filtered uniqueness, temporal constraints, or cross-row business validation rules.
SQL deployment must implement and validate those additional approved constraints.

Generate local SQL baselines from the approved contracts:

```powershell
uv run --locked python .\scripts\export_source_ddl.py
```

Outputs are `database\clarity\schema\001-source-baseline.sql` and the corresponding
Caboodle script. See `database\README.md` for implemented constraints and remaining
integrity/write-path work. These are empty-database definitions, not migrations or
deployed databases; no metadata runtime or cloud resources are created.

The original root `plan.md` remains intentionally ignored. To refresh exported source
dictionaries/contracts from an explicitly reviewed local design:

```powershell
uv run --locked python .\scripts\export_source_models.py --source-plan .\plan.md
```

Review generated changes before accepting a new source contract. Never use an unreviewed
document update to silently alter deployed schemas.

## Deployment and Review Gates

`.azure\deployment-plan.md` tracks preparation and target confirmation.
Framework design is in `docs\ingestion\metadata-design.md`; implemented migrations,
protocol contracts and the 29-task release are in `database\metadata\` and
`metadata\framework\`. Source configurations cover all 28 approved tables.
Never commit credentials, Terraform state, raw logs, or generated source data.

The proposed framework dictionaries are now available in that design document.
`data-models\framework\00-overview.mmd` shows all 17 tables and 30 foreign-key
relationships; open `00-overview.svg` in the same folder for a zoomable preview.
`data-models\framework\relationships.md` lists all relationships, and four additional
focused `.mmd`/`.svg` pairs separate configuration, run state, validation/benchmarks,
and diagnostics. The overview keeps PK/FK columns only to reduce visual clutter.
These remain review artifacts, not deployed control tables.

For a complete schema diagram rather than a keys-only overview, open
`data-models\framework\05-full-schema.mmd` or `05-full-schema.svg` in the same folder.
It shows all 261 columns on all 17 tables, including shared configuration audit fields
and Spark metric extensions, plus the same 30 foreign-key relationships.

The updated behavior review diagrams are `06-orchestration`, `07-release-lifecycle`, and
`08-transformation-order` under `data-models\framework`, each with `.mmd` and `.svg`
versions. They show approved directions without inventing approved ERD additions.
`09-task-dataset-logical.mmd` / `.svg` separately shows the approved logical revision,
not new physical column definitions or deployed tables.

Review `docs\ingestion\schema-discovery-design.md` for the required discovery workflow,
schema comparisons, blocking policy, retained evidence, and recovery behavior. The
framework design's **Required Schema Discovery Before Bronze Ingestion** section
contains the aligned integration specification. Current Python validation checks the
contracts and protocol adapters; the implemented live discovery gate awaits deployed
SQL/Fabric acceptance.

If direct package downloads are unavailable, configure `UV_DEFAULT_INDEX` to your
organization's approved package feed; do not disable certificate verification.
