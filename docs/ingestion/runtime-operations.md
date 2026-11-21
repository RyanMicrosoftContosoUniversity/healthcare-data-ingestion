# Runtime, Release Preparation and Live Acceptance

## Scope and authority

Handoff 03 authorizes local development, not cloud apply/activation. Preserve independent
Clarity/Caboodle generation, 28 append-only Bronze tables and Clarity Patient Silver only.
No new capacity, additional Silver, Gold, Teams or custom backup infrastructure.
The older 17-table diagrams remain historical design assets; executable control contracts
are in `database\metadata\`, including `OPERATIONAL_RECORDS.md` and `SOURCE_COVERAGE.md`.

## Local entry points

Run `.\scripts\Test-Project.ps1` for native tests, Ruff and package builds. Actual Spark
tests require the existing Linux validation image, Python 3.13/Java 21, Spark 4.1/Delta 4.2.
Windows skips are not evidence of Spark acceptance.

Prepare a release after building its matching wheel:

```powershell
uv run --locked python -m healthcare_ingestion.build_artifacts `
  --release metadata\framework\demo-release.json `
  --contracts database\schema-contracts `
  --wheel dist\healthcare_ingestion-0.1.0-py3-none-any.whl `
  --lock uv.lock --output build\releases\0.1.0
```

Preparation validates the wheel's package/version and source contracts, hashes the
wheel/lock/notebooks/DAGs/application modules and refuses to overwrite different content.
All deployment requests remain `UNEXECUTED`; prepared artifacts are `UNPUBLISHED`.
The bundle includes three daily DAGs, five-minute reconciliation, two reusable notebook
definitions, Airflow plugin modules, environment dependencies and request manifests.
Terraform creates separate immutable notebook items/environments per retained version.
Never remove a referenced prior version or activate a repaired obsolete candidate over
a newer active release.

Fabric Runtime 2.0 components and Airflow 2.10.5/Python 3.12 are the documented profiles;
live configuration still needs validation. Official references, checked November 21, 2026:

```text
https://learn.microsoft.com/en-us/fabric/data-engineering/runtime-2-0
https://learn.microsoft.com/en-us/fabric/data-factory/apache-airflow-jobs-concepts
```

Stable environment wheel/external-library uploads and publish are included in the
request manifest. Airflow DAG/plugin file uploads use beta APIs; verify their live
support before publication. Infrastructure remains Terraform-owned; library/code
deployment is application content, not a second infrastructure owner.

## Machine runtime configuration

Airflow reads `HC_RUNTIME_CONFIG_PATH`, pointing to a protected JSON configuration.
Notebook runs receive that same non-secret configuration plus operation IDs, owner
and DAG-run identity. Supply actual `environment`, `data_workspace_id` and
`release_notebooks` keys such as `0.1.0-clarity_bronze`; use Terraform outputs, not guessed IDs.

`connections` maps `metadata-control`, `clarity-source` and `caboodle-source` to actual SQL data-plane
`server`, `database` and `identity_ref`. `identities` maps logical roles to tenant/client
UUIDs and a `certificate_path_env` such as `HC_CONTROL_CERTIFICATE_PATH`.
The referenced PEM/PFX file must be securely delivered to the driver. No private keys,
client secrets, personal tokens or signed URLs belong in metadata, notebook parameters
or Terraform state. A UAI client ID does not make `CertificateCredential` work.
ODBC Driver 18 must be installed; the SQL audience is explicitly
`https://database.windows.net/.default`, with encryption and 30-second connection/query bounds.

`recovery_storage` supplies an Azure Blob `account_url`, `container`, `prefix` and
`identity_ref`; `staging_root` is an approved Files path, not production Tables.
`generator_storage` supplies the generator account URL/identity and distinct
`state_container=population`, `export_container=exports`,
`manifest_container=checkpoints`. `log_ingestion` supplies the reviewed DCE endpoint,
DCR `rule_id`, stream and publisher identity.

## Execution and recovery

Daily queuing durably pins the active framework by environment/workflow/DAG-run identity.
Retrying that run after release activation keeps its original version and operation IDs.
The notebook holds one shared SQL source transaction/catalog pass per execution-profile group.
It checks the expected Blob plan/population checksum and the matching current SQL
head/immutable ledger before registering and freezing bindings. An older recent source
success cannot replace the expected slot. Overall generator failure does not discard
an independently committed source.

Source readers cap control downloads at 4 MiB and references at 128 MiB, reject oversized
or mismatched bytes and preserve seven-digit UTC timestamps. Generation coverage and
changed-row watermarks are different. Zero changed rows can publish fresh verified
coverage; a later processing/publication timestamp cannot make old source data fresh.

Immutable capture, write intent and Delta publication evidence cross the SQL/Delta
failure boundary. Reconciliation recovers a committed Delta write even if its commit
receipt was lost. It never steals live owners or republishes the same operation.
Shared-application metrics are collected once under an exact application/attempt
identity, not copied onto each table.

Airflow submission stores intent/receipt and per-operation dispatch history. A lost
POST response remains `SUBMISSION_UNCERTAIN` across cycles; do not blindly resubmit.
Resolve it against real job evidence before operator intervention. Running/recent jobs
require correlation, not automatic attribution. Dispatch is bounded; unresolved limits
require the operator, without replacing frozen inputs or changing the framework version.

