# Consolidated Data Model and Relationship Reference

**Status:** Proposed for review; not approved for implementation. These are synthetic Clarity and Caboodle simulations, not proprietary Epic schemas. This document consolidates the column definitions and every declared relationship from `plan.md`.

## Model Scope

| Source Database | Tables | Proposed Foreign Keys | Purpose |
| --- | --- | --- | --- |
| Clarity | 13 operational tables | 22 | Patient, encounter, scheduling, coverage, and clinical event simulation. |
| Caboodle | 8 dimensions and 7 facts | 37 | Historical dimensions and event-grained analytical facts derived by a separate simulated transformation process. |

All tables use `dbo` within their respective, separate Azure SQL databases. The FKs below are proposed same-database schema constraints, not a claim that the databases or constraints have already been deployed. Cross-system mappings are lineage, not cross-database FKs.

## Relationship and Diagram Conventions

- **Outgoing FK:** a column on this table references the named parent PK. A non-null FK references exactly one parent; a nullable FK references zero or one.
- **Incoming FK:** a child table references this table. A parent may have zero or many child rows unless a separate uniqueness rule limits it to zero or one.
- **Logical association:** shared business identity or a derivation path, not a declared FK. It must not be presented as an enforced version-specific relationship.
- **Lineage:** a source identifier or code records origin. It does not create an additional FK to a source database or another fact table.
- **Focused diagrams:** all declared FK columns remain visible on every displayed table, including context tables. A comment identifies an off-diagram FK target; no extra target box is required. Edges connect only tables actually drawn.
- **Keys and nullability:** PK = primary key; FK = foreign key; UK/UQ = unique key. Mermaid columns are NOT NULL unless a comment starts with NULL. Composite/filtered uniqueness is described in prose, not falsely marked as single-column uniqueness.
- **Shared columns:** the dictionaries below expand every inherited column. Focused diagrams omit shared audit fields for readability; `shared\01-audit-columns.mmd` and its SVG show them once.

## Patient and Coverage: Logical Association Versus Foreign Key

In Clarity, `Coverage.PatientID` is a direct FK to the unique `Patient.PatientID`. One patient can have multiple enrollments. `Encounter.PrimaryCoverageID` explicitly selects an enrollment for an encounter.

In Caboodle, both `DimPatient` and `DimCoverage` retain historical versions. `(OriginSystem, SourcePatientID)` identifies the same patient across the dimensions, but it does not identify a single `DimPatient` version. Therefore `DimCoverage.SourcePatientID` is not a direct FK to `DimPatient.PatientKey`, and no such FK is invented in the diagrams.

For encounter reporting, `FactEncounter.PatientKey` and `FactEncounter.CoverageKey` identify the selected patient and coverage versions. Coverage enrollments that have not been used by an encounter still exist. Enrollment-level analysis without an encounter requires an explicit as-of join on patient identity and the applicable version/coverage intervals; a join across all historical versions would multiply rows.

## Global Integrity and Temporal Rules

- Use immutable surrogate/event IDs and enforce every declared FK whenever its value is non-null. Do not cascade physical deletes; propagate controlled soft-delete policies without breaking historical references.
- Clinical child events inherit patient/department context through their encounter or parent order. An inherited relationship does not require adding a redundant direct FK.
- Type 2 dimensions are DimPatient, DimProvider, DimDepartment, and DimCoverage. Match origin, source identity, and fact lookup time in the half-open interval [EffectiveFromUtc, EffectiveToUtc). Require one current version per origin/source identity and non-overlapping intervals.
- Initial dimension versions must cover the seeded event horizon or unresolved events are quarantined. A nullable provider means genuinely unassigned, not an unresolved non-null source provider.
- The clinical code dimensions use Type 1 label corrections. Code-system/code pairs are not interchangeable with event IDs.
- Date FKs match the UTC dates of their corresponding event timestamps. The calendar has no origin-system or Type 2 fields.
- Clarity extraction uses ModifiedAtUtc; Caboodle extraction uses EtlModifiedAtUtc. Source corrections, dependent parent changes, SCD expiration, and delete propagation must advance the publication timestamp of affected rows.
- Every count measure is interpreted at its documented grain with status/deletion filters. Do not join facts through source event IDs as if those were FK constraints, or blindly sum unlike doses/observation values.

## Table Index

**Clarity:** `Patient`, `Provider`, `Department`, `Encounter`, `Diagnosis`, `Procedure`, `MedicationOrder`, `MedicationAdministration`, `LaboratoryOrder`, `LaboratoryResult`, `VitalSign`, `Coverage`, `Appointment`.

**Caboodle:** `DimPatient`, `DimProvider`, `DimDepartment`, `DimDate`, `DimDiagnosis`, `DimProcedure`, `DimMedication`, `DimCoverage`, `FactEncounter`, `FactDiagnosis`, `FactProcedure`, `FactMedicationOrder`, `FactMedicationAdministration`, `FactLabResult`, `FactAppointment`.

## Clarity Tables

### Clarity.dbo.Patient

**Grain:** One synthetic patient.

**Primary key:** `PatientID` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Clarity.dbo.Encounter.PatientID` | `PatientID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.Coverage.PatientID` | `PatientID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.Appointment.PatientID` | `PatientID` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- This is the stable patient identity. Encounter, coverage enrollment, and appointment relationships use PatientID, not the medical record number.
- Clinical events relate indirectly to the patient through Encounter, or through their parent medication/laboratory order. Those inherited paths are not additional direct patient FKs.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `PatientID` | `bigint` | No | PK; stable patient identifier used by related tables. |
| `MedicalRecordNumber` | `varchar(30)` | No | UQ; synthetic hospital medical record number. |
| `FirstName` | `nvarchar(100)` | No | Synthetic given name. |
| `LastName` | `nvarchar(100)` | No | Synthetic family name. |
| `BirthDate` | `date` | No | Date of birth for age-based reporting. |
| `AdministrativeSexCode` | `varchar(20)` | No | Administrative demographic code, including an unknown value. |
| `City` | `nvarchar(100)` | Yes | Synthetic city of residence. |
| `StateCode` | `varchar(10)` | Yes | State or region code. |
| `PostalCode` | `varchar(20)` | Yes | Postal identifier stored as text to preserve leading zeros. |
| `DeathDate` | `date` | Yes | Date of death when applicable. |
| `PatientStatus` | `varchar(20)` | No | Operational patient status, such as active or inactive. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\01-patient-coverage.mmd`, `clarity\02-scheduling.mmd`, `clarity\03-encounter.mmd`.

### Clarity.dbo.Provider

**Grain:** One synthetic clinical provider.

**Primary key:** `ProviderID` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Clarity.dbo.Encounter.AttendingProviderID` | `ProviderID` | No; FK is nullable | Many; zero is also allowed |
| `Clarity.dbo.Diagnosis.DiagnosingProviderID` | `ProviderID` | No; FK is nullable | Many; zero is also allowed |
| `Clarity.dbo.Procedure.PerformingProviderID` | `ProviderID` | No; FK is nullable | Many; zero is also allowed |
| `Clarity.dbo.MedicationOrder.OrderingProviderID` | `ProviderID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.MedicationAdministration.AdministeringProviderID` | `ProviderID` | No; FK is nullable | Many; zero is also allowed |
| `Clarity.dbo.LaboratoryOrder.OrderingProviderID` | `ProviderID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.VitalSign.RecordingProviderID` | `ProviderID` | No; FK is nullable | Many; zero is also allowed |
| `Clarity.dbo.Appointment.ProviderID` | `ProviderID` | No; FK is nullable | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- The incoming FKs distinguish attending, diagnosing, performing, ordering, administering, recording, and scheduled-provider roles. Optional roles do not require a fabricated provider.
- No provider-to-department assignment or affiliation table is proposed; co-occurrence on an encounter is not a direct provider-department FK.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `ProviderID` | `bigint` | No | PK; provider identifier. |
| `ProviderCode` | `varchar(30)` | No | UQ; stable source business identifier. |
| `DisplayName` | `nvarchar(200)` | No | Synthetic provider display name. |
| `ProviderTypeCode` | `varchar(30)` | No | Provider role or professional category. |
| `SpecialtyCode` | `varchar(30)` | Yes | Primary specialty classification. |
| `IsActive` | `bit` | No | Indicates whether the provider is currently active. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\02-scheduling.mmd`, `clarity\03-encounter.mmd`, `clarity\04-clinical-observations.mmd`, `clarity\05-medication-workflow.mmd`, `clarity\06-laboratory-workflow.mmd`.

### Clarity.dbo.Department

**Grain:** One hospital department.

