import json
from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_ingestion.source_contracts import validate_source_contract


@pytest.fixture
def contract():
    return {
        "schema_version": 1,
        "source_system": "Clarity",
        "schema": "dbo",
        "tables": [
            {
                "name": "Patient",
                "primary_key": ["PatientID"],
                "columns": [
                    {
                        "name": "PatientID",
                        "sql_type": "bigint",
                        "nullable": False,
                        "purpose": "PK; immutable source identity.",
                    },
                    {
                        "name": "Value",
                        "sql_type": "decimal(18,4)",
                        "nullable": True,
                        "purpose": "Example optional measurement.",
                    },
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "sql_type",
    ["decimal(39,4)", "decimal(8,9)", "nvarchar(4001)", "varchar(8001)", "int; DROP TABLE Patient"],
)
def test_rejects_unsafe_or_invalid_type_declarations(contract, sql_type):
    contract["tables"][0]["columns"][1]["sql_type"] = sql_type
    with pytest.raises(ValueError):
        validate_source_contract(contract)


@pytest.mark.parametrize("nullable", ["No", None, 0, 1])
def test_requires_boolean_nullability(contract, nullable):
    contract["tables"][0]["columns"][1]["nullable"] = nullable
    with pytest.raises(ValueError, match="nullable must be a boolean"):
        validate_source_contract(contract)


def test_rejects_case_insensitive_column_collisions(contract):
    duplicate = deepcopy(contract["tables"][0]["columns"][0])
    duplicate["name"] = "patientid"
    contract["tables"][0]["columns"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate column"):
        validate_source_contract(contract)


@pytest.mark.parametrize("primary_key", [["MissingID"], ["PatientID", "patientid"], []])
def test_rejects_unusable_primary_key(contract, primary_key):
    contract["tables"][0]["primary_key"] = primary_key
    with pytest.raises(ValueError, match="primary.key"):
        validate_source_contract(contract)


def test_rejects_nullable_primary_key(contract):
    contract["tables"][0]["columns"][0]["nullable"] = True
    with pytest.raises(ValueError, match="cannot be nullable"):
        validate_source_contract(contract)


def test_preserves_approved_precision_and_does_not_mutate_input(contract):
    original = deepcopy(contract)
    validate_source_contract(contract)
    assert contract == original


def test_rejects_boolean_in_place_of_numeric_contract_version(contract):
    contract["schema_version"] = True
    with pytest.raises(ValueError, match="schema_version"):
        validate_source_contract(contract)


@pytest.mark.parametrize("source", ["clarity", "caboodle"])
def test_versioned_source_contracts_pass_deployment_input_validation(source):
    root = Path(__file__).resolve().parents[2]
    document = json.loads(
        (root / "database" / "schema-contracts" / f"{source}.json").read_text(encoding="utf-8")
    )
    validate_source_contract(document)