Reconciliation materializes missing daily expectations after 10 AM Eastern, emits a
control heartbeat and replays bounded event outboxes. Schedule queries include failures
and confirmed corruption; late success preserves deadline violation. Only the latest
daily slot per task drives current-freshness alerts. Heartbeat absence uses a 15-minute
window. Successful publications attempt primary event dispatch; reconciliation remains
the fallback when transport is unavailable.

Only matching, protected per-attempt transient transport failures qualify for automatic
retry after the pinned delay. The control store enforces the retry budget. Validation
failures and unresolved Delta uncertainty require correction/operator intervention;
they are not blind notebook retries. `BLOCKED_BY_DEPENDENCY` is the actual storage state.
The pinned task timeout cancels only its Spark job group and fences further publication;
it is separate from the 11 AM availability deadline. A possibly committed write remains
UNCERTAIN until actual Delta reconciliation, rather than being retried blindly.

Execution groups preserve notebook/environment/compute references and Spark settings.
Nondefault profiles require `execution_bindings["<version>:<profile-sha256>"]` with
the exact `signature` returned by `execution_signature` and a deployed `notebook_id`.
Absent or mismatched bindings fail closed. Startup settings must match the actual
session; task runtime settings are applied and restored without leaking to other tasks.
Validate notebook environment/compute binding before adding an entry to this registry.

## Quality, diagnostics and retention

Critical checks block publication; warning checks remain typed evidence. Quarantine
requires configured row/fraction bounds, protected Delta data and content-digest proof.
`replay_input` preserves original lineage and verifies schema/count/content; unprovable
selective replay requires full reprocessing, not an automatic production patch.
Historical source use requires a registered retained manifest plus matching data digest;
missing history fails instead of selecting current source.

`Worker.benchmark` is a separate opt-in invocation on fixed inputs. It cannot publish
production data or advance state. One warm-up and three measured trials materialize
full-column step outputs; artifacts measure I/O/optimizer-boundary effects too.
`Worker.collect_diagnostics` requires the real SQL attempt, activity run and exact Spark
workspace/item/Livy/application/application-attempt IDs. Unsupported fields stay null
with reasons. Diagnostic collection never changes data readiness.
Unexpected collection failures close their diagnostic attempt rather than leaving it
RUNNING. Benchmark input-freeze failures also retain terminal setup-trial evidence.

Mandatory run events are persisted independently of verbosity before delivery.
Operational alert rules stay disabled until real events/thresholds/absence signals
and email recovery/deduplication are accepted. Do not infer memory pressure or duration
regression from unsupported measurements. Transport failure and unsupported fields differ.
`Worker.evaluate_health` accepts actual comparable duration samples and actual sustained
used/allocated-memory samples plus explicit policies. It emits the corresponding events;
no baseline, measurement or automatic compute escalation is fabricated. Collector/session
identity discovery, representative baselines and these policies require live acceptance.

Retain Fabric business data indefinitely, without automatic age purge. Generator
exports/manifests expire only after confirmed consumption and five days, respecting
holds/current population/identities/checkpoints. The generator's `acknowledge_batch`
requires its exclusive lease and exact plan/population digests plus all 13/15 table names;
grant an actual authorized writer and verify all 28 committed outputs and readiness first.
Corruption/latest-failure blocks prohibit the helper's acknowledgement. Acknowledgement
does not release retention/recovery holds. Never acknowledge from notebook success alone.
Diagnostics/benchmarks have 30-day
retention; referenced execution/recovery/release evidence remains protected.

## Local validation checkpoint: November 21, 2026

Full native validation passed 191 tests with two Windows Spark-module skips;
the latest runtime selector passed 30 tests. Actual Linux Spark validation passed
all ten cases against the final timeout-aware code, not merely import/skip checks.
Ruff, source/wheel builds, CI YAML parsing and stable 28-table/454-column exports passed.
Both Terraform modules passed fmt/validate (one existing AzureRM deprecation warning).

`build\releases\0.1.0` contains 51 verified hashed artifacts and 37 package/plugin
modules matching current source, including all four DAG upload requests.
The release embeds contracts under `clarity-source` / `caboodle-source`.
All assets remain UNPUBLISHED and deployment requests UNEXECUTED. The raw demo
physical mappings are logical templates: finalize reviewed SQL/lakehouse bindings
before publication/activation. This is the pre-ADO immutable local bundle checkpoint,
not a claim that its bytes change when later CI builds a new candidate.

The subsequent CI/CD request deployed Azure DevOps definitions **33** (CI), **34**
(infrastructure), **35** (release) in **Contoso-University / Fabric** and published PR
**#1**. Hosted CI **1127 succeeded** against the actual PR code and published its byte-verified
bundle/provenance artifact. See `azure-devops-delivery.md` for delivery order and
remaining inputs. Live SQL/Fabric execution and R53 acceptance have not occurred.

## Infrastructure stop and live inputs

Review the bootstrap/workload Terraform plans before any apply. Bootstrap alone owns
the RG and protected state account; workload Terraform reads the RG. Retain/bootstrap
state securely, migrate it explicitly to Entra-authenticated locked/versioned Blob state,
and do not run initialization that silently copies or overwrites existing state.

Missing live inputs/checks remain: confirmed email/admin IP, registry image digest,
actual service principals/certificate delivery/roles, capacity/network headroom,
SQL/Fabric migration and negative-permission tests, ODBC 18, API/library/Airflow
recognition, all-table ingestion/consumption cleanup, representative seed/daily
throughput and alert delivery. No cloud resources, source seeds or alerts have been activated.
