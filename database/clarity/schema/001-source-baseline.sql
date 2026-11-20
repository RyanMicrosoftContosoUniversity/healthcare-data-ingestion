-- Generated Clarity source baseline; do not edit by hand.

-- For an empty source database with the declared schema already present.

-- Not an upgrade migration; remaining integrity/write-path work: database/README.md.

SET XACT_ABORT ON;
BEGIN TRANSACTION;

CREATE TABLE [dbo].[Patient] (
    [PatientID] bigint NOT NULL,
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
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Patient] PRIMARY KEY ([PatientID]),
    CONSTRAINT [UQ_Patient_MedicalRecordNumber] UNIQUE ([MedicalRecordNumber])
);

CREATE TABLE [dbo].[Provider] (
    [ProviderID] bigint NOT NULL,
    [ProviderCode] varchar(30) NOT NULL,
    [DisplayName] nvarchar(200) NOT NULL,
    [ProviderTypeCode] varchar(30) NOT NULL,
    [SpecialtyCode] varchar(30) NULL,
    [IsActive] bit NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Provider] PRIMARY KEY ([ProviderID]),
    CONSTRAINT [UQ_Provider_ProviderCode] UNIQUE ([ProviderCode])
);

CREATE TABLE [dbo].[Department] (
    [DepartmentID] bigint NOT NULL,
    [DepartmentCode] varchar(30) NOT NULL,
    [DepartmentName] nvarchar(150) NOT NULL,
    [FacilityCode] varchar(30) NOT NULL,
    [DepartmentTypeCode] varchar(30) NOT NULL,
    [IsActive] bit NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Department] PRIMARY KEY ([DepartmentID]),
    CONSTRAINT [UQ_Department_DepartmentCode] UNIQUE ([DepartmentCode])
);

CREATE TABLE [dbo].[Encounter] (
    [EncounterID] bigint NOT NULL,
    [EncounterNumber] varchar(40) NOT NULL,
    [PatientID] bigint NOT NULL,
    [DepartmentID] bigint NOT NULL,
    [AttendingProviderID] bigint NULL,
    [PrimaryCoverageID] bigint NULL,
    [EncounterTypeCode] varchar(30) NOT NULL,
    [EncounterStatus] varchar(20) NOT NULL,
    [ArrivalAtUtc] datetime2(7) NOT NULL,
    [DischargeAtUtc] datetime2(7) NULL,
    [DischargeDispositionCode] varchar(30) NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Encounter] PRIMARY KEY ([EncounterID]),
    CONSTRAINT [UQ_Encounter_EncounterNumber] UNIQUE ([EncounterNumber])
);

CREATE TABLE [dbo].[Diagnosis] (
    [DiagnosisID] bigint NOT NULL,
    [EncounterID] bigint NOT NULL,
    [DiagnosingProviderID] bigint NULL,
    [DiagnosisCodeSystem] varchar(30) NOT NULL,
    [DiagnosisCode] varchar(30) NOT NULL,
    [DiagnosisDescription] nvarchar(250) NOT NULL,
    [DiagnosisSequence] smallint NOT NULL,
    [IsPrimary] bit NOT NULL,
    [DiagnosedAtUtc] datetime2(7) NOT NULL,
    [DiagnosisStatus] varchar(20) NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Diagnosis] PRIMARY KEY ([DiagnosisID])
);

CREATE TABLE [dbo].[Procedure] (
    [ProcedureID] bigint NOT NULL,
    [EncounterID] bigint NOT NULL,
    [PerformingProviderID] bigint NULL,
    [ProcedureCodeSystem] varchar(30) NOT NULL,
    [ProcedureCode] varchar(30) NOT NULL,
    [ProcedureDescription] nvarchar(250) NOT NULL,
    [OrderedAtUtc] datetime2(7) NOT NULL,
    [PerformedAtUtc] datetime2(7) NULL,
    [ProcedureStatus] varchar(20) NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Procedure] PRIMARY KEY ([ProcedureID])
);

CREATE TABLE [dbo].[MedicationOrder] (
    [MedicationOrderID] bigint NOT NULL,
    [EncounterID] bigint NOT NULL,
    [OrderingProviderID] bigint NOT NULL,
    [MedicationCodeSystem] varchar(30) NOT NULL,
    [MedicationCode] varchar(50) NOT NULL,
    [MedicationName] nvarchar(200) NOT NULL,
    [OrderedDose] decimal(18,4) NULL,
    [DoseUnit] varchar(30) NULL,
    [RouteCode] varchar(30) NULL,
    [FrequencyCode] varchar(30) NULL,
    [OrderedAtUtc] datetime2(7) NOT NULL,
    [StartAtUtc] datetime2(7) NULL,
    [EndAtUtc] datetime2(7) NULL,
    [OrderStatus] varchar(20) NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_MedicationOrder] PRIMARY KEY ([MedicationOrderID])
);

