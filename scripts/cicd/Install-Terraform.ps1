$ErrorActionPreference = 'Stop'
$version = '1.13.4'
$archive = "terraform_${version}_windows_amd64.zip"
$directory = Join-Path ([IO.Path]::GetTempPath()) "healthcare-terraform-$version"
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$uri = "https://releases.hashicorp.com/terraform/$version"
Invoke-WebRequest "$uri/$archive" -OutFile (Join-Path $directory $archive)
$checksums = (Invoke-WebRequest "$uri/terraform_${version}_SHA256SUMS").Content
if ($checksums -is [byte[]]) { $checksums = [Text.Encoding]::UTF8.GetString($checksums) }
$line = ($checksums -split "`n" | Where-Object { $_.Trim().EndsWith(" $archive") })
if (@($line).Count -ne 1) { throw 'Terraform archive checksum is missing or ambiguous.' }
$expected = ($line.Trim() -split '\s+')[0]
$actual = (Get-FileHash (Join-Path $directory $archive) -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'Terraform download checksum mismatch.' }
Expand-Archive (Join-Path $directory $archive) -DestinationPath $directory -Force
Write-Host "##vso[task.prependpath]$directory"
& (Join-Path $directory 'terraform.exe') version
if ($LASTEXITCODE -ne 0) { throw 'Terraform verification failed.' }
