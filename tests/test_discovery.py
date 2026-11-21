import copy
from datetime import datetime

import pytest

from healthcare_ingestion.discovery import compare_table, extraction_query, timestamp7

TABLE = {
    "name": "Patient",
    "primary_key": ["PatientId"],
    "columns": [
        {"name": "PatientId", "sql_type": "bigint", "nullable": False},
        {"name": "Modified", "sql_type": "datetime2(7)", "nullable": False},
    ],
}


def test_timestamp_preserves_seventh_digit_and_rejects_lossy_datetime():
    assert timestamp7("2026-11-20T12:00:00.1234567").endswith(".1234567")
    assert timestamp7("2026-11-20T12:00:00.1").endswith(".1000000")
    with pytest.raises(ValueError):
        timestamp7(datetime(2026, 11, 20))
    with pytest.raises(ValueError):
        timestamp7("2026-11-99T12:00:00")


def test_projection_parameterizes_windows_and_rejects_identifier_injection():
    query = extraction_query("dbo", TABLE, "Modified")
    assert "CONVERT(varchar(33),[Modified],126)" in query
    assert query.count("?") == 2
    with pytest.raises(ValueError):
        extraction_query("dbo];DROP TABLE Patient;--", TABLE)


def test_strict_drift_including_nullable_additions_blocks_only_changed_table():
    columns = [{**c, "computed": False, "identity": False} for c in TABLE["columns"]]
    assert compare_table(TABLE, columns, ["PatientId"]).accepted
    changed = copy.deepcopy(columns)
    changed.append(
        {
            "name": "NewNullable",
            "sql_type": "int",
            "nullable": True,
            "computed": False,
            "identity": False,
        }
    )
    assert not compare_table(TABLE, changed, ["PatientId"]).accepted
    assert not compare_table(TABLE, columns, []).accepted
