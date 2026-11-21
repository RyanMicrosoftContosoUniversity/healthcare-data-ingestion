# Executable independent synthetic sources

Local preparation only. No Azure/Fabric deployment or SQL apply is performed by export,
demo, import, change or validate. `load` is an explicit live data operation, gated on the
reviewed deployment and source upgrade scripts; it is not authorized by this handoff.

From the repository root:

```powershell
uv run --locked python .\scripts\synthetic-data\generate.py export-artifacts
uv run --locked python .\scripts\synthetic-data\generate.py demo --state .\generator-state --batch baseline --patients 1000 --history-start 2025-11-01T00:00:00Z --at 2026-11-01T23:59:59Z
uv run --locked python .\scripts\synthetic-data\generate.py change --state .\generator-state --batch day-20261102 --at 2026-11-02T12:00:00Z --profile normal
uv run --locked python .\scripts\synthetic-data\generate.py validate --state .\generator-state --batch day-20261102
```

`demo` is an explicitly synthetic supplemental fixture engine, **not measured Synthea
execution**. The primary clinical path runs a separately reviewed immutable Synthea jar:

```powershell
uv run --locked python .\scripts\synthetic-data\generate.py synthea --state .\generator-state --batch baseline --jar .\generator\synthea-reviewed.jar --jar-sha256 <reviewed-sha256> --synthea-version <immutable-release-or-commit> --reference-date 20261101 --patients 1000 --history-start 2025-11-01T00:00:00Z --at 2026-11-01T23:59:59Z
```

Java and the reviewed jar are operator-supplied; no download or mutable `latest` version
is accepted. The command caps Java at two processors and a 2-GiB heap within the intended
2-vCPU/4-GiB job pilot; full-pilot runtime/container sizing has not been measured. Each attempt has a
45-minute budget; Synthea failures are not blindly retried. An interrupted uncommitted
FHIR export requires review and a fresh output directory, not silent reuse.

Alternatively `import-fhir --fhir-directory <directory> --state ... --batch ... --history-start ... --at ...`
loads fixed R4 bundles from an existing export. Every resource is retained with an
explicit disposition. Unknown resource types, unresolved required references, unsupported
clinical quantities/codes, overflow and truncation fail closed. Imported FHIR attributes
are the explicitly modeled initial baseline, **not evidence of prior attribute history**.
No Type 2 versions before that baseline are inferred. `Claim`, EOB, allergies, devices,
immunizations and other named out-of-scope resources remain in the archive; they have no
approved source-table grain. Vital observations have Clarity rows but no Caboodle fact.

The named operational supplements include unassigned clinician/department, unknown
coverage plan or modeled uninsured enrollment, lab orders when observations lack an order,
scheduled visits, numeric-order administrations, and controlled daily event groups.
Daily clinical groups use a fixed explicitly synthetic workload fixture, not a truncated
or randomly selected imported encounter. Original imported history is unchanged.
They are recorded in `supplemental_rules`, never presented as observed Synthea values.
Missing optional clinical values are explicit NULL; unsupported required data is rejected.
The v1.1 mapping JSON enumerates and executes every one of 454 approved columns. Decimal
rules explicitly use HALF_UP rounding to each approved SQL scale; no binary float
conversion occurs, and original FHIR quantities remain in the archive/export. Conditional
identifier references must resolve uniquely. PractitionerRole actors resolve through their
practitioner. Unnamed locations receive a labeled synthetic name. Unitless medication
doses are explicitly archived with NULL source dose/unit, never assigned a guessed
physical unit. Administrations without request references get labeled supplemental orders,
not falsely inferred Synthea prescription identifiers. Contract
fingerprints prevent schema changes from silently entering source populations.

## State and independent loading

Population batches are immutable, checksummed and predecessor-linked. An atomic head and
shared collision-checked identity manifest survive restarts. Source projections read the
clinical population directly: neither source reads the other's database. SQL checkpoints
advance independently. Snapshot-diff deltas capture old-event corrections, dimension
expiration/insertion, derived fact changes, and leaf soft deletes. A new independent source
may full-seed the latest complete snapshot; an existing source cannot skip batches.
Bootstrap refuses a nonempty source or orphaned commit history without a reconciled
checkpoint; it never silently mixes an unknown existing population into a full seed.

