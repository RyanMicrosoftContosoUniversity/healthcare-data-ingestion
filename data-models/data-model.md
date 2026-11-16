# Table Relationships

Cardinality reads from the table in the heading to the related table. `many` means zero or more; `0 or 1` means optional. All relationships remain proposed.

The logical DimPatient/DimCoverage association is not a foreign key. Its identity columns alone can match multiple historical versions; an actual historical join also needs as-of/version filtering.

## Clarity

### Patient Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | 1 to many | `Patient.PatientID == Encounter.PatientID` |
| Coverage | 1 to many | `Patient.PatientID == Coverage.PatientID` |
| Appointment | 1 to many | `Patient.PatientID == Appointment.PatientID` |

### Provider Table Relationships

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

### Department Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | 1 to many | `Department.DepartmentID == Encounter.DepartmentID` |
| Appointment | 1 to many | `Department.DepartmentID == Appointment.DepartmentID` |

### Encounter Table Relationships

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

### Diagnosis Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `Diagnosis.EncounterID == Encounter.EncounterID` |
| Provider | many to 0 or 1 | `Diagnosis.DiagnosingProviderID == Provider.ProviderID` |

### Procedure Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `Procedure.EncounterID == Encounter.EncounterID` |
| Provider | many to 0 or 1 | `Procedure.PerformingProviderID == Provider.ProviderID` |

### MedicationOrder Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `MedicationOrder.EncounterID == Encounter.EncounterID` |
| Provider | many to 1 | `MedicationOrder.OrderingProviderID == Provider.ProviderID` |
| MedicationAdministration | 1 to many | `MedicationOrder.MedicationOrderID == MedicationAdministration.MedicationOrderID` |

### MedicationAdministration Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| MedicationOrder | many to 1 | `MedicationAdministration.MedicationOrderID == MedicationOrder.MedicationOrderID` |
| Provider | many to 0 or 1 | `MedicationAdministration.AdministeringProviderID == Provider.ProviderID` |

### LaboratoryOrder Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `LaboratoryOrder.EncounterID == Encounter.EncounterID` |
| Provider | many to 1 | `LaboratoryOrder.OrderingProviderID == Provider.ProviderID` |
| LaboratoryResult | 1 to many | `LaboratoryOrder.LaboratoryOrderID == LaboratoryResult.LaboratoryOrderID` |

### LaboratoryResult Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| LaboratoryOrder | many to 1 | `LaboratoryResult.LaboratoryOrderID == LaboratoryOrder.LaboratoryOrderID` |

### VitalSign Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | many to 1 | `VitalSign.EncounterID == Encounter.EncounterID` |
| Provider | many to 0 or 1 | `VitalSign.RecordingProviderID == Provider.ProviderID` |

### Coverage Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Encounter | 0 or 1 to many | `Coverage.CoverageID == Encounter.PrimaryCoverageID` |
| Patient | many to 1 | `Coverage.PatientID == Patient.PatientID` |

### Appointment Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| Patient | many to 1 | `Appointment.PatientID == Patient.PatientID` |
| Provider | many to 0 or 1 | `Appointment.ProviderID == Provider.ProviderID` |
| Department | many to 1 | `Appointment.DepartmentID == Department.DepartmentID` |
| Encounter | 0 or 1 to 0 or 1 | `Appointment.EncounterID == Encounter.EncounterID` |

## Caboodle

### DimPatient Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactEncounter | 1 to many | `DimPatient.PatientKey == FactEncounter.PatientKey` |
| FactDiagnosis | 1 to many | `DimPatient.PatientKey == FactDiagnosis.PatientKey` |
| FactProcedure | 1 to many | `DimPatient.PatientKey == FactProcedure.PatientKey` |
| FactMedicationOrder | 1 to many | `DimPatient.PatientKey == FactMedicationOrder.PatientKey` |
| FactMedicationAdministration | 1 to many | `DimPatient.PatientKey == FactMedicationAdministration.PatientKey` |
| FactLabResult | 1 to many | `DimPatient.PatientKey == FactLabResult.PatientKey` |
| FactAppointment | 1 to many | `DimPatient.PatientKey == FactAppointment.PatientKey` |
| DimCoverage (logical only) | many to many (historical versions) | `DimPatient.OriginSystem == DimCoverage.OriginSystem`<br>AND `DimPatient.SourcePatientID == DimCoverage.SourcePatientID` |

