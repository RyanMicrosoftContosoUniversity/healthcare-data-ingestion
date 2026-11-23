# Azure DevOps delivery

Target: **Contoso-University / Fabric**. Repository:
`RyanMicrosoftContosoUniversity/healthcare-data-ingestion`.

## Independent ownership

The November 23 clarification separates three deployment lanes. Shared validation
remains CI; Azure image builds and SQL migrations remain separate source operations.

| ID | Pipeline | YAML | Owns |
| --- | --- | --- | --- |
| 34 | `healthcare-ingestion-azure-infrastructure` | `pipelines\azure-infrastructure.yml` | All Terraform-managed Azure resources; select `bootstrap` for RG/backend or `azure` for recurring Azure resource updates |
| 36 | `healthcare-ingestion-fabric-infrastructure` | `pipelines\fabric-infrastructure.yml` | Terraform-managed Fabric workspaces, capacity assignment, workspace users/groups/SP access, lakehouses and metadata SQL database |
| 35 | `healthcare-ingestion-fabric-artifacts` | `pipelines\fabric-artifacts.yml` | Versioned Fabric environments/libraries, notebook definitions, Airflow item/DAG/plugin content and declared data-pipeline definitions |
| 33 | `healthcare-ingestion-ci` | `pipelines\ci.yml` | Lint/native/Spark tests, package/bundle and independent Terraform-root validation |
| 37 | `healthcare-ingestion-source-operations` | `pipelines\source-operations.yml` | Existing generator image publication and reviewed SQL migrations; not Terraform infrastructure or Fabric notebook deployment |

Registered November 23, 2026 in the `\healthcare-data-ingestion` folder. Definitions
34/35 retain their history; 36/37 are new. Artifact definition 35 has
`CI_PIPELINE_ID=33` and `FABRIC_INFRA_PIPELINE_ID=36`; source operations 37 has
`CI_PIPELINE_ID=33`. Infrastructure has no application-CI binding.
New definitions were added only to the required existing GitHub and fabric-sc
connection permissions; existing unrelated grants were preserved.

The split was published in GitHub **PR #2**, branch
`build/separate-deployment-pipelines`, and has merged. Delivery definitions
34/35/36/37 now default to `main`; CI 33 also defaults to main.
The runner rejects Terraform delivery from review branches; artifact/source
operations likewise require exact successful main CI.
All five entrypoints and bootstrap/apply/migration template branches compiled
server-side. This is definition registration, not a workload apply.

Azure and Fabric infrastructure pipelines do not consume the ingestion wheel,
notebook bundle or an application CI run. They validate their checked-out Terraform
root, produce a saved plan and require the existing plan review before exact-plan
apply. Delivery is restricted to merged main. Their default is plan only.

Fabric artifacts consume a specific successful main CI run for the same commit
and a successful Fabric infrastructure apply run. This decouples infrastructure
updates from application publication while retaining real artifact/test provenance.
No pipeline creates another capacity, seeds sources or activates a runtime release,
daily generator schedule or operational alerts.

## Terraform roots and state

| Root | Backend key | Boundary |
| --- | --- | --- |
| `infrastructure\terraform\bootstrap` | `healthcare-bootstrap.tfstate` | Resource group, state storage/container and deployment-principal state access |
| `infrastructure\terraform\azure` | `healthcare-azure.tfstate` | SQL, storage, ACR, Container Apps, Azure identities/grants, budgets and monitoring |
| `infrastructure\terraform\fabric` | `healthcare-fabric.tfstate` | Only durable Fabric infrastructure and workspace access |

All three use the protected `hcingestiontfstate/tfstate` backend after bootstrap.
Bootstrap alone owns the group/backend, even though its YAML entry point is the
same Azure lane. Never manage a resource in two roots or manage notebook content
through Terraform as well as artifact publication.

The previous mixed root was not applied through these pipelines. If its old
`healthcare-data-ingestion.tfstate` blob exists, the new Azure/Fabric runner stops:
review and perform a state split/import before applying independent states.
Moving files does not move deployed state. Do not recover by deleting/recreating
resources. Initial bootstrap migrates its local state immediately to the protected
backend; interrupted bootstrap still requires preserved state or reviewed import.
Terraform state is never published as an ADO artifact.

## Inputs and identities

Use the existing GitHub installation connection and **fabric-sc** WIF connection,
authorized only for the relevant definitions. No stored Azure client secret is used.
The deployment identity needs state access plus scoped rights for each lane.
Assigning existing Entra users/groups to Fabric is not creating Entra accounts.

Upload actual per-root JSON inputs as ADO Secure Files:

- Bootstrap: actual `deployment_principal_object_id` matching fabric-sc.
- Azure: confirmed `alert_email`, `budget_start_date` and optional immutable
  `generator_image`. `admin_ipv4=null` leaves personal SQL client access disabled.
  Supply an approved public IPv4 only when that access is needed.
- For new runtime identities: `provision_runtime_principals=true` and the actual
  `deployment_principal_object_id` matching fabric-sc. Terraform creates all four
  principals and emits their real object IDs; no placeholder principal IDs are used.
