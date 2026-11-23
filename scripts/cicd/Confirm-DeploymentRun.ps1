param(
    [Parameter(Mandatory)][int]$RunId,
    [Parameter(Mandatory)][int]$DefinitionId
)
$ErrorActionPreference = 'Stop'
if ($RunId -lt 1 -or $DefinitionId -lt 1) { throw 'Select a Fabric infrastructure apply run and configure FABRIC_INFRA_PIPELINE_ID.' }
if (-not $env:SYSTEM_ACCESSTOKEN) { throw 'Pipeline job access token is unavailable.' }
$uri = "$($env:SYSTEM_COLLECTIONURI)$($env:SYSTEM_TEAMPROJECTID)/_apis/build/builds/$RunId`?api-version=7.1"
$build = Invoke-RestMethod $uri -Headers @{ Authorization = "Bearer $env:SYSTEM_ACCESSTOKEN" }
if ($build.definition.id -ne $DefinitionId -or $build.result -ne 'succeeded' -or $build.status -ne 'completed' -or $build.sourceBranch -ne 'refs/heads/main') {
    throw 'The target bindings must come from a completed successful Fabric infrastructure main build.'
}
