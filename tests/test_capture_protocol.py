from types import SimpleNamespace

import pytest

from healthcare_ingestion import execution


class Cursor:
    def __init__(self, upper):
        self.upper, self.calls = upper, []

    def execute(self, sql, *parameters):
        self.calls.append((sql, parameters))
        return self

    def fetchone(self):
        return (self.upper,)

    def fetchmany(self, _):
        return []

    def close(self):
        pass


class Connection:
    autocommit = False

    def __init__(self, upper):
        self.reader = Cursor(upper)
        self.committed = self.rolled_back = False

    def cursor(self):
        return self.reader

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def capture_fixture(monkeypatch, source="Caboodle", head_batch="expected"):
    table = {
        "name": "DimPatient",
        "primary_key": ["PatientKey"],
        "columns": [
            {"name": "PatientKey", "sql_type": "bigint", "nullable": False},
            {"name": "EtlModifiedAtUtc", "sql_type": "datetime2(7)", "nullable": False},
        ],
    }
    contract = {"schema_version": 1, "source_system": source, "schema": "dbo", "tables": [table]}
    checkpoint = {
        "batch": head_batch,
        "committed_at": "2026-11-21T14:00:00.0000000",
        "coverage_start": "2026-11-20T12:00:00.7654321",
        "coverage_end": "2026-11-21T12:00:00.7654321",
    }
    monkeypatch.setattr(
        execution,
        "discover",
        lambda *_: [SimpleNamespace(accepted=True, expected_hash="approved-schema")],
    )
    monkeypatch.setattr(execution, "source_checkpoint_evidence", lambda *_: checkpoint)
    writer = SimpleNamespace()
    modes = []
    writer.format = lambda _: writer
    writer.mode = lambda value: modes.append(value) or writer
    writer.save = lambda _: None
    frame = SimpleNamespace(write=writer)
    monkeypatch.setattr(execution, "mapped_schema", lambda _: "approved")
    spark = SimpleNamespace(createDataFrame=lambda *_: frame)
    return spark, contract, table, modes


def test_zero_change_coverage_does_not_replace_exact_caboodle_row_watermark(monkeypatch):
    spark, contract, table, modes = capture_fixture(monkeypatch)
    row_time = "2026-11-01T12:00:00.1234567"
    connection = Connection(row_time)
    proof = execution.capture_sql(
        spark,
        connection,
        contract,
        table,
        "attempt-owned",
        "expected",
        row_time,
        lambda: None,
        expected_coverage_end="2026-11-21T12:00:00.7654321",
    )
    assert proof["rows"] == 0
    assert proof["watermark_upper"] == row_time
    assert proof["coverage"]["window_end"] == "2026-11-21T12:00:00.7654321"
    assert proof["watermark_column"] == "EtlModifiedAtUtc"
    assert connection.reader.calls[-1][1] == (row_time, row_time)
    assert "[EtlModifiedAtUtc]" in connection.reader.calls[-1][0]
    assert connection.committed and modes == ["errorifexists"]


def test_latest_expected_source_failure_blocks_older_success(monkeypatch):
    spark, contract, table, _ = capture_fixture(monkeypatch, head_batch="older")
    connection = Connection("2026-11-01T12:00:00.1234567")
    with pytest.raises(ValueError, match="Expected source batch"):
        execution.capture_sql(
            spark,
            connection,
            contract,
            table,
            "attempt",
            "expected",
            None,
            lambda: None,
        )
    assert connection.rolled_back and not connection.committed


def test_source_reset_does_not_advance_watermark(monkeypatch):
    spark, contract, table, _ = capture_fixture(monkeypatch)
    connection = Connection("2026-11-01T12:00:00.1234566")
    with pytest.raises(ValueError, match="regressed"):
        execution.capture_sql(
            spark,
            connection,
            contract,
            table,
            "attempt",
            "expected",
            "2026-11-01T12:00:00.1234567",
            lambda: None,
        )
    assert connection.rolled_back
