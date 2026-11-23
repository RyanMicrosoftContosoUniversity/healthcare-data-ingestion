# ruff: noqa: E402, F811
import hashlib
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

if sys.platform == "win32":
    pytest.skip("Run execution acceptance in the Linux Spark container.", allow_module_level=True)

pytest.importorskip("pyspark")
from test_spark_runtime import spark  # noqa: F401

from healthcare_ingestion.artifacts import LocalArtifactStore, encoded
from healthcare_ingestion.configuration import FunctionSpec, ReleaseSnapshot
from healthcare_ingestion.control_store import (
    CommitEvidence,
    InputBinding,
    MetadataUnavailable,
    SQLiteControlStore,
)
from healthcare_ingestion.delta_io import bronze_frame, current_version, fixed_read
from healthcare_ingestion.execution import reconcile_operation, run_operation, verify_commit
from healthcare_ingestion.function_contracts import FUNCTION_SCHEMAS
from healthcare_ingestion.release import ReleaseManager
from healthcare_ingestion.source_mapping import sql_timestamp


def execution_fixture(spark, tmp_path, with_silver=False):
    template = ReleaseSnapshot.from_dict(
        json.loads(
            (Path(__file__).parents[1] / "metadata" / "framework" / "demo-release.json").read_text()
        )
    )
    task = next(
        task
        for task in template.tasks
        if template.dataset(task.primary_output).layer == "bronze"
        and template.physical(task.inputs[0].dataset_id, "demo").get("table") == "Patient"
    )
    source = template.dataset(task.inputs[0].dataset_id)
    output = template.dataset(task.primary_output)
    target = str(tmp_path / "bronze")
    output = replace(
        output,
        physical_maps={
            "demo": {
                "kind": "delta",
                "path": target,
                "workspace_id": "11111111-1111-1111-1111-111111111111",
                "lakehouse_id": "22222222-2222-2222-2222-222222222222",
                "schema": "clarity",
                "table": "Patient",
            }
        },
    )
    tasks, datasets = (task,), (source, output)
    pipeline_objects = {
        task.pipeline_object_id: template.artifacts["pipeline_objects"][task.pipeline_object_id],
    }
    if with_silver:
        silver_task = next(
            item
            for item in template.tasks
            if template.dataset(item.primary_output).layer == "silver1"
        )
        silver = replace(
            template.dataset(silver_task.primary_output),
            physical_maps={
                "demo": {
                    "kind": "delta",
                    "path": str(tmp_path / "silver"),
                    "workspace_id": "11111111-1111-1111-1111-111111111111",
                    "lakehouse_id": "33333333-3333-3333-3333-333333333333",
                    "schema": "clarity",
                    "table": "Patient",
                }
            },
        )
        silver_task = replace(
            silver_task,
            functions=(
                FunctionSpec("trim", "normalize_names", {"columns": ["FirstName"]}),
                FunctionSpec(
                    "latest",
                    "latest_patient",
                    {
                        "key": "PatientID",
                        "modified": "ModifiedAtUtc",
                        "business_columns": ["PatientID", "FirstName", "ModifiedAtUtc"],
                    },
                ),
            ),
        )
        tasks, datasets = (task, silver_task), (source, output, silver)
        if silver_task.pipeline_object_id:
            pipeline_objects[silver_task.pipeline_object_id] = template.artifacts[
                "pipeline_objects"
            ][silver_task.pipeline_object_id]
    snapshot = replace(
        template,
        tasks=tasks,
        datasets=datasets,
        artifacts={
            **template.artifacts,
            **{
                key: "local-reference:" + hashlib.sha256(key.encode()).hexdigest()
                for key in ("package", "dependencies", "notebooks", "environments", "dags")
            },
            "pipeline_objects": pipeline_objects,
        },
    )
    store = SQLiteControlStore(tmp_path / "control.sqlite")
    manager = ReleaseManager(store)
    manager.publish_candidate(
        snapshot,
        registry=FUNCTION_SCHEMAS,
        review_evidence={
            "branch": "test",
            "pull_request": "test",
            "review": "test",
            "commit": "test",
        },
    )
    manager.begin_candidate(snapshot.version)
    for check in ("tests", "deployment", "environment_publication", "airflow_recognition"):
        manager.record_check(
            snapshot.version, "demo", check, passed=True, evidence={"local_reference": True}
        )
    manager.activate(snapshot.version, "demo")
    now = datetime.now(UTC)
    start, end = sql_timestamp(now - timedelta(hours=1)), sql_timestamp(now)
    source_snapshot = store.register_source_snapshot(
        source.dataset_id,
        "demo",
        "source-batch",
        start,
        end,
        evidence_digest=hashlib.sha256(b"local-source-evidence").hexdigest(),
        artifact_ref="local-source-proof",
        verify_snapshot=lambda: True,
    )
    binding = InputBinding(
        source.dataset_id, "source-batch", start, end, source_snapshot_id=source_snapshot
    )
    store.queue_operation(
        operation_id="capture-op",
        task_id=task.task_id,
        environment="demo",
        window_start=start,
        window_end=end,
        inputs=(binding,),
        release_version=snapshot.version,
    )
    stage = str(tmp_path / "sealed-stage")
    frame = spark.createDataFrame(
        [(1, "Name", "2026-11-20T12:00:00.1234567")],
        "PatientID long, FirstName string, ModifiedAtUtc string",
    )
    frame.write.format("delta").mode("errorifexists").save(stage)
    artifacts = LocalArtifactStore(tmp_path / "proof")
    artifacts.put(
        "capture-op/capture.json",
        {
            "operation_id": "capture-op",
            "release_hash": snapshot.digest,
            "input_versions": {binding.dataset_id: binding.version},
            "dataset_id": output.dataset_id,
            "target_path": target,
            "base_version": -1,
            "window_start": binding.window_start,
            "window_end": binding.window_end,
            "source_coverage_start": binding.window_start,
            "source_coverage_end": binding.window_end,
            "path": stage,
            "version": 0,
            "rows": 1,
            "capture_mode": "FULL",
            "source_name": "Clarity.dbo.Patient",
            "extracted_at": now.isoformat(),
            "dag_run_id": "daily-dag-run",
            "output_layer": "bronze",
            "watermark_upper": "2026-11-20T12:00:00.1234567",
            "approved_table": {
                "name": "Patient",
                "primary_key": ["PatientID"],
                "columns": [
                    {"name": "PatientID", "sql_type": "bigint", "nullable": False},
                    {"name": "FirstName", "sql_type": "nvarchar(100)", "nullable": True},
                    {"name": "ModifiedAtUtc", "sql_type": "datetime2(7)", "nullable": False},
                ],
            },
        },
    )
    return store, snapshot, task, target, artifacts