CREATE TABLE [dbo].[MedicationAdministration] (
    [MedicationAdministrationID] bigint NOT NULL,
    [MedicationOrderID] bigint NOT NULL,
    [AdministeringProviderID] bigint NULL,
    [ScheduledAtUtc] datetime2(7) NULL,
    [RecordedAtUtc] datetime2(7) NOT NULL,
    [AdministeredAtUtc] datetime2(7) NULL,
    [AdministeredDose] decimal(18,4) NULL,
    [DoseUnit] varchar(30) NULL,
    [AdministrationStatus] varchar(20) NOT NULL,
    [NotGivenReason] nvarchar(250) NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_MedicationAdministration] PRIMARY KEY ([MedicationAdministrationID])
);

CREATE TABLE [dbo].[LaboratoryOrder] (
    [LaboratoryOrderID] bigint NOT NULL,
    [EncounterID] bigint NOT NULL,
    [OrderingProviderID] bigint NOT NULL,
    [OrderNumber] varchar(40) NOT NULL,
    [TestCode] varchar(40) NOT NULL,
    [TestName] nvarchar(200) NOT NULL,
    [SpecimenTypeCode] varchar(30) NULL,
    [OrderedAtUtc] datetime2(7) NOT NULL,
    [CollectedAtUtc] datetime2(7) NULL,
    [OrderStatus] varchar(20) NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_LaboratoryOrder] PRIMARY KEY ([LaboratoryOrderID]),
    CONSTRAINT [UQ_LaboratoryOrder_OrderNumber] UNIQUE ([OrderNumber])
);

CREATE TABLE [dbo].[LaboratoryResult] (
    [LaboratoryResultID] bigint NOT NULL,
    [LaboratoryOrderID] bigint NOT NULL,
    [ComponentCode] varchar(40) NOT NULL,
    [ComponentName] nvarchar(200) NOT NULL,
    [NumericValue] decimal(18,6) NULL,
    [TextValue] nvarchar(1000) NULL,
    [ResultUnit] varchar(30) NULL,
    [ReferenceLow] decimal(18,6) NULL,
    [ReferenceHigh] decimal(18,6) NULL,
    [AbnormalFlag] varchar(20) NULL,
    [ResultedAtUtc] datetime2(7) NULL,
    [ResultStatus] varchar(20) NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_LaboratoryResult] PRIMARY KEY ([LaboratoryResultID])
);

CREATE TABLE [dbo].[VitalSign] (
    [VitalSignID] bigint NOT NULL,
    [EncounterID] bigint NOT NULL,
    [RecordingProviderID] bigint NULL,
    [VitalTypeCode] varchar(40) NOT NULL,
    [NumericValue] decimal(18,6) NULL,
    [TextValue] nvarchar(250) NULL,
    [ValueUnit] varchar(30) NULL,
    [MeasuredAtUtc] datetime2(7) NOT NULL,
    [ObservationStatus] varchar(20) NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_VitalSign] PRIMARY KEY ([VitalSignID])
);

CREATE TABLE [dbo].[Coverage] (
    [CoverageID] bigint NOT NULL,
    [PatientID] bigint NOT NULL,
    [CoverageNumber] varchar(40) NOT NULL,
    [PayerCode] varchar(30) NOT NULL,
    [PayerName] nvarchar(150) NOT NULL,
    [PlanCode] varchar(40) NOT NULL,
    [PlanName] nvarchar(150) NOT NULL,
    [CoverageTypeCode] varchar(30) NOT NULL,
    [EffectiveDate] date NOT NULL,
    [TerminationDate] date NULL,
    [CoverageStatus] varchar(20) NOT NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Coverage] PRIMARY KEY ([CoverageID]),
    CONSTRAINT [UQ_Coverage_CoverageNumber] UNIQUE ([CoverageNumber])
);

CREATE TABLE [dbo].[Appointment] (
    [AppointmentID] bigint NOT NULL,
    [AppointmentNumber] varchar(40) NOT NULL,
    [PatientID] bigint NOT NULL,
    [ProviderID] bigint NULL,
    [DepartmentID] bigint NOT NULL,
    [EncounterID] bigint NULL,
    [ScheduledStartAtUtc] datetime2(7) NOT NULL,
    [ScheduledEndAtUtc] datetime2(7) NOT NULL,
    [AppointmentTypeCode] varchar(30) NOT NULL,
    [AppointmentStatus] varchar(20) NOT NULL,
    [CanceledAtUtc] datetime2(7) NULL,
    [CancellationReason] nvarchar(250) NULL,
    [CreatedAtUtc] datetime2(7) NOT NULL,
    [ModifiedAtUtc] datetime2(7) NOT NULL,
    [IsDeleted] bit NOT NULL,
    [DeletedAtUtc] datetime2(7) NULL,
    CONSTRAINT [PK_Appointment] PRIMARY KEY ([AppointmentID]),
    CONSTRAINT [UQ_Appointment_AppointmentNumber] UNIQUE ([AppointmentNumber])
);