- For existing runtime identities: leave `provision_runtime_principals=false` and
  supply all four actual `runtime_principal_object_ids`.
- Fabric: actual control/orchestrator `runtime_principal_object_ids`; optional
  `workspace_access` entries identify `workspace` (`data`/`metadata`), `principal_id`,
  `principal_type` (`User`/`Group`/`ServicePrincipal`) and `role`.

Approved subscription, region and capacity defaults are preserved. Private keys,
tokens and SQL passwords must never be placed in Terraform variables/state or
build artifacts. Inputs do not silently substitute UAIs for certificate identities.

### Runtime principals and Key Vault

The November 23 instruction adds `hcingestion-runtime-kv` in the Azure resource
group and the four `hc-ingestion-runtime-<role>` applications/service principals
(`control`, `source-reader`, `diagnostics`, `orchestrator`). These are managed in
the existing Azure root/state. Entra applications are tenant-level objects, not
resources physically contained in the resource group.

The vault uses Azure RBAC, purge protection and 90-day soft deletion. Each new app
has a distinct 12-month, vault-generated RSA certificate. Terraform reads only
the public certificate into `azuread_application_certificate`; no private-key
resource, certificate import contents or Key Vault secret value is used. Outputs
contain IDs and certificate/secret URIs only. Exportable certificates support the
existing protected PFX-file runtime contract, not retrieval by unauthenticated apps.

The deployment principal explicitly owns both applications and service principals.
Its Microsoft Graph `Application.ReadWrite.OwnedBy` permission requires tenant
admin consent before creation; Terraform does not grant privileges to its own
deployment identity. Discovery on November 23 found no Graph app-role grants on
fabric-sc, so actual principal creation remains blocked until that is resolved.
The deployment application's client ID is `1a7a01d1-ea73-47ec-8051-6b6527f68ce2`.
The runtime apps themselves do not receive Graph API permissions.

The deployment principal has vault-scoped **Key Vault Certificates Officer** for
certificate generation/public readback. Private-key retrieval, certificate-file
delivery to Fabric/Airflow and runtime activation remain separate protected steps.
Automatic Key Vault renewal is not enabled: Entra credential rotation must be
reviewed with overlap before expiry rather than rotating only the vault copy.

After Azure apply, copy its `runtime_principal_object_ids` output into the Fabric
Secure File. Keep managed mode enabled on later Azure runs; switching it off
would attempt protected identity deletion and is rejected.

Azure owns Azure RBAC even when the principal is a Fabric workspace identity.
After Fabric creation, pass its actual `fabric_data_identity_object_id` output as
Azure's `fabric_workspace_identity_object_id` and review/apply the Azure grant
update. The initial Azure plan omits only these not-yet-resolvable grants; Fabric
does not need to own Azure resources or read Azure state. Retain the identity on
subsequent updates; removal would require deletion and is rejected by plan checks.

## Fabric artifact CI/CD

Set `CI_PIPELINE_ID` and `FABRIC_INFRA_PIPELINE_ID` on the artifact definition.
Select `ciRunId` for the exact merged-main commit and `infrastructureRunId` for
the target Fabric apply. The selected build definition, successful main status,
apply-module/run provenance and all bundle hashes are checked before publication.
The apply artifact contains outputs plus deployment provenance, not Terraform state.

The compiler emits a hashed `fabric-items.json` deployment manifest. The initial
bundle contains three Notebook declarations; no new business pipeline is invented.
The publisher can also deploy a declared `DataPipeline` whose `definition_file`
contains Fabric item-definition JSON with InlineBase64 parts. Each item declares
its target workspace alias (`data` or `metadata`), so one release can target both
workspaces. New definition files must be part of the CI-hashed bundle.

Notebook attachments bind to actual environment/lakehouse/workspace IDs without
changing the immutable source bundle. Environments and notebooks are version-named;
an existing version with different notebook/pipeline content fails and requires a
new version rather than overwriting silently. The publisher awaits Fabric operations,
reads definitions back, publishes environment libraries and verifies Airflow file
bytes. Receipts capture target IDs and partial failures. Successful publication is
explicitly **not activation or Airflow recognition evidence**.

## Delivery order

1. Review/merge the pipeline-split PR.
2. Run Azure `module=bootstrap` with actual inputs, review its plan and apply.
3. Run Azure `module=azure` for the foundation. Leave `provision_generator=false`
   and `activate_alerts=false`; registry creation does not require an image.
4. Run Fabric infrastructure for workspaces, database, lakehouses and approved access.
5. Apply Azure's follow-up Fabric-identity grants using the real Fabric output.
6. Publish an immutable generator image through source operations; provision its
   manual job through Azure Terraform only after supplying the real image digest.
7. Publish Fabric artifacts using the successful application CI and Fabric apply IDs.
8. Apply reviewed SQL migrations via source operations after network/DDL permissions
   exist; complete runtime certificates/configuration, recognition and live acceptance
   before publishing/activating a runtime candidate or enabling schedules/alerts.

The actual costed Terraform plan remains the existing apply-review gate, not a new
architecture decision. Deletions/replacements and cross-boundary resource types fail
closed. Restrict saved-plan artifact access to authorized reviewers.
