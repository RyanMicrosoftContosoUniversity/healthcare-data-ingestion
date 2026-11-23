# ruff: noqa: E402
import sys
from datetime import UTC, datetime
from decimal import Decimal

import pytest

if sys.platform == "win32":
    pytest.skip("Spark 4.1 requires the Linux validation container.", allow_module_level=True)

pytest.importorskip("pyspark")
from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from healthcare_ingestion.delta_io import (
    PublicationIntent,
    append_bronze,
    bronze_frame,
    current_version,
    fixed_read,
    merge_patient,
)
from healthcare_ingestion.patient import latest_patient, normalize_names
from healthcare_ingestion.spark_types import mapped_schema


@pytest.fixture(scope="module")
def spark():
    builder = (
        SparkSession.builder.master("local[1]")
        .appName("healthcare-runtime-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog"
        )
    )
    session = configure_spark_with_delta_pip(builder).getOrCreate()
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def test_source_type_fidelity_on_actual_spark(spark):
    table = {
        "columns": [
            {"name": "SmallCode", "sql_type": "tinyint", "nullable": False},
            {"name": "Amount", "sql_type": "decimal(20,10)", "nullable": False},
            {"name": "Name", "sql_type": "nvarchar(100)", "nullable": False},
            {"name": "Modified", "sql_type": "datetime2(7)", "nullable": False},
        ]
    }
    row = (255, Decimal("99.1234567890"), "A\u00f1o", "2026-11-20T12:00:00.1234567")
    assert tuple(spark.createDataFrame([row], mapped_schema(table)).first()) == row


def test_bronze_real_delta_retry_and_distinct_batches(spark, tmp_path):
    source = spark.createDataFrame([(1, "same"), (1, "same")], "PatientID long, Name string")
    now = datetime.now(UTC)
    context = {
        "_ingest_batch_id": "batch-one",
        "_ingest_run_id": "run",
        "_ingest_table_run_id": "table-run",
        "_ingest_source_name": "Clarity.dbo.Patient",
        "_ingest_extracted_at_utc": now,
        "_ingest_landed_at_utc": now,
        "_ingest_capture_mode": "FULL",
    }
    target = str(tmp_path / "bronze")

    def fence():
        return None

    first = PublicationIntent("batch-one", "patient-bronze", -1)
    version = append_bronze(bronze_frame(source, context), target, first, fence)
    assert version == 0
    retry = PublicationIntent("batch-one", "patient-bronze", -1, recovering=True)
    assert append_bronze(bronze_frame(source, context), target, retry, fence) == version
    context["_ingest_batch_id"] = "batch-two"
    second = PublicationIntent("batch-two", "patient-bronze", version)
    append_bronze(bronze_frame(source, context), target, second, fence)
    assert fixed_read(spark, target, current_version(spark, target)).count() == 4
    assert fixed_read(spark, target, 0).count() == 2


def test_patient_actual_spark_ties_and_stale_safe_delta_merge(spark, tmp_path):
    schema = "PatientID long, FirstName string, ModifiedAtUtc string, IsDeleted boolean"
    columns = ["PatientID", "FirstName", "ModifiedAtUtc", "IsDeleted"]
    rows = [
        (1, " Old ", "2026-11-20T12:00:00.1234566", False),
        (1, " New ", "2026-11-20T12:00:00.1234567", True),
    ]
    latest = latest_patient(
        normalize_names(spark.createDataFrame(rows, schema), ["FirstName"]),
        "PatientID",
        "ModifiedAtUtc",
        columns,
    )
    assert latest.first().FirstName == "New"
    assert latest.first().IsDeleted is True
    target = str(tmp_path / "silver")
    merge_patient(
        latest,
        target,
        "PatientID",
        "ModifiedAtUtc",
        PublicationIntent("first", "silver", -1),
        lambda: None,
    )
    older = spark.createDataFrame([rows[0]], schema)
    merge_patient(
        older,
        target,
        "PatientID",
        "ModifiedAtUtc",
        PublicationIntent("older", "silver", 0),
        lambda: None,
    )
    assert fixed_read(spark, target, current_version(spark, target)).first().FirstName == "New"
    conflict = spark.createDataFrame(
        [(1, "One", rows[1][2], True), (1, "Two", rows[1][2], True)], schema
    )
    with pytest.raises(ValueError, match="Conflicting"):
        latest_patient(conflict, "PatientID", "ModifiedAtUtc", columns)


def test_bounded_quarantine_preserves_raw_and_verifies_replay_content(spark, tmp_path):
    from types import SimpleNamespace

    from healthcare_ingestion.artifacts import LocalArtifactStore
    from healthcare_ingestion.quality import QualityRule, evaluate_quality, replay_input

    frame = spark.createDataFrame([(1, "ok"), (2, "")], "PatientID long, FirstName string")
    manifests = []
    store = SimpleNamespace(
        hold_reference=lambda *_: None,
        record_quarantine_manifest=manifests.append,
    )
    artifacts = LocalArtifactStore(tmp_path / "evidence")
    context = {
        "operation_id": "quality-operation",
        "attempt_id": "attempt",
        "release_version": "0.1.0",
    }
    result = evaluate_quality(
        frame,
        (QualityRule("name", "FirstName", "not_blank", quarantine=True),),
        lambda *_: "quality-id",
        str(tmp_path / "quarantine"),
        context,
        store,
        max_quarantine_rows=1,
        max_quarantine_fraction=0.5,
        preserve_raw=True,
        artifacts=artifacts,
    )
    assert result.count() == 2
    assert replay_input(spark, manifests[0], "quality-operation", artifacts).first().PatientID == 2
    with pytest.raises(ValueError, match="full reprocessing"):
        replay_input(spark, manifests[0], "quality-operation")


def test_isolated_benchmark_materializes_four_trials_without_production_publication(
    spark, tmp_path
):
    from healthcare_ingestion.benchmark import benchmark

    frame = spark.createDataFrame([(1, " Test ")], "PatientID long, FirstName string")
    records = []
    result = benchmark(
        frame,
        [{"name": "normalize_names", "parameters": {"columns": ["FirstName"]}}],
        str(tmp_path / "benchmark"),
        records.append,
        {"framework_version": "0.1.0", "input_versions": {"bronze": "0"}},
    )
    assert len(result) == 4
    assert [row["warmup"] for row in result] == [True, False, False, False]
    assert all(row["status"] == "SUCCEEDED" for row in result)
    assert all(row["execution_metrics"]["spark_job_ids"] for row in result)
    assert all(fixed_read(spark, row["artifact"], 0).first().FirstName == "Test" for row in result)
    assert not (tmp_path / "Tables").exists()