**Primary key:** `DepartmentID` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Clarity.dbo.Encounter.DepartmentID` | `DepartmentID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.Appointment.DepartmentID` | `DepartmentID` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Encounter and Appointment each explicitly identify their department. Clinical child events inherit department context through their encounter.
- FacilityCode is a business attribute; there is no Facility table or FK in this baseline.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DepartmentID` | `bigint` | No | PK; department identifier. |
| `DepartmentCode` | `varchar(30)` | No | UQ; stable department business code. |
| `DepartmentName` | `nvarchar(150)` | No | Department display name. |
| `FacilityCode` | `varchar(30)` | No | Synthetic facility containing the department. |
| `DepartmentTypeCode` | `varchar(30)` | No | Classification such as inpatient, outpatient, or emergency. |
| `IsActive` | `bit` | No | Indicates whether the department is currently active. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\02-scheduling.mmd`, `clarity\03-encounter.mmd`.

### Clarity.dbo.Encounter

**Grain:** One visit or admission for one patient.

**Primary key:** `EncounterID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `PatientID` | `Clarity.dbo.Patient.PatientID` | No | Each Encounter references exactly one Patient; each Patient can be referenced by zero to many Encounter rows. |
| `DepartmentID` | `Clarity.dbo.Department.DepartmentID` | No | Each Encounter references exactly one Department; each Department can be referenced by zero to many Encounter rows. |
| `AttendingProviderID` | `Clarity.dbo.Provider.ProviderID` | Yes | Each Encounter references zero or one Provider; each Provider can be referenced by zero to many Encounter rows. |
| `PrimaryCoverageID` | `Clarity.dbo.Coverage.CoverageID` | Yes | Each Encounter references zero or one Coverage; each Coverage can be referenced by zero to many Encounter rows. |

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Clarity.dbo.Diagnosis.EncounterID` | `EncounterID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.Procedure.EncounterID` | `EncounterID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.MedicationOrder.EncounterID` | `EncounterID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.LaboratoryOrder.EncounterID` | `EncounterID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.VitalSign.EncounterID` | `EncounterID` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Clarity.dbo.Appointment.EncounterID` | `EncounterID` | No; FK is nullable | One, when populated (filtered uniqueness) |

**Relationship Rules and Logical Associations**

- PrimaryCoverageID must belong to PatientID and the coverage period must include the UTC arrival date. It represents the explicitly assigned primary enrollment, not every enrollment held by the patient.
- An appointment may link to this encounter, but the filtered uniqueness rule permits at most one linked appointment per encounter.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `EncounterID` | `bigint` | No | PK; encounter identifier. |
| `EncounterNumber` | `varchar(40)` | No | UQ; source visit or admission business identifier. |
| `PatientID` | `bigint` | No | FK to `Patient.PatientID`. |
| `DepartmentID` | `bigint` | No | FK to `Department.DepartmentID`; encounter department. |
| `AttendingProviderID` | `bigint` | Yes | FK to `Provider.ProviderID`; assigned attending provider. |
| `PrimaryCoverageID` | `bigint` | Yes | FK to `Coverage.CoverageID`; explicitly assigned primary enrollment, if known. |
| `EncounterTypeCode` | `varchar(30)` | No | Visit classification. |
| `EncounterStatus` | `varchar(20)` | No | Status such as planned, in progress, completed, or canceled. |
| `ArrivalAtUtc` | `datetime2(7)` | No | Start of the encounter. |
| `DischargeAtUtc` | `datetime2(7)` | Yes | End of the encounter; absent for open encounters. |
| `DischargeDispositionCode` | `varchar(30)` | Yes | Discharge outcome classification. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\02-scheduling.mmd`, `clarity\03-encounter.mmd`, `clarity\04-clinical-observations.mmd`, `clarity\05-medication-workflow.mmd`, `clarity\06-laboratory-workflow.mmd`.

### Clarity.dbo.Diagnosis

**Grain:** One diagnosis assignment to an encounter; repeated codes can occur on different assignments.

**Primary key:** `DiagnosisID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `EncounterID` | `Clarity.dbo.Encounter.EncounterID` | No | Each Diagnosis references exactly one Encounter; each Encounter can be referenced by zero to many Diagnosis rows. |
| `DiagnosingProviderID` | `Clarity.dbo.Provider.ProviderID` | Yes | Each Diagnosis references zero or one Provider; each Provider can be referenced by zero to many Diagnosis rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce uniqueness of (EncounterID, DiagnosisSequence), positive sequences, and at most one active, non-deleted primary assignment per encounter.
- DiagnosisCodeSystem and DiagnosisCode are business-code attributes, not FKs to an operational diagnosis catalog. The corresponding Caboodle dimension is populated separately.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DiagnosisID` | `bigint` | No | PK; diagnosis assignment identifier. |
| `EncounterID` | `bigint` | No | FK to `Encounter.EncounterID`. |
| `DiagnosingProviderID` | `bigint` | Yes | FK to `Provider.ProviderID`. |
| `DiagnosisCodeSystem` | `varchar(30)` | No | Code namespace; use a documented synthetic value set. |
| `DiagnosisCode` | `varchar(30)` | No | Diagnosis business code within the code system. |
| `DiagnosisDescription` | `nvarchar(250)` | No | Synthetic diagnosis label. |
| `DiagnosisSequence` | `smallint` | No | Positive ordering within the encounter. |
| `IsPrimary` | `bit` | No | Identifies the primary diagnosis assignment. |
| `DiagnosedAtUtc` | `datetime2(7)` | No | Clinical assignment timestamp. |
| `DiagnosisStatus` | `varchar(20)` | No | Assignment status, including corrected or canceled scenarios. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\04-clinical-observations.mmd`.

### Clarity.dbo.Procedure

**Grain:** One procedure event associated with an encounter. Use `[Procedure]` when SQL identifier quoting is required.

**Primary key:** `ProcedureID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `EncounterID` | `Clarity.dbo.Encounter.EncounterID` | No | Each Procedure references exactly one Encounter; each Encounter can be referenced by zero to many Procedure rows. |
| `PerformingProviderID` | `Clarity.dbo.Provider.ProviderID` | Yes | Each Procedure references zero or one Provider; each Provider can be referenced by zero to many Procedure rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- ProcedureCodeSystem and ProcedureCode are business-code attributes; ProcedureID identifies an event, not a catalog member.
- Use [Procedure] where SQL identifier quoting is required. An unperformed order may have no PerformedAtUtc value.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `ProcedureID` | `bigint` | No | PK; procedure event identifier. |
| `EncounterID` | `bigint` | No | FK to `Encounter.EncounterID`. |
| `PerformingProviderID` | `bigint` | Yes | FK to `Provider.ProviderID`. |
| `ProcedureCodeSystem` | `varchar(30)` | No | Namespace for the synthetic procedure code. |
| `ProcedureCode` | `varchar(30)` | No | Procedure business code within the code system. |
| `ProcedureDescription` | `nvarchar(250)` | No | Procedure label. |
| `OrderedAtUtc` | `datetime2(7)` | No | Time the procedure was requested. |
| `PerformedAtUtc` | `datetime2(7)` | Yes | Actual performance time; absent for unperformed orders. |
| `ProcedureStatus` | `varchar(20)` | No | Status such as ordered, completed, or canceled. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\04-clinical-observations.mmd`.

### Clarity.dbo.MedicationOrder

**Grain:** One medication order for an encounter.

