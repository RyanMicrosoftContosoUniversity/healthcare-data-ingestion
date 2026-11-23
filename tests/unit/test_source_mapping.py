import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from healthcare_ingestion.generator import _inputs
from healthcare_ingestion.source_mapping import (
    _evaluate,
    normalize_row,
    project_source,
    sql_timestamp,
    stable_id,
    validate_mapping,
)
from healthcare_ingestion.sql_source_integrity import validate_source_rows
from healthcare_ingestion.synthetic_fhir import parse_bundles
from healthcare_ingestion.synthetic_population import change_population, local_demo_population

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json"
START, AT = "2025-11-01T00:00:00Z", "2026-11-01T23:59:59Z"


def fixture_population():
    bundle = json.loads(FIXTURE.read_text(), parse_float=Decimal)
    return parse_bundles([bundle], history_start=START, publication_at=AT)


def test_all_28_models_and_454_columns_have_executable_coverage():
    population = fixture_population()
    models, columns = 0, 0
    for source in ("Clarity", "Caboodle"):
        contract, mapping = _inputs(ROOT, source)
        validate_mapping(mapping, contract)
        output = project_source(population, contract, mapping)
        validate_source_rows(output, contract)
        for table in contract["tables"]:
            assert output[table["name"]], table["name"]
            assert set(output[table["name"]][0]) == {c["name"] for c in table["columns"]}
            models += 1
            columns += len(table["columns"])
    assert (models, columns) == (28, 454)


def test_fixture_identifiers_relationships_temporal_precision_and_catalogs():
    population = fixture_population()
    clarity_contract, mapping = _inputs(ROOT, "Clarity")
    caboodle_contract, _ = _inputs(ROOT, "Caboodle")
    clarity = project_source(population, clarity_contract, mapping)
    caboodle = project_source(population, caboodle_contract, mapping)
    patient = clarity["Patient"][0]
    assert patient["PatientID"] == stable_id("Patient", "Patient/patient-a")
    assert clarity["Encounter"][0]["PatientID"] == patient["PatientID"]
    assert clarity["Encounter"][0]["AttendingProviderID"] == stable_id(
        "Provider", "Practitioner/provider-a"
    )
    assert clarity["LaboratoryResult"][0]["NumericValue"] == Decimal("123.123456")
    assert clarity["MedicationOrder"][0]["OrderedDose"] == Decimal("1.2500")
    assert clarity["Encounter"][0]["ArrivalAtUtc"].endswith(".0000007")
    assert caboodle["FactEncounter"][0]["ArrivalAtUtc"].endswith(".0000007")
    assert caboodle["FactEncounter"][0]["LengthOfStayMinutes"] == Decimal("30.00")
    assert (
        caboodle["FactMedicationAdministration"][0]["SourceMedicationOrderID"]
        == (clarity["MedicationOrder"][0]["MedicationOrderID"])
    )
    assert caboodle["DimPatient"][0]["SourcePatientID"] == patient["PatientID"]
    assert caboodle["DimPatient"][0]["PatientKey"] != patient["PatientID"]
    assert population["resource_dispositions"]["Immunization/archive-only-a"].startswith(
        "archive-only"
    )


def test_event_time_dimensions_keep_old_facts_and_use_new_versions():
    baseline = local_demo_population(patients=12, history_start=START, publication_at=AT)
    changed = change_population(baseline, batch="day1", at="2026-11-02T12:00:00Z")
    contract, mapping = _inputs(ROOT, "Caboodle")
    old = project_source(baseline, contract, mapping)
    new = project_source(changed, contract, mapping)
    validate_source_rows(new, contract)
    before = {row["SourceEncounterID"]: row for row in old["FactEncounter"]}
    for row in new["FactEncounter"]:
        if row["SourceEncounterID"] in before:
            assert row["PatientKey"] == before[row["SourceEncounterID"]]["PatientKey"]
    expired = [row for row in new["DimPatient"] if not row["IsCurrent"]]
    assert len(expired) == 10
    assert all(row["EffectiveToUtc"] == "2026-11-02T12:00:00.0000000" for row in expired)
    assert any(
        row["PatientKey"] not in {r["PatientKey"] for r in old["DimPatient"]}
        for row in new["FactEncounter"]
    )


@pytest.mark.parametrize("damage", ["missing-column", "extra-column", "fingerprint", "operation"])
def test_mapping_drift_is_rejected(damage):
    contract, mapping = _inputs(ROOT, "Clarity")
    mapping = copy.deepcopy(mapping)
    rules = mapping["sources"]["Clarity"]["tables"]["Patient"]["columns"]
    if damage == "missing-column":
        del rules["BirthDate"]
    elif damage == "extra-column":
        rules["NewColumn"] = {"op": "field", "field": "NewColumn"}
    elif damage == "fingerprint":
        mapping["sources"]["Clarity"]["contract_sha256"] = "changed"
    else:
        rules["BirthDate"]["op"] = "silently_default"
    with pytest.raises(ValueError):
        validate_mapping(mapping, contract)


@pytest.mark.parametrize("value", ["0.1234567", "1000000000000.000000", 0.1])
def test_decimal_precision_truncation_float_and_overflow_are_rejected(value):
    population = fixture_population()
    contract, mapping = _inputs(ROOT, "Clarity")
    table = next(t for t in contract["tables"] if t["name"] == "LaboratoryResult")
    row = project_source(population, contract, mapping)["LaboratoryResult"][0]
    row["NumericValue"] = value
    with pytest.raises(ValueError):
        normalize_row(row, table)


