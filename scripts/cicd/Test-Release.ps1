param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$env:SOURCE_DATE_EPOCH = git show -s --format=%ct HEAD
if ($LASTEXITCODE -ne 0) { throw 'Commit timestamp lookup failed.' }
uv run --locked ruff check .
if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
uv run --locked ruff format --check .
if ($LASTEXITCODE -ne 0) { throw 'Formatting failed.' }
uv run --locked pytest --junitxml=build\native-tests.xml
if ($LASTEXITCODE -ne 0) { throw 'Native tests failed.' }
uv run --locked python -m build
if ($LASTEXITCODE -ne 0) { throw 'Package build failed.' }
$version = uv run --locked python -c "import pathlib,tomllib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])"
if ($LASTEXITCODE -ne 0) { throw 'Version lookup failed.' }
uv run --locked python -m healthcare_ingestion.build_artifacts `
    --release metadata\framework\demo-release.json --contracts database\schema-contracts `
    --wheel "dist\healthcare_ingestion-$version-py3-none-any.whl" --lock uv.lock `
    --output "$OutputDirectory\bundle"
if ($LASTEXITCODE -ne 0) { throw 'Bundle compilation failed.' }
uv run --locked python scripts\cicd\delivery.py seal $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'CI provenance sealing failed.' }