**Primary key:** `MedicationOrderID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `EncounterID` | `Clarity.dbo.Encounter.EncounterID` | No | Each MedicationOrder references exactly one Encounter; each Encounter can be referenced by zero to many MedicationOrder rows. |
| `OrderingProviderID` | `Clarity.dbo.Provider.ProviderID` | No | Each MedicationOrder references exactly one Provider; each Provider can be referenced by zero to many MedicationOrder rows. |

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Clarity.dbo.MedicationAdministration.MedicationOrderID` | `MedicationOrderID` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- This is an order entity, not a medication catalog. MedicationCode identifies a product within MedicationCodeSystem but is not an operational FK in this baseline.
- Its encounter determines the patient and department for all linked administration records.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `MedicationOrderID` | `bigint` | No | PK; medication order identifier. |
| `EncounterID` | `bigint` | No | FK to `Encounter.EncounterID`. |
| `OrderingProviderID` | `bigint` | No | FK to `Provider.ProviderID`. |
| `MedicationCodeSystem` | `varchar(30)` | No | Namespace for the synthetic medication identifier. |
| `MedicationCode` | `varchar(50)` | No | Medication product code within the code system. |
| `MedicationName` | `nvarchar(200)` | No | Synthetic medication display name. |
| `OrderedDose` | `decimal(18,4)` | Yes | Structured ordered quantity; absent for text-only instructions. |
| `DoseUnit` | `varchar(30)` | Yes | Unit associated with `OrderedDose`. |
| `RouteCode` | `varchar(30)` | Yes | Administration route classification. |
| `FrequencyCode` | `varchar(30)` | Yes | Synthetic frequency classification. |
| `OrderedAtUtc` | `datetime2(7)` | No | Order creation event time. |
| `StartAtUtc` | `datetime2(7)` | Yes | Intended treatment start time. |
| `EndAtUtc` | `datetime2(7)` | Yes | Intended or actual end time. |
| `OrderStatus` | `varchar(20)` | No | Status such as active, discontinued, or canceled. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\05-medication-workflow.mmd`.

### Clarity.dbo.MedicationAdministration

**Grain:** One administration event or documented non-administration against an order.

**Primary key:** `MedicationAdministrationID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `MedicationOrderID` | `Clarity.dbo.MedicationOrder.MedicationOrderID` | No | Each MedicationAdministration references exactly one MedicationOrder; each MedicationOrder can be referenced by zero to many MedicationAdministration rows. |
| `AdministeringProviderID` | `Clarity.dbo.Provider.ProviderID` | Yes | Each MedicationAdministration references zero or one Provider; each Provider can be referenced by zero to many MedicationAdministration rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- MedicationOrderID determines the encounter and patient indirectly; there is no additional direct EncounterID or PatientID on this table.
- Documented non-administrations are valid events. AdministeredAtUtc and AdministeredDose can be null without removing the order relationship.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `MedicationAdministrationID` | `bigint` | No | PK; administration event identifier. |
| `MedicationOrderID` | `bigint` | No | FK to `MedicationOrder.MedicationOrderID`; determines the encounter. |
| `AdministeringProviderID` | `bigint` | Yes | FK to `Provider.ProviderID`. |
| `ScheduledAtUtc` | `datetime2(7)` | Yes | Planned administration time. |
| `RecordedAtUtc` | `datetime2(7)` | No | Time the administration or non-administration was documented. |
| `AdministeredAtUtc` | `datetime2(7)` | Yes | Actual event time; absent when not administered. |
| `AdministeredDose` | `decimal(18,4)` | Yes | Actual quantity administered, when applicable. |
| `DoseUnit` | `varchar(30)` | Yes | Unit for the administered quantity. |
| `AdministrationStatus` | `varchar(20)` | No | Status such as given, held, refused, or not given. |
| `NotGivenReason` | `nvarchar(250)` | Yes | Synthetic explanation for a non-administration. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\05-medication-workflow.mmd`.

### Clarity.dbo.LaboratoryOrder

**Grain:** One ordered laboratory test or panel.

**Primary key:** `LaboratoryOrderID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `EncounterID` | `Clarity.dbo.Encounter.EncounterID` | No | Each LaboratoryOrder references exactly one Encounter; each Encounter can be referenced by zero to many LaboratoryOrder rows. |
| `OrderingProviderID` | `Clarity.dbo.Provider.ProviderID` | No | Each LaboratoryOrder references exactly one Provider; each Provider can be referenced by zero to many LaboratoryOrder rows. |

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Clarity.dbo.LaboratoryResult.LaboratoryOrderID` | `LaboratoryOrderID` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- One test/panel order can have many LaboratoryResult component rows. TestCode is a business attribute, not a FK to a separate test catalog.
- The encounter supplies the patient and department context for its result components.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `LaboratoryOrderID` | `bigint` | No | PK; laboratory order identifier. |
| `EncounterID` | `bigint` | No | FK to `Encounter.EncounterID`. |
| `OrderingProviderID` | `bigint` | No | FK to `Provider.ProviderID`. |
| `OrderNumber` | `varchar(40)` | No | UQ; laboratory order business identifier. |
| `TestCode` | `varchar(40)` | No | Synthetic ordered test or panel code. |
| `TestName` | `nvarchar(200)` | No | Test or panel name. |
| `SpecimenTypeCode` | `varchar(30)` | Yes | Specimen classification. |
| `OrderedAtUtc` | `datetime2(7)` | No | Order event time. |
| `CollectedAtUtc` | `datetime2(7)` | Yes | Specimen collection time. |
| `OrderStatus` | `varchar(20)` | No | Order processing status. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\06-laboratory-workflow.mmd`.

### Clarity.dbo.LaboratoryResult

**Grain:** One result component on a laboratory order. Corrections update the same result ID; separate components have separate IDs.

**Primary key:** `LaboratoryResultID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `LaboratoryOrderID` | `Clarity.dbo.LaboratoryOrder.LaboratoryOrderID` | No | Each LaboratoryResult references exactly one LaboratoryOrder; each LaboratoryOrder can be referenced by zero to many LaboratoryResult rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- The parent order supplies encounter, patient, department, and ordering-provider context; these are indirect relationships, not extra direct FKs.
- Corrections retain LaboratoryResultID. ComponentCode is not unique across orders and is not a FK to a component catalog.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `LaboratoryResultID` | `bigint` | No | PK; stable result component identifier. |
| `LaboratoryOrderID` | `bigint` | No | FK to `LaboratoryOrder.LaboratoryOrderID`. |
| `ComponentCode` | `varchar(40)` | No | Synthetic observation component code. |
| `ComponentName` | `nvarchar(200)` | No | Observation component label. |
| `NumericValue` | `decimal(18,6)` | Yes | Numeric result, when applicable. |
| `TextValue` | `nvarchar(1000)` | Yes | Qualitative result or explanatory text. |
| `ResultUnit` | `varchar(30)` | Yes | Unit associated with a numeric result. |
| `ReferenceLow` | `decimal(18,6)` | Yes | Synthetic lower reference bound in the result unit. |
| `ReferenceHigh` | `decimal(18,6)` | Yes | Synthetic upper reference bound in the result unit. |
| `AbnormalFlag` | `varchar(20)` | Yes | Source-provided synthetic result classification. |
| `ResultedAtUtc` | `datetime2(7)` | Yes | Clinical result time; absent for pending components. |
| `ResultStatus` | `varchar(20)` | No | Status such as pending, preliminary, final, corrected, or canceled. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\06-laboratory-workflow.mmd`.

### Clarity.dbo.VitalSign

**Grain:** One observation component at one measurement time. Represent multi-component observations as separate rows.

**Primary key:** `VitalSignID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `EncounterID` | `Clarity.dbo.Encounter.EncounterID` | No | Each VitalSign references exactly one Encounter; each Encounter can be referenced by zero to many VitalSign rows. |
| `RecordingProviderID` | `Clarity.dbo.Provider.ProviderID` | Yes | Each VitalSign references zero or one Provider; each Provider can be referenced by zero to many VitalSign rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Each row is one observation component. The encounter supplies the patient and department; multi-component observations use separate rows.
- There is no standalone Caboodle vital-sign fact in the initial scope.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `VitalSignID` | `bigint` | No | PK; observation identifier. |
| `EncounterID` | `bigint` | No | FK to `Encounter.EncounterID`. |
| `RecordingProviderID` | `bigint` | Yes | FK to `Provider.ProviderID`. |
| `VitalTypeCode` | `varchar(40)` | No | Synthetic observation type, such as temperature or pulse. |
| `NumericValue` | `decimal(18,6)` | Yes | Numeric observation value. |
| `TextValue` | `nvarchar(250)` | Yes | Non-numeric observation value or explanation. |
| `ValueUnit` | `varchar(30)` | Yes | Unit for a numeric observation. |
| `MeasuredAtUtc` | `datetime2(7)` | No | Observation event time. |
| `ObservationStatus` | `varchar(20)` | No | Observation lifecycle status. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\04-clinical-observations.mmd`.

### Clarity.dbo.Coverage

**Grain:** One patient enrollment in a synthetic insurance plan for a coverage period.

