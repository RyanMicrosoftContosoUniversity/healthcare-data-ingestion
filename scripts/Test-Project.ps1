$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    & uv run --locked ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
    & uv run --locked ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Formatting check failed.' }
    & uv run --locked pytest
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & uv run --locked python -m build
    if ($LASTEXITCODE -ne 0) { throw 'Package build failed.' }
}
finally {
    Pop-Location
}
