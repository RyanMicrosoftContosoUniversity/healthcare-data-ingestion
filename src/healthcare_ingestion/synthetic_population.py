"""Durable, deterministic population batches and controlled independent-source workloads."""

import copy
import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from healthcare_ingestion.source_mapping import sql_timestamp, stable_id
from healthcare_ingestion.synthetic_fhir import TABLES, demo_bundle, parse_bundles

AUDIT_COLUMNS = {
    "CreatedAtUtc",
    "ModifiedAtUtc",
    "EtlCreatedAtUtc",
    "EtlModifiedAtUtc",
    "EtlBatchID",
    "OriginModifiedAtUtc",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def atomic_json(path: Path, value, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    with pending.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, default=str, indent=indent)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


@contextmanager
def file_lock(path: Path):
    """OS locks release on process death; no stale lockfile bypass or overlapping writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class IdentityManifest:
    def __init__(self, identities: dict | None = None):
        self.identities = dict(identities or {})
        self.reverse = {}
        for reference, key in self.identities.items():
            if key in self.reverse and self.reverse[key] != reference:
                raise ValueError("Existing identity manifest contains a bigint collision.")
            self.reverse[key] = reference

    def assign(self, namespace: str, reference: str) -> int:
        name = f"{namespace}|{reference}"
        key = stable_id(namespace, reference)
        if name in self.identities and self.identities[name] != key:
            raise ValueError("Identity algorithm/manifest changed.")
        if key in self.reverse and self.reverse[key] != name:
            raise ValueError("Deterministic bigint collision; population rejected.")
        self.identities[name], self.reverse[key] = key, name
        return key

    def capture(self, population: dict):
        for name, rows in population["tables"].items():
            for row in rows:
                reference = row["_origin_ref"]
                key = self.assign(name, reference)
                if key != row[name + "ID"]:
                    raise ValueError("Row identity differs from its persistent FHIR reference.")


class PopulationStore:
    """Immutable batches, atomic head, identity manifest, and explicit predecessor chain."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def read_batch(self, batch: str) -> dict:
        self._validate_batch(batch)
        document = json.loads((self.directory / "batches" / f"{batch}.json").read_text())
        if document["digest"] != digest(document["population"]):
            raise ValueError("Persistent population batch checksum mismatch.")
        return document

    def head(self):
        path = self.directory / "population-head.json"
        return json.loads(path.read_text())["batch"] if path.exists() else None

    def publish(self, batch: str, population: dict, predecessor: str | None = None) -> dict:
        self._validate_batch(batch)
        with file_lock(self.directory / "population.lock"):
            path = self.directory / "batches" / f"{batch}.json"
            if path.exists():
                existing = self.read_batch(batch)
                if (
                    existing["digest"] != digest(population)
                    or existing["predecessor"] != predecessor
                ):
                    raise ValueError("Conflicting rerun of immutable population batch.")
                # Repair a process failure after immutable batch write but before head write.
                if self.head() == predecessor:
                    atomic_json(self.directory / "identities.json", existing["identities"])
                    atomic_json(self.directory / "population-head.json", {"batch": batch})
                return existing
            if self.head() != predecessor:
                raise ValueError("Population predecessor is stale; overlapping windows rejected.")
            identities_path = self.directory / "identities.json"
            identities = IdentityManifest(
                json.loads(identities_path.read_text()) if identities_path.exists() else None
            )
            identities.capture(population)
            document = {
                "batch": batch,
                "predecessor": predecessor,
                "digest": digest(population),
                "population": population,
                "identities": identities.identities,
            }
            atomic_json(path, document)
            atomic_json(identities_path, identities.identities)
            atomic_json(self.directory / "population-head.json", {"batch": batch})
            return document

    @staticmethod
    def _validate_batch(batch):
        if not isinstance(batch, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", batch):
            raise ValueError("Batch names must be safe immutable identifiers.")


def local_demo_population(
    *,
    patients: int = 1000,
    history_start: str,
    publication_at: str,
) -> dict:
    if not 1 <= patients <= 1000:
        raise ValueError("Pilot baseline supports 1..1000 patients without runtime escalation.")
    result = parse_bundles(
        [demo_bundle(number, history_start) for number in range(patients)],
        history_start=history_start,
        publication_at=publication_at,
    )
    result["generator"] = {
        "engine": "explicit-local-supplement",
        "version": "1.0.0",
        "is_synthea_execution": False,
        "patients": patients,
        "months": 12,
    }
    return result


def change_population(previous: dict, *, batch: str, at: str, profile: str = "normal") -> dict:
    """No truncation: deterministic complete event groups with measured row-change totals."""
    if profile not in {"normal", "zero", "spike"}:
        raise ValueError("Unknown population change profile.")
    at = sql_timestamp(at)
    if at < previous["publication"]["at"]:
        raise ValueError("Incremental windows must advance monotonically.")
    result = copy.deepcopy(previous)
    result["publication"] = {"at": at, "batch_id": str(uuid5(NAMESPACE_URL, batch))}
    result["coverage"]["end"] = at
    result["change_profile"] = profile
    if profile == "zero":
        return result
    tables = result["tables"]
    patients = sorted(tables["Patient"], key=lambda r: r["PatientID"])
    if not patients or not tables["Encounter"]:
        raise ValueError("A change profile requires an established patient/encounter population.")

    def changed(row):
        row["ModifiedAtUtc"] = at

    # Five explicitly synthetic new patients/enrollments; clinical source populations are
    # not regenerated and their historical identities are never renumbered.
    for index in range(5):
        ref = f"daily-patient:{batch}:{index}"
        template = copy.deepcopy(patients[index % len(patients)])
        key = stable_id("Patient", ref)
        template.update(
            {
                "PatientID": key,
                "_origin_ref": ref,
                "MedicalRecordNumber": f"MRN{key}",
                "FirstName": f"SyntheticNew{index}",
                "City": "Synthetic daily city",
                "CreatedAtUtc": at,
                "ModifiedAtUtc": at,
                "DeathDate": None,
                "PatientStatus": "active",
                "IsDeleted": 0,
                "DeletedAtUtc": None,
            }
        )
        tables["Patient"].append(template)
        result["histories"].setdefault("Patient", {})[str(key)] = [
            {"row": copy.deepcopy(template), "from": at, "to": None}
        ]
        cov_ref = f"daily-coverage:{batch}:{index}"
        cov_key = stable_id("Coverage", cov_ref)
        enrollment = {
            **copy.deepcopy(tables["Coverage"][0]),
            "CoverageID": cov_key,
            "_origin_ref": cov_ref,
            "PatientID": key,
            "CoverageNumber": f"COV{cov_key}",
            "EffectiveDate": at[:10],
            "TerminationDate": None,
            "CoverageStatus": "active",
            "CreatedAtUtc": at,
            "ModifiedAtUtc": at,
            "IsDeleted": 0,
            "DeletedAtUtc": None,
        }
        tables["Coverage"].append(enrollment)
        result["histories"].setdefault("Coverage", {})[str(cov_key)] = [
            {"row": copy.deepcopy(enrollment), "from": at, "to": None}
        ]
    # Type 2 location changes are effective only from this approved synthetic window.
    for index, patient in enumerate(patients[:10]):
        key = str(patient["PatientID"])
        history = (
            result["histories"]
            .setdefault("Patient", {})
            .setdefault(
                key, [{"row": copy.deepcopy(patient), "from": result["history_start"], "to": None}]
            )
        )
        patient["City"] = f"Synthetic location {batch}-{index}"
        changed(patient)
        if history[-1]["from"] == at:
            # Same clinical instant corrects its existing version; no empty SCD interval.
            history[-1]["row"] = copy.deepcopy(patient)
        else:
            history[-1]["to"] = at
            history.append({"row": copy.deepcopy(patient), "from": at, "to": None})
    # Explicit workload fixtures avoid truncating or depending on the clinical content
    # of a randomly selected Synthea encounter. Imported clinical history stays intact.
    encounter_count = 25 if profile == "normal" else 250
    fixture = demo_bundle(0, at[:7] + "-01", months=1)
    for entry in fixture["entry"]:
        resource = entry["resource"]
        if resource["resourceType"] == "Encounter":
            resource["period"] = {"start": at, "end": at}
        for field in ("recordedDate", "performedDateTime", "authoredOn", "effectiveDateTime"):
            if field in resource:
                resource[field] = at
    template_population = parse_bundles([fixture], history_start=at, publication_at=at)
    template_tables = template_population["tables"]
    template_encounter = template_tables["Encounter"][0]
    encounter_id = template_encounter["EncounterID"]
    attending = tables["Encounter"][0]["AttendingProviderID"] or tables["Provider"][0]["ProviderID"]
    department = tables["Encounter"][0]["DepartmentID"]
    template_groups = {}
    for name in TABLES:
        if name in {"Patient", "Provider", "Department", "Coverage"}:
            continue
        if name == "Encounter":
            rows = [template_encounter]
        elif name == "MedicationAdministration":
            orders = {
                r["MedicationOrderID"]
                for r in template_tables["MedicationOrder"]
                if r["EncounterID"] == encounter_id
            }
            rows = [r for r in template_tables[name] if r["MedicationOrderID"] in orders]
        elif name == "LaboratoryResult":
            orders = {
                r["LaboratoryOrderID"]
                for r in template_tables["LaboratoryOrder"]
                if r["EncounterID"] == encounter_id
            }
            rows = [r for r in template_tables[name] if r["LaboratoryOrderID"] in orders]
        else:
            rows = [r for r in template_tables[name] if r.get("EncounterID") == encounter_id]
        template_groups[name] = copy.deepcopy(rows)
    if not template_groups["LaboratoryResult"]:
        raise ValueError("Workload supplement requires an established numeric laboratory fixture.")
    for index in range(encounter_count):
        patient = patients[index % len(patients)]
        id_map = {}
        clones = {}
        for name, rows in template_groups.items():
            clones[name] = []
            for ordinal, original in enumerate(rows):
                ref = f"daily-event:{batch}:{index}:{name}:{ordinal}"
                key = stable_id(name, ref)
                id_map[original[name + "ID"]] = key
                clone = copy.deepcopy(original)
                clone.update(
                    {
                        name + "ID": key,
                        "_origin_ref": ref,
                        "CreatedAtUtc": at,
                        "ModifiedAtUtc": at,
                        "IsDeleted": 0,
                        "DeletedAtUtc": None,
                    }
                )
                clones[name].append(clone)
        for name, rows in clones.items():
            for clone in rows:
                for field, value in list(clone.items()):
                    if field.endswith("ID") and field != name + "ID" and value in id_map:
                        clone[field] = id_map[value]
                    if field.endswith("ProviderID"):
                        clone[field] = attending
                    if field == "DepartmentID":
                        clone[field] = department
                    if field.endswith("AtUtc") and field not in AUDIT_COLUMNS and value is not None:
                        clone[field] = at
                if "PatientID" in clone:
                    clone["PatientID"] = patient["PatientID"]
                if name == "Encounter":
                    eligible = [
                        c
                        for c in tables["Coverage"]
                        if c["PatientID"] == patient["PatientID"]
                        and c["EffectiveDate"] <= at[:10]
                        and not c["IsDeleted"]
                        and (c["TerminationDate"] is None or at[:10] <= c["TerminationDate"])
                    ]
                    clone["PrimaryCoverageID"] = (
                        eligible[0]["CoverageID"] if len(eligible) == 1 else (None)
                    )
                    clone["EncounterNumber"] = f"ENC{clone['EncounterID']}"
                if name == "Appointment":
                    clone["AppointmentNumber"] = f"APT{clone['AppointmentID']}"
                if name == "LaboratoryOrder":
                    clone["OrderNumber"] = f"LAB{clone['LaboratoryOrderID']}"
                tables[name].append(clone)
        # Two additional synthetic components per order make normal ~500-1000 combined
        # changes. They use explicit fixture codes, never fabricated patient clinical values.
        for component in range(2):
            original = clones["LaboratoryResult"][0]
            ref = f"daily-extra-lab:{batch}:{index}:{component}"
            clone = {
                **original,
                "LaboratoryResultID": stable_id("LaboratoryResult", ref),
                "_origin_ref": ref,
                "ComponentCode": f"DEMO-EXTRA-{component}",
                "ComponentName": f"Synthetic workload component {component}",
            }
            tables["LaboratoryResult"].append(clone)
    # Correct four existing stable lab IDs, then soft-delete two eligible leaf results.
    candidates = [
        r
        for r in tables["LaboratoryResult"]
        if r["CreatedAtUtc"] < at and not r["IsDeleted"] and r["NumericValue"] is not None
    ]
    from decimal import Decimal

    for row in candidates[:4]:
        row["NumericValue"] = str(Decimal(str(row["NumericValue"])) + Decimal("0.000001"))
        row["ResultStatus"] = "corrected"
        changed(row)
    for row in candidates[4:6]:
        row["IsDeleted"], row["DeletedAtUtc"] = 1, at
        changed(row)
    result["supplemental_rules"].append(
        {
            "rule": "controlled-daily-workload-v1",
            "batch": batch,
            "new_patients": 5,
            "demographic_updates": min(10, len(patients)),
            "encounters": encounter_count,
            "corrections": min(4, len(candidates)),
            "leaf_soft_deletes": min(2, max(0, len(candidates) - 4)),
        }
    )
    return result


def row_signature(row: dict) -> str:
    return digest({k: v for k, v in row.items() if k not in AUDIT_COLUMNS})


def source_delta(current: dict, previous: dict | None, contract: dict) -> dict:
    """Snapshot-diff incremental loading, including audit-safe zero-change runs."""
    output = {}
    for table in contract["tables"]:
        name, keys = table["name"], table["primary_key"]
        old = {tuple(r[k] for k in keys): r for r in (previous or {}).get(name, [])}
        new = {tuple(r[k] for k in keys): r for r in current[name]}
        if len(new) != len(current[name]):
            raise ValueError(f"{name}: duplicate row identities.")
        if old.keys() - new.keys():
            raise ValueError(f"{name}: physical row removal is not an approved write scenario.")
        output[name] = [
            row
            for key, row in new.items()
            if key not in old or row_signature(row) != row_signature(old[key])
        ]
    return output
