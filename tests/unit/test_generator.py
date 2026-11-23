import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from healthcare_ingestion.generator import main, run_synthea, synthea_command

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace():
    path = ROOT / (".source-test-state-" + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_cli_demo_normal_rerun_zero_and_validation(workspace, capsys):
    shared = ["--root", str(ROOT)]
    assert (
        main(
            shared
            + [
                "demo",
                "--state",
                str(workspace),
                "--batch",
                "baseline",
                "--patients",
                "12",
                "--history-start",
                "2025-11-01T00:00:00Z",
                "--at",
                "2026-11-01T23:59:59Z",
            ]
        )
        == 0
    )
    args = shared + [
        "change",
        "--state",
        str(workspace),
        "--batch",
        "day1",
        "--at",
        "2026-11-02T12:00:00Z",
        "--profile",
        "normal",
    ]
    assert main(args) == 0
    assert main(args) == 0
    assert (
        main(
            shared
            + [
                "change",
                "--state",
                str(workspace),
                "--batch",
                "zero",
                "--at",
                "2026-11-03T12:00:00Z",
                "--profile",
                "zero",
            ]
        )
        == 0
    )
    assert main(shared + ["validate", "--state", str(workspace), "--batch", "zero"]) == 0
    output = capsys.readouterr().out
    assert "SyntheticNew" not in output and "MedicalRecordNumber" not in output
    assert '"Clarity": 0' in output and '"Caboodle": 0' in output


def test_fixed_bundle_import_is_validated_before_population_publication(workspace):
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "import-fhir",
                "--state",
                str(workspace),
                "--batch",
                "fixture",
                "--fhir-directory",
                str(ROOT / "scripts" / "synthetic-data" / "fixtures"),
                "--history-start",
                "2025-11-01T00:00:00Z",
                "--at",
                "2026-11-01T23:59:59Z",
            ]
        )
        == 0
    )
    document = json.loads((workspace / "batches" / "fixture.json").read_text())
    assert "Patient/patient-a" in document["population"]["fhir_archive"]


def test_pinned_synthea_command_cpu_memory_history_and_no_patient_logs(workspace):
    jar = workspace / "fixture.jar"
    jar.write_bytes(b"not-executed-test-binary")
    command = synthea_command(
        jar=jar,
        expected_sha256=hashlib.sha256(jar.read_bytes()).hexdigest(),
        output=workspace / "output",
        patients=1000,
        seed=1,
        reference_date="20261101",
    )
    assert "-XX:ActiveProcessorCount=2" in command
    assert "-Xmx2g" in command
    assert "--generate.thread_pool_size=2" in command
    assert "--generate.log_patients.detail=none" in command
    assert "--exporter.years_of_history=1" in command
    with pytest.raises(ValueError, match="fingerprint"):
        synthea_command(
            jar=jar,
            expected_sha256="0" * 64,
            output=workspace / "output",
            patients=1000,
            seed=1,
            reference_date="20261101",
        )
    with pytest.raises(ValueError, match="immutable"):
        run_synthea(version="latest")


def test_synthea_wrapper_reuses_only_verified_completed_output(workspace, monkeypatch):
    jar = workspace / "fixture.jar"
    jar.write_bytes(b"not-executed-test-binary")
    output = workspace / "output"
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        (output / "fhir").mkdir()
        shutil.copyfile(
            ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json",
            output / "fhir" / "fixture.json",
        )
        from types import SimpleNamespace

        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("healthcare_ingestion.generator.subprocess.run", fake_run)
    kwargs = {
        "version": "reviewed-fixture-release",
        "jar": jar,
        "expected_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "output": output,
        "patients": 1,
        "seed": 1,
        "reference_date": "20261101",
    }
    first = run_synthea(**kwargs)
    assert run_synthea(**kwargs) == first
    assert len(calls) == 1 and calls[0][1]["timeout"] == 2700
    (output / "fhir" / "fixture.json").write_text("{}")
    with pytest.raises(ValueError, match="evidence changed"):
        run_synthea(**kwargs)


def test_synthea_coverage_uses_verified_simulation_end_not_publication_clock():
    from healthcare_ingestion.generator import synthea_coverage_end

    end = synthea_coverage_end(
        {
            "inputs": {
                "simulation_end_date": "20261120",
                "simulation_timezone": "UTC",
            }
        }
    )
    assert end == "2026-11-20T00:00:00.0000000"
    with pytest.raises(ValueError, match="UTC"):
        synthea_coverage_end(
            {
                "inputs": {
                    "simulation_end_date": "20261120",
                    "simulation_timezone": "local",
                }
            }
        )