**Primary key:** `CoverageID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `PatientID` | `Clarity.dbo.Patient.PatientID` | No | Each Coverage references exactly one Patient; each Patient can be referenced by zero to many Coverage rows. |

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Clarity.dbo.Encounter.PrimaryCoverageID` | `CoverageID` | No; FK is nullable | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- This is a patient enrollment for a coverage period, not a payer/plan catalog. PayerCode and PlanCode do not reference additional baseline tables.
- A patient can have multiple enrollments. An enrollment can be assigned as primary coverage to zero or many encounters, but each encounter selects at most one.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `CoverageID` | `bigint` | No | PK; patient coverage identifier. |
| `PatientID` | `bigint` | No | FK to `Patient.PatientID`. |
| `CoverageNumber` | `varchar(40)` | No | UQ; synthetic enrollment business identifier. |
| `PayerCode` | `varchar(30)` | No | Synthetic payer identifier. |
| `PayerName` | `nvarchar(150)` | No | Synthetic payer display name. |
| `PlanCode` | `varchar(40)` | No | Plan identifier within the payer. |
| `PlanName` | `nvarchar(150)` | No | Synthetic plan name. |
| `CoverageTypeCode` | `varchar(30)` | No | Insurance category. |
| `EffectiveDate` | `date` | No | First covered date. |
| `TerminationDate` | `date` | Yes | Last covered date, inclusive; absent for open coverage. |
| `CoverageStatus` | `varchar(20)` | No | Enrollment lifecycle status. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\01-patient-coverage.mmd`, `clarity\03-encounter.mmd`.

### Clarity.dbo.Appointment

**Grain:** One scheduled care visit, including canceled visits and no-shows.

**Primary key:** `AppointmentID` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `PatientID` | `Clarity.dbo.Patient.PatientID` | No | Each Appointment references exactly one Patient; each Patient can be referenced by zero to many Appointment rows. |
| `ProviderID` | `Clarity.dbo.Provider.ProviderID` | Yes | Each Appointment references zero or one Provider; each Provider can be referenced by zero to many Appointment rows. |
| `DepartmentID` | `Clarity.dbo.Department.DepartmentID` | No | Each Appointment references exactly one Department; each Department can be referenced by zero to many Appointment rows. |
| `EncounterID` | `Clarity.dbo.Encounter.EncounterID` | Yes | Each Appointment references zero or one Encounter; each Encounter can be referenced by zero to 1 Appointment rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- EncounterID is nullable and has filtered uniqueness for non-null values. Consequently, both sides of the appointment-to-encounter relationship are optional and at most one.
- If an encounter is linked, both records must identify the same patient. Canceled visits and no-shows can remain unlinked.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `AppointmentID` | `bigint` | No | PK; appointment identifier. |
| `AppointmentNumber` | `varchar(40)` | No | UQ; scheduling business identifier. |
| `PatientID` | `bigint` | No | FK to `Patient.PatientID`. |
| `ProviderID` | `bigint` | Yes | FK to `Provider.ProviderID`; scheduled provider. |
| `DepartmentID` | `bigint` | No | FK to `Department.DepartmentID`. |
| `EncounterID` | `bigint` | Yes | FK to `Encounter.EncounterID`; populated if the appointment becomes an encounter. |
| `ScheduledStartAtUtc` | `datetime2(7)` | No | Scheduled visit start. |
| `ScheduledEndAtUtc` | `datetime2(7)` | No | Scheduled visit end. |
| `AppointmentTypeCode` | `varchar(30)` | No | Visit scheduling category. |
| `AppointmentStatus` | `varchar(20)` | No | Status such as scheduled, arrived, completed, canceled, or no-show. |
| `CanceledAtUtc` | `datetime2(7)` | Yes | Cancellation event time, when applicable. |
| `CancellationReason` | `nvarchar(250)` | Yes | Synthetic cancellation explanation. |
| `CreatedAtUtc` | `datetime2(7)` | No | Creation timestamp, assigned by the source write process. |
| `ModifiedAtUtc` | `datetime2(7)` | No | Updated on every insert, update, correction, and soft delete; proposed incremental watermark. |
| `IsDeleted` | `bit` | No | Soft-delete indicator; defaults to `0`. |
| `DeletedAtUtc` | `datetime2(7)` | Yes | Deletion timestamp; populated only when `IsDeleted = 1`. |

**Focused Mermaid diagrams:** `clarity\02-scheduling.mmd`.

## Caboodle Tables

### Caboodle.dbo.DimPatient

**Grain:** One historical version of one patient. **History:** Type 2 for selected demographic/location/status changes; corrections follow an explicitly documented policy.

**Primary key:** `PatientKey` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactEncounter.PatientKey` | `PatientKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactDiagnosis.PatientKey` | `PatientKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactProcedure.PatientKey` | `PatientKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationOrder.PatientKey` | `PatientKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationAdministration.PatientKey` | `PatientKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactLabResult.PatientKey` | `PatientKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactAppointment.PatientKey` | `PatientKey` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Logical association with DimCoverage: match OriginSystem and SourcePatientID to identify the same real-world synthetic patient. A patient can have multiple enrollments, and both dimensions can have multiple historical versions.
- That pair is not unique in DimPatient, so DimCoverage.SourcePatientID is not a FK to a specific PatientKey. A temporal patient/coverage analysis must explicitly select an as-of time and valid version/coverage period; do not join all versions on patient identity alone.
- For encounter reporting, FactEncounter carries both PatientKey and CoverageKey. Enrollment records without encounters still exist independently in DimCoverage.
- Business identity is scoped by OriginSystem and the named source entity ID. Historical versions have different surrogate PKs; preserve old PKs when publishing a new version.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourcePatientID` | `Clarity.dbo.Patient.PatientID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `PatientKey` | `bigint` | No | Surrogate PK for a patient version. |
| `SourcePatientID` | `bigint` | No | Lineage to `Clarity.dbo.Patient.PatientID`. |
| `MedicalRecordNumber` | `varchar(30)` | No | Patient business identifier. |
| `FirstName` | `nvarchar(100)` | No | Synthetic given name. |
| `LastName` | `nvarchar(100)` | No | Synthetic family name. |
| `BirthDate` | `date` | No | Supports age-at-event calculations; do not persist a continually changing current age. |
| `AdministrativeSexCode` | `varchar(20)` | No | Administrative demographic classification. |
| `City` | `nvarchar(100)` | Yes | Patient city for this version. |
| `StateCode` | `varchar(10)` | Yes | Patient state or region for this version. |
| `PostalCode` | `varchar(20)` | Yes | Patient postal identifier for this version. |
| `DeathDate` | `date` | Yes | Date of death when known. |
| `PatientStatus` | `varchar(20)` | No | Patient lifecycle status for this version. |
| `EffectiveFromUtc` | `datetime2(7)` | No | Inclusive beginning of this Type 2 dimension version. |
| `EffectiveToUtc` | `datetime2(7)` | Yes | Exclusive end of this version; null for the current version. |
| `IsCurrent` | `bit` | No | Identifies the current version for the source business key. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\01-patient-coverage.mmd`, `caboodle\facts\01-encounter.mmd`, `caboodle\facts\02-diagnosis.mmd`, `caboodle\facts\03-procedure.mmd`, `caboodle\facts\04-medication-order.mmd`, `caboodle\facts\05-medication-administration.mmd`, `caboodle\facts\06-lab-result.mmd`, `caboodle\facts\07-appointment.mmd`.

### Caboodle.dbo.DimProvider

**Grain:** One historical version of a provider. **History:** Type 2 for specialty, role, and active-status changes.

**Primary key:** `ProviderKey` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactEncounter.AttendingProviderKey` | `ProviderKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactDiagnosis.DiagnosingProviderKey` | `ProviderKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactProcedure.PerformingProviderKey` | `ProviderKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationOrder.OrderingProviderKey` | `ProviderKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationAdministration.AdministeringProviderKey` | `ProviderKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactLabResult.OrderingProviderKey` | `ProviderKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactAppointment.ProviderKey` | `ProviderKey` | No; FK is nullable | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Each incoming provider FK represents its named clinical role. Match the provider source identity and the fact lookup time to choose a Type 2 version.
- There is no direct relationship to DimDepartment; both are conformed dimensions referenced independently by facts.
- Business identity is scoped by OriginSystem and the named source entity ID. Historical versions have different surrogate PKs; preserve old PKs when publishing a new version.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceProviderID` | `Clarity.dbo.Provider.ProviderID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `ProviderKey` | `bigint` | No | Surrogate PK for a provider version. |
| `SourceProviderID` | `bigint` | No | Lineage to `Provider.ProviderID`. |
| `ProviderCode` | `varchar(30)` | No | Stable provider business identifier. |
| `DisplayName` | `nvarchar(200)` | No | Provider display name for this version. |
| `ProviderTypeCode` | `varchar(30)` | No | Provider role/category for this version. |
| `SpecialtyCode` | `varchar(30)` | Yes | Specialty for this version. |
| `IsActive` | `bit` | No | Active status for this version. |
| `EffectiveFromUtc` | `datetime2(7)` | No | Inclusive beginning of this Type 2 dimension version. |
| `EffectiveToUtc` | `datetime2(7)` | Yes | Exclusive end of this version; null for the current version. |
| `IsCurrent` | `bit` | No | Identifies the current version for the source business key. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\02-provider-department.mmd`, `caboodle\facts\01-encounter.mmd`, `caboodle\facts\02-diagnosis.mmd`, `caboodle\facts\03-procedure.mmd`, `caboodle\facts\04-medication-order.mmd`, `caboodle\facts\05-medication-administration.mmd`, `caboodle\facts\06-lab-result.mmd`, `caboodle\facts\07-appointment.mmd`.

### Caboodle.dbo.DimDepartment

**Grain:** One historical version of a department. **History:** Type 2 for facility, classification, and active-status changes.

**Primary key:** `DepartmentKey` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactEncounter.DepartmentKey` | `DepartmentKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactDiagnosis.DepartmentKey` | `DepartmentKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactProcedure.DepartmentKey` | `DepartmentKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationOrder.DepartmentKey` | `DepartmentKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationAdministration.DepartmentKey` | `DepartmentKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactLabResult.DepartmentKey` | `DepartmentKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactAppointment.DepartmentKey` | `DepartmentKey` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Every baseline fact references a department version. Clinical facts derive the source department from the encounter; appointment facts use the scheduled department.
- FacilityCode remains a descriptive attribute; there is no DimFacility table or FK in the baseline.
- Business identity is scoped by OriginSystem and the named source entity ID. Historical versions have different surrogate PKs; preserve old PKs when publishing a new version.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceDepartmentID` | `Clarity.dbo.Department.DepartmentID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DepartmentKey` | `bigint` | No | Surrogate PK for a department version. |
| `SourceDepartmentID` | `bigint` | No | Lineage to `Department.DepartmentID`. |
| `DepartmentCode` | `varchar(30)` | No | Stable department business code. |
| `DepartmentName` | `nvarchar(150)` | No | Department name for this version. |
| `FacilityCode` | `varchar(30)` | No | Owning facility for this version. |
| `DepartmentTypeCode` | `varchar(30)` | No | Department classification for this version. |
| `IsActive` | `bit` | No | Active status for this version. |
| `EffectiveFromUtc` | `datetime2(7)` | No | Inclusive beginning of this Type 2 dimension version. |
| `EffectiveToUtc` | `datetime2(7)` | Yes | Exclusive end of this version; null for the current version. |
| `IsCurrent` | `bit` | No | Identifies the current version for the source business key. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\02-provider-department.mmd`, `caboodle\facts\01-encounter.mmd`, `caboodle\facts\02-diagnosis.mmd`, `caboodle\facts\03-procedure.mmd`, `caboodle\facts\04-medication-order.mmd`, `caboodle\facts\05-medication-administration.mmd`, `caboodle\facts\06-lab-result.mmd`, `caboodle\facts\07-appointment.mmd`.

