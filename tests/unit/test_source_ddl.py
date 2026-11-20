import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_ingestion.source_ddl import render_source_ddl


@pytest.fixture
def contract():
    def column(name, purpose, sql_type="bigint", nullable=False):
        return {"name": name, "sql_type": sql_type, "nullable": nullable, "purpose": purpose}

    return {
        "schema_version": 1,
        "source_system": "Clarity",
        "schema": "dbo",
        "tables": [
            {
                "name": "Procedure",
                "primary_key": ["procedureid"],
                "columns": [
                    column("ProcedureID", "PK."),
                    column("PatientID", "FK to `Patient.PatientID`."),
                    column("LineageID", "Lineage; not a FK to another fact."),
                    column("Value", "Optional measurement.", "decimal(18,4)", True),
                ],
            },
            {
                "name": "Patient",
                "primary_key": ["PatientID"],
                "columns": [
                    column("PatientID", "PK."),
                    column("ExternalID", "UQ; stable identity.", "varchar(40)"),
                ],
            },
        ],
    }


def test_renders_exact_columns_keys_and_forward_reference_without_mutating(contract):
    original = deepcopy(contract)
    sql = render_source_ddl(contract)
    assert "CREATE TABLE [dbo].[Procedure]" in sql
    assert "[Value] decimal(18,4) NULL" in sql
    assert "PRIMARY KEY ([ProcedureID])" in sql
    assert "UNIQUE ([ExternalID])" in sql
    assert sql.index("ALTER TABLE") > sql.rindex("CREATE TABLE")
    assert "REFERENCES [dbo].[Patient] ([PatientID])" in sql
    assert sql.count("FOREIGN KEY") == 1
    assert "ON DELETE NO ACTION ON UPDATE NO ACTION" in sql
    assert sql == render_source_ddl(contract)
    assert contract == original


def test_recognizes_event_time_fk_wording(contract):
    contract["tables"][0]["columns"][1]["purpose"] = (
        "FK to the event-time version of `Patient.PatientID`."
    )
    assert "REFERENCES [dbo].[Patient] ([PatientID])" in render_source_ddl(contract)


@pytest.mark.parametrize(
    ("purpose", "message"),
    [
        ("FK to `Missing.PatientID`.", "unknown FK target"),
        ("FK to `Patient.Missing`.", "unknown FK target"),
        ("FK to some future notation.", "unrecognized FK"),
    ],
)
def test_rejects_missing_or_ambiguous_relationships(contract, purpose, message):
    contract["tables"][0]["columns"][1]["purpose"] = purpose
    with pytest.raises(ValueError, match=message):
        render_source_ddl(contract)


def test_rejects_non_unique_reference_and_accepts_explicit_candidate_key(contract):
    column = contract["tables"][0]["columns"][1]
    column.update(purpose="FK to `Patient.ExternalID`.", sql_type="varchar(40)")
    assert "REFERENCES [dbo].[Patient] ([ExternalID])" in render_source_ddl(contract)
    contract["tables"][1]["columns"][1]["purpose"] = "Not unique."
    with pytest.raises(ValueError, match="not unique"):
        render_source_ddl(contract)


def test_rejects_relationship_type_mismatch(contract):
    contract["tables"][0]["columns"][1]["sql_type"] = "int"
    with pytest.raises(ValueError, match="types do not match"):
        render_source_ddl(contract)


def test_renders_composite_pk_but_rejects_reference_to_only_one_member(contract):
    contract["tables"][1]["primary_key"].append("ExternalID")
    contract["tables"][1]["columns"][1]["purpose"] = "Second PK member."
    with pytest.raises(ValueError, match="not unique"):
        render_source_ddl(contract)
    contract["tables"][0]["columns"][1]["purpose"] = "No FK."
    assert "PRIMARY KEY ([PatientID], [ExternalID])" in render_source_ddl(contract)


def test_long_constraint_names_are_bounded_and_distinct(contract):
    contract["tables"] = [contract["tables"][1]]
    contract["tables"][0]["name"] = "T" * 128
    for column in contract["tables"][0]["columns"]:
        column["name"] = ("C" * 127) + ("A" if column["sql_type"] == "bigint" else "B")
        column["purpose"] = "UQ; identity."
    contract["tables"][0]["primary_key"] = [contract["tables"][0]["columns"][0]["name"]]
    names = re.findall(r"CONSTRAINT \[([^]]+)\]", render_source_ddl(contract))
    assert all(len(name) <= 128 for name in names)
    assert len(set(names)) == len(names)


def test_unsafe_input_is_rejected_before_rendering(contract):
    contract["tables"][0]["columns"][0]["sql_type"] = "int); DROP TABLE Patient; --"
    with pytest.raises(ValueError, match="unsupported SQL type"):
        render_source_ddl(contract)


@pytest.mark.parametrize(
    ("source", "expected_tables", "expected_columns", "expected_fks", "expected_uqs"),
    [("clarity", 13, 183, 22, 7), ("caboodle", 15, 271, 37, 1)],
)
def test_committed_scripts_match_every_contract_column_and_relationship(
    source, expected_tables, expected_columns, expected_fks, expected_uqs
):
    root = Path(__file__).resolve().parents[2]
    contract = json.loads(
        (root / "database" / "schema-contracts" / f"{source}.json").read_text(encoding="utf-8")
    )
    sql = render_source_ddl(contract)
    assert sql == (root / "database" / source / "schema" / "001-source-baseline.sql").read_text(
        encoding="utf-8"
    )
    bodies = re.findall(r"CREATE TABLE \[dbo\]\.\[([^]]+)\] \(\n(.*?)\n\);", sql, re.S)
    assert len(bodies) == expected_tables
    assert sum(len(table["columns"]) for table in contract["tables"]) == expected_columns
    for (name, body), table in zip(bodies, contract["tables"], strict=True):
        assert name == table["name"]
        actual = re.findall(r"^    \[([^]]+)\] (.*?) (NOT NULL|NULL),?$", body, re.M)
        expected = [
            (column["name"], column["sql_type"], "NULL" if column["nullable"] else "NOT NULL")
            for column in table["columns"]
        ]
        assert actual == expected
    assert sql.count("PRIMARY KEY") == expected_tables
    assert sql.count("FOREIGN KEY") == expected_fks
    assert sql.count(" UNIQUE ") == expected_uqs
    if source == "caboodle":
        assert sql.count("REFERENCES [dbo].[DimPatient]") == 7
        assert sql.count("REFERENCES [dbo].[DimDepartment]") == 7
        assert "REFERENCES [dbo].[Fact" not in sql
