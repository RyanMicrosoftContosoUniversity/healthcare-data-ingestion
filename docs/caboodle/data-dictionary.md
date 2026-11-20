# Caboodle Source Data Dictionary

The user approved this synthetic source model. Column definitions below are exported from the local design; this is not a proprietary Epic specification.

> Population decision: generate both sources independently with shared synthetic identities. Earlier Clarity-to-Caboodle ETL language below is historical mapping context, not an instruction to build that ETL. Source-to-Bronze reconciliation is performed independently for each source.

**Proposed dimensions:**

- `DimPatient`
- `DimProvider`
- `DimDepartment`
- `DimDate`
- `DimDiagnosis`
- `DimProcedure`
- `DimMedication`
- `DimCoverage`

**Proposed facts:**

- `FactEncounter`
- `FactDiagnosis`
- `FactProcedure`
- `FactMedicationOrder`
- `FactMedicationAdministration`
- `FactLabResult`
- `FactAppointment`

**Model requirements:**

- Define star schemas and fact grain explicitly.
- Define surrogate keys, natural/business keys, and dimension relationships.
- Include historical tracking and selected slowly changing dimensions.
- Map analytical entities back to representative Clarity source entities.
- Document where transformation or aggregation legitimately changes row counts.

##### Analytical Data Dictionary Conventions

Caboodle remains an analytical source simulation, not a second operational schema. The approved model contains eight dimensions and seven facts in `dbo` in the separate Caboodle database. Generate it independently with consistent shared synthetic identities; do not build Clarity-to-Caboodle ETL. The reusable Fabric ingestion engine ingests each source independently.

All dimension and fact keys are generated `bigint` surrogate PKs unless explicitly stated otherwise. Source identifiers are retained for lineage and replay matching, not reused as surrogate keys. `DimDate.DateKey` is an `int` in `YYYYMMDD` form. SQL types describe the Azure SQL source databases; destination type mappings must be validated separately.

**Shared columns on every Caboodle table, including `DimDate`:**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `EtlCreatedAtUtc` | `datetime2(7)` | No | Timestamp when the row was first published to Caboodle. |
| `EtlModifiedAtUtc` | `datetime2(7)` | No | Updated on every Caboodle row change, including SCD expiration and delete propagation; proposed Fabric extraction watermark. |
| `EtlBatchID` | `uniqueidentifier` | No | Identifier of the simulated transformation batch that last changed the row. |

**Additional shared columns on every Caboodle table except `DimDate`:**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `OriginSystem` | `varchar(30)` | No | Business lineage system; initially `Clarity`. This is distinct from ingestion metadata `SourceSystem = Caboodle`. |
| `OriginModifiedAtUtc` | `datetime2(7)` | No | Latest contributing source modification timestamp; for lineage, not the Caboodle extraction watermark. |
| `IsDeleted` | `bit` | No | Indicates a deleted source event/entity or retired catalog member without physically removing history. |

**Additional history columns on `DimPatient`, `DimProvider`, `DimDepartment`, and `DimCoverage`:**

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `EffectiveFromUtc` | `datetime2(7)` | No | Inclusive beginning of this Type 2 dimension version. |
| `EffectiveToUtc` | `datetime2(7)` | Yes | Exclusive end of this version; null for the current version. |
| `IsCurrent` | `bit` | No | Identifies the current version for the source business key. |

These shared columns are part of each applicable table's definition. Type 2 validity represents the synthetic attribute-change timeline, not the time Fabric ingested the row. The simulator must provide deterministic change-effective times; historical attributes before the initial snapshot must not be invented.

##### DimPatient

**Grain:** One historical version of one patient. **History:** Type 2 for selected demographic/location/status changes; corrections follow an explicitly documented policy.

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

##### DimProvider

**Grain:** One historical version of a provider. **History:** Type 2 for specialty, role, and active-status changes.

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `ProviderKey` | `bigint` | No | Surrogate PK for a provider version. |
| `SourceProviderID` | `bigint` | No | Lineage to `Provider.ProviderID`. |
| `ProviderCode` | `varchar(30)` | No | Stable provider business identifier. |
| `DisplayName` | `nvarchar(200)` | No | Provider display name for this version. |
| `ProviderTypeCode` | `varchar(30)` | No | Provider role/category for this version. |
| `SpecialtyCode` | `varchar(30)` | Yes | Specialty for this version. |
| `IsActive` | `bit` | No | Active status for this version. |

##### DimDepartment