### DimProvider Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactEncounter | 0 or 1 to many | `DimProvider.ProviderKey == FactEncounter.AttendingProviderKey` |
| FactDiagnosis | 0 or 1 to many | `DimProvider.ProviderKey == FactDiagnosis.DiagnosingProviderKey` |
| FactProcedure | 0 or 1 to many | `DimProvider.ProviderKey == FactProcedure.PerformingProviderKey` |
| FactMedicationOrder | 1 to many | `DimProvider.ProviderKey == FactMedicationOrder.OrderingProviderKey` |
| FactMedicationAdministration | 0 or 1 to many | `DimProvider.ProviderKey == FactMedicationAdministration.AdministeringProviderKey` |
| FactLabResult | 1 to many | `DimProvider.ProviderKey == FactLabResult.OrderingProviderKey` |
| FactAppointment | 0 or 1 to many | `DimProvider.ProviderKey == FactAppointment.ProviderKey` |

### DimDepartment Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactEncounter | 1 to many | `DimDepartment.DepartmentKey == FactEncounter.DepartmentKey` |
| FactDiagnosis | 1 to many | `DimDepartment.DepartmentKey == FactDiagnosis.DepartmentKey` |
| FactProcedure | 1 to many | `DimDepartment.DepartmentKey == FactProcedure.DepartmentKey` |
| FactMedicationOrder | 1 to many | `DimDepartment.DepartmentKey == FactMedicationOrder.DepartmentKey` |
| FactMedicationAdministration | 1 to many | `DimDepartment.DepartmentKey == FactMedicationAdministration.DepartmentKey` |
| FactLabResult | 1 to many | `DimDepartment.DepartmentKey == FactLabResult.DepartmentKey` |
| FactAppointment | 1 to many | `DimDepartment.DepartmentKey == FactAppointment.DepartmentKey` |

### DimDate Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactEncounter | 1 to many | `DimDate.DateKey == FactEncounter.ArrivalDateKey` |
| FactEncounter | 0 or 1 to many | `DimDate.DateKey == FactEncounter.DischargeDateKey` |
| FactDiagnosis | 1 to many | `DimDate.DateKey == FactDiagnosis.DiagnosisDateKey` |
| FactProcedure | 1 to many | `DimDate.DateKey == FactProcedure.OrderedDateKey` |
| FactProcedure | 0 or 1 to many | `DimDate.DateKey == FactProcedure.PerformedDateKey` |
| FactMedicationOrder | 1 to many | `DimDate.DateKey == FactMedicationOrder.OrderedDateKey` |
| FactMedicationAdministration | 0 or 1 to many | `DimDate.DateKey == FactMedicationAdministration.AdministrationDateKey` |
| FactMedicationAdministration | 1 to many | `DimDate.DateKey == FactMedicationAdministration.RecordedDateKey` |
| FactLabResult | 1 to many | `DimDate.DateKey == FactLabResult.OrderedDateKey` |
| FactLabResult | 0 or 1 to many | `DimDate.DateKey == FactLabResult.ResultDateKey` |
| FactAppointment | 1 to many | `DimDate.DateKey == FactAppointment.ScheduledDateKey` |

### DimDiagnosis Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactDiagnosis | 1 to many | `DimDiagnosis.DiagnosisKey == FactDiagnosis.DiagnosisKey` |

### DimProcedure Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactProcedure | 1 to many | `DimProcedure.ProcedureKey == FactProcedure.ProcedureKey` |

### DimMedication Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactMedicationOrder | 1 to many | `DimMedication.MedicationKey == FactMedicationOrder.MedicationKey` |
| FactMedicationAdministration | 1 to many | `DimMedication.MedicationKey == FactMedicationAdministration.MedicationKey` |

### DimCoverage Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| FactEncounter | 0 or 1 to many | `DimCoverage.CoverageKey == FactEncounter.CoverageKey` |
| DimPatient (logical only) | many to many (historical versions) | `DimCoverage.OriginSystem == DimPatient.OriginSystem`<br>AND `DimCoverage.SourcePatientID == DimPatient.SourcePatientID` |

