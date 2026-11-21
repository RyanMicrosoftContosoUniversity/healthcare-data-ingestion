# Azure DevOps delivery

Target: **Contoso-University / Fabric**, GitHub repository
`RyanMicrosoftContosoUniversity/healthcare-data-ingestion`.
The three YAML definitions live under `pipelines`. They use hosted agents and the
existing GitHub installation connection. Only infrastructure and release delivery
use the federated Azure connection **fabric-sc**; no personal token or stored Azure
client secret is used by those jobs.

| Pipeline | Purpose | Default |
| --- | --- | --- |
| `healthcare-ingestion-ci` | Native lint/tests/build, actual Linux Spark/Delta tests, both Terraform modules; hashed release artifact | PR/main validation only |
| `healthcare-ingestion-infrastructure` | Bootstrap or workload validation, saved plan, restricted review and exact-plan apply | Plan only; no implicit apply |
| `healthcare-ingestion-release` | Immutable ACR image, transactional SQL migrations or verified Fabric assets | No source seeding, release/schedule/alert activation |

Registered definition IDs are **33**, **34**, **35**, respectively, in folder
`\healthcare-data-ingestion`. Review branch: `build/healthcare-ado-delivery`, PR **#1**.
Actual PR CI run: **1127**. All three definitions passed server-side YAML compilation.

Set `CI_PIPELINE_ID` on both delivery definitions and `INFRA_PIPELINE_ID` on the
release definition to the registered IDs. Select `ciRunId` for the exact successful
main commit being delivered. Draft/unreviewed branches may run CI but cannot deploy
cloud changes. Pipeline job tokens require read access to these specific builds and
artifacts. Authorize the GitHub and Azure connections only for relevant definitions.

## Delivery order

1. Review/merge the implementation PR and run CI on main.
2. Run infrastructure with `module=bootstrap`, its actual JSON Secure File and
   `apply=true`. Review the saved plan before resuming. The initial bootstrap state
   migrates immediately to `hcingestiontfstate/tfstate/healthcare-bootstrap.tfstate`.
3. Run workload foundation with actual admin IP, confirmed email and all four
   certificate-backed runtime SP object IDs. Leave `provision_generator=false` and
   `activate_alerts=false`; this provisions the registry without needing a nonexistent
   image and creates no generator job.
4. Run release `operation=generator-image`. Use its actual immutable image digest in
   the reviewed workload inputs; set `provision_generator=true` only when appropriate.
   The new job is manual, not scheduled.
5. Provision/grant the approved database migration identity, authorize its network
   access, then run `database-migrations` with its endpoint JSON Secure File.
6. Run `fabric-assets` with the successful workload apply's `infrastructureRunId`.
   Environment publication is awaited; every Airflow uploaded file is read back and
   hashed. Receipts distinguish complete publication from partial failure.
7. Complete certificate delivery, SQL/runtime grants, actual physical maps,
   Airflow requirements/configuration/recognition and live acceptance described in
   `runtime-operations.md`. Only real PR review and acceptance evidence may publish
   or activate a `ReleaseManager` candidate. These delivery jobs do not manufacture
   that evidence, seed production sources or enable operational alerts.

The actual costed Terraform plan is the existing infrastructure approval gate, not
a new architecture decision. Delete/replacement actions fail rather than bypassing
that gate. Operational alert or generator-schedule activation is deliberately
rejected by this initial-delivery pipeline until separately accepted.

## Inputs and recovery

Secure Files contain **JSON**, not HCL or passwords. Bootstrap requires
`deployment_principal_object_id` matching the actual `fabric-sc` principal.
Workload requires `admin_ipv4`, `alert_email` and `runtime_principal_object_ids`
with `control`, `source-reader`, `diagnostics`, `orchestrator`. Approved subscription,
tenant, capacity and region defaults are retained. Never put certificate private
keys, tokens or SQL passwords into Terraform variables/state or pipeline artifacts.

The migration JSON has exactly `clarity`, `caboodle`, `metadata`, each containing
`server` and `database`. Metadata must be the dedicated Fabric SQL transactional
endpoint, not a lakehouse analytics endpoint. ODBC 18 and pre-existing approved
DDL privileges are checked; runtime identities are not promoted to administrators.

Bootstrap cannot blindly rerun local state over existing resources. If its initial
apply is interrupted before remote-state migration, preserve the surviving state
when possible or import the existing protected group/account/container/role into
the remote bootstrap state. Never delete/recreate them to recover. Terraform state
is not published as an Azure DevOps artifact.

Saved plan artifacts can contain infrastructure metadata; restrict project/build
artifact access to authorized reviewers. A newer CI build or changed variables
does not replace an already-reviewed plan. Multi-version retention needs all actual
verified prior bundles; the first-release pipeline rejects substituting one bundle
for every historical version.