**Grain:** One historical version of a department. **History:** Type 2 for facility, classification, and active-status changes.

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DepartmentKey` | `bigint` | No | Surrogate PK for a department version. |
| `SourceDepartmentID` | `bigint` | No | Lineage to `Department.DepartmentID`. |
| `DepartmentCode` | `varchar(30)` | No | Stable department business code. |
| `DepartmentName` | `nvarchar(150)` | No | Department name for this version. |
| `FacilityCode` | `varchar(30)` | No | Owning facility for this version. |
| `DepartmentTypeCode` | `varchar(30)` | No | Department classification for this version. |
| `IsActive` | `bit` | No | Active status for this version. |

##### DimDate

**Grain:** One UTC calendar date. **History:** Static calendar attributes; no Type 2 columns or origin columns.

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

##### DimDiagnosis

**Grain:** One diagnosis code within an origin system and code system. **History:** Type 1 description corrections.

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `DiagnosisKey` | `bigint` | No | Surrogate PK for the diagnosis code. |
| `DiagnosisCodeSystem` | `varchar(30)` | No | Code namespace from `Diagnosis`. |
| `DiagnosisCode` | `varchar(30)` | No | Business code from `Diagnosis`; not a diagnosis assignment ID. |
| `DiagnosisDescription` | `nvarchar(250)` | No | Standardized synthetic label for the code. |

##### DimProcedure

**Grain:** One procedure code within an origin system and code system. **History:** Type 1 description corrections.

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `ProcedureKey` | `bigint` | No | Surrogate PK for the procedure code. |
| `ProcedureCodeSystem` | `varchar(30)` | No | Code namespace from `[Procedure]`. |
| `ProcedureCode` | `varchar(30)` | No | Business code from `[Procedure]`; not a procedure event ID. |
| `ProcedureDescription` | `nvarchar(250)` | No | Standardized synthetic procedure label. |

##### DimMedication

**Grain:** One medication product code within an origin system and code system. **History:** Type 1 name corrections.

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `MedicationKey` | `bigint` | No | Surrogate PK for the medication product. |
| `MedicationCodeSystem` | `varchar(30)` | No | Medication code namespace from `MedicationOrder`. |
| `MedicationCode` | `varchar(50)` | No | Product identifier; not an order identifier. |
| `MedicationName` | `nvarchar(200)` | No | Standardized synthetic medication name. |

Dose, unit, route, and frequency belong to orders or administration events, not this product dimension. The simulator must keep code-to-label mappings consistent and explicitly retire catalog members; deleting one event must not retire a code used elsewhere.

##### DimCoverage

**Grain:** One historical version of a patient's coverage enrollment, not one payer or plan. **History:** Type 2 for plan attributes, status, and coverage-period changes.

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

`FactEncounter.CoverageKey` references the enrollment explicitly assigned by `Encounter.PrimaryCoverageID`. Do not join facts to all coverage versions or enrollments using patient ID alone.

##### Shared Fact Columns

Every fact includes the shared Caboodle audit/origin columns above and these conformed dimension references:

| Column | SQL Data Type | Nullable | Purpose |
| --- | --- | --- | --- |
| `PatientKey` | `bigint` | No | FK to the event-time version of `DimPatient.PatientKey`. |
| `DepartmentKey` | `bigint` | No | FK to the event-time version of `DimDepartment.DepartmentKey`. |

Each fact below has its own surrogate PK. Enforce uniqueness on `(OriginSystem, SourceEventID)` using that table's named source event ID column; `FactEncounter` uses `SourceEncounterID`. Corrections update the existing fact instead of inserting a duplicate.

##### FactEncounter

**Grain:** One encounter, updated as its lifecycle progresses (accumulating snapshot). **Dimension lookup time:** `ArrivalAtUtc`.

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

##### FactDiagnosis

**Grain:** One diagnosis assignment, not one distinct code per encounter. **Dimension lookup time:** `DiagnosedAtUtc`.

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

##### FactProcedure

**Grain:** One procedure event, including orders not yet performed. **Dimension lookup time:** `PerformedAtUtc`, otherwise `OrderedAtUtc`.

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

##### FactMedicationOrder

**Grain:** One medication order. **Dimension lookup time:** `OrderedAtUtc`.

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

##### FactMedicationAdministration

**Grain:** One documented administration or non-administration event. **Dimension lookup time:** `AdministeredAtUtc`, otherwise `RecordedAtUtc`.

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

##### FactLabResult

**Grain:** One laboratory result component, including pending components. **Dimension lookup time:** `ResultedAtUtc`, otherwise the parent order's `OrderedAtUtc`.

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

##### FactAppointment

**Grain:** One scheduled appointment, whether or not an encounter occurs. **Dimension lookup time:** `ScheduledStartAtUtc`.

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

##### Dimensional Relationships and Transformation Rules

- Fact dimension-key columns are FKs to their named dimensions. Dimensions load before dependent facts; facts do not require joins to other facts to resolve their patient, department, provider, or catalog dimensions.
- For Type 2 dimensions, resolve keys using the fact's documented lookup time and the half-open interval `[EffectiveFromUtc, EffectiveToUtc)`. Match origin system and source identifier as well as time. Initial versions must cover the seeded event horizon or unmatched events must be quarantined.
- Enforce one current version per `(OriginSystem, SourceEntityID)` and no overlapping version intervals. Use each dimension's named source ID column; preserve older surrogate keys when creating new versions.
- `DimDiagnosis`, `DimProcedure`, and `DimMedication` have unique `(OriginSystem, CodeSystem, Code)` business keys using their respective column names. Resolve conflicting labels deterministically and record the conflict rather than multiplying catalog rows.
- Nullable provider keys represent genuinely unassigned providers. A non-null source provider that cannot be resolved is an error, not permission to silently write null. Quarantine unresolved required references for bounded replay after their dimensions arrive.
- Derive patient/department references from the encounter for clinical events and from the appointment for scheduled visits. Administration events traverse their medication order; laboratory results traverse their laboratory order.
- When source event times, parent links, or dimension history are corrected, recompute affected dimension keys and derived measures. A change to a contributing parent must refresh dependent Caboodle rows and their `EtlModifiedAtUtc`, even when the child source row itself did not change.
- Propagate source soft deletes without removing historical dimension versions or breaking fact references. Update all affected rows' publication timestamps; normal business counts exclude `IsDeleted = 1`.
- Date-key columns match the UTC dates of their associated timestamps. Optional, not-yet-occurred events retain null date keys rather than fabricated dates.
- Count measures are additive at their documented event grain after status/deletion filters. Doses require compatible medication/unit groupings; lab values and vital observations must not be blindly summed.
- Resolve `FactEncounter.CoverageKey` only from the source encounter's explicit primary coverage assignment, including patient, coverage-period, and dimension-version validation. `VitalSign` and `LaboratoryOrder` are ingested into Bronze but have no standalone Caboodle fact in the initial scope; laboratory orders contribute to `FactLabResult`.

##### Clarity-to-Caboodle Mapping and Reconciliation

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
