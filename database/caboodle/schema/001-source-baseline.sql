-- Generated Caboodle source baseline; do not edit by hand.

-- For an empty source database with the declared schema already present.

-- Not an upgrade migration; remaining integrity/write-path work: database/README.md.

SET XACT_ABORT ON;
BEGIN TRANSACTION;

CREATE TABLE [dbo].[DimPatient] (
    [PatientKey] bigint NOT NULL,
    [SourcePatientID] bigint NOT NULL,
    [MedicalRecordNumber] varchar(30) NOT NULL,
    [FirstName] nvarchar(100) NOT NULL,
    [LastName] nvarchar(100) NOT NULL,
    [BirthDate] date NOT NULL,
    [AdministrativeSexCode] varchar(20) NOT NULL,
    [City] nvarchar(100) NULL,
    [StateCode] varchar(10) NULL,
    [PostalCode] varchar(20) NULL,
    [DeathDate] date NULL,
    [PatientStatus] varchar(20) NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [EffectiveFromUtc] datetime2(7) NOT NULL,
    [EffectiveToUtc] datetime2(7) NULL,
    [IsCurrent] bit NOT NULL,
    CONSTRAINT [PK_DimPatient] PRIMARY KEY ([PatientKey])
);

CREATE TABLE [dbo].[DimProvider] (
    [ProviderKey] bigint NOT NULL,
    [SourceProviderID] bigint NOT NULL,
    [ProviderCode] varchar(30) NOT NULL,
    [DisplayName] nvarchar(200) NOT NULL,
    [ProviderTypeCode] varchar(30) NOT NULL,
    [SpecialtyCode] varchar(30) NULL,
    [IsActive] bit NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [EffectiveFromUtc] datetime2(7) NOT NULL,
    [EffectiveToUtc] datetime2(7) NULL,
    [IsCurrent] bit NOT NULL,
    CONSTRAINT [PK_DimProvider] PRIMARY KEY ([ProviderKey])
);

CREATE TABLE [dbo].[DimDepartment] (
    [DepartmentKey] bigint NOT NULL,
    [SourceDepartmentID] bigint NOT NULL,
    [DepartmentCode] varchar(30) NOT NULL,
    [DepartmentName] nvarchar(150) NOT NULL,
    [FacilityCode] varchar(30) NOT NULL,
    [DepartmentTypeCode] varchar(30) NOT NULL,
    [IsActive] bit NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [EffectiveFromUtc] datetime2(7) NOT NULL,
    [EffectiveToUtc] datetime2(7) NULL,
    [IsCurrent] bit NOT NULL,
    CONSTRAINT [PK_DimDepartment] PRIMARY KEY ([DepartmentKey])
);

CREATE TABLE [dbo].[DimDate] (
    [DateKey] int NOT NULL,
    [CalendarDate] date NOT NULL,
    [CalendarYear] smallint NOT NULL,
    [CalendarQuarter] tinyint NOT NULL,
    [MonthNumber] tinyint NOT NULL,
    [MonthName] nvarchar(10) NOT NULL,
    [DayOfMonth] tinyint NOT NULL,
    [IsoDayOfWeek] tinyint NOT NULL,
    [IsWeekend] bit NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    CONSTRAINT [PK_DimDate] PRIMARY KEY ([DateKey]),
    CONSTRAINT [UQ_DimDate_CalendarDate] UNIQUE ([CalendarDate])
);

CREATE TABLE [dbo].[DimDiagnosis] (
    [DiagnosisKey] bigint NOT NULL,
    [DiagnosisCodeSystem] varchar(30) NOT NULL,
    [DiagnosisCode] varchar(30) NOT NULL,
    [DiagnosisDescription] nvarchar(250) NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_DimDiagnosis] PRIMARY KEY ([DiagnosisKey])
);

CREATE TABLE [dbo].[DimProcedure] (
    [ProcedureKey] bigint NOT NULL,
    [ProcedureCodeSystem] varchar(30) NOT NULL,
    [ProcedureCode] varchar(30) NOT NULL,
    [ProcedureDescription] nvarchar(250) NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_DimProcedure] PRIMARY KEY ([ProcedureKey])
);