`normal` measures 500-1000 combined source-row changes, including five new patients,
up to ten Type 2 location changes, 25 coherent encounter groups, four eligible corrections
and two eligible leaf soft deletes. Baselines with too few correctable results report
the actual eligible counts; they do not invent candidates. `zero` commits a zero-row
source checkpoint; `spike` targets roughly 5000 complete rows. No clinical groups are
truncated to hit counts. All generated supplements remain explicitly synthetic.
Static UTC calendar members are preseeded through the following calendar year, so advancing
a zero-change window does not create a calendar row. Unused code catalogs are retained;
deleting/correcting an event does not physically remove its previously published catalog.

After authorized source deployment, review/apply each source's baseline then its
`database\<source>\migrations\002-synthetic-integrity-and-write-path.sql` in that source
database only. The transactional upgrade is repeatable, non-destructive and fails on
invalid existing data. It adds filtered/composite uniqueness, period/unit checks, audit
mutation triggers, prohibited physical deletes/PK mutation, a final relational/temporal
validation procedure, and the committed source checkpoint table. It does not create a
third database. Validate migration behavior live before production use.
The approved execution path for **both** baseline 001 and upgrade 002 is
`sql_source_migrations.execute_source_migration_sql(admin_connection, sql_text)`.
It requires a dedicated non-autocommit connection with database CONTROL or db_ddladmin,
acquires `healthcare-ingestion-source` **Exclusive/Public/Transaction** before any DDL,
and keeps an outer transaction across nested script BEGIN/COMMIT and GO batches.
Ordinary generator DML identities must not have those DDL permissions. Upgrade 002 also
acquires that exact exclusive fence itself before schema changes. Baseline 001 remains
the generated model definition: **do not execute it directly without the admin wrapper**.
An active shared discovery/capture fence makes the zero-timeout DDL acquisition fail
before schema mutation; no workflow/diagnostic redesign is needed.
An append-only `SyntheticSourceBatchCommit` ledger retains immutable evidence for each
committed batch, alongside the current checkpoint head. Post-commit readback and older
idempotent reruns use that ledger, so a subsequent producer cannot erase acknowledgement
evidence by advancing the head. Ledger inserts and head changes share the source transaction.

The loader uses the root `cloud` extra's pinned `azure-identity` and `pyodbc` dependencies,
ODBC Driver 18, networking and an explicitly approved managed identity. It offers no
SQL-password or personal-account fallback. Example **only after deployment authorization**:

```powershell
uv run --locked --extra cloud python .\scripts\synthetic-data\generate.py load --state .\generator-state --batch baseline --source Clarity --server <approved-clarity>.database.windows.net --database <approved-db> --managed-identity-client-id <approved-client-id>
```

Run Caboodle separately with its approved server/database. A shared worker OS lock
serializes both loaders; an exclusive transaction-owned SQL application lock prevents
overlapping writes to each source database across hosts.
Extraction must acquire a **shared** transaction-owned lock on the exact resource
`healthcare-ingestion-source` before live discovery, row extraction and checkpoint capture,
and retain it on that same connection until extraction ends. Helpers
`acquire_source_read_lock(cursor)` and `source_checkpoint_evidence(cursor, source)` expose
this integration contract. Audit triggers reject DML that lacks the exclusive producer
fence. A timestamp watermark alone is not a source-consistency or late-commit guarantee.
Parameterized upserts, database-maintained publication timestamps and checkpoint commit
are one transaction; final SQL integrity validation runs before commit. Only actual
post-commit SQL evidence updates the local mirror. A post-commit read/process failure is
recovered by the SQL checkpoint without rewriting rows. One classified transient retry
is allowed, with a fresh 45-minute attempt; no runtime escalation. Logs contain only
source/batch IDs, counts and commit times, never source data or original SQL errors.

## Consumption job host and durable Blob authority

`scripts\synthetic-data\Dockerfile` runs
`python -m healthcare_ingestion.generator_host` as nonroot UID 10001. It installs Java 17
and ODBC Driver 18, uses locked cloud dependencies, downloads the official immutable
Synthea **v3.4.0** asset 312917735, and checks its bytes against:

```text
38678aab1e667d26671163824aad60ee5e30fa366f3d59d5ea5765ebb5702432
```

The version/URL/hash/asset ID and deterministic patient/clinician seed **20261120** live
in `synthea-pin.json`. The command fixes both Synthea reference and simulation end date;
neither `latest` nor a mutable branch is accepted. Rebuilding the image is required after
source or pin changes; no image push/deployment is part of local preparation.

Host environment:

