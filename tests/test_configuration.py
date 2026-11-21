import json
from dataclasses import replace
from pathlib import Path
from runpy import run_path
from shutil import rmtree
from uuid import uuid4

import pytest

from healthcare_ingestion.configuration import (
    ConfigurationError,
    DatasetSpec,
    FunctionSpec,
    InputSpec,
    ReleaseSnapshot,
    TaskSpec,
)
from healthcare_ingestion.function_contracts import FUNCTION_SCHEMAS


@pytest.fixture
def protocol_path():
    """All test scratch stays in this checkout and is removed after each test."""
    root = Path.cwd() / ".protocol-test-work"
    path = root / str(uuid4())
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        rmtree(path)
        try:
            root.rmdir()
        except OSError:
            pass


def make_snapshot(version="1.0.0", *, functions=()):
    physical = {
        "demo": {
            "connection_ref": "approved-connection",
            "table": "Patient",
            "path": "abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse/Tables/Patient",
        }
    }
    return ReleaseSnapshot(
        version,
        version,
        (
            DatasetSpec(
                "source.patient", "Clarity Patient", "source", True, physical_maps=physical
            ),
            DatasetSpec("bronze.patient", "Patient observations", "bronze", physical_maps=physical),
            DatasetSpec(
                "silver.patient", "Patient current state", "silver1", physical_maps=physical
            ),
        ),
        (
            TaskSpec(
                "clarity.patient",
                "clarity_bronze",
                "bronze.patient",
                (InputSpec("source.patient", "source"),),
            ),
            TaskSpec(
                "patient.silver",
                "patient_silver",
                "silver.patient",
                (InputSpec("bronze.patient", "patient"),),
                functions=functions,
            ),
        ),
        artifacts={
            key: f"sha256:{key}-pinned"
            for key in ("package", "dependencies", "notebooks", "environments", "dags")
        },
        framework_defaults={
            "scheduler": {"retries": 2, "retry_delay_seconds": 30, "timeout_seconds": 3600},
            "spark": {"startup": {"spark.executor.memory": "4g"}, "runtime": {}},
            "events": {"coalesce": True, "reconcile_seconds": 300, "max_retries": 3},
        },
        stage_defaults={"silver1": {"scheduler": {"retries": 1}}},
    )


def test_snapshot_round_trip_deep_immutability_and_precedence():
    snapshot = make_snapshot()
    task = replace(
        snapshot.tasks[1],
        overrides={
            "scheduler": {"retries": 0, "timeout_seconds": None},
            "spark": {"runtime": {"spark.sql.shuffle.partitions": "8"}},
        },
    )
    snapshot = replace(snapshot, tasks=(snapshot.tasks[0], task))
    result = ReleaseSnapshot.from_dict(snapshot.to_dict())
    assert result.digest == snapshot.digest
    settings = result.effective_settings("patient.silver")
    assert settings["scheduler"] == {
        "retries": 0,
        "retry_delay_seconds": 30,
        "timeout_seconds": 3600,
    }
    assert settings["spark"]["startup"]["spark.executor.memory"] == "4g"
    with pytest.raises(TypeError):
        result.artifacts["package"] = "mutated"
    with pytest.raises(TypeError):
        result.dataset("bronze.patient").physical_maps["demo"]["table"] = "mutated"
    assert result.graph()["patient.silver"] == ("clarity.patient",)
    with pytest.raises(ConfigurationError, match="No approved"):
        result.physical("silver.patient", "production")


