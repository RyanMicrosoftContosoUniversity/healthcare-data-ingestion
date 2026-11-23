"""Executable, versioned mappings from synthetic clinical records to approved SQL models."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from healthcare_ingestion.source_contracts import validate_source_contract

MAPPING_VERSION = "1.1.0"
MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
DIMENSIONS = {
    "DimPatient": ("Patient", "PatientID", "PatientKey"),
    "DimProvider": ("Provider", "ProviderID", "ProviderKey"),
    "DimDepartment": ("Department", "DepartmentID", "DepartmentKey"),
    "DimCoverage": ("Coverage", "CoverageID", "CoverageKey"),
}
CATALOGS = {
    "DimDiagnosis": ("Diagnosis", "Diagnosis", "DiagnosisKey"),
    "DimProcedure": ("Procedure", "Procedure", "ProcedureKey"),
    "DimMedication": ("MedicationOrder", "Medication", "MedicationKey"),
}
FACTS = {
    "FactEncounter": ("Encounter", "EncounterID", "EncounterKey", "ArrivalAtUtc"),
    "FactDiagnosis": ("Diagnosis", "DiagnosisID", "DiagnosisFactKey", "DiagnosedAtUtc"),
    "FactProcedure": ("Procedure", "ProcedureID", "ProcedureFactKey", "PerformedAtUtc"),
    "FactMedicationOrder": (
        "MedicationOrder",
        "MedicationOrderID",
        "MedicationOrderKey",
        "OrderedAtUtc",
    ),
    "FactMedicationAdministration": (
        "MedicationAdministration",
        "MedicationAdministrationID",
        "MedicationAdministrationKey",
        "AdministeredAtUtc",
    ),
    "FactLabResult": ("LaboratoryResult", "LaboratoryResultID", "LabResultKey", "ResultedAtUtc"),
    "FactAppointment": ("Appointment", "AppointmentID", "AppointmentKey", "ScheduledStartAtUtc"),
}
DATE_FIELDS = {
    "ArrivalDateKey": "ArrivalAtUtc",
    "DischargeDateKey": "DischargeAtUtc",
    "DiagnosisDateKey": "DiagnosedAtUtc",
    "OrderedDateKey": "OrderedAtUtc",
    "PerformedDateKey": "PerformedAtUtc",
    "AdministrationDateKey": "AdministeredAtUtc",
    "RecordedDateKey": "RecordedAtUtc",
    "ResultDateKey": "ResultedAtUtc",
    "ScheduledDateKey": "ScheduledStartAtUtc",
}


def stable_id(namespace: str, reference: str) -> int:
    """Use positive signed bigint keys, independent of resource ordering and source loads."""
    value = hashlib.sha256(f"healthcare-demo-v1|{namespace}|{reference}".encode()).digest()
    return int.from_bytes(value[:8], "big") & ((1 << 63) - 1) or 1


def sql_timestamp(value: str | datetime) -> str:
    """Retain all seven datetime2 digits; Python datetime alone cannot do this."""
    text = value.isoformat() if isinstance(value, datetime) else value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,7}))?(?:\+00:00)?", text)
    if not match:
        raise ValueError("Timestamps must be ISO UTC with at most seven fractional digits.")
    datetime.fromisoformat(match[1])
    return match[1] + "." + (match[2] or "").ljust(7, "0")


def mapping_document(contracts: list[dict]) -> dict:
    """Create reviewable column rules; any new unsupported column fails immediately."""
    document = {
        "mapping_version": MAPPING_VERSION,
        "input": "synthetic-clinical-v1",
        "policies": {
            "missing_required_clinical": "reject",
            "missing_optional_clinical": "explicit-null",
            "unknown_resource": "reject",
            "history": "baseline plus explicitly recorded changes; no inferred prior versions",
            "supplemental": "synthetic_fhir.py and synthetic_population.py named rules",
            "caboodle_vitals": "retained in population; no approved Caboodle vital fact",
            "decimal_rounding": "ROUND_HALF_UP to approved SQL scale; raw FHIR remains exact",
        },
        "sources": {},
    }
    for contract in contracts:
        validate_source_contract(contract)
        tables = {}
        for table in contract["tables"]:
            name = table["name"]
            if contract["source_system"] == "Clarity":
                rules = {c["name"]: {"op": "field", "field": c["name"]} for c in table["columns"]}
                source = name
            else:
                source = (
                    DIMENSIONS.get(name) or CATALOGS.get(name) or FACTS.get(name) or ("Calendar",)
                )[0]
                rules = {}
                for c in table["columns"]:
                    column = c["name"]
                    if column in DATE_FIELDS:
                        rule = {"op": "datekey", "field": DATE_FIELDS[column]}
                    elif column == "LengthOfStayMinutes":
                        rule = {"op": "minutes", "start": "ArrivalAtUtc", "end": "DischargeAtUtc"}
                    elif column == "ScheduledDurationMinutes":
                        rule = {
                            "op": "minutes",
                            "start": "ScheduledStartAtUtc",
                            "end": "ScheduledEndAtUtc",
                        }
                    elif column.endswith("Count"):
                        rule = {"op": "constant", "value": 1}
                    else:
                        rule = {"op": "field", "field": column}
                    rules[column] = rule
            for column in table["columns"]:
                if column["sql_type"].lower().startswith("decimal") and (
                    rules[column["name"]]["op"] == "field"
                ):
                    rules[column["name"]] = {
                        "op": "decimal",
                        "field": column["name"],
                        "scale": int(re.findall(r"\d+", column["sql_type"])[1]),
                        "rounding": "ROUND_HALF_UP",
                    }
            tables[name] = {"input_table": source, "columns": rules}
        document["sources"][contract["source_system"]] = {
            "contract_sha256": contract_digest(contract),
            "tables": tables,
        }
    return document


def contract_digest(contract: dict) -> str:
    return hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()


def validate_mapping(document: dict, contract: dict) -> None:
    validate_source_contract(contract)
    if document.get("mapping_version") != MAPPING_VERSION:
        raise ValueError("Unsupported executable mapping version.")
    source = document["sources"][contract["source_system"]]
    if source.get("contract_sha256") != contract_digest(contract):
        raise ValueError("Mapping contract fingerprint does not match the approved model.")
    expected = {t["name"]: t for t in contract["tables"]}
    if set(source["tables"]) != set(expected):
        raise ValueError("Mapping must cover every approved table, with no extra tables.")
    for name, table in expected.items():
        definition = source["tables"][name]
        expected_input = (
            name
            if contract["source_system"] == "Clarity"
            else (
                (DIMENSIONS.get(name) or CATALOGS.get(name) or FACTS.get(name) or ("Calendar",))[0]
            )
        )
        if definition["input_table"] != expected_input:
            raise ValueError(f"{name}: unsupported input-table binding.")
        rules = definition["columns"]
        if set(rules) != {c["name"] for c in table["columns"]}:
            raise ValueError(f"{name}: mapping must cover every column exactly.")
        for column, rule in rules.items():
            op = rule.get("op")
            if op not in {"field", "datekey", "minutes", "constant", "decimal"}:
                raise ValueError(f"{name}: unsupported mapping operation.")
            required = (
                {"field"}
                if op in {"field", "datekey", "decimal"}
                else ({"start", "end"} if op == "minutes" else {"value"})
            )
            if not required <= rule.keys():
                raise ValueError(f"{name}: incomplete mapping rule.")
            if op == "decimal":
                sql_type = next(c["sql_type"] for c in table["columns"] if c["name"] == column)
                if not sql_type.lower().startswith("decimal") or (
                    rule.get("scale") != int(re.findall(r"\d+", sql_type)[1])
                    or rule.get("rounding") != "ROUND_HALF_UP"
                ):
                    raise ValueError(f"{name}: decimal rule must match the approved scale.")


def load_mapping(path: Path, contract: dict) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    validate_mapping(document, contract)
    return document


def normalize_row(row: dict, table: dict) -> dict:
    if set(row) != {c["name"] for c in table["columns"]}:
        raise ValueError(f"{table['name']}: row does not match the approved column set.")
    result = {}
    for column in table["columns"]:
        name, kind, value = column["name"], column["sql_type"].lower(), row[column["name"]]
        if value is None:
            if not column["nullable"]:
                raise ValueError(f"{table['name']}.{name}: required value absent.")
        elif kind.startswith("decimal"):
            precision, scale = map(int, re.findall(r"\d+", kind))
            if isinstance(value, float):
                raise ValueError(f"{table['name']}.{name}: binary float input rejected.")
            value = Decimal(str(value))
            quantum = Decimal(1).scaleb(-scale)
            if not value.is_finite() or value != value.quantize(quantum):
                raise ValueError(f"{table['name']}.{name}: decimal precision loss rejected.")
            if abs(value) >= Decimal(10) ** (precision - scale):
                raise ValueError(f"{table['name']}.{name}: decimal overflow.")
            value = value.quantize(quantum)
        elif kind.startswith("datetime2"):
            value = sql_timestamp(value)
        elif kind == "date":
            value = date.fromisoformat(str(value)).isoformat()
        elif kind in {"bigint", "int", "smallint", "tinyint", "bit"}:
            if not isinstance(value, int):
                raise ValueError(f"{table['name']}.{name}: integer required.")
            bounds = {
                "bigint": (-(2**63), 2**63 - 1),
                "int": (-(2**31), 2**31 - 1),
                "smallint": (-32768, 32767),
                "tinyint": (0, 255),
                "bit": (0, 1),
            }
            if not bounds[kind][0] <= value <= bounds[kind][1]:
                raise ValueError(f"{table['name']}.{name}: integer overflow.")
        elif kind == "uniqueidentifier":
            import uuid

            value = str(uuid.UUID(str(value)))
        else:
            if not isinstance(value, str):
                raise ValueError(f"{table['name']}.{name}: text required.")
            size = re.search(r"\((\d+)\)", kind)
            length = (
                len(value.encode("utf-16-le")) // 2
                if kind.startswith("n")
                else len(value.encode("ascii"))
            )
            if size and length > int(size[1]):
                raise ValueError(f"{table['name']}.{name}: text truncation rejected.")
        result[name] = value
    return result


def _evaluate(rule: dict, context: dict):
    op = rule["op"]
    if op == "constant":
        return rule["value"]
    if op == "decimal":
        value = context[rule["field"]]
        if value is None:
            return None
        if isinstance(value, float):
            raise ValueError("Binary float decimal mapping input rejected.")
        return Decimal(str(value)).quantize(
            Decimal(1).scaleb(-rule["scale"]),
            rounding=ROUND_HALF_UP,
        )
    if op in {"field", "datekey"}:
        value = context[rule["field"]]  # Missing is an error, not implicit NULL.
        return int(value[:10].replace("-", "")) if op == "datekey" and value else value
    start, end = context[rule["start"]], context[rule["end"]]
    if start is None or end is None:
        return None

    # Integer ticks preserve datetime2(7) precision before the approved scale-2 measure.
    def ticks(text):
        base, fraction = sql_timestamp(text).split(".")
        dt = datetime.fromisoformat(base)
        return (
            dt.toordinal() * 86400 + dt.hour * 3600 + dt.minute * 60 + dt.second
        ) * 10_000_000 + int(fraction)

    return (Decimal(ticks(end) - ticks(start)) / Decimal(600_000_000)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def project_source(population: dict, contract: dict, mapping: dict) -> dict[str, list[dict]]:
    """Project directly from the shared clinical archive, never from another SQL source."""
    validate_mapping(mapping, contract)
    contexts = (
        population["tables"]
        if contract["source_system"] == "Clarity"
        else (_caboodle_contexts(population))
    )
    output = {}
    for table in contract["tables"]:
        name = table["name"]
        rules = mapping["sources"][contract["source_system"]]["tables"][name]["columns"]
        output[name] = [
            normalize_row({c: _evaluate(r, row) for c, r in rules.items()}, table)
            for row in contexts[name]
        ]
    return output


def _dimension_payload(row: dict) -> dict:
    return {
        k: v
        for k, v in row.items()
        if not k.startswith("_") and k not in {"CreatedAtUtc", "ModifiedAtUtc"}
    }


def _caboodle_contexts(population: dict) -> dict:
    tables, audit = population["tables"], population["publication"]
    result = {}
    indexes = {name: {row[name + "ID"]: row for row in rows} for name, rows in tables.items()}
    origin = {
        "OriginSystem": "Clarity",
        "OriginModifiedAtUtc": audit["at"],
        "IsDeleted": 0,
        "EtlCreatedAtUtc": audit["at"],
        "EtlModifiedAtUtc": audit["at"],
        "EtlBatchID": audit["batch_id"],
    }
    versions = {}
    for dim, (source, identity, key) in DIMENSIONS.items():
        result[dim] = []
        versions[dim] = {}
        for row in tables[source]:
            history = population.get("histories", {}).get(source, {}).get(str(row[identity]))
            history = history or [{"row": row, "from": population["history_start"], "to": None}]
            if history[-1]["to"] is not None or (
                _dimension_payload(history[-1]["row"]) != _dimension_payload(row)
            ):
                raise ValueError(f"{dim}: current row and explicit version history disagree.")
            versions[dim][row[identity]] = []
            for version in history:
                ctx = {
                    **version["row"],
                    **origin,
                    "IsDeleted": version["row"]["IsDeleted"],
                    "OriginModifiedAtUtc": max(
                        version["row"]["ModifiedAtUtc"],
                        version["to"] or version["row"]["ModifiedAtUtc"],
                    ),
                    "Source" + identity: row[identity],
                    key: stable_id(dim, f"{row[identity]}|{version['from']}"),
                    "EffectiveFromUtc": version["from"],
                    "EffectiveToUtc": version["to"],
                    "IsCurrent": int(version["to"] is None),
                }
                if source == "Coverage":
                    ctx["SourcePatientID"] = row["PatientID"]
                result[dim].append(ctx)
                versions[dim][row[identity]].append(ctx)

    def resolve(dim, identity, event):
        if identity is None:
            return None
        matches = [
            v
            for v in versions[dim].get(identity, [])
            if v["EffectiveFromUtc"] <= event
            and (v["EffectiveToUtc"] is None or event < v["EffectiveToUtc"])
        ]
        if len(matches) != 1:
            raise ValueError(f"{dim}: missing or ambiguous event-time dimension version.")
        return matches[0][DIMENSIONS[dim][2]]

    catalog_keys = {}
    for dim, (source, prefix, key) in CATALOGS.items():
        catalog = {}
        for row in population.get("catalogs", {}).get(prefix, []):
            business = (row[prefix + "CodeSystem"], row[prefix + "Code"])
            label = row[prefix + ("Name" if prefix == "Medication" else "Description")]
            catalog[business] = {
                **origin,
                **row,
                key: stable_id(dim, "|".join(business)),
                "_label": label,
            }
        labels = {}
        for row in tables[source]:
            business = (row[prefix + "CodeSystem"], row[prefix + "Code"])
            label = row[prefix + ("Name" if prefix == "Medication" else "Description")]
            if business in labels and labels[business] != label:
                raise ValueError(f"{dim}: conflicting catalog code labels.")
            if business in catalog and catalog[business]["IsDeleted"] and not row["IsDeleted"]:
                raise ValueError(f"{dim}: a catalog in active use cannot be retired.")
            labels[business] = label
            catalog[business] = {
                **row,
                **origin,
                "OriginModifiedAtUtc": max(
                    row["ModifiedAtUtc"],
                    catalog.get(business, {}).get("OriginModifiedAtUtc", row["ModifiedAtUtc"]),
                ),
                key: stable_id(dim, "|".join(business)),
                "_label": label,
            }
        result[dim] = list(catalog.values())
        catalog_keys[dim] = {business: row[key] for business, row in catalog.items()}

    first_day = date.fromisoformat(population["history_start"][:10])
    last_day = date.fromisoformat(population.get("calendar_end", audit["at"][:10]))
    calendar_dates = {
        (first_day + timedelta(days=offset)).isoformat()
        for offset in range((last_day - first_day).days + 1)
    }
    for fact, (source, identity, key, lookup) in FACTS.items():
        result[fact] = []
        for row in tables[source]:
            parent = {}
            if source == "MedicationAdministration":
                parent = indexes["MedicationOrder"][row["MedicationOrderID"]]
            elif source == "LaboratoryResult":
                parent = indexes["LaboratoryOrder"][row["LaboratoryOrderID"]]
            ctx = {**parent, **row}
            encounter = indexes["Encounter"].get(ctx.get("EncounterID"))
            if source not in {"Encounter", "Appointment"}:
                if encounter is None:
                    raise ValueError(f"{source}: missing encounter.")
                ctx = {**encounter, **ctx}
            event = ctx.get(lookup)
            if event is None:
                fallback = {
                    "FactProcedure": "OrderedAtUtc",
                    "FactMedicationAdministration": "RecordedAtUtc",
                    "FactLabResult": "OrderedAtUtc",
                }.get(fact)
                event = ctx.get(fallback)
            if event is None:
                raise ValueError(f"{fact}: event-time lookup absent.")
            ctx.update(
                {
                    **origin,
                    "IsDeleted": int(
                        any(r.get("IsDeleted", 0) for r in (row, parent, encounter or {}))
                    ),
                    "OriginModifiedAtUtc": max(
                        r["ModifiedAtUtc"]
                        for r in (row, parent, encounter or {})
                        if r.get("ModifiedAtUtc")
                    ),
                    key: stable_id(fact, str(row[identity])),
                    "Source" + identity: row[identity],
                    "PatientKey": resolve("DimPatient", ctx["PatientID"], event),
                    "DepartmentKey": resolve("DimDepartment", ctx["DepartmentID"], event),
                }
            )
            if "EncounterID" in ctx:
                ctx["SourceEncounterID"] = ctx["EncounterID"]
            for role in ("Attending", "Diagnosing", "Performing", "Ordering", "Administering", ""):
                field = role + "ProviderID"
                if field in ctx:
                    ctx[role + "ProviderKey"] = resolve("DimProvider", ctx[field], event)
            if source == "Encounter":
                ctx["CoverageKey"] = resolve("DimCoverage", ctx["PrimaryCoverageID"], event)
            if source == "MedicationAdministration":
                ctx["SourceMedicationOrderID"] = row["MedicationOrderID"]
            if source == "LaboratoryResult":
                ctx["SourceLaboratoryOrderID"] = row["LaboratoryOrderID"]
            for dim, (catalog_source, prefix, catalog_key) in CATALOGS.items():
                if source == catalog_source or (
                    source == "MedicationAdministration" and prefix == "Medication"
                ):
                    business = (ctx[prefix + "CodeSystem"], ctx[prefix + "Code"])
                    ctx[catalog_key] = catalog_keys[dim][business]
            for field in DATE_FIELDS.values():
                if ctx.get(field):
                    calendar_dates.add(ctx[field][:10])
            result[fact].append(ctx)
    result["DimDate"] = []
    for text in sorted(calendar_dates):
        day = date.fromisoformat(text)
        result["DimDate"].append(
            {
                "DateKey": int(day.strftime("%Y%m%d")),
                "CalendarDate": text,
                "CalendarYear": day.year,
                "CalendarQuarter": (day.month - 1) // 3 + 1,
                "MonthNumber": day.month,
                "MonthName": MONTH_NAMES[day.month],
                "DayOfMonth": day.day,
                "IsoDayOfWeek": day.isoweekday(),
                "IsWeekend": int(day.isoweekday() > 5),
                **origin,
            }
        )
    return result
