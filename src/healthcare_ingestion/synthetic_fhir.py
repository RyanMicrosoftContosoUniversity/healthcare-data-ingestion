"""Strict Synthea R4 bundle parsing and explicitly named synthetic supplemental rules.

Raw resources are retained in the durable population. Missing optional values are NULL;
required unsupported clinical representations fail. Supplements are operational fixtures,
not asserted Synthea observations, and are separately recorded in the population manifest.
"""

import copy
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from healthcare_ingestion.source_mapping import sql_timestamp, stable_id

TABLES = (
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
)
SUPPORTED = {
    "Patient",
    "Practitioner",
    "PractitionerRole",
    "Organization",
    "Location",
    "Encounter",
    "Condition",
    "Procedure",
    "MedicationRequest",
    "MedicationAdministration",
    "Medication",
    "Observation",
    "Coverage",
    "Appointment",
    "ServiceRequest",
    "DiagnosticReport",
}
# These have no approved relational grain. They remain in the immutable archive and
# have explicit dispositions, rather than being silently discarded.
ARCHIVE_ONLY = {
    "AllergyIntolerance",
    "CarePlan",
    "CareTeam",
    "Immunization",
    "Device",
    "SupplyDelivery",
    "ImagingStudy",
    "Claim",
    "ExplanationOfBenefit",
    "Provenance",
    "DocumentReference",
}
SYSTEMS = {
    "http://snomed.info/sct": "SNOMED",
    "http://loinc.org": "LOINC",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RXNORM",
    "http://hl7.org/fhir/sid/icd-10-cm": "ICD10CM",
    "http://www.ama-assn.org/go/cpt": "CPT",
    "http://www.ada.org/cdt": "CDT",
    "urn:synthetic": "SYNTHETIC",
}


def _time(value: str) -> str:
    # FHIR permits offsets; normalize them without losing the 7th digit.
    if value.endswith("Z") or value.endswith("+00:00"):
        return sql_timestamp(value)
    import re

    if re.search(r"\.\d{8,}", value):
        raise ValueError("FHIR timestamp precision exceeds the approved datetime2(7) contract.")
    precise = re.search(r"\.(\d{7})(?=[+-]\d\d:\d\d$)", value)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return sql_timestamp(value)
    from datetime import UTC

    canonical = sql_timestamp(dt.astimezone(UTC))
    return canonical[:-1] + precise[1][-1] if precise else canonical


def _name(resource: dict) -> tuple[str, str]:
    name = resource["name"][0]
    if not name.get("given") or not name.get("family"):
        raise ValueError("Patient/Practitioner structured given and family names required.")
    return " ".join(name["given"]), name["family"]


def _code(concept: dict) -> tuple[str, str, str]:
    coding = concept.get("coding", [])
    supported = [c for c in coding if c.get("system") in SYSTEMS and c.get("code")]
    if not supported:
        raise ValueError("Unsupported or absent required clinical coding system.")
    code = supported[0]
    label = code.get("display") or concept.get("text")
    if not label:
        raise ValueError("Required clinical code label absent.")
    return SYSTEMS[code["system"]], str(code["code"]), label


def _quantity(quantity: dict | None):
    if not quantity:
        return None, None
    if quantity.get("comparator"):
        raise ValueError("Comparator quantities need an approved representation.")
    unit = quantity.get("code") or quantity.get("unit")
    if quantity.get("value") is None:
        return None, unit
    if not unit:
        raise ValueError("A known numeric quantity requires a unit.")
    if isinstance(quantity["value"], float):
        raise ValueError("Binary float quantities rejected; parse FHIR JSON using Decimal.")
    return str(Decimal(str(quantity["value"]))), quantity.get("code") or quantity["unit"]


def _observation_value(resource: dict):
    if "valueQuantity" in resource:
        quantity = resource["valueQuantity"]
        if quantity.get("value") is None:
            if resource.get("dataAbsentReason"):
                _, text, _ = _observation_value(
                    {k: v for k, v in resource.items() if k != "valueQuantity"}
                )
                return None, text, quantity.get("code") or quantity.get("unit")
            if resource.get("status") not in {"registered", "preliminary"}:
                raise ValueError(
                    "Final quantitative observations require a value or absence reason."
                )
        numeric, unit = _quantity(resource["valueQuantity"])
        return numeric, None, unit
    if "valueString" in resource:
        return None, resource["valueString"], None
    if "valueCodeableConcept" in resource:
        concept = resource["valueCodeableConcept"]
        text = concept.get("text") or next(
            (c["display"] for c in concept.get("coding", []) if c.get("display")), None
        )
        if text:
            return None, text, None
    if resource.get("dataAbsentReason"):
        reason = resource["dataAbsentReason"]
        text = reason.get("text") or next(
            (c.get("display") or c.get("code") for c in reason.get("coding", [])), None
        )
        return None, f"Absent: {text or 'unknown'}", None
    if resource.get("status") in {"registered", "preliminary", "cancelled"}:
        return None, None, None
    raise ValueError("Unsupported/missing observation value; not silently dropped.")


