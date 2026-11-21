param(
    [Parameter(Mandatory)][ValidateSet('Plan', 'Apply')][string]$Phase,
    [Parameter(Mandatory)][ValidateSet('bootstrap', 'workload')][string]$Module
)
$ErrorActionPreference = 'Stop'
if (-not $env:idToken -or -not $env:servicePrincipalId) { throw 'The approved federated Azure service connection is required.' }
$env:ARM_USE_OIDC = 'true'
$env:ARM_OIDC_TOKEN = $env:idToken
$env:ARM_CLIENT_ID = $env:servicePrincipalId
$env:ARM_TENANT_ID = $env:tenantId
$env:ARM_SUBSCRIPTION_ID = '910ebf13-1058-405d-b6cf-eda03e5288d1'
$env:FABRIC_USE_CLI = 'true'
$env:TF_IN_AUTOMATION = 'true'
$account = az account show -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $account.id -ne $env:ARM_SUBSCRIPTION_ID -or $account.tenantId -ne '35acf02c-4b87-4ae6-9221-ff5cafd430b4') {
    throw 'Service connection targets a different approved subscription/tenant.'
}
$moduleDirectory = (Resolve-Path 'infrastructure\terraform').Path
if ($Module -eq 'bootstrap') { $moduleDirectory = Join-Path $moduleDirectory 'bootstrap' }
$planDirectory = $env:PLAN_DIRECTORY
New-Item -ItemType Directory -Force $planDirectory | Out-Null
$planFile = Join-Path $planDirectory 'reviewed.tfplan'
$receiptFile = Join-Path $planDirectory 'plan-evidence.json'
$backendKey = if ($Module -eq 'bootstrap') { 'healthcare-bootstrap.tfstate' } else { 'healthcare-data-ingestion.tfstate' }
$backendArguments = @(
    '-backend-config=resource_group_name=healthcare-data-ingestion-rg',
    '-backend-config=storage_account_name=hcingestiontfstate',
    '-backend-config=container_name=tfstate',
    "-backend-config=key=$backendKey",
    '-backend-config=use_azuread_auth=true',
    '-backend-config=use_oidc=true'
)
function Invoke-Tf([string[]]$Arguments) {
    & terraform "-chdir=$moduleDirectory" @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Terraform $($Arguments[0]) failed." }
}
if ($Phase -eq 'Plan') {
    if (-not (Test-Path $env:VARIABLES_FILE)) { throw 'Actual reviewed JSON deployment inputs are required.' }
    $variables = Get-Content $env:VARIABLES_FILE -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in @('subscription_id', 'tenant_id')) {
        $expected = if ($key -eq 'subscription_id') { $env:ARM_SUBSCRIPTION_ID } else { $account.tenantId }
        if ($variables.ContainsKey($key) -and $variables[$key] -ne $expected) { throw "Unapproved $key." }
    }
    if ($variables.activate_alerts -or $variables.activate_generator) {
        throw 'Live runtime/email acceptance is required before separate schedule or alert activation.'
    }
    if ($Module -eq 'workload' -and (
        $variables.ContainsKey('generator_image') -and
        $variables.generator_image -and
        $variables.generator_image -notmatch '^hcingestionacr\.azurecr\.io/.+@sha256:[0-9a-f]{64}$'
    )) { throw 'The generator image must be the actual published immutable registry digest.' }
    $stateMode = 'remote'
    if ($Module -eq 'bootstrap') {
        $principal = az ad sp show --id $env:ARM_CLIENT_ID --query id -o tsv
        if ($LASTEXITCODE -ne 0 -or $variables.deployment_principal_object_id -ne $principal) {
            throw 'Bootstrap deployment principal must match the actual federated service principal.'
        }
        $exists = az group exists --name healthcare-data-ingestion-rg -o tsv
        if ($LASTEXITCODE -ne 0) { throw 'Resource group discovery failed.' }
        if ($exists -eq 'false') { $stateMode = 'initial-local' }
    } else {
        $version = (Get-Content "$env:RELEASE_ROOT\bundle\release.json" -Raw | ConvertFrom-Json).framework_version
        if ($variables.framework_version -and $variables.framework_version -ne $version) { throw 'Framework input does not match validated bundle.' }
        $variables.framework_version = $version
        if (-not $variables.retained_framework_versions) { $variables.retained_framework_versions = @($version) }
        if (@($variables.retained_framework_versions).Count -ne 1) {
            throw 'Retained multi-version releases require all verified prior bundles; do not substitute the current bundle.'
        }
        $variables.release_bundle_directories = @{ $version = "$env:RELEASE_ROOT\bundle" }
    }
    $variablesFile = Join-Path $env:AGENT_TEMPDIRECTORY 'healthcare.auto.tfvars.json'
    $variables | ConvertTo-Json -Depth 30 | Set-Content $variablesFile
} else {
    $evidence = Get-Content $receiptFile -Raw | ConvertFrom-Json
    if ($evidence.commit -ne $env:BUILD_SOURCEVERSION -or $evidence.module -ne $Module) { throw 'Reviewed plan source/module mismatch.' }
    if ($evidence.plan_sha256 -ne (Get-FileHash $planFile -Algorithm SHA256).Hash) { throw 'Reviewed plan was changed.' }
    $stateMode = $evidence.state_mode
}
if ($Module -eq 'bootstrap') {
    $backend = if ($stateMode -eq 'initial-local') { 'local' } else { 'azurerm' }
    "terraform { backend `"$backend`" {} }" | Set-Content (Join-Path $moduleDirectory 'backend_override.tf')
}
if ($stateMode -eq 'initial-local') {
    Invoke-Tf @('init', '-input=false', '-lockfile=readonly')
} else {
    Invoke-Tf (@('init', '-input=false', '-lockfile=readonly') + $backendArguments)
}
Invoke-Tf @('validate')
if ($Phase -eq 'Plan') {
    Invoke-Tf @('plan', '-input=false', '-lock-timeout=5m', "-var-file=$variablesFile", "-out=$planFile")
    & terraform "-chdir=$moduleDirectory" show -json $planFile | Set-Content (Join-Path $planDirectory 'reviewed.plan.json')
    if ($LASTEXITCODE -ne 0) { throw 'Plan rendering failed.' }
    uv run --locked python scripts\cicd\delivery.py plan-check "$planDirectory\reviewed.plan.json"
    if ($LASTEXITCODE -ne 0) { throw 'Plan contains unapproved deletion/replacement.' }
    @{
        commit = $env:BUILD_SOURCEVERSION
        module = $Module
        state_mode = $stateMode
        plan_sha256 = (Get-FileHash $planFile -Algorithm SHA256).Hash
        subscription_id = $env:ARM_SUBSCRIPTION_ID
    } | ConvertTo-Json | Set-Content $receiptFile
} else {
    Invoke-Tf @('apply', '-input=false', '-lock-timeout=5m', $planFile)
    if ($stateMode -eq 'initial-local') {
        'terraform { backend "azurerm" {} }' | Set-Content (Join-Path $moduleDirectory 'backend_override.tf')
        $migrated = $false
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            & terraform "-chdir=$moduleDirectory" init -input=false -migrate-state -force-copy @backendArguments
            if ($LASTEXITCODE -eq 0) { $migrated = $true; break }
            Start-Sleep -Seconds 30
        }
        if (-not $migrated) { throw 'Bootstrap state migration failed. Recover/import the existing bootstrap resources; never recreate or destroy them.' }
    }
    & terraform "-chdir=$moduleDirectory" output -json | Set-Content (Join-Path $planDirectory 'outputs.json')
    if ($LASTEXITCODE -ne 0) { throw 'Deployment output collection failed.' }
}