def test_registered_functions_parameters_repetitions_and_auxiliary_reads():
    schema = {
        "type": "object",
        "properties": {
            "columns": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        "required": ["columns"],
        "additionalProperties": False,
    }
    functions = (
        FunctionSpec("names.first", "trim_names", {"columns": ["FirstName"]}, ("patient",)),
        FunctionSpec("names.last", "trim_names", {"columns": ["LastName"]}, ("patient",)),
    )
    snapshot = make_snapshot(functions=functions)
    snapshot.validate({"trim_names": schema})
    with pytest.raises(ConfigurationError, match="Unregistered"):
        snapshot.validate({})
    with pytest.raises(ConfigurationError, match="unknown parameters"):
        make_snapshot(
            functions=(
                replace(
                    functions[0],
                    parameters={
                        "columns": ["FirstName"],
                        "raw_code": "x",
                    },
                ),
            )
        ).validate({"trim_names": schema})
    with pytest.raises(ConfigurationError, match="distinct stable"):
        make_snapshot(functions=(functions[0], functions[0]))
    with pytest.raises(ConfigurationError, match="untracked"):
        make_snapshot(functions=(replace(functions[0], input_aliases=("hidden",)),))


def test_missing_ambiguous_cyclic_retired_and_exceptional_edges_rejected():
    snapshot = make_snapshot()
    with pytest.raises(ConfigurationError, match="Missing producer"):
        replace(snapshot, tasks=(snapshot.tasks[1],))
    with pytest.raises(ConfigurationError, match="Ambiguous"):
        replace(snapshot, tasks=(*snapshot.tasks, replace(snapshot.tasks[0], task_id="duplicate")))
    with pytest.raises(ConfigurationError, match="Cyclic"):
        replace(
            snapshot,
            tasks=(
                replace(snapshot.tasks[0], inputs=(InputSpec("silver.patient", "cycle"),)),
                snapshot.tasks[1],
            ),
        )
    with pytest.raises(ConfigurationError, match="duplicate an inferred"):
        replace(
            snapshot,
            tasks=(
                snapshot.tasks[0],
                replace(snapshot.tasks[1], ordering_after=("clarity.patient",)),
            ),
        )
    with pytest.raises(ConfigurationError, match="retired"):
        replace(
            snapshot,
            datasets=(
                snapshot.datasets[0],
                replace(snapshot.datasets[1], retired=True),
                snapshot.datasets[2],
            ),
        )
    with pytest.raises(ConfigurationError, match="explicit input lineage"):
        replace(snapshot, tasks=(replace(snapshot.tasks[0], inputs=()),))


def test_scheduler_policy_never_leaks_into_spark_or_accepts_unknown_fields():
    with pytest.raises(ConfigurationError, match="Unknown spark"):
        replace(make_snapshot(), framework_defaults={"spark": {"retries": 3}})
    with pytest.raises(ConfigurationError, match="must be positive"):
        replace(make_snapshot(), framework_defaults={"scheduler": {"timeout_seconds": 0}})
    with pytest.raises(ConfigurationError, match="framework version must match"):
        replace(make_snapshot(), framework_version="1.0.1")


def test_demo_patient_functions_match_runtime_and_complete_approved_source_contract():
    root = Path(__file__).resolve().parents[1]
    snapshot = ReleaseSnapshot.from_dict(
        json.loads(
            (root / "metadata" / "framework" / "demo-release.json").read_text(encoding="utf-8")
        )
    )
    source = json.loads(
        (root / "database" / "schema-contracts" / "clarity.json").read_text(encoding="utf-8")
    )
    patient = next(table for table in source["tables"] if table["name"] == "Patient")
    expected_columns = [column["name"] for column in patient["columns"]]
    snapshot.validate(FUNCTION_SCHEMAS)
    task = snapshot.task("curate.clarity.patient")
    normalize, latest = task.functions
    assert normalize.occurrence_id == "patient.names.trim.v1"
    assert latest.occurrence_id == "patient.state.latest.v1"
    assert normalize.parameters["columns"] == ("FirstName", "LastName")
    assert latest.parameters["key"] == "PatientID"
    assert latest.parameters["modified"] == "ModifiedAtUtc"
    assert list(latest.parameters["business_columns"]) == expected_columns
    assert len(snapshot.tasks) == 29 and len(snapshot.datasets) == 57
    assert {item.workflow for item in snapshot.tasks} == {
        "clarity_bronze",
        "caboodle_bronze",
        "patient_silver",
    }
    inspector = run_path(str(root / "database" / "metadata" / "inspect_metadata.py"))
    generated = inspector["demo_snapshot"]()
    assert generated.to_dict() == snapshot.to_dict()
    assert generated.digest == snapshot.digest
    assert inspector["column_dictionary"]() == (
        root / "database" / "metadata" / "COLUMN_DICTIONARY.md"
    ).read_text(encoding="utf-8")