def parse_bundles(
    bundles: list[dict],
    *,
    history_start: str,
    publication_at: str,
    batch_id: str | None = None,
    coverage_end: str | None = None,
) -> dict:
    """Resolve all FHIR references, preserve IDs, and build a source-neutral population."""
    start, at = sql_timestamp(history_start), sql_timestamp(publication_at)
    covered_end = sql_timestamp(coverage_end or publication_at)
    if not start <= covered_end <= at:
        raise ValueError("Verified source coverage must lie within the generation horizon.")
    resources, aliases = {}, {}
    for bundle in bundles:
        if bundle.get("resourceType") != "Bundle":
            raise ValueError("Only FHIR R4 Bundles are accepted.")
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if not resource or not resource.get("id"):
                raise ValueError("Bundle resource and immutable id are required.")
            kind = resource["resourceType"]
            if kind not in SUPPORTED | ARCHIVE_ONLY:
                raise ValueError(f"Unsupported FHIR resource type: {kind}")
            ref = f"{kind}/{resource['id']}"
            if ref in resources and resources[ref] != resource:
                raise ValueError("Conflicting duplicate FHIR resource identity.")
            resources[ref] = copy.deepcopy(resource)
            for alias in (ref, entry.get("fullUrl")):
                if alias:
                    if alias in aliases and aliases[alias] != ref:
                        raise ValueError("Ambiguous FHIR reference alias.")
                    aliases[alias] = ref
    resources = dict(sorted(resources.items()))
    tables = {name: [] for name in TABLES}
    supplements = []
    dispositions = {
        ref: "archive-only:no-approved-grain"
        for ref in resources
        if resources[ref]["resourceType"] in ARCHIVE_ONLY
    }

    def resolve(value, kinds):
        reference = value.get("reference") if isinstance(value, dict) else value
        ref = aliases.get(reference)
        if ref is None and reference and "?identifier=" in reference:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(reference)
            kind = parsed.path.rsplit("/", 1)[-1]
            query = parse_qs(parsed.query, keep_blank_values=True)
            terms = query.get("identifier", [])
            if set(query) != {"identifier"} or len(terms) != 1:
                raise ValueError("Ambiguous conditional FHIR reference.")
            identifier = terms[0].split("|", 1)
            if not all(identifier):
                raise ValueError("Conditional FHIR identifiers cannot be empty.")
            matches = [
                candidate
                for candidate, target in resources.items()
                if target["resourceType"] == kind
                and any(
                    item.get("value") == identifier[-1]
                    and (len(identifier) == 1 or item.get("system") == identifier[0])
                    for item in target.get("identifier", [])
                )
            ]
            if len(matches) != 1:
                raise ValueError("Conditional FHIR reference has no unique target.")
            ref = matches[0]
        if ref is None and reference:
            tail = "/".join(reference.split("/")[-2:])
            ref = aliases.get(tail)
        if ref is None or resources[ref]["resourceType"] not in kinds:
            raise ValueError("Unresolved or incompatible FHIR reference.")
        return ref

    def identity(kind, ref):
        return stable_id(kind, ref)

    def emit(table, ref, **fields):
        if any(field not in fields for field in (table + "ID",)):
            fields[table + "ID"] = identity(table, ref)
        row = {
            **fields,
            "CreatedAtUtc": at,
            "ModifiedAtUtc": at,
            "IsDeleted": 0,
            "DeletedAtUtc": None,
            "_origin_ref": ref,
        }
        tables[table].append(row)
        if ref in resources:
            dispositions[ref] = "mapped:" + table
        elif ref.split("#component-")[0] in resources:
            dispositions[ref.split("#component-")[0]] = "mapped:Observation-components"
        else:
            supplements.append({"rule": ref.split(":")[0], "reference": ref, "table": table})
        return row

    provider_ref = "supplemental-provider:unassigned"
    provider_id = identity("Provider", provider_ref)
    emit(
        "Provider",
        provider_ref,
        ProviderCode=f"PRV{provider_id}",
        DisplayName="Synthetic unassigned clinician",
        ProviderTypeCode="UNKNOWN",
        SpecialtyCode=None,
        IsActive=1,
    )
    department_ref = "supplemental-department:default"
    department_id = identity("Department", department_ref)
    emit(
        "Department",
        department_ref,
        DepartmentCode=f"DEP{department_id}",
        DepartmentName="Synthetic outpatient department",
        FacilityCode="SYNTHETIC",
        DepartmentTypeCode="outpatient",
        IsActive=1,
    )
    for ref, resource in resources.items():
        kind = resource["resourceType"]
        if kind == "Patient":
            first, last = _name(resource)
            address = (resource.get("address") or [{}])[0]
            patient_id = identity("Patient", ref)
            emit(
                "Patient",
                ref,
                MedicalRecordNumber=f"MRN{patient_id}",
                FirstName=first,
                LastName=last,
                BirthDate=resource["birthDate"],
                AdministrativeSexCode=resource.get("gender", "unknown"),
                City=address.get("city"),
                StateCode=address.get("state"),
                PostalCode=address.get("postalCode"),
                DeathDate=(resource.get("deceasedDateTime") or "")[:10] or None,
                PatientStatus="inactive"
                if resource.get("deceasedBoolean") or resource.get("deceasedDateTime")
                else "active",
            )
        elif kind == "Practitioner":
            first, last = _name(resource)
            key = identity("Provider", ref)
            emit(
                "Provider",
                ref,
                ProviderCode=f"PRV{key}",
                DisplayName=f"{first} {last}",
                ProviderTypeCode="CLINICIAN",
                SpecialtyCode=None,
                IsActive=int(resource.get("active", True)),
            )
        elif kind in {"Organization", "Location"}:
            key = identity("Department", ref)
            display = resource.get("name") or resource.get("description")
            if not display:
                display = f"Synthetic unknown care location {key}"
                supplements.append(
                    {
                        "rule": "unnamed-care-location",
                        "reference": ref,
                        "table": "Department",
                    }
                )
            emit(
                "Department",
                ref,
                DepartmentCode=f"DEP{key}",
                DepartmentName=display,
                FacilityCode=f"FAC{key}",
                DepartmentTypeCode="unknown",
                IsActive=int(resource.get("active", True)),
            )
        elif kind in {"Medication", "DiagnosticReport", "ServiceRequest", "PractitionerRole"}:
            dispositions[ref] = "reference-context:resolved-or-archived"

    def provider(resource, field):
        value = resource.get(field)
        if not value:
            return provider_id
        if isinstance(value, list):
            value = value[0]
        value = value.get("actor") or value.get("individual") or value
        ref = resolve(value, {"Practitioner", "PractitionerRole"})
        if resources[ref]["resourceType"] == "PractitionerRole":
            ref = resolve(resources[ref]["practitioner"], {"Practitioner"})
        return identity("Provider", ref)

    def department(resource):
        if resource.get("location"):
            value = resource["location"][0]["location"]
            return identity("Department", resolve(value, {"Location"}))
        if resource.get("serviceProvider"):
            return identity("Department", resolve(resource["serviceProvider"], {"Organization"}))
        return department_id

    encounters = {}
    for ref, resource in resources.items():
        if resource["resourceType"] != "Encounter":
            continue
        patient_ref = resolve(resource["subject"], {"Patient"})
        arrival = _time(resource["period"]["start"])
        if not start <= arrival <= covered_end:
            dispositions[ref] = "archive-only:outside-retention-window"
            continue
        discharge = _time(resource["period"]["end"]) if resource["period"].get("end") else None
        encounters[ref] = emit(
            "Encounter",
            ref,
            EncounterNumber=f"ENC{identity('Encounter', ref)}",
            PatientID=identity("Patient", patient_ref),
            DepartmentID=department(resource),
            AttendingProviderID=provider(resource, "participant"),
            PrimaryCoverageID=None,
            EncounterTypeCode=resource.get("class", {}).get("code", "unknown"),
            EncounterStatus=resource["status"],
            ArrivalAtUtc=arrival,
            DischargeAtUtc=discharge,
            DischargeDispositionCode=None,
        )
    coverage_by_patient = defaultdict(list)
    for ref, resource in resources.items():
        if resource["resourceType"] != "Coverage":
            continue
        patient_ref = resolve(resource["beneficiary"], {"Patient"})
        payer = (resource.get("payor") or [{"display": "Synthetic unknown payer"}])[0]
        period = resource.get("period", {})
        enrollment = emit(
            "Coverage",
            ref,
            PatientID=identity("Patient", patient_ref),
            CoverageNumber=f"COV{identity('Coverage', ref)}",
            PayerCode="SYNTHETIC",
            PayerName=payer.get("display", "Synthetic unknown payer"),
            PlanCode="SYNTHETIC",
            PlanName="Synthetic supplemental plan",
            CoverageTypeCode="unknown",
            EffectiveDate=period.get("start", start[:10])[:10],
            TerminationDate=period.get("end", "")[:10] or None,
            CoverageStatus=resource["status"],
        )
        coverage_by_patient[enrollment["PatientID"]].append(enrollment)
        supplements.append({"rule": "coverage-plan-unknown", "reference": ref, "table": "Coverage"})
    # Exactly one modeled enrollment per otherwise uninsured synthetic patient; no
    # arbitrary patient-level join to real or multiple coverage periods.
    for patient in tables["Patient"]:
        key = patient["PatientID"]
        if coverage_by_patient[key]:
            continue
        ref = f"supplemental-coverage:{key}"
        enrollment = emit(
            "Coverage",
            ref,
            PatientID=key,
            CoverageNumber=f"COV{identity('Coverage', ref)}",
            PayerCode="SYNTHETIC",
            PayerName="Synthetic demonstration payer",
            PlanCode="DEMO",
            PlanName="Synthetic demonstration plan",
            CoverageTypeCode="synthetic",
            EffectiveDate=start[:10],
            TerminationDate=None,
            CoverageStatus="active",
        )
        coverage_by_patient[key].append(enrollment)
    for encounter in encounters.values():
        candidates = [
            cov
            for cov in coverage_by_patient[encounter["PatientID"]]
            if cov["EffectiveDate"] <= encounter["ArrivalAtUtc"][:10]
            and (
                cov["TerminationDate"] is None
                or encounter["ArrivalAtUtc"][:10] <= cov["TerminationDate"]
            )
        ]
        if len(candidates) == 1:
            encounter["PrimaryCoverageID"] = candidates[0]["CoverageID"]

    def linked_encounter(resource):
        reference = resource.get("encounter") or resource.get("context")
        if reference is None:
            raise ValueError("Clinical resource requires an explicit encounter reference.")
        ref = resolve(reference, {"Encounter"})
        if ref not in encounters:
            return None
        encounter = encounters[ref]
        subject = resource.get("subject") or resource.get("patient")
        if subject and identity("Patient", resolve(subject, {"Patient"})) != encounter["PatientID"]:
            raise ValueError("FHIR clinical patient differs from encounter patient.")
        return encounter

    lab_orders = {}
    for ref, resource in resources.items():
        if resource["resourceType"] == "ServiceRequest":
            encounter = linked_encounter(resource)
            if encounter is None:
                dispositions[ref] = "archive-only:encounter-outside-retention-window"
                continue
            _, code, label = _code(resource["code"])
            lab_orders[ref] = emit(
                "LaboratoryOrder",
                ref,
                EncounterID=encounter["EncounterID"],
                OrderingProviderID=provider(resource, "requester"),
                OrderNumber=f"LAB{identity('LaboratoryOrder', ref)}",
                TestCode=code,
                TestName=label,
                SpecimenTypeCode=None,
                OrderedAtUtc=_time(resource.get("authoredOn") or encounter["ArrivalAtUtc"]),
                CollectedAtUtc=None,
                OrderStatus=resource["status"],
            )
        elif resource["resourceType"] == "DiagnosticReport":
            for result in resource.get("result", []):
                resolve(result, {"Observation"})
            if resource.get("encounter"):
                linked_encounter(resource)
            dispositions[ref] = "reference-context:DiagnosticReport-observations-retained"

    sequences = defaultdict(int)
    med_orders = {}
    for ref, resource in resources.items():
        kind = resource["resourceType"]
        if kind not in {"Condition", "Procedure", "MedicationRequest", "Observation"}:
            continue
        encounter = linked_encounter(resource)
        if encounter is None:
            dispositions[ref] = "archive-only:encounter-outside-retention-window"
            continue
        common = {"EncounterID": encounter["EncounterID"]}
        event = encounter["ArrivalAtUtc"]
        if kind == "Condition":
            system, code, label = _code(resource["code"])
            event = _time(resource.get("recordedDate") or resource.get("onsetDateTime") or event)
            if event < start:
                event = encounter["ArrivalAtUtc"]
                supplements.append(
                    {
                        "rule": "diagnosis-assignment-at-retained-encounter",
                        "reference": ref,
                        "table": "Diagnosis",
                    }
                )
            sequences[encounter["EncounterID"]] += 1
            sequence = sequences[encounter["EncounterID"]]
            supplements.append(
                {
                    "rule": "deterministic-diagnosis-assignment-order",
                    "reference": ref,
                    "table": "Diagnosis",
                }
            )
            emit(
                "Diagnosis",
                ref,
                **common,
                DiagnosingProviderID=provider(resource, "asserter"),
                DiagnosisCodeSystem=system,
                DiagnosisCode=code,
                DiagnosisDescription=label,
                DiagnosisSequence=sequence,
                IsPrimary=int(sequence == 1),
                DiagnosedAtUtc=event,
                DiagnosisStatus=(
                    resource.get("clinicalStatus", {}).get("coding") or [{"code": "active"}]
                )[0]["code"],
            )
        elif kind == "Procedure":
            system, code, label = _code(resource["code"])
            performed = resource.get("performedDateTime") or (
                resource.get("performedPeriod", {}).get("start")
            )
            supplements.append(
                {
                    "rule": "procedure-order-at-encounter",
                    "reference": ref,
                    "table": "Procedure",
                }
            )
            emit(
                "Procedure",
                ref,
                **common,
                PerformingProviderID=provider(resource, "performer"),
                ProcedureCodeSystem=system,
                ProcedureCode=code,
                ProcedureDescription=label,
                OrderedAtUtc=event,
                PerformedAtUtc=_time(performed) if performed else None,
                ProcedureStatus=resource["status"],
            )
        elif kind == "MedicationRequest":
            concept = resource.get("medicationCodeableConcept")
            if concept is None:
                medication_ref = resolve(resource["medicationReference"], {"Medication"})
                concept = resources[medication_ref]["code"]
                dispositions[medication_ref] = "mapped:MedicationOrder-reference"
            system, code, label = _code(concept)
            dosage = (resource.get("dosageInstruction") or [{}])[0]
            quantities = dosage.get("doseAndRate") or [{}]
            if len(quantities) > 1 or len(resource.get("dosageInstruction", [])) > 1:
                raise ValueError("Multi-dose medication instructions need an approved rule.")
            quantity = quantities[0].get("doseQuantity")
            if (
                quantity
                and quantity.get("value") is not None
                and not (quantity.get("unit") or quantity.get("code") or quantity.get("comparator"))
            ):
                dose, unit = None, None
                supplements.append(
                    {
                        "rule": "unitless-dose-retained-in-fhir-archive",
                        "reference": ref,
                        "table": "MedicationOrder",
                    }
                )
            else:
                dose, unit = _quantity(quantity)
            if quantities[0].get("doseRange") or dosage.get("timing", {}).get("repeat"):
                # The approved FrequencyCode is a classification, not a complete regimen.
                supplements.append(
                    {
                        "rule": "regimen-retained-in-fhir-archive",
                        "reference": ref,
                        "table": "MedicationOrder",
                    }
                )
            authored = _time(resource.get("authoredOn") or event)
            if not resource.get("authoredOn"):
                supplements.append(
                    {
                        "rule": "medication-order-at-encounter",
                        "reference": ref,
                        "table": "MedicationOrder",
                    }
                )
            bounds = dosage.get("timing", {}).get("repeat", {}).get("boundsPeriod", {})
            route = dosage.get("route", {}).get("coding", [])
            med_orders[ref] = emit(
                "MedicationOrder",
                ref,
                **common,
                OrderingProviderID=provider(resource, "requester"),
                MedicationCodeSystem=system,
                MedicationCode=code,
                MedicationName=label,
                OrderedDose=dose,
                DoseUnit=unit,
                RouteCode=str(route[0]["code"]) if route else None,
                FrequencyCode=None,
                OrderedAtUtc=authored,
                StartAtUtc=_time(bounds["start"]) if bounds.get("start") else None,
                EndAtUtc=_time(bounds["end"]) if bounds.get("end") else None,
                OrderStatus=resource["status"],
            )
        elif kind == "Observation":
            categories = {
                c.get("code")
                for concept in resource.get("category", [])
                for c in concept.get("coding", [])
            }
            parts = resource.get("component") or [resource]
            if resource.get("component") and any(k.startswith("value") for k in resource):
                raise ValueError("Mixed observation parent/component values need an approved rule.")
            event = _time(
                resource.get("effectiveDateTime")
                or resource.get("effectivePeriod", {}).get("start")
                or event
            )
            for index, part in enumerate(parts):
                system, code, label = _code(part["code"])
                numeric, text, unit = _observation_value({**resource, **part, "component": []})
                component_ref = ref if len(parts) == 1 else f"{ref}#component-{index}"
                if "vital-signs" in categories:
                    emit(
                        "VitalSign",
                        component_ref,
                        **common,
                        RecordingProviderID=provider(resource, "performer"),
                        VitalTypeCode=code,
                        NumericValue=numeric,
                        TextValue=text,
                        ValueUnit=unit,
                        MeasuredAtUtc=event,
                        ObservationStatus=resource["status"],
                    )
                elif "laboratory" in categories:
                    based_on = resource.get("basedOn", [])
                    if len(based_on) > 1:
                        raise ValueError("Observation requires at most one explicit lab order.")
                    order_ref = (
                        resolve(based_on[0], {"ServiceRequest"})
                        if based_on
                        else (f"supplemental-lab-order:{ref}")
                    )
                    if based_on:
                        order = lab_orders.get(order_ref)
                        if order is None or order["EncounterID"] != encounter["EncounterID"]:
                            raise ValueError("Observation lab order/encounter mismatch.")
                    elif index == 0:
                        emit(
                            "LaboratoryOrder",
                            order_ref,
                            **common,
                            OrderingProviderID=provider(resource, "performer"),
                            OrderNumber=f"LAB{identity('LaboratoryOrder', order_ref)}",
                            TestCode=code,
                            TestName=label,
                            SpecimenTypeCode=None,
                            OrderedAtUtc=event,
                            CollectedAtUtc=None,
                            OrderStatus="ordered"
                            if resource["status"] == "registered"
                            else ("completed"),
                        )
                    bounds = (part.get("referenceRange") or [{}])[0]
                    low, low_unit = _quantity(bounds.get("low"))
                    high, high_unit = _quantity(bounds.get("high"))
                    if unit is None:
                        unit = low_unit or high_unit
                    if any(u and u != unit for u in (low_unit, high_unit)):
                        raise ValueError("Observation/reference range units differ.")
                    interpretation = (part.get("interpretation") or [{}])[0].get("coding", [])
                    emit(
                        "LaboratoryResult",
                        component_ref,
                        LaboratoryOrderID=identity("LaboratoryOrder", order_ref),
                        ComponentCode=code,
                        ComponentName=label,
                        NumericValue=numeric,
                        TextValue=text,
                        ResultUnit=unit,
                        ReferenceLow=low,
                        ReferenceHigh=high,
                        AbnormalFlag=interpretation[0].get("code") if interpretation else None,
                        ResultedAtUtc=event
                        if resource["status"] not in {"registered", "cancelled"}
                        else None,
                        ResultStatus=resource["status"],
                    )
                else:
                    dispositions[ref] = "archive-only:observation-category-no-approved-grain"
            if resource.get("component"):
                dispositions[ref] = "mapped:Observation-components"

    for ref, resource in resources.items():
        if resource["resourceType"] == "MedicationAdministration":
            encounter = linked_encounter(resource)
            if encounter is None:
                dispositions[ref] = "archive-only:encounter-outside-retention-window"
                continue
            if resource.get("request"):
                order_ref = resolve(resource["request"], {"MedicationRequest"})
            else:
                concept = resource.get("medicationCodeableConcept")
                if concept is None:
                    medication_ref = resolve(resource["medicationReference"], {"Medication"})
                    concept = resources[medication_ref]["code"]
                system, code, label = _code(concept)
                given = resource.get("effectiveDateTime") or resource.get(
                    "effectivePeriod", {}
                ).get("start")
                if given is None:
                    raise ValueError("Unlinked medication administrations require an event time.")
                order_ref = f"supplemental-order:{ref}"
                med_orders[order_ref] = emit(
                    "MedicationOrder",
                    order_ref,
                    EncounterID=encounter["EncounterID"],
                    OrderingProviderID=provider_id,
                    MedicationCodeSystem=system,
                    MedicationCode=code,
                    MedicationName=label,
                    OrderedDose=None,
                    DoseUnit=None,
                    RouteCode=None,
                    FrequencyCode=None,
                    OrderedAtUtc=_time(given),
                    StartAtUtc=None,
                    EndAtUtc=None,
                    OrderStatus="completed",
                )
                supplements.append(
                    {
                        "rule": "administration-order-not-provided",
                        "reference": ref,
                        "table": "MedicationOrder",
                    }
                )
            order = med_orders.get(order_ref)
            if order is None:
                dispositions[ref] = "archive-only:order-outside-retention-window"
                continue
            if resource.get("subject"):
                if encounter["EncounterID"] != order["EncounterID"]:
                    raise ValueError("Medication administration/order encounter mismatch.")
            dosage = resource.get("dosage", {})
            quantity = dosage.get("dose")
            if (
                quantity
                and quantity.get("value") is not None
                and not (quantity.get("unit") or quantity.get("code") or quantity.get("comparator"))
            ):
                dose, unit = None, None
                supplements.append(
                    {
                        "rule": "unitless-dose-retained-in-fhir-archive",
                        "reference": ref,
                        "table": "MedicationAdministration",
                    }
                )
            else:
                dose, unit = _quantity(quantity)
            given = resource.get("effectiveDateTime") or resource.get("effectivePeriod", {}).get(
                "start"
            )
            event = _time(given) if given else order["OrderedAtUtc"]
            supplements.append(
                {
                    "rule": "administration-documentation-at-event",
                    "reference": ref,
                    "table": "MedicationAdministration",
                }
            )
            emit(
                "MedicationAdministration",
                ref,
                MedicationOrderID=order["MedicationOrderID"],
                AdministeringProviderID=provider(resource, "performer"),
                ScheduledAtUtc=None,
                RecordedAtUtc=event,
                AdministeredAtUtc=event if resource["status"] == "completed" else None,
                AdministeredDose=dose,
                DoseUnit=unit,
                AdministrationStatus=resource["status"],
                NotGivenReason=resource.get("statusReason", [{}])[0].get("text"),
            )
        elif resource["resourceType"] == "Appointment":
            participants = resource["participant"]
            patient_refs = []
            clinician_refs = []
            for participant in participants:
                actor = resolve(participant["actor"], {"Patient", "Practitioner", "Location"})
                if resources[actor]["resourceType"] == "Patient":
                    patient_refs.append(actor)
                elif resources[actor]["resourceType"] == "Practitioner":
                    clinician_refs.append(actor)
            if len(patient_refs) != 1:
                raise ValueError("Appointment requires exactly one resolved patient.")
            if len(clinician_refs) > 1:
                raise ValueError("Multiple scheduled providers require an approved mapping.")
            patient_ref = patient_refs[0]
            emit(
                "Appointment",
                ref,
                AppointmentNumber=f"APT{identity('Appointment', ref)}",
                PatientID=identity("Patient", patient_ref),
                ProviderID=identity("Provider", clinician_refs[0]) if clinician_refs else None,
                DepartmentID=department_id,
                EncounterID=None,
                ScheduledStartAtUtc=_time(resource["start"]),
                ScheduledEndAtUtc=_time(resource["end"]),
                AppointmentTypeCode="unknown",
                AppointmentStatus=resource["status"],
                CanceledAtUtc=None,
                CancellationReason=None,
            )
    # Synthea normally has no scheduling resource or administration event. Add modeled
    # completed scheduling rows and one clearly synthetic administration per numeric order.
    for ref, encounter in encounters.items():
        emit(
            "Appointment",
            f"supplemental-appointment:{ref}",
            AppointmentNumber=f"APT{identity('Appointment', ref)}",
            PatientID=encounter["PatientID"],
            ProviderID=encounter["AttendingProviderID"],
            DepartmentID=encounter["DepartmentID"],
            EncounterID=encounter["EncounterID"],
            ScheduledStartAtUtc=encounter["ArrivalAtUtc"],
            ScheduledEndAtUtc=encounter["DischargeAtUtc"]
            or sql_timestamp(
                datetime.fromisoformat(encounter["ArrivalAtUtc"][:26]) + timedelta(minutes=30)
            ),
            AppointmentTypeCode=encounter["EncounterTypeCode"],
            AppointmentStatus="completed",
            CanceledAtUtc=None,
            CancellationReason=None,
        )
    administered_orders = {r["MedicationOrderID"] for r in tables["MedicationAdministration"]}
    for ref, order in med_orders.items():
        if order["MedicationOrderID"] in administered_orders or order["OrderedDose"] is None:
            continue
        emit(
            "MedicationAdministration",
            f"supplemental-administration:{ref}",
            MedicationOrderID=order["MedicationOrderID"],
            AdministeringProviderID=order["OrderingProviderID"],
            ScheduledAtUtc=order["OrderedAtUtc"],
            RecordedAtUtc=order["OrderedAtUtc"],
            AdministeredAtUtc=order["OrderedAtUtc"],
            AdministeredDose=order["OrderedDose"],
            DoseUnit=order["DoseUnit"],
            AdministrationStatus="given",
            NotGivenReason=None,
        )
    if set(resources) != set(dispositions):
        raise ValueError("Every archived FHIR resource requires an explicit mapping disposition.")
    catalogs = {}
    for table, prefix in (
        ("Diagnosis", "Diagnosis"),
        ("Procedure", "Procedure"),
        ("MedicationOrder", "Medication"),
    ):
        fields = [
            prefix + "CodeSystem",
            prefix + "Code",
            prefix + ("Name" if prefix == "Medication" else "Description"),
        ]
        retained = {
            (row[fields[0]], row[fields[1]]): {
                **{field: row[field] for field in fields},
                "IsDeleted": 0,
                "OriginModifiedAtUtc": row["ModifiedAtUtc"],
            }
            for row in tables[table]
        }
        catalogs[prefix] = list(retained.values())
    return {
        "format_version": 1,
        "history_start": start,
        "coverage": {"start": start, "end": covered_end},
        "calendar_end": f"{int(at[:4]) + 1}-12-31",
        "publication": {"at": at, "batch_id": batch_id or str(uuid5(NAMESPACE_URL, at))},
        "tables": tables,
        "histories": {},
        "catalogs": catalogs,
        "fhir_archive": resources,
        "resource_dispositions": dispositions,
        "supplemental_rules": supplements,
        "identity_references": {
            ref: stable_id(resources[ref]["resourceType"], ref) for ref in resources
        },
    }