| Variable | Binding |
| --- | --- |
| `AZURE_CLIENT_ID` | Approved user-assigned managed identity; omit only for explicitly approved system identity |
| `GENERATOR_STORAGE_ACCOUNT` | Existing approved Blob account |
| `GENERATOR_STATE_CONTAINER` | Existing dedicated durable-state container |
| `GENERATOR_EXPORT_CONTAINER` | Existing dedicated FHIR export container |
| `GENERATOR_MANIFEST_CONTAINER` | Existing dedicated plan/export-manifest container |
| `CLARITY_SQL_SERVER`, `CLARITY_SQL_DATABASE` | Approved independent Clarity endpoint/database |
| `CABOODLE_SQL_SERVER`, `CABOODLE_SQL_DATABASE` | Approved independent Caboodle endpoint/database |
| `GENERATOR_TIMEOUT_SECONDS` | 1..2700; default 2700; no runtime escalation |
| `GENERATOR_BATCH` | Optional explicit immutable batch ID |
| `GENERATOR_PUBLICATION_AT` | Optional fixed UTC publication time |
| `GENERATOR_HISTORY_START` | Optional history start; default one calendar year before publication |

The three containers must be distinct; `terraform-state` is prohibited. The host neither
creates accounts/containers nor offers SQL-password/personal-credential fallback.
CLI: `--root` (default current directory), `--state` (default `generator-host-state`),
`--batch`, `--profile normal|zero|spike`, `--at`, `--history-start`, `--patients` (default
1000, bounded by the Synthea pilot). An empty durable population gets `seed-YYYYMMDD`,
then UTC daily runs get `daily-YYYYMMDD`. An incomplete expected batch is automatically
selected for recovery instead of advancing to today's batch. Explicit batch IDs override
selection, not the previous-incomplete-batch safety check.

Job settings remain one worker, replica parallelism/completion **1**, **2 vCPU/4 GiB**,
replica timeout **2700 seconds**, at most one external retry. A 60-second Blob lease
renewed every 20 seconds serializes the whole host, including serial Clarity/Caboodle
loads. Linux process timing reserves cleanup within the cap. SQL uses the same exclusive
`healthcare-ingestion-source`, Transaction/Public database fence as the shared extractor.
ODBC query budgets use `Connection.timeout` and refresh cursors when the remaining budget
changes; nonexistent `Cursor.timeout` is not used.

Mutable authority is state-container blob `generator/control-v1.json`; updates require
both its active lease and ETag. Other state objects are immutable `objects/<sha256>`.
Plans are `plans/<batch>/<plan-digest>.json`; exports are
`exports/<batch>/<content-sha256>/<relative-file>`; export manifests are
`export-manifests/<batch>/<manifest-digest>.json`. Referenced payloads are size/hash checked.
Ephemeral caches cannot substitute unreferenced local batches for authoritative Blob state.

Public APIs:

```python
from healthcare_ingestion.generator_host import HostConfig, requested_plan, run_job
from healthcare_ingestion.generator_blob import BlobStateStore
from healthcare_ingestion.sql_source import acquire_source_read_lock, source_checkpoint_evidence

config = HostConfig.from_env(root, state_directory)
plan = requested_plan(
    config, batch="seed-20261120", profile="normal", at="2026-11-20T23:59:59Z", patients=1000
)
# run_job(config, blobs, plan) is a live publication operation; requires authorization.
```

Control contains `schema_version`, `files`, `batches`, `expected`, `last_good`, `acks`,
`holds`, `retired`. Expected shape is
`{batch, plan_digest, status, attempt_id}`. Each immutable-plan batch summary contains
`plan_digest`, `plan_ref`, `status`, `attempts`, `artifacts`, `source_digests`, `tables`.
Attempt journals contain `attempt_id`, `status`, `retryable`, `started_at`, and on completion
`ended_at`; failures also contain payload-free `error_code`. Statuses are
`RUNNING`, `FAILED`, `SUCCEEDED`. Nontransient failures and retry exhaustion block; abandoned
RUNNING permits one recovery. A lost lease cannot publish FAILED, so persisted RUNNING
remains explicit incomplete evidence. Valid independent SQL checkpoints are not erased.

Both checkpoint helper forms below return exactly
`{batch, population_digest, mapping_digest, contract_digest, row_count, committed_at,
coverage_start, coverage_end}`:

