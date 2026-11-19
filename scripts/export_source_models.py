"""Export the approved local design into versioned dictionaries and typed source contracts."""

import argparse
import json
import re
from pathlib import Path

from healthcare_ingestion.source_contracts import validate_source_contract

CLARITY = (
    "Patient Provider Department Encounter Diagnosis Procedure MedicationOrder "
    "MedicationAdministration LaboratoryOrder LaboratoryResult VitalSign Coverage Appointment"
).split()
CABOODLE = (
    "DimPatient DimProvider DimDepartment DimDate DimDiagnosis DimProcedure DimMedication "
    "DimCoverage FactEncounter FactDiagnosis FactProcedure FactMedicationOrder "
    "FactMedicationAdministration FactLabResult FactAppointment"
).split()


def _section(text: str, heading: str, level: int) -> str:
    pattern = rf"^{re.escape('#' * level + ' ' + heading)}\r?\n(.*?)(?=^#{{1,{level}}} |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError(f"Missing section: {heading}")
    return match[1].strip()


def _columns(text: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not cells[0].startswith("`") or not cells[1].startswith("`"):
            continue
        if cells[2] not in {"Yes", "No"}:
            raise ValueError(f"Invalid column nullability: {line}")
        result.append(
            {
                "name": cells[0].strip("`"),
                "sql_type": cells[1].strip("`"),
                "nullable": cells[2] == "Yes",
                "purpose": cells[3],
            }
        )
    return result


def export_models(text: str) -> tuple[dict, dict]:
    """Prepare both exports in memory and validate them before writing any artifacts."""
    clarity = _section(text, "Clarity Operational Model", 4)
    caboodle = _section(text, "Caboodle Analytical Model", 4)
    clarity_shared = _columns(_section(clarity, "Data Dictionary Conventions", 5))
    caboodle_shared = _columns(_section(caboodle, "Analytical Data Dictionary Conventions", 5))
    common = caboodle_shared[:3]
    origin = caboodle_shared[3:6]
    history = caboodle_shared[6:]
    if len(clarity_shared) != 4 or [len(common), len(origin), len(history)] != [3, 3, 3]:
        raise ValueError("Unexpected shared-column conventions; review the exporter before use.")
    fact_shared = _columns(_section(caboodle, "Shared Fact Columns", 5))
    contracts = {}
    documents = {}
    for system, body, names in (("Clarity", clarity, CLARITY), ("Caboodle", caboodle, CABOODLE)):
        tables = []
        for name in names:
            columns = _columns(_section(body, name, 5))
            if not columns:
                raise ValueError(f"{system}.{name} has no declared columns.")
            primary_key = [c["name"] for c in columns if re.search(r"\bPK\b", c["purpose"])]
            if system == "Clarity":
                columns += clarity_shared
            else:
                if name.startswith("Fact"):
                    columns += fact_shared
                columns += common
                if name != "DimDate":
                    columns += origin
                if name in {"DimPatient", "DimProvider", "DimDepartment", "DimCoverage"}:
                    columns += history
            tables.append({"name": name, "primary_key": primary_key, "columns": columns})
        contract = {"schema_version": 1, "source_system": system, "schema": "dbo", "tables": tables}
        validate_source_contract(contract)
        contracts[system] = contract
        documents[system] = (
            f"# {system} Source Data Dictionary\n\n"
            "The user approved this synthetic source model. Column definitions below are "
            "exported from the local design; this is not a proprietary Epic specification.\n\n"
            "> Population decision: generate both sources independently with shared synthetic "
            "identities. Earlier Clarity-to-Caboodle ETL language below is historical mapping "
            "context, not an instruction to build that ETL. Source-to-Bronze reconciliation "
            "is performed independently for each source.\n\n" + body + "\n"
        )
    return contracts, documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    contracts, documents = export_models(args.source_plan.read_text(encoding="utf-8-sig"))
    for system, contract in contracts.items():
        dictionary = root / "docs" / system.lower() / "data-dictionary.md"
        dictionary.parent.mkdir(parents=True, exist_ok=True)
        dictionary.write_text(documents[system], encoding="utf-8")
        target = root / "database" / "schema-contracts" / f"{system.lower()}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        print(f"{system}: {len(contract['tables'])} tables exported.")


if __name__ == "__main__":
    main()