CREATE TABLE [dbo].[DimMedication] (
    [MedicationKey] bigint NOT NULL,
    [MedicationCodeSystem] varchar(30) NOT NULL,
    [MedicationCode] varchar(50) NOT NULL,
    [MedicationName] nvarchar(200) NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_DimMedication] PRIMARY KEY ([MedicationKey])
);

CREATE TABLE [dbo].[DimCoverage] (
    [CoverageKey] bigint NOT NULL,
    [SourceCoverageID] bigint NOT NULL,
    [SourcePatientID] bigint NOT NULL,
    [CoverageNumber] varchar(40) NOT NULL,
    [PayerCode] varchar(30) NOT NULL,
    [PayerName] nvarchar(150) NOT NULL,
    [PlanCode] varchar(40) NOT NULL,
    [PlanName] nvarchar(150) NOT NULL,
    [CoverageTypeCode] varchar(30) NOT NULL,
    [EffectiveDate] date NOT NULL,
    [TerminationDate] date NULL,
    [CoverageStatus] varchar(20) NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [EffectiveFromUtc] datetime2(7) NOT NULL,
    [EffectiveToUtc] datetime2(7) NULL,
    [IsCurrent] bit NOT NULL,
    CONSTRAINT [PK_DimCoverage] PRIMARY KEY ([CoverageKey])
);

CREATE TABLE [dbo].[FactEncounter] (
    [EncounterKey] bigint NOT NULL,
    [SourceEncounterID] bigint NOT NULL,
    [EncounterNumber] varchar(40) NOT NULL,
    [AttendingProviderKey] bigint NULL,
    [CoverageKey] bigint NULL,
    [ArrivalDateKey] int NOT NULL,
    [DischargeDateKey] int NULL,
    [ArrivalAtUtc] datetime2(7) NOT NULL,
    [DischargeAtUtc] datetime2(7) NULL,
    [EncounterTypeCode] varchar(30) NOT NULL,
    [EncounterStatus] varchar(20) NOT NULL,
    [DischargeDispositionCode] varchar(30) NULL,
    [LengthOfStayMinutes] decimal(18,2) NULL,
    [EncounterCount] int NOT NULL,
    [PatientKey] bigint NOT NULL,
    [DepartmentKey] bigint NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_FactEncounter] PRIMARY KEY ([EncounterKey])
);

CREATE TABLE [dbo].[FactDiagnosis] (
    [DiagnosisFactKey] bigint NOT NULL,
    [SourceDiagnosisID] bigint NOT NULL,
    [SourceEncounterID] bigint NOT NULL,
    [DiagnosisKey] bigint NOT NULL,
    [DiagnosingProviderKey] bigint NULL,
    [DiagnosisDateKey] int NOT NULL,
    [DiagnosedAtUtc] datetime2(7) NOT NULL,
    [DiagnosisSequence] smallint NOT NULL,
    [IsPrimary] bit NOT NULL,
    [DiagnosisStatus] varchar(20) NOT NULL,
    [DiagnosisCount] int NOT NULL,
    [PatientKey] bigint NOT NULL,
    [DepartmentKey] bigint NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_FactDiagnosis] PRIMARY KEY ([DiagnosisFactKey])
);

CREATE TABLE [dbo].[FactProcedure] (
    [ProcedureFactKey] bigint NOT NULL,
    [SourceProcedureID] bigint NOT NULL,
    [SourceEncounterID] bigint NOT NULL,
    [ProcedureKey] bigint NOT NULL,
    [PerformingProviderKey] bigint NULL,
    [OrderedDateKey] int NOT NULL,
    [PerformedDateKey] int NULL,
    [OrderedAtUtc] datetime2(7) NOT NULL,
    [PerformedAtUtc] datetime2(7) NULL,
    [ProcedureStatus] varchar(20) NOT NULL,
    [ProcedureCount] int NOT NULL,
    [PatientKey] bigint NOT NULL,
    [DepartmentKey] bigint NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_FactProcedure] PRIMARY KEY ([ProcedureFactKey])
);