### Caboodle.dbo.DimDate

**Grain:** One UTC calendar date. **History:** Static calendar attributes; no Type 2 columns or origin columns.

**Primary key:** `DateKey` (`int`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactEncounter.ArrivalDateKey` | `DateKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactEncounter.DischargeDateKey` | `DateKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactDiagnosis.DiagnosisDateKey` | `DateKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactProcedure.OrderedDateKey` | `DateKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactProcedure.PerformedDateKey` | `DateKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationOrder.OrderedDateKey` | `DateKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationAdministration.AdministrationDateKey` | `DateKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationAdministration.RecordedDateKey` | `DateKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactLabResult.OrderedDateKey` | `DateKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactLabResult.ResultDateKey` | `DateKey` | No; FK is nullable | Many; zero is also allowed |
| `Caboodle.dbo.FactAppointment.ScheduledDateKey` | `DateKey` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Each incoming FK is a named date role of this same physical calendar dimension, not another date table.
- Optional event dates remain null until the associated event occurs. DimDate is generated, not sourced from a Clarity calendar table, and has no origin or Type 2 columns.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DateKey` | `int` | No | PK; calendar date encoded as `YYYYMMDD`. |
| `CalendarDate` | `date` | No | UQ; actual date value. |
| `CalendarYear` | `smallint` | No | Four-digit calendar year. |
| `CalendarQuarter` | `tinyint` | No | Quarter number, 1-4. |
| `MonthNumber` | `tinyint` | No | Month number, 1-12. |
| `MonthName` | `nvarchar(10)` | No | Month display label. |
| `DayOfMonth` | `tinyint` | No | Day number within the month. |
| `IsoDayOfWeek` | `tinyint` | No | Monday = 1 through Sunday = 7; independent of SQL session settings. |
| `IsWeekend` | `bit` | No | Saturday/Sunday indicator. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\04-calendar.mmd`, `caboodle\facts\01-encounter.mmd`, `caboodle\facts\02-diagnosis.mmd`, `caboodle\facts\03-procedure.mmd`, `caboodle\facts\04-medication-order.mmd`, `caboodle\facts\05-medication-administration.mmd`, `caboodle\facts\06-lab-result.mmd`, `caboodle\facts\07-appointment.mmd`.

### Caboodle.dbo.DimDiagnosis

**Grain:** One diagnosis code within an origin system and code system. **History:** Type 1 description corrections.

**Primary key:** `DiagnosisKey` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactDiagnosis.DiagnosisKey` | `DiagnosisKey` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Unique business key: (OriginSystem, DiagnosisCodeSystem, DiagnosisCode). Description changes use Type 1 corrections.
- Many source diagnosis assignments share a code member. Source assignment IDs belong to FactDiagnosis, not to this catalog dimension.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DiagnosisKey` | `bigint` | No | Surrogate PK for the diagnosis code. |
| `DiagnosisCodeSystem` | `varchar(30)` | No | Code namespace from `Diagnosis`. |
| `DiagnosisCode` | `varchar(30)` | No | Business code from `Diagnosis`; not a diagnosis assignment ID. |
| `DiagnosisDescription` | `nvarchar(250)` | No | Standardized synthetic label for the code. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\03-clinical-code-catalogs.mmd`, `caboodle\facts\02-diagnosis.mmd`.

### Caboodle.dbo.DimProcedure

**Grain:** One procedure code within an origin system and code system. **History:** Type 1 description corrections.

**Primary key:** `ProcedureKey` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactProcedure.ProcedureKey` | `ProcedureKey` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Unique business key: (OriginSystem, ProcedureCodeSystem, ProcedureCode). Description changes use Type 1 corrections.
- ProcedureKey identifies a catalog code; it is not the source procedure event ID.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `ProcedureKey` | `bigint` | No | Surrogate PK for the procedure code. |
| `ProcedureCodeSystem` | `varchar(30)` | No | Code namespace from `[Procedure]`. |
| `ProcedureCode` | `varchar(30)` | No | Business code from `[Procedure]`; not a procedure event ID. |
| `ProcedureDescription` | `nvarchar(250)` | No | Standardized synthetic procedure label. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\03-clinical-code-catalogs.mmd`, `caboodle\facts\03-procedure.mmd`.

### Caboodle.dbo.DimMedication

**Grain:** One medication product code within an origin system and code system. **History:** Type 1 name corrections.

**Primary key:** `MedicationKey` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactMedicationOrder.MedicationKey` | `MedicationKey` | Yes; FK is NOT NULL | Many; zero is also allowed |
| `Caboodle.dbo.FactMedicationAdministration.MedicationKey` | `MedicationKey` | Yes; FK is NOT NULL | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Unique business key: (OriginSystem, MedicationCodeSystem, MedicationCode). Name corrections use Type 1 updates.
- Dose, route, and frequency belong to order/administration events. The catalog is shared by medication-order and medication-administration facts.

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `MedicationKey` | `bigint` | No | Surrogate PK for the medication product. |
| `MedicationCodeSystem` | `varchar(30)` | No | Medication code namespace from `MedicationOrder`. |
| `MedicationCode` | `varchar(50)` | No | Product identifier; not an order identifier. |
| `MedicationName` | `nvarchar(200)` | No | Standardized synthetic medication name. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\03-clinical-code-catalogs.mmd`, `caboodle\facts\04-medication-order.mmd`, `caboodle\facts\05-medication-administration.mmd`.

### Caboodle.dbo.DimCoverage

**Grain:** One historical version of a patient's coverage enrollment, not one payer or plan. **History:** Type 2 for plan attributes, status, and coverage-period changes.

**Primary key:** `CoverageKey` (`bigint`).

**Outgoing Foreign Keys**

None. This table has no declared outgoing FK constraints.

**Incoming Foreign Keys**

| Referencing Table and Column | This Table Key | Child Must Reference a Parent? | Maximum Child Rows per Parent |
| --- | --- | --- | --- |
| `Caboodle.dbo.FactEncounter.CoverageKey` | `CoverageKey` | No; FK is nullable | Many; zero is also allowed |

**Relationship Rules and Logical Associations**

- Logical patient association: (OriginSystem, SourcePatientID) identifies the patient also represented in DimPatient, but not a unique historical PatientKey. No direct patient-dimension FK is declared.
- FactEncounter.CoverageKey is resolved only from the source encounter PrimaryCoverageID, with matching patient, valid coverage period, and event-time dimension version.
- EffectiveDate/TerminationDate describe the enrollment period. EffectiveFromUtc/EffectiveToUtc describe this dimension version; the two intervals have different purposes.
- Business identity is scoped by OriginSystem and the named source entity ID. Historical versions have different surrogate PKs; preserve old PKs when publishing a new version.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceCoverageID` | `Clarity.dbo.Coverage.CoverageID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourcePatientID` | `Clarity.dbo.Patient.PatientID` | Also identifies the patient logically associated with DimPatient; does not select a patient dimension version. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `CoverageKey` | `bigint` | No | Surrogate PK for a coverage version. |
| `SourceCoverageID` | `bigint` | No | Lineage to `Coverage.CoverageID`. |
| `SourcePatientID` | `bigint` | No | Lineage to the enrolled patient; not a FK to a versioned patient dimension. |
| `CoverageNumber` | `varchar(40)` | No | Enrollment business identifier. |
| `PayerCode` | `varchar(30)` | No | Synthetic payer identifier. |
| `PayerName` | `nvarchar(150)` | No | Payer display name for this version. |
| `PlanCode` | `varchar(40)` | No | Plan code within the payer. |
| `PlanName` | `nvarchar(150)` | No | Plan label for this version. |
| `CoverageTypeCode` | `varchar(30)` | No | Insurance category for this version. |
| `EffectiveDate` | `date` | No | Coverage period start; distinct from dimension-version validity. |
| `TerminationDate` | `date` | Yes | Inclusive coverage period end. |
| `CoverageStatus` | `varchar(20)` | No | Enrollment lifecycle status for this version. |
| `EffectiveFromUtc` | `datetime2(7)` | No | Inclusive beginning of this Type 2 dimension version. |
| `EffectiveToUtc` | `datetime2(7)` | Yes | Exclusive end of this version; null for the current version. |
| `IsCurrent` | `bit` | No | Identifies the current version for the source business key. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\dimensions\01-patient-coverage.mmd`, `caboodle\facts\01-encounter.mmd`.

### Caboodle.dbo.FactEncounter

**Grain:** One encounter, updated as its lifecycle progresses (accumulating snapshot). **Dimension lookup time:** `ArrivalAtUtc`.

**Primary key:** `EncounterKey` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `AttendingProviderKey` | `Caboodle.dbo.DimProvider.ProviderKey` | Yes | Each FactEncounter references zero or one DimProvider; each DimProvider can be referenced by zero to many FactEncounter rows. |
| `CoverageKey` | `Caboodle.dbo.DimCoverage.CoverageKey` | Yes | Each FactEncounter references zero or one DimCoverage; each DimCoverage can be referenced by zero to many FactEncounter rows. |
| `ArrivalDateKey` | `Caboodle.dbo.DimDate.DateKey` | No | Each FactEncounter references exactly one DimDate; each DimDate can be referenced by zero to many FactEncounter rows. |
| `DischargeDateKey` | `Caboodle.dbo.DimDate.DateKey` | Yes | Each FactEncounter references zero or one DimDate; each DimDate can be referenced by zero to many FactEncounter rows. |
| `PatientKey` | `Caboodle.dbo.DimPatient.PatientKey` | No | Each FactEncounter references exactly one DimPatient; each DimPatient can be referenced by zero to many FactEncounter rows. |
| `DepartmentKey` | `Caboodle.dbo.DimDepartment.DepartmentKey` | No | Each FactEncounter references exactly one DimDepartment; each DimDepartment can be referenced by zero to many FactEncounter rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce composite uniqueness on (OriginSystem, SourceEncounterID). Replay/correction updates the existing fact rather than creating another row for the same source event.
- PatientKey and DepartmentKey are direct conformed-dimension FKs. SourceEncounterID and other source event IDs are lineage only, not references to FactEncounter or another fact.
- Resolve CoverageKey only from the explicit source primary-coverage assignment at arrival. Nullable discharge date/time represent an encounter that has not closed.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceEncounterID` | `Clarity.dbo.Encounter.EncounterID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `EncounterKey` | `bigint` | No | Surrogate PK for the encounter fact. |
| `SourceEncounterID` | `bigint` | No | Lineage to `Encounter.EncounterID`; replay matching identifier. |
| `EncounterNumber` | `varchar(40)` | No | Source visit/admission business identifier. |
| `AttendingProviderKey` | `bigint` | Yes | FK to `DimProvider.ProviderKey`; attending role. |
| `CoverageKey` | `bigint` | Yes | FK to `DimCoverage.CoverageKey`; assigned primary enrollment version at arrival. |
| `ArrivalDateKey` | `int` | No | FK to `DimDate.DateKey` for arrival. |
| `DischargeDateKey` | `int` | Yes | FK to `DimDate.DateKey`; absent for open encounters. |
| `ArrivalAtUtc` | `datetime2(7)` | No | Encounter start timestamp. |
| `DischargeAtUtc` | `datetime2(7)` | Yes | Encounter end timestamp. |
| `EncounterTypeCode` | `varchar(30)` | No | Visit classification. |
| `EncounterStatus` | `varchar(20)` | No | Current encounter status. |
| `DischargeDispositionCode` | `varchar(30)` | Yes | Discharge classification. |
| `LengthOfStayMinutes` | `decimal(18,2)` | Yes | Derived elapsed duration; null until discharge. |
| `EncounterCount` | `int` | No | Constant `1` at this grain; filter deleted/canceled rows as required by the metric. |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\facts\01-encounter.mmd`.

### Caboodle.dbo.FactDiagnosis

**Grain:** One diagnosis assignment, not one distinct code per encounter. **Dimension lookup time:** `DiagnosedAtUtc`.

**Primary key:** `DiagnosisFactKey` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `DiagnosisKey` | `Caboodle.dbo.DimDiagnosis.DiagnosisKey` | No | Each FactDiagnosis references exactly one DimDiagnosis; each DimDiagnosis can be referenced by zero to many FactDiagnosis rows. |
| `DiagnosingProviderKey` | `Caboodle.dbo.DimProvider.ProviderKey` | Yes | Each FactDiagnosis references zero or one DimProvider; each DimProvider can be referenced by zero to many FactDiagnosis rows. |
| `DiagnosisDateKey` | `Caboodle.dbo.DimDate.DateKey` | No | Each FactDiagnosis references exactly one DimDate; each DimDate can be referenced by zero to many FactDiagnosis rows. |
| `PatientKey` | `Caboodle.dbo.DimPatient.PatientKey` | No | Each FactDiagnosis references exactly one DimPatient; each DimPatient can be referenced by zero to many FactDiagnosis rows. |
| `DepartmentKey` | `Caboodle.dbo.DimDepartment.DepartmentKey` | No | Each FactDiagnosis references exactly one DimDepartment; each DimDepartment can be referenced by zero to many FactDiagnosis rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce composite uniqueness on (OriginSystem, SourceDiagnosisID). Replay/correction updates the existing fact rather than creating another row for the same source event.
- PatientKey and DepartmentKey are direct conformed-dimension FKs. SourceEncounterID and other source event IDs are lineage only, not references to FactEncounter or another fact.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceDiagnosisID` | `Clarity.dbo.Diagnosis.DiagnosisID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceEncounterID` | `Clarity.dbo.Encounter.EncounterID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DiagnosisFactKey` | `bigint` | No | Surrogate PK for the assignment fact. |
| `SourceDiagnosisID` | `bigint` | No | Lineage to `Diagnosis.DiagnosisID`; replay matching identifier. |
| `SourceEncounterID` | `bigint` | No | Source encounter identifier for lineage; not a FK to another fact. |
| `DiagnosisKey` | `bigint` | No | FK to `DimDiagnosis.DiagnosisKey`. |
| `DiagnosingProviderKey` | `bigint` | Yes | FK to `DimProvider.ProviderKey`. |
| `DiagnosisDateKey` | `int` | No | FK to `DimDate.DateKey`. |
| `DiagnosedAtUtc` | `datetime2(7)` | No | Assignment event time. |
| `DiagnosisSequence` | `smallint` | No | Source encounter ordering. |
| `IsPrimary` | `bit` | No | Source primary-assignment flag. |
| `DiagnosisStatus` | `varchar(20)` | No | Assignment lifecycle status. |
| `DiagnosisCount` | `int` | No | Constant `1` per assignment. |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\facts\02-diagnosis.mmd`.

### Caboodle.dbo.FactProcedure

**Grain:** One procedure event, including orders not yet performed. **Dimension lookup time:** `PerformedAtUtc`, otherwise `OrderedAtUtc`.

**Primary key:** `ProcedureFactKey` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `ProcedureKey` | `Caboodle.dbo.DimProcedure.ProcedureKey` | No | Each FactProcedure references exactly one DimProcedure; each DimProcedure can be referenced by zero to many FactProcedure rows. |
| `PerformingProviderKey` | `Caboodle.dbo.DimProvider.ProviderKey` | Yes | Each FactProcedure references zero or one DimProvider; each DimProvider can be referenced by zero to many FactProcedure rows. |
| `OrderedDateKey` | `Caboodle.dbo.DimDate.DateKey` | No | Each FactProcedure references exactly one DimDate; each DimDate can be referenced by zero to many FactProcedure rows. |
| `PerformedDateKey` | `Caboodle.dbo.DimDate.DateKey` | Yes | Each FactProcedure references zero or one DimDate; each DimDate can be referenced by zero to many FactProcedure rows. |
| `PatientKey` | `Caboodle.dbo.DimPatient.PatientKey` | No | Each FactProcedure references exactly one DimPatient; each DimPatient can be referenced by zero to many FactProcedure rows. |
| `DepartmentKey` | `Caboodle.dbo.DimDepartment.DepartmentKey` | No | Each FactProcedure references exactly one DimDepartment; each DimDepartment can be referenced by zero to many FactProcedure rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce composite uniqueness on (OriginSystem, SourceProcedureID). Replay/correction updates the existing fact rather than creating another row for the same source event.
- PatientKey and DepartmentKey are direct conformed-dimension FKs. SourceEncounterID and other source event IDs are lineage only, not references to FactEncounter or another fact.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceProcedureID` | `Clarity.dbo.Procedure.ProcedureID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceEncounterID` | `Clarity.dbo.Encounter.EncounterID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `ProcedureFactKey` | `bigint` | No | Surrogate PK for the procedure event. |
| `SourceProcedureID` | `bigint` | No | Lineage to `[Procedure].ProcedureID`. |
| `SourceEncounterID` | `bigint` | No | Source encounter identifier for lineage; not a FK to another fact. |
| `ProcedureKey` | `bigint` | No | FK to `DimProcedure.ProcedureKey`. |
| `PerformingProviderKey` | `bigint` | Yes | FK to `DimProvider.ProviderKey`. |
| `OrderedDateKey` | `int` | No | FK to `DimDate.DateKey`. |
| `PerformedDateKey` | `int` | Yes | FK to `DimDate.DateKey`; null until performed. |
| `OrderedAtUtc` | `datetime2(7)` | No | Procedure order time. |
| `PerformedAtUtc` | `datetime2(7)` | Yes | Actual procedure time. |
| `ProcedureStatus` | `varchar(20)` | No | Event lifecycle status. |
| `ProcedureCount` | `int` | No | Constant `1` per procedure event; completed counts require a status filter. |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\facts\03-procedure.mmd`.

### Caboodle.dbo.FactMedicationOrder

**Grain:** One medication order. **Dimension lookup time:** `OrderedAtUtc`.

**Primary key:** `MedicationOrderKey` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `MedicationKey` | `Caboodle.dbo.DimMedication.MedicationKey` | No | Each FactMedicationOrder references exactly one DimMedication; each DimMedication can be referenced by zero to many FactMedicationOrder rows. |
| `OrderingProviderKey` | `Caboodle.dbo.DimProvider.ProviderKey` | No | Each FactMedicationOrder references exactly one DimProvider; each DimProvider can be referenced by zero to many FactMedicationOrder rows. |
| `OrderedDateKey` | `Caboodle.dbo.DimDate.DateKey` | No | Each FactMedicationOrder references exactly one DimDate; each DimDate can be referenced by zero to many FactMedicationOrder rows. |
| `PatientKey` | `Caboodle.dbo.DimPatient.PatientKey` | No | Each FactMedicationOrder references exactly one DimPatient; each DimPatient can be referenced by zero to many FactMedicationOrder rows. |
| `DepartmentKey` | `Caboodle.dbo.DimDepartment.DepartmentKey` | No | Each FactMedicationOrder references exactly one DimDepartment; each DimDepartment can be referenced by zero to many FactMedicationOrder rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce composite uniqueness on (OriginSystem, SourceMedicationOrderID). Replay/correction updates the existing fact rather than creating another row for the same source event.
- PatientKey and DepartmentKey are direct conformed-dimension FKs. SourceEncounterID and other source event IDs are lineage only, not references to FactEncounter or another fact.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceMedicationOrderID` | `Clarity.dbo.MedicationOrder.MedicationOrderID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceEncounterID` | `Clarity.dbo.Encounter.EncounterID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `MedicationOrderKey` | `bigint` | No | Surrogate PK for the order fact. |
| `SourceMedicationOrderID` | `bigint` | No | Lineage to `MedicationOrder.MedicationOrderID`. |
| `SourceEncounterID` | `bigint` | No | Source encounter identifier for lineage; not a FK to another fact. |
| `MedicationKey` | `bigint` | No | FK to `DimMedication.MedicationKey`. |
| `OrderingProviderKey` | `bigint` | No | FK to `DimProvider.ProviderKey`. |
| `OrderedDateKey` | `int` | No | FK to `DimDate.DateKey`. |
| `OrderedAtUtc` | `datetime2(7)` | No | Medication order time. |
| `StartAtUtc` | `datetime2(7)` | Yes | Intended treatment start. |
| `EndAtUtc` | `datetime2(7)` | Yes | Intended or actual treatment end. |
| `OrderedDose` | `decimal(18,4)` | Yes | Source structured ordered quantity. |
| `DoseUnit` | `varchar(30)` | Yes | Quantity unit; retain when analyzing doses. |
| `RouteCode` | `varchar(30)` | Yes | Ordered route. |
| `FrequencyCode` | `varchar(30)` | Yes | Ordered frequency. |
| `OrderStatus` | `varchar(20)` | No | Order lifecycle status. |
| `OrderCount` | `int` | No | Constant `1` per order. |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\facts\04-medication-order.mmd`.

### Caboodle.dbo.FactMedicationAdministration

**Grain:** One documented administration or non-administration event. **Dimension lookup time:** `AdministeredAtUtc`, otherwise `RecordedAtUtc`.

**Primary key:** `MedicationAdministrationKey` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `MedicationKey` | `Caboodle.dbo.DimMedication.MedicationKey` | No | Each FactMedicationAdministration references exactly one DimMedication; each DimMedication can be referenced by zero to many FactMedicationAdministration rows. |
| `AdministeringProviderKey` | `Caboodle.dbo.DimProvider.ProviderKey` | Yes | Each FactMedicationAdministration references zero or one DimProvider; each DimProvider can be referenced by zero to many FactMedicationAdministration rows. |
| `AdministrationDateKey` | `Caboodle.dbo.DimDate.DateKey` | Yes | Each FactMedicationAdministration references zero or one DimDate; each DimDate can be referenced by zero to many FactMedicationAdministration rows. |
| `RecordedDateKey` | `Caboodle.dbo.DimDate.DateKey` | No | Each FactMedicationAdministration references exactly one DimDate; each DimDate can be referenced by zero to many FactMedicationAdministration rows. |
| `PatientKey` | `Caboodle.dbo.DimPatient.PatientKey` | No | Each FactMedicationAdministration references exactly one DimPatient; each DimPatient can be referenced by zero to many FactMedicationAdministration rows. |
| `DepartmentKey` | `Caboodle.dbo.DimDepartment.DepartmentKey` | No | Each FactMedicationAdministration references exactly one DimDepartment; each DimDepartment can be referenced by zero to many FactMedicationAdministration rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce composite uniqueness on (OriginSystem, SourceMedicationAdministrationID). Replay/correction updates the existing fact rather than creating another row for the same source event.
- PatientKey and DepartmentKey are direct conformed-dimension FKs. SourceEncounterID and other source event IDs are lineage only, not references to FactEncounter or another fact.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceMedicationAdministrationID` | `Clarity.dbo.MedicationAdministration.MedicationAdministrationID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceEncounterID` | `Clarity.dbo.Encounter.EncounterID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceMedicationOrderID` | `Clarity.dbo.MedicationOrder.MedicationOrderID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `MedicationAdministrationKey` | `bigint` | No | Surrogate PK for the administration fact. |
| `SourceMedicationAdministrationID` | `bigint` | No | Lineage to `MedicationAdministration.MedicationAdministrationID`. |
| `SourceEncounterID` | `bigint` | No | Source encounter identifier resolved through the medication order. |
| `SourceMedicationOrderID` | `bigint` | No | Degenerate order identifier for lineage; no fact-to-fact FK. |
| `MedicationKey` | `bigint` | No | FK to `DimMedication.MedicationKey`, resolved through the source order. |
| `AdministeringProviderKey` | `bigint` | Yes | FK to `DimProvider.ProviderKey`. |
| `AdministrationDateKey` | `int` | Yes | FK to `DimDate.DateKey` for the actual administration date. |
| `RecordedDateKey` | `int` | No | FK to `DimDate.DateKey` for documentation. |
| `ScheduledAtUtc` | `datetime2(7)` | Yes | Planned event time. |
| `RecordedAtUtc` | `datetime2(7)` | No | Documentation time, including non-administrations. |
| `AdministeredAtUtc` | `datetime2(7)` | Yes | Actual administration time. |
| `AdministeredDose` | `decimal(18,4)` | Yes | Actual quantity administered. |
| `DoseUnit` | `varchar(30)` | Yes | Unit for the administered quantity. |
| `AdministrationStatus` | `varchar(20)` | No | Distinguishes given, held, refused, and other outcomes. |
| `AdministrationEventCount` | `int` | No | Constant `1` per documented event, not necessarily a dose given. |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\facts\05-medication-administration.mmd`.

### Caboodle.dbo.FactLabResult

**Grain:** One laboratory result component, including pending components. **Dimension lookup time:** `ResultedAtUtc`, otherwise the parent order's `OrderedAtUtc`.

**Primary key:** `LabResultKey` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `OrderingProviderKey` | `Caboodle.dbo.DimProvider.ProviderKey` | No | Each FactLabResult references exactly one DimProvider; each DimProvider can be referenced by zero to many FactLabResult rows. |
| `OrderedDateKey` | `Caboodle.dbo.DimDate.DateKey` | No | Each FactLabResult references exactly one DimDate; each DimDate can be referenced by zero to many FactLabResult rows. |
| `ResultDateKey` | `Caboodle.dbo.DimDate.DateKey` | Yes | Each FactLabResult references zero or one DimDate; each DimDate can be referenced by zero to many FactLabResult rows. |
| `PatientKey` | `Caboodle.dbo.DimPatient.PatientKey` | No | Each FactLabResult references exactly one DimPatient; each DimPatient can be referenced by zero to many FactLabResult rows. |
| `DepartmentKey` | `Caboodle.dbo.DimDepartment.DepartmentKey` | No | Each FactLabResult references exactly one DimDepartment; each DimDepartment can be referenced by zero to many FactLabResult rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce composite uniqueness on (OriginSystem, SourceLaboratoryResultID). Replay/correction updates the existing fact rather than creating another row for the same source event.
- PatientKey and DepartmentKey are direct conformed-dimension FKs. SourceEncounterID and other source event IDs are lineage only, not references to FactEncounter or another fact.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceLaboratoryResultID` | `Clarity.dbo.LaboratoryResult.LaboratoryResultID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceEncounterID` | `Clarity.dbo.Encounter.EncounterID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceLaboratoryOrderID` | `Clarity.dbo.LaboratoryOrder.LaboratoryOrderID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `LabResultKey` | `bigint` | No | Surrogate PK for the result component fact. |
| `SourceLaboratoryResultID` | `bigint` | No | Lineage to `LaboratoryResult.LaboratoryResultID`. |
| `SourceEncounterID` | `bigint` | No | Source encounter identifier resolved through the laboratory order. |
| `SourceLaboratoryOrderID` | `bigint` | No | Degenerate parent order identifier for lineage. |
| `OrderingProviderKey` | `bigint` | No | FK to `DimProvider.ProviderKey`, resolved through the order. |
| `OrderedDateKey` | `int` | No | FK to `DimDate.DateKey` for the parent order. |
| `ResultDateKey` | `int` | Yes | FK to `DimDate.DateKey`; absent for pending results. |
| `OrderedAtUtc` | `datetime2(7)` | No | Parent laboratory order time. |
| `ResultedAtUtc` | `datetime2(7)` | Yes | Result event time. |
| `TestCode` | `varchar(40)` | No | Ordered test/panel code from `LaboratoryOrder`. |
| `ComponentCode` | `varchar(40)` | No | Observation component code. |
| `ComponentName` | `nvarchar(200)` | No | Component display name. |
| `NumericValue` | `decimal(18,6)` | Yes | Numeric result; not additive across observations. |
| `TextValue` | `nvarchar(1000)` | Yes | Qualitative result or explanation. |
| `ResultUnit` | `varchar(30)` | Yes | Numeric result unit. |
| `ReferenceLow` | `decimal(18,6)` | Yes | Synthetic lower reference bound. |
| `ReferenceHigh` | `decimal(18,6)` | Yes | Synthetic upper reference bound. |
| `AbnormalFlag` | `varchar(20)` | Yes | Source-provided synthetic result classification. |
| `ResultStatus` | `varchar(20)` | No | Result lifecycle status. |
| `ResultCount` | `int` | No | Constant `1` per component; final-result reporting requires a status filter. |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\facts\06-lab-result.mmd`.

### Caboodle.dbo.FactAppointment

**Grain:** One scheduled appointment, whether or not an encounter occurs. **Dimension lookup time:** `ScheduledStartAtUtc`.

**Primary key:** `AppointmentKey` (`bigint`).

**Outgoing Foreign Keys**

| FK Column | References | Nullable | Cardinality and Meaning |
| --- | --- | --- | --- |
| `ProviderKey` | `Caboodle.dbo.DimProvider.ProviderKey` | Yes | Each FactAppointment references zero or one DimProvider; each DimProvider can be referenced by zero to many FactAppointment rows. |
| `ScheduledDateKey` | `Caboodle.dbo.DimDate.DateKey` | No | Each FactAppointment references exactly one DimDate; each DimDate can be referenced by zero to many FactAppointment rows. |
| `PatientKey` | `Caboodle.dbo.DimPatient.PatientKey` | No | Each FactAppointment references exactly one DimPatient; each DimPatient can be referenced by zero to many FactAppointment rows. |
| `DepartmentKey` | `Caboodle.dbo.DimDepartment.DepartmentKey` | No | Each FactAppointment references exactly one DimDepartment; each DimDepartment can be referenced by zero to many FactAppointment rows. |

**Incoming Foreign Keys**

None. No proposed table has a direct FK to this table.

**Relationship Rules and Logical Associations**

- Enforce composite uniqueness on (OriginSystem, SourceAppointmentID). Replay/correction updates the existing fact rather than creating another row for the same source event.
- PatientKey and DepartmentKey are direct conformed-dimension FKs. SourceEncounterID and other source event IDs are lineage only, not references to FactEncounter or another fact.
- An unlinked appointment can have a null SourceEncounterID. Its patient and department come from scheduling, not from an invented encounter.

**Source Lineage (Not Foreign Keys)**

| Local Column | Origin in the Clarity Simulation | Meaning |
| --- | --- | --- |
| `SourceAppointmentID` | `Clarity.dbo.Appointment.AppointmentID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |
| `SourceEncounterID` | `Clarity.dbo.Encounter.EncounterID` | Retained source identity, scoped by OriginSystem; no cross-database or fact-to-fact FK. |

**Complete Column Dictionary**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `AppointmentKey` | `bigint` | No | Surrogate PK for the appointment fact. |
| `SourceAppointmentID` | `bigint` | No | Lineage to `Appointment.AppointmentID`. |
| `SourceEncounterID` | `bigint` | Yes | Linked source encounter identifier, if any; not a FK to another fact. |
| `AppointmentNumber` | `varchar(40)` | No | Scheduling business identifier. |
| `ProviderKey` | `bigint` | Yes | FK to `DimProvider.ProviderKey`; scheduled provider. |
| `ScheduledDateKey` | `int` | No | FK to `DimDate.DateKey`. |
| `ScheduledStartAtUtc` | `datetime2(7)` | No | Scheduled start. |
| `ScheduledEndAtUtc` | `datetime2(7)` | No | Scheduled end. |
| `AppointmentTypeCode` | `varchar(30)` | No | Scheduling category. |
| `AppointmentStatus` | `varchar(20)` | No | Includes canceled visits and no-shows. |
| `CanceledAtUtc` | `datetime2(7)` | Yes | Cancellation event time. |
| `ScheduledDurationMinutes` | `decimal(18,2)` | No | Derived scheduled duration. |
| `AppointmentCount` | `int` | No | Constant `1` per appointment. |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Focused Mermaid diagrams:** `caboodle\facts\07-appointment.mmd`.

## Cross-System Mapping and Reconciliation

| Clarity Source | Caboodle Target | Expected Relationship |
| --- | --- | --- |
| `Patient` | `DimPatient` | One patient to one or more historical versions. |
| `Provider` | `DimProvider` | One provider to one or more historical versions. |
| `Department` | `DimDepartment` | One department to one or more historical versions. |
| Calendar generation | `DimDate` | One row per generated calendar date; no Clarity source table. |
| Distinct diagnosis code-system/code pairs | `DimDiagnosis` | Many assignments can share one catalog member. |
| Distinct procedure code-system/code pairs | `DimProcedure` | Many procedure events can share one catalog member. |
| Distinct medication code-system/code pairs | `DimMedication` | Many orders can share one catalog member. |
| `Coverage` | `DimCoverage` | One enrollment to one or more historical versions. |
| `Encounter` | `FactEncounter` | One source encounter to one fact row. |
| `Diagnosis` | `FactDiagnosis` | One assignment to one fact row. |
| `[Procedure]` | `FactProcedure` | One procedure event to one fact row. |
| `MedicationOrder` | `FactMedicationOrder` | One order to one fact row. |
| `MedicationAdministration` plus parent order | `FactMedicationAdministration` | One administration record to one fact row. |
| `LaboratoryResult` plus parent order | `FactLabResult` | One result component to one fact row; one order can produce many components. |
| `Appointment` | `FactAppointment` | One appointment to one fact row, including unlinked appointments. |
| `VitalSign` | No initial analytical fact | Retained in Clarity Bronze ingestion scope. |

Reconcile source identities and soft-delete/status filters at a consistent simulated transformation checkpoint. Account explicitly for quarantined records, transformation lag, SCD version expansion, and catalog deduplication. Reconcile each Azure SQL table to its Fabric Bronze target independently; do not compare Clarity patient counts with all historical `DimPatient` versions or laboratory order counts with result-component counts.

These mappings are derivations and lineage, not FK constraints across the two Azure SQL databases.

## Review and Maintenance

- Review the outgoing/incoming FK lists together with the per-table logical-association and lineage notes; an absent drawn table does not mean an absent FK column.
- Native sources and matching SVGs remain under clarity, caboodle\facts, caboodle\dimensions, and shared. The older clarity.md and caboodle.md are consolidated diagram references, not replacements for the focused native diagrams.
- Keep plan.md, this reference, Mermaid FK columns/edges, and rendered previews synchronized when a model decision changes. Do not mark the model approved solely because the diagrams render.
