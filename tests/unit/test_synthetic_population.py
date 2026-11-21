import copy
import json
import shutil
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from healthcare_ingestion.generator import _inputs
from healthcare_ingestion.source_mapping import project_source
from healthcare_ingestion.synthetic_fhir import parse_bundles
from healthcare_ingestion.synthetic_population import (
    IdentityManifest,
    PopulationStore,
    change_population,
    file_lock,
    local_demo_population,
    source_delta,
)

ROOT = Path(__file__).resolve().parents[2]
START, AT = "2025-11-01T00:00:00Z", "2026-11-01T23:59:59Z"


@pytest.fixture
def workspace():
    path = ROOT / (".source-test-state-" + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_manifest_population_restart_rerun_checksum_and_conflicts(workspace):
    population = local_demo_population(patients=2, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    original = store.publish("baseline", population)
    restarted = PopulationStore(workspace)
    assert restarted.publish("baseline", population) == original
    assert restarted.head() == "baseline"
    assert json.loads((workspace / "identities.json").read_text()) == original["identities"]
    changed = copy.deepcopy(population)
    changed["tables"]["Patient"][0]["City"] = "Different city"
    with pytest.raises(ValueError, match="Conflicting"):
        restarted.publish("baseline", changed)
    with pytest.raises(ValueError, match="stale"):
        restarted.publish("day1", changed)
    path = workspace / "batches" / "baseline.json"
    document = json.loads(path.read_text())
    document["population"]["tables"]["Patient"][0]["City"] = "Tampered"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="checksum"):
        restarted.read_batch("baseline")


def test_post_batch_pre_head_failure_repairs_manifest_and_head(workspace):
    population = local_demo_population(patients=2, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    original = store.publish("baseline", population)
    (workspace / "population-head.json").unlink()
    (workspace / "identities.json").unlink()
    assert store.publish("baseline", population) == original
    assert store.head() == "baseline"
    assert (workspace / "identities.json").exists()


def test_os_lock_prevents_overlapping_writes(workspace):
    with file_lock(workspace / "lock"):
        with pytest.raises(OSError):
            with file_lock(workspace / "lock"):
                pytest.fail("second writer entered the locked section")


@pytest.mark.parametrize(
    "profile,bounds", [("zero", (0, 0)), ("normal", (500, 1000)), ("spike", (4500, 5500))]
)
def test_deterministic_profiles_and_corrections_deletes(profile, bounds):
    population = local_demo_population(patients=12, history_start=START, publication_at=AT)
    changed = change_population(
        population, batch="day1", at="2026-11-02T12:00:00Z", profile=profile
    )
    assert changed == change_population(
        population, batch="day1", at="2026-11-02T12:00:00Z", profile=profile
    )
    combined = 0
    for source in ("Clarity", "Caboodle"):
        contract, mapping = _inputs(ROOT, source)
        before, after = (project_source(p, contract, mapping) for p in (population, changed))
        delta = source_delta(after, before, contract)
        combined += sum(map(len, delta.values()))
        if profile != "zero":
            table = "LaboratoryResult" if source == "Clarity" else "FactLabResult"
            assert sum(row["IsDeleted"] for row in delta[table]) == 2
            assert sum(row["ResultStatus"] == "corrected" for row in delta[table]) == 4
    assert bounds[0] <= combined <= bounds[1]
    if profile != "zero":
        assert len(changed["tables"]["Patient"]) == 17
        IdentityManifest().capture(changed)


def test_unknown_missing_patient_reference_and_unsupported_clinical_values_fail():
    fixture = json.loads(
        (ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json").read_text(),
        parse_float=Decimal,
    )
    for damage in ("unknown", "patient", "value", "unit"):
        bundle = copy.deepcopy(fixture)
        if damage == "unknown":
            bundle["entry"].append({"resource": {"id": "x", "resourceType": "UnapprovedClinical"}})
        elif damage == "patient":
            bundle["entry"][3]["resource"]["subject"]["reference"] = "Patient/missing"
        elif damage == "value":
            bundle["entry"][8]["resource"]["valueQuantity"] = {"value": "10"}
        else:
            bundle["entry"][8]["resource"]["referenceRange"][0]["low"]["unit"] = "mmol/L"
        with pytest.raises(ValueError):
            parse_bundles([bundle], history_start=START, publication_at=AT)


def test_missing_optional_data_are_null_and_required_names_rejected():
    fixture = json.loads(
        (ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json").read_text(),
        parse_float=Decimal,
    )
    del fixture["entry"][0]["resource"]["address"]
    population = parse_bundles([fixture], history_start=START, publication_at=AT)
    assert population["tables"]["Patient"][0]["PostalCode"] is None
    del fixture["entry"][0]["resource"]["name"][0]["family"]
    with pytest.raises(ValueError):
        parse_bundles([fixture], history_start=START, publication_at=AT)


def test_explicit_service_request_and_component_identifiers_are_preserved():
    fixture = json.loads(
        (ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json").read_text(),
        parse_float=Decimal,
    )
    observation = fixture["entry"][8]["resource"]
    order = {
        "resourceType": "ServiceRequest",
        "id": "actual-lab-order",
        "subject": observation["subject"],
        "encounter": observation["encounter"],
        "code": observation["code"],
        "status": "completed",
        "authoredOn": "2026-10-12T10:00:00Z",
    }
    fixture["entry"].append({"resource": order, "fullUrl": "urn:uuid:actual-lab-order"})
    observation["basedOn"] = [{"reference": "urn:uuid:actual-lab-order"}]
    population = parse_bundles([fixture], history_start=START, publication_at=AT)
    assert population["tables"]["LaboratoryOrder"][0]["_origin_ref"] == (
        "ServiceRequest/actual-lab-order"
    )
    assert (
        population["tables"]["LaboratoryResult"][0]["LaboratoryOrderID"]
        == (population["tables"]["LaboratoryOrder"][0]["LaboratoryOrderID"])
    )


def test_1000_patient_demo_has_12_months_complete_history_and_all_tables():
    population = local_demo_population(patients=1000, history_start=START, publication_at=AT)
    assert len(population["tables"]["Patient"]) == 1000
    assert len(population["tables"]["Encounter"]) == 12000
    assert all(population["tables"].values())
    assert len({row["PatientID"] for row in population["tables"]["Patient"]}) == 1000
    assert {row["ArrivalAtUtc"][:7] for row in population["tables"]["Encounter"]} == {
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    }


def test_conditional_location_role_and_unitless_dose_are_explicitly_preserved():
    fixture = json.loads(
        (ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json").read_text(),
        parse_float=Decimal,
    )
    encounter = next(
        e["resource"] for e in fixture["entry"] if e["resource"]["resourceType"] == "Encounter"
    )
    practitioner = next(
        e["resource"] for e in fixture["entry"] if e["resource"]["resourceType"] == "Practitioner"
    )
    location = {
        "resourceType": "Location",
        "id": "conditional-location",
        "identifier": [{"system": "urn:location", "value": "fixture-location"}],
    }
    role = {
        "resourceType": "PractitionerRole",
        "id": "fixture-role",
        "practitioner": {"reference": "Practitioner/" + practitioner["id"]},
    }
    fixture["entry"].extend([{"resource": location}, {"resource": role}])
    encounter["location"] = [
        {
            "location": {
                "reference": "Location?identifier=urn%3Alocation%7Cfixture-location",
            }
        }
    ]
    encounter["participant"] = [{"individual": {"reference": "PractitionerRole/fixture-role"}}]
    medication = next(
        e["resource"]
        for e in fixture["entry"]
        if e["resource"]["resourceType"] == "MedicationRequest"
    )
    medication["dosageInstruction"] = [{"doseAndRate": [{"doseQuantity": {"value": 2}}]}]
    population = parse_bundles([fixture], history_start=START, publication_at=AT)
    assert population["tables"]["MedicationOrder"][0]["OrderedDose"] is None
    rules = {r["rule"] for r in population["supplemental_rules"]}
    assert {"unitless-dose-retained-in-fhir-archive", "unnamed-care-location"} <= rules
    archived = population["fhir_archive"]
    assert (
        archived["MedicationRequest/" + medication["id"]]["dosageInstruction"]
        == (medication["dosageInstruction"])
    )
    value = encounter["location"][0]["location"]
    original_reference = value["reference"]
    value["reference"] += "&_id=unsupported-filter"
    with pytest.raises(ValueError, match="conditional"):
        parse_bundles([fixture], history_start=START, publication_at=AT)
    value["reference"] = original_reference
    # A search reference is never resolved by arbitrary first-match selection.
    fixture["entry"].append({"resource": {**location, "id": "ambiguous-location"}})
    with pytest.raises(ValueError, match="unique target"):
        parse_bundles([fixture], history_start=START, publication_at=AT)


def test_decimal_mapping_is_explicit_half_up_and_archive_retains_full_precision():
    fixture = json.loads(
        (ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json").read_text(),
        parse_float=Decimal,
    )
    observation = fixture["entry"][8]["resource"]
    observation["valueQuantity"]["value"] = Decimal("1.2344565")
    population = parse_bundles([fixture], history_start=START, publication_at=AT)
    for source, table in (("Clarity", "LaboratoryResult"), ("Caboodle", "FactLabResult")):
        contract, mapping = _inputs(ROOT, source)
        assert project_source(population, contract, mapping)[table][0]["NumericValue"] == (
            Decimal("1.234457")
        )
    assert population["fhir_archive"]["Observation/" + observation["id"]]["valueQuantity"][
        "value"
    ] == Decimal("1.2344565")


def test_unlinked_administration_gets_named_order_and_archives_unknown_dose_units():
    fixture = json.loads(
        (ROOT / "scripts" / "synthetic-data" / "fixtures" / "synthea-r4.json").read_text(),
        parse_float=Decimal,
    )
    request = next(
        e["resource"]
        for e in fixture["entry"]
        if e["resource"]["resourceType"] == "MedicationRequest"
    )
    administration = {
        "resourceType": "MedicationAdministration",
        "id": "unlinked-administration",
        "subject": request["subject"],
        "context": request["encounter"],
        "medicationCodeableConcept": request["medicationCodeableConcept"],
        "effectiveDateTime": "2026-10-12T10:00:00Z",
        "status": "completed",
        "dosage": {"dose": {"value": 2}},
    }
    fixture["entry"].append({"resource": administration})
    population = parse_bundles([fixture], history_start=START, publication_at=AT)
    row = next(
        r
        for r in population["tables"]["MedicationAdministration"]
        if r["_origin_ref"] == "MedicationAdministration/unlinked-administration"
    )
    order = next(
        r
        for r in population["tables"]["MedicationOrder"]
        if r["MedicationOrderID"] == row["MedicationOrderID"]
    )
    assert row["AdministeredDose"] is None and order["OrderedDose"] is None
    assert row["RecordedAtUtc"] == order["OrderedAtUtc"]
    rules = {r["rule"] for r in population["supplemental_rules"]}
    assert {"administration-order-not-provided", "unitless-dose-retained-in-fhir-archive"} <= rules
    assert population["fhir_archive"]["MedicationAdministration/unlinked-administration"] == (
        administration
    )
    for source in ("Clarity", "Caboodle"):
        contract, mapping = _inputs(ROOT, source)
        assert project_source(population, contract, mapping)


def test_equal_supplied_at_batches_correct_dimensions_without_empty_intervals():
    population = local_demo_population(patients=12, history_start=START, publication_at=AT)
    first = change_population(population, batch="one", at="2026-11-02T12:00:00Z")
    second = change_population(first, batch="two", at="2026-11-02T12:00:00Z")
    assert first["coverage"]["end"] == second["coverage"]["end"]
    combined = 0
    for source in ("Clarity", "Caboodle"):
        contract, mapping = _inputs(ROOT, source)
        before, after = (project_source(p, contract, mapping) for p in (first, second))
        from healthcare_ingestion.sql_source_integrity import validate_source_rows

        validate_source_rows(after, contract)
        combined += sum(map(len, source_delta(after, before, contract).values()))
    assert 500 <= combined <= 1000
    for versions in second["histories"]["Patient"].values():
        assert all(v["to"] is None or v["from"] < v["to"] for v in versions)