def demo_bundle(patient_number: int, history_start: str, months: int = 12) -> dict:
    """Deterministic explicit clinical supplement for local tests, not a Synthea substitute."""
    start = date.fromisoformat(history_start[:10])
    patient = f"Patient/demo-{patient_number}"
    practitioner = "Practitioner/demo-provider"
    entries = [
        {
            "resource": {
                "resourceType": "Patient",
                "id": f"demo-{patient_number}",
                "name": [{"given": [f"Synthetic{patient_number}"], "family": "Demonstration"}],
                "birthDate": "1980-01-01",
                "gender": "unknown",
                "address": [{"city": "Synthetic City", "state": "MA", "postalCode": "02101"}],
            }
        },
        {
            "resource": {
                "resourceType": "Practitioner",
                "id": "demo-provider",
                "name": [{"given": ["Synthetic"], "family": "Clinician"}],
            }
        },
    ]
    for month in range(months):
        absolute = start.year * 12 + start.month - 1 + month
        day = start.replace(year=absolute // 12, month=absolute % 12 + 1, day=1)
        event = f"{day.isoformat()}T10:00:00Z"
        encounter = f"Encounter/demo-{patient_number}-{month}"
        suffix = f"demo-{patient_number}-{month}"
        common = {"subject": {"reference": patient}, "encounter": {"reference": encounter}}
        resources = [
            {
                "resourceType": "Encounter",
                "id": suffix,
                "subject": {"reference": patient},
                "status": "finished",
                "class": {"code": "AMB"},
                "participant": [{"individual": {"reference": practitioner}}],
                "period": {"start": event, "end": f"{day.isoformat()}T11:00:00Z"},
            },
            {
                "resourceType": "Condition",
                "id": suffix,
                **common,
                "recordedDate": event,
                "code": {
                    "coding": [
                        {
                            "system": "urn:synthetic",
                            "code": "DEMO-DX",
                            "display": "Synthetic diagnosis",
                        }
                    ]
                },
            },
            {
                "resourceType": "Procedure",
                "id": suffix,
                **common,
                "status": "completed",
                "performedDateTime": event,
                "code": {
                    "coding": [
                        {
                            "system": "urn:synthetic",
                            "code": "DEMO-PX",
                            "display": "Synthetic procedure",
                        }
                    ]
                },
            },
            {
                "resourceType": "MedicationRequest",
                "id": suffix,
                **common,
                "status": "active",
                "authoredOn": event,
                "requester": {"reference": practitioner},
                "medicationCodeableConcept": {
                    "coding": [
                        {
                            "system": "urn:synthetic",
                            "code": "DEMO-RX",
                            "display": "Synthetic medication",
                        }
                    ]
                },
                "dosageInstruction": [
                    {"doseAndRate": [{"doseQuantity": {"value": "1.2500", "unit": "mg"}}]}
                ],
            },
        ]
        for category, code, value, unit in (
            ("laboratory", "DEMO-LAB", "4.123456", "mmol/L"),
            ("vital-signs", "DEMO-PULSE", "72", "/min"),
        ):
            resources.append(
                {
                    "resourceType": "Observation",
                    "id": suffix + "-" + category,
                    **common,
                    "status": "final",
                    "effectiveDateTime": event,
                    "category": [{"coding": [{"code": category}]}],
                    "code": {
                        "coding": [
                            {
                                "system": "urn:synthetic",
                                "code": code,
                                "display": "Synthetic " + category,
                            }
                        ]
                    },
                    "valueQuantity": {"value": value, "unit": unit},
                }
            )
        entries.extend({"resource": resource} for resource in resources)
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}
