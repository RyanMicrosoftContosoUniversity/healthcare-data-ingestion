"""Offline SQL dictionary/check and complete demo configuration export; never deploys."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from healthcare_ingestion.configuration import (
    DatasetSpec,
    FunctionSpec,
    InputSpec,
    ReleaseSnapshot,
    TaskSpec,
)
from healthcare_ingestion.function_contracts import FUNCTION_SCHEMAS
from healthcare_ingestion.metadata_migrations import load_migrations

ROOT = Path(__file__).resolve().parents[2]
METADATA = ROOT / "database" / "metadata"

_SOURCES = {
    "Clarity": (
        "Patient",
        "Provider",
        "Department",
        "Encounter",
        "Diagnosis",
        "Procedure",
        "MedicationOrder",
        "MedicationAdministration",
        "LaboratoryOrder",
        "LaboratoryResult",
        "VitalSign",
        "Coverage",
        "Appointment",
    ),
    "Caboodle": (
        "DimPatient",
        "DimProvider",
        "DimDepartment",
        "DimDate",
        "DimDiagnosis",
        "DimProcedure",
        "DimMedication",
        "DimCoverage",
        "FactEncounter",
        "FactDiagnosis",
        "FactProcedure",
        "FactMedicationOrder",
        "FactMedicationAdministration",
        "FactLabResult",
        "FactAppointment",
    ),
}


def column_dictionary() -> str:
    lines = [
        "# Fabric SQL physical column dictionary",
        "",
        "Generated from the versioned, additive T-SQL migrations. These definitions are",
        "reviewable implementation artifacts, not evidence of live deployment.",
        "All runtime timestamps are UTC `datetime2(7)`; coverage windows are canonical",
        "UTC ISO `varchar(27)` so DB-API does not truncate the seventh fractional digit.",
        "Keys, composite correlation FKs, constraints and indexes are authoritative in SQL.",
        "No FK cascade deletion is permitted. JSON also requires application validation.",
        "",
    ]
    sql = "\n".join(m.sql for m in load_migrations(METADATA / "migrations"))
    for match in re.finditer(r"CREATE TABLE (\w+\.\w+)\s*\((.*?)\n\);", sql, re.DOTALL):
        name, body = match.groups()
        body += "\n" + "\n".join(
            re.findall(
                rf"ALTER TABLE {re.escape(name)}\s+ADD\s+(.*?);",
                sql,
                re.DOTALL,
            )
        )
        lines.extend(
            (f"## `{name}`", "", "| Column | SQL type | Nullable |", "| --- | --- | --- |")
        )
        for column in re.finditer(
            r"^\s*,?\s*\[?(\w+)\]?\s+"
            r"((?:varchar|nvarchar|char|datetime2|decimal)\([^)]+\)|bigint|int|bit)\s+"
            r"(NOT NULL|NULL)([^\n]*)",
            body,
            re.MULTILINE | re.IGNORECASE,
        ):
            column_name, sql_type, nullable, _ = column.groups()
            lines.append(
                f"| `{column_name}` | `{sql_type}` | "
                f"{'No' if nullable.upper() == 'NOT NULL' else 'Yes'} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def demo_snapshot() -> ReleaseSnapshot:
    """Unpublished template; placeholders fail candidate/activation evidence gates."""
    contract = json.loads(
        (ROOT / "database" / "schema-contracts" / "clarity.json").read_text(encoding="utf-8")
    )
    patient = next(table for table in contract["tables"] if table["name"] == "Patient")
    patient_columns = [column["name"] for column in patient["columns"]]
    datasets, tasks, mappings = [], [], {}
    for system, names in _SOURCES.items():
        domain = system.lower()
        for name in names:
            logical = f"{domain}.{name.lower()}"
            source_id, bronze_id = f"source.{logical}", f"bronze.{logical}"
            datasets.extend(
                (
                    DatasetSpec(
                        source_id,
                        f"{system}.dbo.{name}",
                        "source",
                        external=True,
                        physical_maps={
                            "demo": {
                                "kind": "sql",
                                "connection_ref": f"{domain}-source",
                                "schema": "dbo",
                                "table": name,
                            }
                        },
                    ),
                    DatasetSpec(
                        bronze_id,
                        f"{system} {name} Bronze observations",
                        "bronze",
                        physical_maps={
                            "demo": {
                                "kind": "delta",
                                "workspace_ref": "data-workspace",
                                "lakehouse_ref": "bronze-lakehouse",
                                "schema": domain,
                                "table": name,
                            }
                        },
                    ),
                )
            )
            mapping_id = f"{logical}.source-to-bronze"
            mappings[mapping_id] = {
                "source_dataset": source_id,
                "target_dataset": bronze_id,
                "source_contract_ref": f"{domain}-approved-contract",
                "source_schema": "dbo",
                "source_table": name,
                "capture_mode": "CHECKPOINT",
                "strict_schema": True,
                "initial_nonempty": name in {"Patient", "DimPatient"},
            }
            tasks.append(
                TaskSpec(
                    f"ingest.{logical}",
                    f"{domain}_bronze",
                    bronze_id,
                    (InputSpec(source_id, "source"),),
                    pipeline_object_id=mapping_id,
                )
            )
    datasets.append(
        DatasetSpec(
            "silver1.clarity.patient",
            "Clarity Patient latest state",
            "silver1",
            physical_maps={
                "demo": {
                    "kind": "delta",
                    "workspace_ref": "data-workspace",
                    "lakehouse_ref": "silver-lakehouse",
                    "schema": "clarity",
                    "table": "Patient",
                }
            },
        )
    )
    tasks.append(
        TaskSpec(
            "curate.clarity.patient",
            "patient_silver",
            "silver1.clarity.patient",
            (InputSpec("bronze.clarity.patient", "patient"),),
            (
                FunctionSpec(
                    "patient.names.trim.v1",
                    "normalize_names",
                    {"columns": ["FirstName", "LastName"]},
                    ("patient",),
                ),
                FunctionSpec(
                    "patient.state.latest.v1",
                    "latest_patient",
                    {
                        "key": "PatientID",
                        "modified": "ModifiedAtUtc",
                        "business_columns": patient_columns,
                    },
                    ("patient",),
                ),
            ),
        )
    )
    snapshot = ReleaseSnapshot(
        "0.1.0",
        "0.1.0",
        tuple(datasets),
        tuple(tasks),
        {
            **{
                name: {"state": "UNPUBLISHED", "approved_digest_required": True}
                for name in ("package", "dependencies", "notebooks", "environments", "dags")
            },
            "pipeline_objects": mappings,
        },
        framework_defaults={
            "scheduler": {
                "retries": 2,
                "retry_delay_seconds": 30,
                "timeout_seconds": 3600,
                "priority": 10,
            },
            "spark": {"startup": {}, "runtime": {}},
            "execution": {"concurrency_limit": 1},
            "events": {
                "coalesce": True,
                "reconcile_seconds": 300,
                "max_retries": 3,
                "retry_delay_seconds": 30,
            },
        },
        stage_defaults={
            "bronze": {
                "execution": {
                    "notebook_ref": "generic-bronze",
                    "environment_ref": "bronze-environment",
                    "compute_profile_ref": "bronze-profile",
                    "ingestion_strategy": "checkpoint_append",
                }
            },
            "silver1": {
                "execution": {
                    "notebook_ref": "generic-silver1",
                    "environment_ref": "silver1-environment",
                    "compute_profile_ref": "silver1-profile",
                    "ingestion_strategy": "latest_state_merge",
                }
            },
        },
    )
    snapshot.validate(FUNCTION_SCHEMAS)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-dictionary", action="store_true")
    parser.add_argument("--write-demo", action="store_true")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    dictionary_path = METADATA / "COLUMN_DICTIONARY.md"
    demo_path = ROOT / "metadata" / "framework" / "demo-release.json"
    if arguments.write_dictionary:
        dictionary_path.write_text(column_dictionary(), encoding="utf-8")
    if arguments.write_demo:
        demo_path.parent.mkdir(parents=True, exist_ok=True)
        demo_path.write_text(
            json.dumps(demo_snapshot().to_dict(), indent=2) + "\n", encoding="utf-8"
        )
    if arguments.check:
        if dictionary_path.read_text(encoding="utf-8") != column_dictionary():
            raise SystemExit("Metadata physical dictionary is not synchronized with migrations")
        snapshot = ReleaseSnapshot.from_dict(json.loads(demo_path.read_text(encoding="utf-8")))
        snapshot.validate(FUNCTION_SCHEMAS)
        if len(snapshot.tasks) != 29 or len(snapshot.datasets) != 57:
            raise SystemExit("Demo must contain 28 source/Bronze mappings plus Patient-only Silver")
        if {t.workflow for t in snapshot.tasks} != {
            "clarity_bronze",
            "caboodle_bronze",
            "patient_silver",
        }:
            raise SystemExit("Demo requires exactly three logical workflows")
        print(f"Metadata SQL dictionary and complete demo snapshot valid: {snapshot.digest}")


if __name__ == "__main__":
    main()
