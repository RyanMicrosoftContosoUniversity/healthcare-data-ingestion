"""Offline source write-path validation, including composite and temporal relationships."""

from collections import defaultdict
from decimal import Decimal

from healthcare_ingestion.source_ddl import _REFERENCE
from healthcare_ingestion.source_mapping import DATE_FIELDS, normalize_row

EVENT_TIMES = {
    "FactEncounter": ("ArrivalAtUtc",),
    "FactDiagnosis": ("DiagnosedAtUtc",),
    "FactProcedure": ("PerformedAtUtc", "OrderedAtUtc"),
    "FactMedicationOrder": ("OrderedAtUtc",),
    "FactMedicationAdministration": ("AdministeredAtUtc", "RecordedAtUtc"),
    "FactLabResult": ("ResultedAtUtc", "OrderedAtUtc"),
    "FactAppointment": ("ScheduledStartAtUtc",),
}
PERIODS = (
    ("BirthDate", "DeathDate"),
    ("ArrivalAtUtc", "DischargeAtUtc"),
    ("OrderedAtUtc", "PerformedAtUtc"),
    ("OrderedAtUtc", "CollectedAtUtc"),
    ("OrderedAtUtc", "StartAtUtc"),
    ("StartAtUtc", "EndAtUtc"),
    ("EffectiveDate", "TerminationDate"),
    ("ScheduledStartAtUtc", "ScheduledEndAtUtc"),
    ("EffectiveFromUtc", "EffectiveToUtc"),
    ("ReferenceLow", "ReferenceHigh"),
    ("CreatedAtUtc", "ModifiedAtUtc"),
    ("EtlCreatedAtUtc", "EtlModifiedAtUtc"),
)


def validate_source_rows(rows: dict, contract: dict) -> None:
    """Reject invalid complete snapshots before any SQL transaction is started."""
    expected = {t["name"]: t for t in contract["tables"]}
    if set(rows) != set(expected):
        raise ValueError("Source snapshot must contain all approved models exactly.")
    indexes = {}
    for name, table in expected.items():
        normalized = [normalize_row(row, table) for row in rows[name]]
        indexes[name] = {tuple(r[k] for k in table["primary_key"]): r for r in normalized}
        if len(indexes[name]) != len(normalized):
            raise ValueError(f"{name}: duplicate primary key.")
        unique = [c["name"] for c in table["columns"] if c["purpose"].startswith("UQ;")]
        for column in unique:
            values = [row[column] for row in normalized if row[column] is not None]
            if len(values) != len(set(values)):
                raise ValueError(f"{name}: duplicate unique business key.")
        for row in normalized:
            for lower, upper in PERIODS:
                if row.get(lower) is not None and row.get(upper) is not None:
                    if row[lower] > row[upper] or (
                        lower == "EffectiveFromUtc" and row[lower] == row[upper]
                    ):
                        raise ValueError(f"{name}: reversed or empty temporal/reference interval.")
            for value, unit in (
                ("OrderedDose", "DoseUnit"),
                ("AdministeredDose", "DoseUnit"),
                ("NumericValue", "ResultUnit" if "ResultUnit" in row else "ValueUnit"),
            ):
                if value in row and unit in row and row[value] is not None and row[unit] is None:
                    raise ValueError(f"{name}: incompatible quantity/value unit pair.")
            if (
                "ResultUnit" in row
                and any(row.get(field) is not None for field in ("ReferenceLow", "ReferenceHigh"))
                and row["ResultUnit"] is None
            ):
                raise ValueError(f"{name}: reference bounds require a known result unit.")
            if "DeletedAtUtc" in row and bool(row["IsDeleted"]) != bool(row["DeletedAtUtc"]):
                raise ValueError(f"{name}: soft-delete timestamp mismatch.")
        for column in table["columns"]:
            reference = _REFERENCE.match(column["purpose"])
            if reference:
                target = {r[reference[2]] for r in rows[reference[1]]}
                if any(
                    r[column["name"]] is not None and r[column["name"]] not in target
                    for r in normalized
                ):
                    raise ValueError(f"{name}: dangling foreign key.")
    if contract["source_system"] == "Clarity":
        _clarity(rows)
    else:
        _caboodle(rows)


def _one_unique(rows, fields, name, predicate=lambda r: True):
    keys = [tuple(r[field] for field in fields) for r in rows if predicate(r)]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{name}: composite/filtered business uniqueness violation.")


def _clarity(rows):
    encounters = {r["EncounterID"]: r for r in rows["Encounter"]}
    coverage = {r["CoverageID"]: r for r in rows["Coverage"]}
    for row in rows["Encounter"]:
        cov = coverage.get(row["PrimaryCoverageID"])
        if cov and (
            cov["PatientID"] != row["PatientID"]
            or cov["EffectiveDate"] > row["ArrivalAtUtc"][:10]
            or (cov["TerminationDate"] and cov["TerminationDate"] < row["ArrivalAtUtc"][:10])
        ):
            raise ValueError("Encounter: assigned coverage patient/date mismatch.")
    _one_unique(
        rows["Appointment"], ["EncounterID"], "Appointment", lambda r: r["EncounterID"] is not None
    )
    for row in rows["Appointment"]:
        if row["EncounterID"] is not None:
            if encounters[row["EncounterID"]]["PatientID"] != row["PatientID"]:
                raise ValueError("Appointment: patient differs from linked encounter.")
    _one_unique(rows["Diagnosis"], ["EncounterID", "DiagnosisSequence"], "Diagnosis")
    _one_unique(
        rows["Diagnosis"],
        ["EncounterID"],
        "Diagnosis active primary",
        lambda r: (
            r["IsPrimary"]
            and not r["IsDeleted"]
            and r["DiagnosisStatus"] not in {"canceled", "cancelled", "inactive"}
        ),
    )
    if any(r["DiagnosisSequence"] <= 0 for r in rows["Diagnosis"]):
        raise ValueError("Diagnosis: sequence must be positive.")


