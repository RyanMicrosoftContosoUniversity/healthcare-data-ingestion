param(
    [Parameter(Mandatory)][int]$RunId,
    [Parameter(Mandatory)][int]$DefinitionId
)
$ErrorActionPreference = 'Stop'
if ($RunId -lt 1 -or $DefinitionId -lt 1) { throw 'Select a successful healthcare CI run; CI_PIPELINE_ID must be configured.' }
if ($env:BUILD_SOURCEBRANCH -ne 'refs/heads/main') { throw 'Cloud delivery requires the reviewed, merged main branch.' }
if (-not $env:SYSTEM_ACCESSTOKEN) { throw 'Pipeline job access token is unavailable.' }
$uri = "$($env:SYSTEM_COLLECTIONURI)$($env:SYSTEM_TEAMPROJECTID)/_apis/build/builds/$RunId`?api-version=7.1"
$build = Invoke-RestMethod $uri -Headers @{ Authorization = "Bearer $env:SYSTEM_ACCESSTOKEN" }
if ($build.definition.id -ne $DefinitionId -or $build.result -ne 'succeeded' -or $build.status -ne 'completed') {
    throw 'The selected run is not a completed successful healthcare CI build.'
}
if ($build.sourceVersion -ne $env:BUILD_SOURCEVERSION -or $build.sourceBranch -ne 'refs/heads/main') {
    throw 'CI must validate the exact main commit being delivered, not another branch or a newer checkout.'
}