def test_clinical_composite_temporal_and_quantity_failures():
    contract, mapping = _inputs(ROOT, "Clarity")
    rows = project_source(fixture_population(), contract, mapping)
    for name, field, value in (
        ("Encounter", "PatientID", -1),
        ("Encounter", "DischargeAtUtc", "2026-10-11T10:00:00.0000007"),
        ("LaboratoryResult", "ResultUnit", None),
        ("Diagnosis", "DiagnosisSequence", 0),
        ("Appointment", "PatientID", -1),
        ("LaboratoryResult", "IsDeleted", 1),
    ):
        damaged = copy.deepcopy(rows)
        damaged[name][0][field] = value
        with pytest.raises(ValueError):
            validate_source_rows(damaged, contract)
    damaged = copy.deepcopy(rows)
    damaged["Appointment"].append(
        {**damaged["Appointment"][0], "AppointmentID": 777, "AppointmentNumber": "APT777"}
    )
    with pytest.raises(ValueError, match="uniqueness"):
        validate_source_rows(damaged, contract)


def test_caboodle_event_time_and_date_keys_are_validated():
    contract, mapping = _inputs(ROOT, "Caboodle")
    rows = project_source(fixture_population(), contract, mapping)
    for name, field, value in (
        ("FactEncounter", "ArrivalDateKey", 20261013),
        ("DimPatient", "EffectiveFromUtc", "2026-10-13T00:00:00Z"),
        ("DimPatient", "IsCurrent", 0),
        ("FactEncounter", "LengthOfStayMinutes", Decimal("31.00")),
    ):
        damaged = copy.deepcopy(rows)
        damaged[name][0][field] = value
        with pytest.raises(ValueError):
            validate_source_rows(damaged, contract)


def test_timestamp_keeps_seventh_digit_and_rejects_ambiguous_zone():
    assert sql_timestamp("2026-01-02T03:04:05.1234567Z").endswith(".1234567")
    with pytest.raises(ValueError):
        sql_timestamp("2026-01-02T03:04:05.1234567-05:00")


def test_derived_duration_rounds_like_sql_without_losing_datetime2_ticks():
    assert _evaluate(
        {"op": "minutes", "start": "start", "end": "end"},
        {"start": "2026-01-01T00:00:00.0000000", "end": "2026-01-01T00:00:00.3000000"},
    ) == Decimal("0.01")
    assert _evaluate(
        {"op": "minutes", "start": "start", "end": "end"},
        {"start": "2026-01-01T00:00:00.0000000", "end": "2026-01-01T00:00:00.2999999"},
    ) == Decimal("0.00")


def test_corrected_parent_catalog_and_soft_delete_propagate_without_changing_event_keys():
    population = fixture_population()
    contract, mapping = _inputs(ROOT, "Caboodle")
    before = project_source(population, contract, mapping)
    population["tables"]["MedicationOrder"][0]["MedicationCode"] = "CORRECTED"
    population["tables"]["MedicationOrder"][0]["MedicationName"] = "Synthetic corrected product"
    after = project_source(population, contract, mapping)
    validate_source_rows(after, contract)
    old_catalog_keys = {row["MedicationKey"] for row in before["DimMedication"]}
    assert old_catalog_keys < {row["MedicationKey"] for row in after["DimMedication"]}
    assert (
        after["FactMedicationAdministration"][0]["MedicationKey"]
        == (after["FactMedicationOrder"][0]["MedicationKey"])
    )
    assert (
        after["FactMedicationAdministration"][0]["MedicationAdministrationKey"]
        == (before["FactMedicationAdministration"][0]["MedicationAdministrationKey"])
    )
    population["tables"]["Encounter"][0]["IsDeleted"] = 1
    population["tables"]["Encounter"][0]["DeletedAtUtc"] = "2026-11-01T23:59:59.0000000"
    deleted = project_source(population, contract, mapping)
    validate_source_rows(deleted, contract)
    assert all(
        row["IsDeleted"]
        for name, rows in deleted.items()
        if name.startswith("Fact")
        for row in rows
    )


def test_pending_numeric_component_preserves_known_units_ranges_and_null_result_time():
    bundle = json.loads(FIXTURE.read_text(), parse_float=Decimal)
    observation = bundle["entry"][8]["resource"]
    observation["status"] = "registered"
    del observation["valueQuantity"]["value"]
    population = parse_bundles([bundle], history_start=START, publication_at=AT)
    for source in ("Clarity", "Caboodle"):
        contract, mapping = _inputs(ROOT, source)
        rows = project_source(population, contract, mapping)
        validate_source_rows(rows, contract)
        result = rows["LaboratoryResult" if source == "Clarity" else "FactLabResult"][0]
        assert result["NumericValue"] is None
        assert result["ResultUnit"] == "mg/dL"
        assert result["ReferenceLow"] == Decimal("70.000000")
        assert result["ResultedAtUtc"] is None


def test_current_attribute_changes_cannot_silently_bypass_explicit_dimension_history():
    baseline = local_demo_population(patients=12, history_start=START, publication_at=AT)
    changed = change_population(baseline, batch="day1", at="2026-11-02T12:00:00Z")
    patient = next(
        row
        for row in changed["tables"]["Patient"]
        if str(row["PatientID"]) in changed["histories"]["Patient"]
    )
    patient["FirstName"] = "Unrecorded synthetic correction"
    contract, mapping = _inputs(ROOT, "Caboodle")
    with pytest.raises(ValueError, match="history disagree"):
        project_source(changed, contract, mapping)