def _caboodle(rows):
    dimensions = {}
    for name in ("DimPatient", "DimProvider", "DimDepartment", "DimCoverage"):
        business = "Source" + name[3:] + "ID"
        key = name[3:] + "Key"
        groups = defaultdict(list)
        dimensions[name] = {r[key]: r for r in rows[name]}
        for row in rows[name]:
            if bool(row["IsCurrent"]) != (row["EffectiveToUtc"] is None):
                raise ValueError(f"{name}: current flag/validity mismatch.")
            groups[(row["OriginSystem"], row[business])].append(row)
        for versions in groups.values():
            versions.sort(key=lambda r: r["EffectiveFromUtc"])
            if sum(r["IsCurrent"] for r in versions) != 1:
                raise ValueError(f"{name}: exactly one current version required.")
            for left, right in zip(versions, versions[1:]):
                if left["EffectiveToUtc"] is None or (
                    left["EffectiveToUtc"] > right["EffectiveFromUtc"]
                ):
                    raise ValueError(f"{name}: overlapping dimension versions.")
    for name, prefix in (
        ("DimDiagnosis", "Diagnosis"),
        ("DimProcedure", "Procedure"),
        ("DimMedication", "Medication"),
    ):
        _one_unique(rows[name], ["OriginSystem", prefix + "CodeSystem", prefix + "Code"], name)
    encounters = {r["SourceEncounterID"]: r for r in rows["FactEncounter"]}
    orders = {r["SourceMedicationOrderID"]: r for r in rows["FactMedicationOrder"]}
    for name, candidates in EVENT_TIMES.items():
        event_id = {
            "FactEncounter": "SourceEncounterID",
            "FactDiagnosis": "SourceDiagnosisID",
            "FactProcedure": "SourceProcedureID",
            "FactMedicationOrder": "SourceMedicationOrderID",
            "FactMedicationAdministration": "SourceMedicationAdministrationID",
            "FactLabResult": "SourceLaboratoryResultID",
            "FactAppointment": "SourceAppointmentID",
        }[name]
        _one_unique(rows[name], ["OriginSystem", event_id], name)
        for row in rows[name]:
            event = next((row.get(field) for field in candidates if row.get(field)), None)
            if event is None:
                raise ValueError(f"{name}: dimension lookup event is missing.")
            for field, dim in (
                ("PatientKey", "DimPatient"),
                ("DepartmentKey", "DimDepartment"),
                ("CoverageKey", "DimCoverage"),
                ("AttendingProviderKey", "DimProvider"),
                ("DiagnosingProviderKey", "DimProvider"),
                ("PerformingProviderKey", "DimProvider"),
                ("OrderingProviderKey", "DimProvider"),
                ("AdministeringProviderKey", "DimProvider"),
                ("ProviderKey", "DimProvider"),
            ):
                if row.get(field) is None:
                    continue
                version = dimensions[dim][row[field]]
                if event < version["EffectiveFromUtc"] or (
                    version["EffectiveToUtc"] and event >= version["EffectiveToUtc"]
                ):
                    raise ValueError(f"{name}: event-time dimension relationship invalid.")
            for key, field in DATE_FIELDS.items():
                if key in row:
                    value = int(row[field][:10].replace("-", "")) if row.get(field) else None
                    if row[key] != value:
                        raise ValueError(f"{name}: date key/event mismatch.")
            parent = encounters.get(row.get("SourceEncounterID"))
            patient = dimensions["DimPatient"][row["PatientKey"]]
            if parent:
                parent_patient = dimensions["DimPatient"][parent["PatientKey"]]
                if patient["SourcePatientID"] != parent_patient["SourcePatientID"]:
                    raise ValueError(f"{name}: patient differs from parent encounter.")
                if row["IsDeleted"] < parent["IsDeleted"]:
                    raise ValueError(f"{name}: parent delete was not propagated.")
            if name == "FactEncounter" and row["CoverageKey"] is not None:
                cov = dimensions["DimCoverage"][row["CoverageKey"]]
                if cov["SourcePatientID"] != patient["SourcePatientID"] or (
                    cov["EffectiveDate"] > event[:10]
                    or cov["TerminationDate"]
                    and cov["TerminationDate"] < event[:10]
                ):
                    raise ValueError("FactEncounter: assigned enrollment patient/date mismatch.")
            if name == "FactMedicationAdministration":
                order = orders.get(row["SourceMedicationOrderID"])
                if (
                    order is None
                    or order["SourceEncounterID"] != row["SourceEncounterID"]
                    or (
                        order["MedicationKey"] != row["MedicationKey"]
                        or row["IsDeleted"] < order["IsDeleted"]
                    )
                ):
                    raise ValueError("FactMedicationAdministration: corrected parent mismatch.")
            if name == "FactEncounter" and row["DischargeAtUtc"]:
                from healthcare_ingestion.source_mapping import _evaluate

                expected = _evaluate(
                    {"op": "minutes", "start": "ArrivalAtUtc", "end": "DischargeAtUtc"}, row
                )
                if Decimal(str(row["LengthOfStayMinutes"])) != expected:
                    raise ValueError("FactEncounter: derived length of stay mismatch.")
    _one_unique(rows["FactDiagnosis"], ["SourceEncounterID", "DiagnosisSequence"], "FactDiagnosis")