ALTER TABLE [dbo].[Encounter] WITH CHECK
    ADD CONSTRAINT [FK_Encounter_PatientID] FOREIGN KEY ([PatientID])
    REFERENCES [dbo].[Patient] ([PatientID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Encounter] WITH CHECK
    ADD CONSTRAINT [FK_Encounter_DepartmentID] FOREIGN KEY ([DepartmentID])
    REFERENCES [dbo].[Department] ([DepartmentID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Encounter] WITH CHECK
    ADD CONSTRAINT [FK_Encounter_AttendingProviderID] FOREIGN KEY ([AttendingProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Encounter] WITH CHECK
    ADD CONSTRAINT [FK_Encounter_PrimaryCoverageID] FOREIGN KEY ([PrimaryCoverageID])
    REFERENCES [dbo].[Coverage] ([CoverageID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Diagnosis] WITH CHECK
    ADD CONSTRAINT [FK_Diagnosis_EncounterID] FOREIGN KEY ([EncounterID])
    REFERENCES [dbo].[Encounter] ([EncounterID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Diagnosis] WITH CHECK
    ADD CONSTRAINT [FK_Diagnosis_DiagnosingProviderID] FOREIGN KEY ([DiagnosingProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Procedure] WITH CHECK
    ADD CONSTRAINT [FK_Procedure_EncounterID] FOREIGN KEY ([EncounterID])
    REFERENCES [dbo].[Encounter] ([EncounterID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Procedure] WITH CHECK
    ADD CONSTRAINT [FK_Procedure_PerformingProviderID] FOREIGN KEY ([PerformingProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[MedicationOrder] WITH CHECK
    ADD CONSTRAINT [FK_MedicationOrder_EncounterID] FOREIGN KEY ([EncounterID])
    REFERENCES [dbo].[Encounter] ([EncounterID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[MedicationOrder] WITH CHECK
    ADD CONSTRAINT [FK_MedicationOrder_OrderingProviderID] FOREIGN KEY ([OrderingProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[MedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_MedicationAdministration_MedicationOrderID] FOREIGN KEY ([MedicationOrderID])
    REFERENCES [dbo].[MedicationOrder] ([MedicationOrderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[MedicationAdministration] WITH CHECK
    ADD CONSTRAINT [FK_MedicationAdministration_AdministeringProviderID] FOREIGN KEY ([AdministeringProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[LaboratoryOrder] WITH CHECK
    ADD CONSTRAINT [FK_LaboratoryOrder_EncounterID] FOREIGN KEY ([EncounterID])
    REFERENCES [dbo].[Encounter] ([EncounterID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[LaboratoryOrder] WITH CHECK
    ADD CONSTRAINT [FK_LaboratoryOrder_OrderingProviderID] FOREIGN KEY ([OrderingProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[LaboratoryResult] WITH CHECK
    ADD CONSTRAINT [FK_LaboratoryResult_LaboratoryOrderID] FOREIGN KEY ([LaboratoryOrderID])
    REFERENCES [dbo].[LaboratoryOrder] ([LaboratoryOrderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[VitalSign] WITH CHECK
    ADD CONSTRAINT [FK_VitalSign_EncounterID] FOREIGN KEY ([EncounterID])
    REFERENCES [dbo].[Encounter] ([EncounterID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[VitalSign] WITH CHECK
    ADD CONSTRAINT [FK_VitalSign_RecordingProviderID] FOREIGN KEY ([RecordingProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Coverage] WITH CHECK
    ADD CONSTRAINT [FK_Coverage_PatientID] FOREIGN KEY ([PatientID])
    REFERENCES [dbo].[Patient] ([PatientID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Appointment] WITH CHECK
    ADD CONSTRAINT [FK_Appointment_PatientID] FOREIGN KEY ([PatientID])
    REFERENCES [dbo].[Patient] ([PatientID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Appointment] WITH CHECK
    ADD CONSTRAINT [FK_Appointment_ProviderID] FOREIGN KEY ([ProviderID])
    REFERENCES [dbo].[Provider] ([ProviderID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Appointment] WITH CHECK
    ADD CONSTRAINT [FK_Appointment_DepartmentID] FOREIGN KEY ([DepartmentID])
    REFERENCES [dbo].[Department] ([DepartmentID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[Appointment] WITH CHECK
    ADD CONSTRAINT [FK_Appointment_EncounterID] FOREIGN KEY ([EncounterID])
    REFERENCES [dbo].[Encounter] ([EncounterID])
    ON DELETE NO ACTION ON UPDATE NO ACTION;

COMMIT TRANSACTION;
