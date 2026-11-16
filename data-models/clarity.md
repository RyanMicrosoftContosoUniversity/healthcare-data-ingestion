# Clarity Table Relationships

Cardinality reads from the table in the heading to the related table. `many` means zero or more; `0 or 1` means optional. All relationships remain proposed.

## Patient Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | 1 to many | `Patient.PatientID == Encounter.PatientID` |
| Coverage | 1 to many | `Patient.PatientID == Coverage.PatientID` |
| Appointment | 1 to many | `Patient.PatientID == Appointment.PatientID` |

## Provider Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | 0 or 1 to many | `Provider.ProviderID == Encounter.AttendingProviderID` |
| Diagnosis | 0 or 1 to many | `Provider.ProviderID == Diagnosis.DiagnosingProviderID` |
| Procedure | 0 or 1 to many | `Provider.ProviderID == Procedure.PerformingProviderID` |
| MedicationOrder | 1 to many | `Provider.ProviderID == MedicationOrder.OrderingProviderID` |
| MedicationAdministration | 0 or 1 to many | `Provider.ProviderID == MedicationAdministration.AdministeringProviderID` |
| LaboratoryOrder | 1 to many | `Provider.ProviderID == LaboratoryOrder.OrderingProviderID` |
| VitalSign | 0 or 1 to many | `Provider.ProviderID == VitalSign.RecordingProviderID` |
| Appointment | 0 or 1 to many | `Provider.ProviderID == Appointment.ProviderID` |

## Department Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | 1 to many | `Department.DepartmentID == Encounter.DepartmentID` |
| Appointment | 1 to many | `Department.DepartmentID == Appointment.DepartmentID` |

## Encounter Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Patient | many to 1 | `Encounter.PatientID == Patient.PatientID` |
| Department | many to 1 | `Encounter.DepartmentID == Department.DepartmentID` |
| Provider | many to 0 or 1 | `Encounter.AttendingProviderID == Provider.ProviderID` |
| Coverage | many to 0 or 1 | `Encounter.PrimaryCoverageID == Coverage.CoverageID` |
| Diagnosis | 1 to many | `Encounter.EncounterID == Diagnosis.EncounterID` |
| Procedure | 1 to many | `Encounter.EncounterID == Procedure.EncounterID` |
| MedicationOrder | 1 to many | `Encounter.EncounterID == MedicationOrder.EncounterID` |
| LaboratoryOrder | 1 to many | `Encounter.EncounterID == LaboratoryOrder.EncounterID` |
| VitalSign | 1 to many | `Encounter.EncounterID == VitalSign.EncounterID` |
| Appointment | 0 or 1 to 0 or 1 | `Encounter.EncounterID == Appointment.EncounterID` |

## Diagnosis Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `Diagnosis.EncounterID == Encounter.EncounterID` |
| Provider | many to 0 or 1 | `Diagnosis.DiagnosingProviderID == Provider.ProviderID` |

## Procedure Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `Procedure.EncounterID == Encounter.EncounterID` |
| Provider | many to 0 or 1 | `Procedure.PerformingProviderID == Provider.ProviderID` |

## MedicationOrder Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `MedicationOrder.EncounterID == Encounter.EncounterID` |
| Provider | many to 1 | `MedicationOrder.OrderingProviderID == Provider.ProviderID` |
| MedicationAdministration | 1 to many | `MedicationOrder.MedicationOrderID == MedicationAdministration.MedicationOrderID` |

## MedicationAdministration Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| MedicationOrder | many to 1 | `MedicationAdministration.MedicationOrderID == MedicationOrder.MedicationOrderID` |
| Provider | many to 0 or 1 | `MedicationAdministration.AdministeringProviderID == Provider.ProviderID` |

## LaboratoryOrder Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `LaboratoryOrder.EncounterID == Encounter.EncounterID` |
| Provider | many to 1 | `LaboratoryOrder.OrderingProviderID == Provider.ProviderID` |
| LaboratoryResult | 1 to many | `LaboratoryOrder.LaboratoryOrderID == LaboratoryResult.LaboratoryOrderID` |

## LaboratoryResult Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| LaboratoryOrder | many to 1 | `LaboratoryResult.LaboratoryOrderID == LaboratoryOrder.LaboratoryOrderID` |

## VitalSign Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `VitalSign.EncounterID == Encounter.EncounterID` |
| Provider | many to 0 or 1 | `VitalSign.RecordingProviderID == Provider.ProviderID` |

## Coverage Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | 0 or 1 to many | `Coverage.CoverageID == Encounter.PrimaryCoverageID` |
| Patient | many to 1 | `Coverage.PatientID == Patient.PatientID` |

## Appointment Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Patient | many to 1 | `Appointment.PatientID == Patient.PatientID` |
| Provider | many to 0 or 1 | `Appointment.ProviderID == Provider.ProviderID` |
| Department | many to 1 | `Appointment.DepartmentID == Department.DepartmentID` |
| Encounter | 0 or 1 to 0 or 1 | `Appointment.EncounterID == Encounter.EncounterID` |
