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

`discussions\discussed-changes.md` is reconciled in
`docs\architecture\orchestration-design.md`: independent Bronze/Silver 1,
dependency-gated Silver 2, freshness versus availability SLA, automatic blocked-work
recovery, and metadata-generated versioned Airflow releases. The 17-table framework is
still a baseline awaiting review, not a finalized release/readiness schema. Discovery
uses the one-pass direction; exact drift policy and a lightweight second check remain open.
These architecture decisions do not expand the first Patient-only Silver build.

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

The new behavior review diagrams are `06-orchestration`, `07-release-lifecycle`, and
`08-transformation-order` under `data-models\framework`, each with `.mmd` and `.svg`
versions. They show approved directions without inventing approved ERD additions.

Review `docs\ingestion\schema-discovery-design.md` for the required discovery workflow,
schema comparisons, blocking policy, retained evidence, and recovery behavior. The
framework design's **Required Schema Discovery Before Bronze Ingestion** section
contains the aligned integration specification. Current Python validation checks the
local contract files only; live discovery and its ingestion gate have not been implemented.

If direct package downloads are unavailable, configure `UV_DEFAULT_INDEX` to your
organization's approved package feed; do not disable certificate verification.