CREATE TABLE [dbo].[FactMedicationOrder] (
    [MedicationOrderKey] bigint NOT NULL,
    [SourceMedicationOrderID] bigint NOT NULL,
    [SourceEncounterID] bigint NOT NULL,
    [MedicationKey] bigint NOT NULL,
    [OrderingProviderKey] bigint NOT NULL,
    [OrderedDateKey] int NOT NULL,
    [OrderedAtUtc] datetime2(7) NOT NULL,
    [StartAtUtc] datetime2(7) NULL,
    [EndAtUtc] datetime2(7) NULL,
    [OrderedDose] decimal(18,4) NULL,
    [DoseUnit] varchar(30) NULL,
    [RouteCode] varchar(30) NULL,
    [FrequencyCode] varchar(30) NULL,
    [OrderStatus] varchar(20) NOT NULL,
    [OrderCount] int NOT NULL,
    [PatientKey] bigint NOT NULL,
    [DepartmentKey] bigint NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_FactMedicationOrder] PRIMARY KEY ([MedicationOrderKey])
);

CREATE TABLE [dbo].[FactMedicationAdministration] (
    [MedicationAdministrationKey] bigint NOT NULL,
    [SourceMedicationAdministrationID] bigint NOT NULL,
    [SourceEncounterID] bigint NOT NULL,
    [SourceMedicationOrderID] bigint NOT NULL,
    [MedicationKey] bigint NOT NULL,
    [AdministeringProviderKey] bigint NULL,
    [AdministrationDateKey] int NULL,
    [RecordedDateKey] int NOT NULL,
    [ScheduledAtUtc] datetime2(7) NULL,
    [RecordedAtUtc] datetime2(7) NOT NULL,
    [AdministeredAtUtc] datetime2(7) NULL,
    [AdministeredDose] decimal(18,4) NULL,
    [DoseUnit] varchar(30) NULL,
    [AdministrationStatus] varchar(20) NOT NULL,
    [AdministrationEventCount] int NOT NULL,
    [PatientKey] bigint NOT NULL,
    [DepartmentKey] bigint NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_FactMedicationAdministration] PRIMARY KEY ([MedicationAdministrationKey])
);

CREATE TABLE [dbo].[FactLabResult] (
    [LabResultKey] bigint NOT NULL,
    [SourceLaboratoryResultID] bigint NOT NULL,
    [SourceEncounterID] bigint NOT NULL,
    [SourceLaboratoryOrderID] bigint NOT NULL,
    [OrderingProviderKey] bigint NOT NULL,
    [OrderedDateKey] int NOT NULL,
    [ResultDateKey] int NULL,
    [OrderedAtUtc] datetime2(7) NOT NULL,
    [ResultedAtUtc] datetime2(7) NULL,
    [TestCode] varchar(40) NOT NULL,
    [ComponentCode] varchar(40) NOT NULL,
    [ComponentName] nvarchar(200) NOT NULL,
    [NumericValue] decimal(18,6) NULL,
    [TextValue] nvarchar(1000) NULL,
    [ResultUnit] varchar(30) NULL,
    [ReferenceLow] decimal(18,6) NULL,
    [ReferenceHigh] decimal(18,6) NULL,
    [AbnormalFlag] varchar(20) NULL,
    [ResultStatus] varchar(20) NOT NULL,
    [ResultCount] int NOT NULL,
    [PatientKey] bigint NOT NULL,
    [DepartmentKey] bigint NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_FactLabResult] PRIMARY KEY ([LabResultKey])
);