def test_patient_generic_execution_with_frozen_parameters_and_typed_quality(spark, tmp_path):
    store, snapshot, bronze_task, _, artifacts = execution_fixture(
        spark,
        tmp_path,
        with_silver=True,
    )
    run_operation(
        store,
        snapshot,
        "capture-op",
        bronze_task.task_id,
        "demo",
        "worker",
        spark,
        artifacts,
        str(tmp_path / "staging"),
    )
    output = store.output_history(bronze_task.primary_output, "demo")[0]
    silver_task = next(
        task for task in snapshot.tasks if snapshot.dataset(task.primary_output).layer == "silver1"
    )
    store.queue_operation(
        operation_id="silver-op",
        task_id=silver_task.task_id,
        environment="demo",
        window_start=output["window_start"],
        window_end=output["window_end"],
        inputs=(
            InputBinding(
                bronze_task.primary_output,
                output["delta_version"],
                output["window_start"],
                output["window_end"],
                output_id=output["output_id"],
            ),
        ),
        release_version=snapshot.version,
    )
    assert run_operation(
        store,
        snapshot,
        "silver-op",
        silver_task.task_id,
        "demo",
        "worker",
        spark,
        artifacts,
        str(tmp_path / "staging"),
    )
    target = snapshot.physical(silver_task.primary_output, "demo")["path"]
    assert fixed_read(spark, target, 0).first().FirstName == "Name"
    quality = store.operational_records("quality_outcome", "silver-op")
    assert any(
        row["check"] == "post_write_reconciliation" and row["status"] == "PASS" for row in quality
    )