```python
# Same SERIALIZABLE, non-autocommit connection; retain fence throughout extraction.
acquire_source_read_lock(cursor)
head = source_checkpoint_evidence(cursor, "Clarity")
ledger = source_checkpoint_evidence(cursor, "Clarity", expected_batch)
assert head == ledger and head["batch"] == expected_batch
```

`coverage_start` / `coverage_end` are durable generation horizons, **not publication or
completion clocks**. Populations carry `coverage: {start, end}`. Initial source seeds use
the approved initial history horizon; subsequent commits start at the previous immutable
source coverage end and end at the new population's verified covered-through time.
Freshness must use `coverage_end`, with no `committed_at` or row-audit fallback. A late old
batch remains old/stale. Zero-change plans advance coverage only when their generation
horizon advances. Missing coverage metadata is rejected. Nonempty legacy checkpoint
tables require a reviewed generation-evidence backfill; the upgrade refuses to invent
coverage from old commit markers.

The pinned Synthea path fixes Java's timezone to UTC and derives its actual seed end from
the verified `simulation_end_date`: **midnight UTC** on that date, not `--at`'s later time
of day. Its default initial horizon begins one calendar year before that actual end.
Imported FHIR's explicitly supplied `--at` attests its complete input horizon; it is not
derived from the latest clinical event. Controlled daily/zero plans cover the continuing
cohort through their supplied `--at`.

`committed_at` remains a diagnostic publication marker, selected in SQL under the
exclusive fence before DML and verified after the actual commit. It is not the physical
completion instant and is never the source coverage clock. `row_count` counts changed rows.
`dbo.PrepareSyntheticSourcePublication` selects `SYSUTCDATETIME()` only when strictly above
the maximum prior head/ledger marker and **every model's native audit maximum**; otherwise
it advances that upper bound by **one datetime2(7) tick (100 ns)**. Parameterized upserts
and all source audit triggers share this read-only per-session stamp. Fresh non-pooled
ODBC sessions prevent stamp reuse across attempts. Unchanged rows are not rewritten.
Both equal caller `--at` values and repeated/backward SQL timer values therefore leave
changed rows strictly beyond the previous committed native audit boundary. True zero
commits update only auxiliary coverage/head/ledger state, not source row audits.

Equal clinical instants remain unchanged: a second demographic change at the same `--at`
corrects the existing same-instant dimension version instead of creating an empty SCD
interval. Native audits still distinguish its committed correction. Row capture remains
`audit > last table audit watermark AND audit <= MAX(audit)` under the shared fence;
no capture-window widening or changes to the approved 454 source columns are introduced.

Raw exports are uploaded and journaled before clinical parsing, so a rejected or
interrupted baseline retains durable review evidence. Five-day cleanup runs after
successful publication. It deletes only successful,
exactly Fabric-acknowledged export/export-manifest artifacts with no recovery hold,
excluding expected and last-good source batches. It never age-purges population/identity
state, checkpoints, or plans. Fenced retirement precedes conditional ETag deletion and
rejects late holds. Fabric/operator callers must acquire the same Blob lease:

```python
with blobs.exclusive():
    blobs.acknowledge_batch(
        batch,
        plan_digest=summary["plan_digest"],
        source_digests=summary["source_digests"],
        tables=summary["tables"],
    )
    blobs.set_hold(batch, "fabric-recovery", active=True)
    # Release hold only after dependent recovery is no longer needed.
    blobs.set_hold(batch, "fabric-recovery", active=False)
    deleted = blobs.cleanup()
```

Local acceptance ran the pinned jar with five patients inside a 2-vCPU/4-GiB container:
8 retained encounters; all 13 canonical clinical tables populated; both complete source
projections passed integrity checks (171 Clarity rows, 922 Caboodle rows). This is a
lightweight smoke result, **not** a measured 1000-patient seed or daily SQL load.
The same image round-tripped the population/identities through durable local JSON and
validated subsequent zero/normal/spike profiles: **0 / 550 / 5050** combined source-row
changes. The source-focused suite has **64 passing tests**, including simulated Blob
server leases/ETags, failure/restart journals, independent source recovery, safe retention,
strict ODBC cursor budgets, same-`--at` corrections against a frozen native clock, and
independent coverage/publication clocks; these are not live Blob/SQL acceptance.
Live Azure SQL migration/load correctness, S0 throughput, Blob/managed-identity connectivity,
and full-pilot sizing remain unverified. Offline tests do not replace the final reviewed
Terraform deployment and live acceptance gates.