CREATE TABLE [dbo].[FactAppointment] (
    [AppointmentKey] bigint NOT NULL,
    [SourceAppointmentID] bigint NOT NULL,
    [SourceEncounterID] bigint NULL,
    [AppointmentNumber] varchar(40) NOT NULL,
    [ProviderKey] bigint NULL,
    [ScheduledDateKey] int NOT NULL,
    [ScheduledStartAtUtc] datetime2(7) NOT NULL,
    [ScheduledEndAtUtc] datetime2(7) NOT NULL,
    [AppointmentTypeCode] varchar(30) NOT NULL,
    [AppointmentStatus] varchar(20) NOT NULL,
    [CanceledAtUtc] datetime2(7) NULL,
    [ScheduledDurationMinutes] decimal(18,2) NOT NULL,
    [AppointmentCount] int NOT NULL,
    [PatientKey] bigint NOT NULL,
    [DepartmentKey] bigint NOT NULL,
    [EtlCreatedAtUtc] datetime2(7) NOT NULL,
    [EtlModifiedAtUtc] datetime2(7) NOT NULL,
    [EtlBatchID] uniqueidentifier NOT NULL,
    [OriginSystem] varchar(30) NOT NULL,
    [OriginModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    CONSTRAINT [PK_FactAppointment] PRIMARY KEY ([AppointmentKey])
);

ALTER TABLE [dbo].[FactEncounter] WITH CHECK
    ADD CONSTRAINT [FK_FactEncounter_AttendingProviderKey] FOREIGN KEY ([AttendingProviderKey])
    REFERENCES [dbo].[DimProvider] ([ProviderKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactEncounter] WITH CHECK
    ADD CONSTRAINT [FK_FactEncounter_CoverageKey] FOREIGN KEY ([CoverageKey])
    REFERENCES [dbo].[DimCoverage] ([CoverageKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactEncounter] WITH CHECK
    ADD CONSTRAINT [FK_FactEncounter_ArrivalDateKey] FOREIGN KEY ([ArrivalDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactEncounter] WITH CHECK
    ADD CONSTRAINT [FK_FactEncounter_DischargeDateKey] FOREIGN KEY ([DischargeDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactEncounter] WITH CHECK
    ADD CONSTRAINT [FK_FactEncounter_PatientKey] FOREIGN KEY ([PatientKey])
    REFERENCES [dbo].[DimPatient] ([PatientKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactEncounter] WITH CHECK
    ADD CONSTRAINT [FK_FactEncounter_DepartmentKey] FOREIGN KEY ([DepartmentKey])
    REFERENCES [dbo].[DimDepartment] ([DepartmentKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactDiagnosis] WITH CHECK
    ADD CONSTRAINT [FK_FactDiagnosis_DiagnosisKey] FOREIGN KEY ([DiagnosisKey])
    REFERENCES [dbo].[DimDiagnosis] ([DiagnosisKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactDiagnosis] WITH CHECK
    ADD CONSTRAINT [FK_FactDiagnosis_DiagnosingProviderKey] FOREIGN KEY ([DiagnosingProviderKey])
    REFERENCES [dbo].[DimProvider] ([ProviderKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactDiagnosis] WITH CHECK
    ADD CONSTRAINT [FK_FactDiagnosis_DiagnosisDateKey] FOREIGN KEY ([DiagnosisDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactDiagnosis] WITH CHECK
    ADD CONSTRAINT [FK_FactDiagnosis_PatientKey] FOREIGN KEY ([PatientKey])
    REFERENCES [dbo].[DimPatient] ([PatientKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactDiagnosis] WITH CHECK
    ADD CONSTRAINT [FK_FactDiagnosis_DepartmentKey] FOREIGN KEY ([DepartmentKey])
    REFERENCES [dbo].[DimDepartment] ([DepartmentKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactProcedure] WITH CHECK
    ADD CONSTRAINT [FK_FactProcedure_ProcedureKey] FOREIGN KEY ([ProcedureKey])
    REFERENCES [dbo].[DimProcedure] ([ProcedureKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactProcedure] WITH CHECK
    ADD CONSTRAINT [FK_FactProcedure_PerformingProviderKey] FOREIGN KEY ([PerformingProviderKey])
    REFERENCES [dbo].[DimProvider] ([ProviderKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactProcedure] WITH CHECK
    ADD CONSTRAINT [FK_FactProcedure_OrderedDateKey] FOREIGN KEY ([OrderedDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactProcedure] WITH CHECK
    ADD CONSTRAINT [FK_FactProcedure_PerformedDateKey] FOREIGN KEY ([PerformedDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactProcedure] WITH CHECK
    ADD CONSTRAINT [FK_FactProcedure_PatientKey] FOREIGN KEY ([PatientKey])
    REFERENCES [dbo].[DimPatient] ([PatientKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactProcedure] WITH CHECK
    ADD CONSTRAINT [FK_FactProcedure_DepartmentKey] FOREIGN KEY ([DepartmentKey])
    REFERENCES [dbo].[DimDepartment] ([DepartmentKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationOrder_MedicationKey] FOREIGN KEY ([MedicationKey])
    REFERENCES [dbo].[DimMedication] ([MedicationKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationOrder_OrderingProviderKey] FOREIGN KEY ([OrderingProviderKey])
    REFERENCES [dbo].[DimProvider] ([ProviderKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationOrder_OrderedDateKey] FOREIGN KEY ([OrderedDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationOrder_PatientKey] FOREIGN KEY ([PatientKey])
    REFERENCES [dbo].[DimPatient] ([PatientKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationOrder_DepartmentKey] FOREIGN KEY ([DepartmentKey])
    REFERENCES [dbo].[DimDepartment] ([DepartmentKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationAdministration_MedicationKey] FOREIGN KEY ([MedicationKey])
    REFERENCES [dbo].[DimMedication] ([MedicationKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationAdministration_AdministeringProviderKey] FOREIGN KEY ([AdministeringProviderKey])
    REFERENCES [dbo].[DimProvider] ([ProviderKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationAdministration_AdministrationDateKey] FOREIGN KEY ([AdministrationDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationAdministration_RecordedDateKey] FOREIGN KEY ([RecordedDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationAdministration_PatientKey] FOREIGN KEY ([PatientKey])
    REFERENCES [dbo].[DimPatient] ([PatientKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_FactMedicationAdministration_DepartmentKey] FOREIGN KEY ([DepartmentKey])
    REFERENCES [dbo].[DimDepartment] ([DepartmentKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactLabResult] WITH CHECK
    ADD CONSTRAINT [FK_FactLabResult_OrderingProviderKey] FOREIGN KEY ([OrderingProviderKey])
    REFERENCES [dbo].[DimProvider] ([ProviderKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactLabResult] WITH CHECK
    ADD CONSTRAINT [FK_FactLabResult_OrderedDateKey] FOREIGN KEY ([OrderedDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactLabResult] WITH CHECK
    ADD CONSTRAINT [FK_FactLabResult_ResultDateKey] FOREIGN KEY ([ResultDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactLabResult] WITH CHECK
    ADD CONSTRAINT [FK_FactLabResult_PatientKey] FOREIGN KEY ([PatientKey])
    REFERENCES [dbo].[DimPatient] ([PatientKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactLabResult] WITH CHECK
    ADD CONSTRAINT [FK_FactLabResult_DepartmentKey] FOREIGN KEY ([DepartmentKey])
    REFERENCES [dbo].[DimDepartment] ([DepartmentKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactAppointment] WITH CHECK
    ADD CONSTRAINT [FK_FactAppointment_ProviderKey] FOREIGN KEY ([ProviderKey])
    REFERENCES [dbo].[DimProvider] ([ProviderKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactAppointment] WITH CHECK
    ADD CONSTRAINT [FK_FactAppointment_ScheduledDateKey] FOREIGN KEY ([ScheduledDateKey])
    REFERENCES [dbo].[DimDate] ([DateKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactAppointment] WITH CHECK
    ADD CONSTRAINT [FK_FactAppointment_PatientKey] FOREIGN KEY ([PatientKey])
    REFERENCES [dbo].[DimPatient] ([PatientKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[FactAppointment] WITH CHECK
    ADD CONSTRAINT [FK_FactAppointment_DepartmentKey] FOREIGN KEY ([DepartmentKey])
    REFERENCES [dbo].[DimDepartment] ([DepartmentKey])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

COMMIT TRANSACTION;