### FactEncounter Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| DimProvider | many to 0 or 1 | `FactEncounter.AttendingProviderKey == DimProvider.ProviderKey` |
| DimCoverage | many to 0 or 1 | `FactEncounter.CoverageKey == DimCoverage.CoverageKey` |
| DimDate | many to 1 | `FactEncounter.ArrivalDateKey == DimDate.DateKey` |
| DimDate | many to 0 or 1 | `FactEncounter.DischargeDateKey == DimDate.DateKey` |
| DimPatient | many to 1 | `FactEncounter.PatientKey == DimPatient.PatientKey` |
| DimDepartment | many to 1 | `FactEncounter.DepartmentKey == DimDepartment.DepartmentKey` |

### FactDiagnosis Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| DimDiagnosis | many to 1 | `FactDiagnosis.DiagnosisKey == DimDiagnosis.DiagnosisKey` |
| DimProvider | many to 0 or 1 | `FactDiagnosis.DiagnosingProviderKey == DimProvider.ProviderKey` |
| DimDate | many to 1 | `FactDiagnosis.DiagnosisDateKey == DimDate.DateKey` |
| DimPatient | many to 1 | `FactDiagnosis.PatientKey == DimPatient.PatientKey` |
| DimDepartment | many to 1 | `FactDiagnosis.DepartmentKey == DimDepartment.DepartmentKey` |

### FactProcedure Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| DimProcedure | many to 1 | `FactProcedure.ProcedureKey == DimProcedure.ProcedureKey` |
| DimProvider | many to 0 or 1 | `FactProcedure.PerformingProviderKey == DimProvider.ProviderKey` |
| DimDate | many to 1 | `FactProcedure.OrderedDateKey == DimDate.DateKey` |
| DimDate | many to 0 or 1 | `FactProcedure.PerformedDateKey == DimDate.DateKey` |
| DimPatient | many to 1 | `FactProcedure.PatientKey == DimPatient.PatientKey` |
| DimDepartment | many to 1 | `FactProcedure.DepartmentKey == DimDepartment.DepartmentKey` |

### FactMedicationOrder Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| DimMedication | many to 1 | `FactMedicationOrder.MedicationKey == DimMedication.MedicationKey` |
| DimProvider | many to 1 | `FactMedicationOrder.OrderingProviderKey == DimProvider.ProviderKey` |
| DimDate | many to 1 | `FactMedicationOrder.OrderedDateKey == DimDate.DateKey` |
| DimPatient | many to 1 | `FactMedicationOrder.PatientKey == DimPatient.PatientKey` |
| DimDepartment | many to 1 | `FactMedicationOrder.DepartmentKey == DimDepartment.DepartmentKey` |

### FactMedicationAdministration Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| DimMedication | many to 1 | `FactMedicationAdministration.MedicationKey == DimMedication.MedicationKey` |
| DimProvider | many to 0 or 1 | `FactMedicationAdministration.AdministeringProviderKey == DimProvider.ProviderKey` |
| DimDate | many to 0 or 1 | `FactMedicationAdministration.AdministrationDateKey == DimDate.DateKey` |
| DimDate | many to 1 | `FactMedicationAdministration.RecordedDateKey == DimDate.DateKey` |
| DimPatient | many to 1 | `FactMedicationAdministration.PatientKey == DimPatient.PatientKey` |
| DimDepartment | many to 1 | `FactMedicationAdministration.DepartmentKey == DimDepartment.DepartmentKey` |

### FactLabResult Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| DimProvider | many to 1 | `FactLabResult.OrderingProviderKey == DimProvider.ProviderKey` |
| DimDate | many to 1 | `FactLabResult.OrderedDateKey == DimDate.DateKey` |
| DimDate | many to 0 or 1 | `FactLabResult.ResultDateKey == DimDate.DateKey` |
| DimPatient | many to 1 | `FactLabResult.PatientKey == DimPatient.PatientKey` |
| DimDepartment | many to 1 | `FactLabResult.DepartmentKey == DimDepartment.DepartmentKey` |

### FactAppointment Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| DimProvider | many to 0 or 1 | `FactAppointment.ProviderKey == DimProvider.ProviderKey` |
| DimDate | many to 1 | `FactAppointment.ScheduledDateKey == DimDate.DateKey` |
| DimPatient | many to 1 | `FactAppointment.PatientKey == DimPatient.PatientKey` |
| DimDepartment | many to 1 | `FactAppointment.DepartmentKey == DimDepartment.DepartmentKey` |
