# Synthetic Healthcare Data Ingestion

Build synthetic Clarity/Caboodle sources and a metadata-driven Microsoft Fabric ingestion
framework. These models are representative simulations, not proprietary Epic schemas.

## Implementation Boundary

The approved release ends at all-table Bronze ingestion and a working Clarity Patient
Silver flow, with reusable Python utilities, isolated benchmarks, diagnostics, and alerts.
No Gold, reporting, or additional Silver domains are included.

Implementation is staged. Source models are approved; cloud target confirmation and
framework/control-table design approval remain separate gates. The presence of source
contracts or design documents does not mean databases or pipelines have been deployed.

The accepted control store is a **Fabric SQL Database in a dedicated metadata workspace**,
separate from the data/ingestion workspace. It holds the authoritative framework
configuration, runtime state, and logging metadata. Workspace/database names and access
will be confirmed before creation; the two simulated source databases remain in Azure SQL.

The Bronze metadata column set is accepted, with `_ingest_source_name` as a readable
string such as `Clarity.dbo.Patient`. The complete eight-column contract is under
**Accepted Bronze Row Metadata** in `docs\ingestion\metadata-design.md`; internal
control-store source-object IDs remain unchanged. Other framework approvals are pending.

`discussions\discussion-02.md` consolidates the earlier record and is reconciled in
`docs\architecture\orchestration-design.md`. Approved directions now include task JSON
function arrays, logical datasets/normalized inputs, smaller domain DAGs, hybrid
readiness coordination, event-primary recovery with reconciliation fallback, candidate
activation, and audited incident rollback. Latest expected upstream failure blocks
consumers by default even if an older success is recent.

Airflow hosting is selected: a **new Fabric-managed Apache Airflow job** for this
project. Workspace/item/capacity placement and other deployment settings remain pending;
no separate self-managed Airflow host is planned.

**Synthea plus versioned mapping configuration** is selected for source generation and
loading into the approved Azure SQL models through independent source loaders.
**Azure Container Apps Jobs on Consumption** is selected for generation, with
**approximately $10/month as the generation planning target**, not a fixed fee or
enforced cap. That estimate excludes SQL databases, normal Fabric ingestion and the
initial historical seed. Generator sizing, persistent storage, exact schedule and
deployment targets remain open; no resources have been deployed.

The workload is **demo-first and cost-conscious**, not hospital-volume simulation.
The approved profile is 1,000 initial patients with 12 months retained history and
about 500-1,000 daily source-row changes across both databases, including controlled
corrections/soft deletes and on-demand zero-change/spike scenarios. Standard S0 (10 DTU)
per SQL database is the accepted initial evaluation baseline, not a deployment approval
or throughput guarantee. Correctness, recovery and isolated benchmarks remain in scope.

Synthetic data generation runs well before daily Fabric ingestion, with source data
intended to be ready before the 10:00 AM start. The generator's exact start time and
handling of late/failed generation remain open; continuous generation is not assumed.

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
**Decisions still needed from you:** `docs\architecture\build-decisions.md` lists
D01-D12 with the implementation, provisioning, or activation gate each blocks.
The original 17-table diagrams are baseline, not finalized revised physical schemas.
These decisions do not expand the first Patient-only Silver build or authorize cloud
creation. **Strict schema comparison is approved**: nullable additions, widening and
other ingestion-relevant contract differences block only the affected table pending
review/approved revision, without automatic contract/target evolution. One source pass
remains the direction; optional lightweight recheck, unavailable-evidence handling and
other discovery mechanics still need review.

## Local Development

Use Python 3.11-3.13 and `uv`. The eventual Spark environment must be validated and pinned
against Fabric's approved runtime before deploying Spark-dependent code.

```powershell
uv sync --group dev --python 3.11
.\scripts\Test-Project.ps1
```

`uv.lock` records resolved dependencies. The initial package intentionally has no Spark
or cloud SDK runtime dependencies; add those only with the approved execution components.

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
Framework tables are documented in `docs\ingestion\metadata-design.md` for review
before implementing control storage, the 28 source configuration records, or Bronze flows.
The standalone process document `docs\ingestion\schema-discovery-design.md` also
requires explicit review before that build begins.
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
local contract files only; live discovery and its ingestion gate have not been implemented.

If direct package downloads are unavailable, configure `UV_DEFAULT_INDEX` to your
organization's approved package feed; do not disable certificate verification.