def test_delta_commit_without_saved_receipt_is_reconciled(spark, tmp_path, monkeypatch):
    store, snapshot, task, target, artifacts = execution_fixture(spark, tmp_path)
    original_put = artifacts.put

    def unavailable(key, value):
        if key.endswith("/commit.json"):
            raise OSError("Injected recovery artifact outage.")
        return original_put(key, value)

    monkeypatch.setattr(artifacts, "put", unavailable)
    with pytest.raises(OSError):
        run_operation(
            store,
            snapshot,
            "capture-op",
            task.task_id,
            "demo",
            "worker",
            spark,
            artifacts,
            str(tmp_path / "staging"),
        )
    assert current_version(spark, target) == 0
    monkeypatch.setattr(artifacts, "put", original_put)
    assert reconcile_operation(store, "capture-op", spark, artifacts)
    assert current_version(spark, target) == 0


def test_sealed_capture_before_write_and_post_delta_control_failure(spark, tmp_path, monkeypatch):
    store, snapshot, task, target, artifacts = execution_fixture(spark, tmp_path)
    original_publish = store.publish

    def unavailable(*_, **__):
        raise MetadataUnavailable("Injected control-store outage.")

    monkeypatch.setattr(store, "publish", unavailable)
    with pytest.raises(MetadataUnavailable):
        run_operation(
            store,
            snapshot,
            "capture-op",
            task.task_id,
            "demo",
            "worker",
            spark,
            artifacts,
            str(tmp_path / "staging"),
        )
    assert current_version(spark, target) == 0
    assert store.operation("capture-op")["status"] == "UNCERTAIN"
    assert not store.output_history(task.primary_output, "demo")
    monkeypatch.setattr(store, "publish", original_publish)
    assert reconcile_operation(store, "capture-op", spark, artifacts)
    assert reconcile_operation(store, "capture-op", spark, artifacts)
    assert current_version(spark, target) == 0
    assert len(store.output_history(task.primary_output, "demo")) == 1
    assert fixed_read(spark, target, 0).first()._ingest_run_id == "daily-dag-run"


def test_wrong_pinned_task_rejected_before_claim(spark, tmp_path):
    store, snapshot, _, target, artifacts = execution_fixture(spark, tmp_path)
    with pytest.raises(ValueError, match="pinned"):
        run_operation(
            store,
            snapshot,
            "capture-op",
            "wrong-task",
            "demo",
            "worker",
            spark,
            artifacts,
            str(tmp_path / "staging"),
        )
    assert store.operation("capture-op")["status"] == "QUEUED"
    assert current_version(spark, target) == -1


def test_reconciliation_rejects_wrong_business_values(spark, tmp_path):
    from healthcare_ingestion.delta_io import PublicationIntent, append_bronze

    store, snapshot, task, target, artifacts = execution_fixture(spark, tmp_path)
    proof = artifacts.get("capture-op/capture.json")
    changed = spark.createDataFrame(
        [(1, "Different", "2026-11-20T12:00:00.1234567")],
        "PatientID long, FirstName string, ModifiedAtUtc string",
    )
    now = datetime.now(UTC)
    context = {
        "_ingest_batch_id": "capture-op",
        "_ingest_run_id": "run",
        "_ingest_table_run_id": "attempt",
        "_ingest_source_name": "Clarity.dbo.Patient",
        "_ingest_extracted_at_utc": now,
        "_ingest_landed_at_utc": now,
        "_ingest_capture_mode": "FULL",
    }
    append_bronze(
        bronze_frame(changed, context),
        target,
        PublicationIntent("capture-op", task.primary_output, -1),
        lambda: None,
    )
    evidence = CommitEvidence(
        operation_id="capture-op",
        dataset_id=task.primary_output,
        delta_version="0",
        window_start=proof["window_start"],
        window_end=proof["window_end"],
        input_versions=proof["input_versions"],
        validation_digest=hashlib.sha256(encoded(proof)).hexdigest(),
        coverage_verified=True,
        changed_rows=1,
        commit_token="capture-op",
        source_coverage_start=proof["source_coverage_start"],
        source_coverage_end=proof["source_coverage_end"],
    )
    assert not verify_commit(spark, artifacts, evidence)
    assert not store.output_history(task.primary_output, "demo")
