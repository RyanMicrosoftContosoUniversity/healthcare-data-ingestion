import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from test_configuration import protocol_path as _local_fixture

from healthcare_ingestion.control_store import _TABLES, ControlError, SQLiteControlStore
from healthcare_ingestion.metadata_migrations import apply_migrations, load_migrations
from healthcare_ingestion.operational_records import SPARK_METRIC_TYPES

ROOT = Path(__file__).resolve().parents[1]
protocol_path = _local_fixture


def test_versioned_forward_only_ddl_and_legacy_history_preservation():
    migrations = load_migrations(ROOT / "database" / "metadata" / "migrations")
    assert [m.migration_id for m in migrations] == [
        "0001_configuration",
        "0002_control",
        "0003_legacy_preservation",
        "0004_operational_records",
        "0005_waiting_operations",
        "0006_source_coverage",
    ]
    combined = "\n".join(m.sql for m in migrations)
    for schema, table in _TABLES.values():
        assert re.search(rf"CREATE TABLE {schema}\.{table}\s*\(", combined)
    legacy = migrations[2].sql
    assert "cfg.TransformationStep" in legacy
    assert "LegacyTransformationStepArchive" in legacy
    assert "IngestionTransformationRun.TransformationStepID" in legacy
    assert "UX_ProcessingTask_producer" in combined
    assert "UX_ReconciliationRun_owner" in combined
    assert "FK_TaskOperation_attempt" in combined
    assert "varchar(27)" in combined  # 100ns source-window precision is not lost by pyodbc.


def test_reference_tables_match_physical_column_names_and_are_local_only(protocol_path):
    store = SQLiteControlStore(protocol_path / "control.db")
    migrations = load_migrations(ROOT / "database" / "metadata" / "migrations")
    sql = "\n".join(m.sql for m in migrations)
    types = r"(?:varchar|nvarchar|char|bigint|int|bit|datetime2|decimal)"
    with closing(sqlite3.connect(store.path)) as connection:
        for schema, table in _TABLES.values():
            physical = re.search(
                rf"CREATE TABLE {schema}\.{table}\s*\((.*?)\n\);",
                sql,
                re.DOTALL,
            ).group(1)
            physical += "\n" + "\n".join(
                re.findall(
                    rf"ALTER TABLE {schema}\.{table}\s+ADD\s+(.*?);",
                    sql,
                    re.DOTALL,
                )
            )
            columns = set(
                re.findall(
                    rf"^\s*\[?(\w+)\]?\s+{types}\b",
                    physical,
                    re.MULTILINE | re.IGNORECASE,
                )
            )
            reference = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({schema}_{table})").fetchall()
            }
            assert columns == reference, (table, columns ^ reference)
    with pytest.raises(ControlError, match="Fabric SQL"):
        apply_migrations(store, ROOT / "database" / "metadata" / "migrations")


def test_reject_destructive_unversioned_and_missing_transactions(protocol_path):
    path = protocol_path / "0001_bad.sql"
    path.write_text("SET XACT_ABORT ON; BEGIN TRANSACTION; DROP TABLE cfg.Dataset; COMMIT;")
    with pytest.raises(ControlError, match="Destructive"):
        load_migrations(protocol_path)
    path.write_text("CREATE TABLE anything(id int)")
    with pytest.raises(ControlError, match="boundaries"):
        load_migrations(protocol_path)


def test_role_artifact_separates_runtime_configuration_and_corruption_clearing():
    permissions = (ROOT / "database" / "metadata" / "permissions.sql").read_text(encoding="utf-8")
    code = re.sub(r"--[^\n]*", "", permissions)
    assert "DENY INSERT, UPDATE, DELETE ON SCHEMA::cfg TO ingestion_runtime" in code
    assert re.search(r"GRANT UPDATE ON ops\.DatasetBlock.*?TO ingestion_operator", code, re.DOTALL)
    assert not re.search(r"GRANT UPDATE ON ops\.DatasetBlock.*?TO ingestion_runtime", code)
    assert not re.search(r"CREATE\s+(USER|LOGIN)|ADD\s+MEMBER", code, re.IGNORECASE)


def test_operational_spark_fields_match_all_fifty_nullable_baseline_types():
    dictionary = (ROOT / "docs" / "ingestion" / "spark-metric-columns.md").read_text(
        encoding="utf-8"
    )
    expected = {}
    for line in dictionary.splitlines():
        if not line.startswith("| `"):
            continue
        cells = line.split("|")
        names = re.findall(r"`([^`]+)`", cells[1])
        sql_type = re.findall(r"`([^`]+)`", cells[2])[0]
        expected.update(dict.fromkeys(names, sql_type))
    assert len(expected) == 50
    assert SPARK_METRIC_TYPES == expected
    physical = (
        ROOT / "database" / "metadata" / "migrations" / "0004_operational_records.sql"
    ).read_text(encoding="utf-8")
    for field, sql_type in expected.items():
        assert re.search(rf"^\s+{field}\s+{re.escape(sql_type)}\s+NULL", physical, re.MULTILINE)


def test_each_migration_supplies_required_ledger_description():
    migrations = load_migrations(ROOT / "database" / "metadata" / "migrations")
    for migration in migrations:
        columns = re.search(
            r"INSERT\s+(?:INTO\s+)?cfg\.MetadataMigration\s*\(([^)]+)\)",
            migration.sql,
            re.IGNORECASE,
        ).group(1)
        assert {"migration_id", "description"} <= {name.strip() for name in columns.split(",")}


def test_source_coverage_migration_leaves_unknown_history_unfabricated():
    migration = load_migrations(ROOT / "database" / "metadata" / "migrations")[-1]
    code = re.sub(r"--[^\n]*", "", migration.sql)
    assert not re.search(r"\bUPDATE\b", code, re.IGNORECASE)
    assert "FK_OperationInput_snapshot_source_coverage" in code
    assert "FK_DatasetReadiness_source_coverage" in code
