-- Source-only upgrade 002. Offline-generated; review before Azure SQL execution.

-- No third database. Requires the approved 001 baseline in this source database.

SET XACT_ABORT ON;
SET NOCOUNT ON;
BEGIN TRANSACTION;

DECLARE @result int; EXEC @result=sys.sp_getapplock @Resource=N'healthcare-ingestion-source', @DbPrincipal=N'public', @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=0; IF @result<0 THROW 51004,'Source DDL requires the exclusive extraction fence.',1;

IF OBJECT_ID(N'[dbo].[Patient]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[Provider]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[Department]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[Encounter]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[Diagnosis]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[Procedure]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[MedicationOrder]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[MedicationAdministration]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[LaboratoryOrder]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[LaboratoryResult]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[VitalSign]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[Coverage]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[Appointment]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'dbo.SyntheticSourceCheckpoint',N'U') IS NULL
CREATE TABLE dbo.SyntheticSourceCheckpoint (
 SourceSystem varchar(30) NOT NULL PRIMARY KEY,
 BatchName varchar(80) NOT NULL, PopulationDigest char(64) NOT NULL,
 MappingDigest char(64) NOT NULL, ContractDigest char(64) NOT NULL,
 RowCount bigint NOT NULL CHECK(RowCount>=0), CommittedAtUtc datetime2(7) NOT NULL,
 CoverageStartUtc datetime2(7) NOT NULL, CoverageEndUtc datetime2(7) NOT NULL,
 CONSTRAINT CK_SyntheticSourceIdentity CHECK(SourceSystem='Clarity')
);

IF OBJECT_ID(N'dbo.SyntheticSourceBatchCommit',N'U') IS NULL
CREATE TABLE dbo.SyntheticSourceBatchCommit (
 SourceSystem varchar(30) NOT NULL, BatchName varchar(80) NOT NULL,
 PopulationDigest char(64) NOT NULL, MappingDigest char(64) NOT NULL,
 ContractDigest char(64) NOT NULL, RowCount bigint NOT NULL CHECK(RowCount>=0),
 CommittedAtUtc datetime2(7) NOT NULL,
 CoverageStartUtc datetime2(7) NOT NULL, CoverageEndUtc datetime2(7) NOT NULL,
 CONSTRAINT PK_SyntheticSourceBatchCommit PRIMARY KEY(SourceSystem,BatchName),
 CONSTRAINT CK_SyntheticBatchSource CHECK(SourceSystem='Clarity')
);

IF COL_LENGTH(N'dbo.SyntheticSourceCheckpoint',N'CoverageStartUtc') IS NULL ALTER TABLE dbo.SyntheticSourceCheckpoint ADD CoverageStartUtc datetime2(7) NULL;

IF COL_LENGTH(N'dbo.SyntheticSourceCheckpoint',N'CoverageEndUtc') IS NULL ALTER TABLE dbo.SyntheticSourceCheckpoint ADD CoverageEndUtc datetime2(7) NULL;

EXEC(N'IF EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CoverageStartUtc IS NULL OR CoverageEndUtc IS NULL) THROW 51008,''Legacy coverage requires reviewed generation evidence backfill.'',1;');

EXEC(N'IF EXISTS(SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N''dbo.SyntheticSourceCheckpoint'') AND name=N''CoverageStartUtc'' AND is_nullable=1) ALTER TABLE dbo.SyntheticSourceCheckpoint ALTER COLUMN CoverageStartUtc datetime2(7) NOT NULL;');

EXEC(N'IF EXISTS(SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N''dbo.SyntheticSourceCheckpoint'') AND name=N''CoverageEndUtc'' AND is_nullable=1) ALTER TABLE dbo.SyntheticSourceCheckpoint ALTER COLUMN CoverageEndUtc datetime2(7) NOT NULL;');

EXEC(N'IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE name=N''CK_SyntheticSourceCheckpoint_Coverage'') ALTER TABLE dbo.SyntheticSourceCheckpoint WITH CHECK ADD CONSTRAINT CK_SyntheticSourceCheckpoint_Coverage CHECK(CoverageStartUtc<=CoverageEndUtc);');

IF COL_LENGTH(N'dbo.SyntheticSourceBatchCommit',N'CoverageStartUtc') IS NULL ALTER TABLE dbo.SyntheticSourceBatchCommit ADD CoverageStartUtc datetime2(7) NULL;

IF COL_LENGTH(N'dbo.SyntheticSourceBatchCommit',N'CoverageEndUtc') IS NULL ALTER TABLE dbo.SyntheticSourceBatchCommit ADD CoverageEndUtc datetime2(7) NULL;

EXEC(N'IF EXISTS(SELECT 1 FROM dbo.SyntheticSourceBatchCommit WHERE CoverageStartUtc IS NULL OR CoverageEndUtc IS NULL) THROW 51008,''Legacy coverage requires reviewed generation evidence backfill.'',1;');

EXEC(N'IF EXISTS(SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N''dbo.SyntheticSourceBatchCommit'') AND name=N''CoverageStartUtc'' AND is_nullable=1) ALTER TABLE dbo.SyntheticSourceBatchCommit ALTER COLUMN CoverageStartUtc datetime2(7) NOT NULL;');

EXEC(N'IF EXISTS(SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N''dbo.SyntheticSourceBatchCommit'') AND name=N''CoverageEndUtc'' AND is_nullable=1) ALTER TABLE dbo.SyntheticSourceBatchCommit ALTER COLUMN CoverageEndUtc datetime2(7) NOT NULL;');

EXEC(N'IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE name=N''CK_SyntheticSourceBatchCommit_Coverage'') ALTER TABLE dbo.SyntheticSourceBatchCommit WITH CHECK ADD CONSTRAINT CK_SyntheticSourceBatchCommit_Coverage CHECK(CoverageStartUtc<=CoverageEndUtc);');

EXEC(N'CREATE OR ALTER PROCEDURE dbo.PrepareSyntheticSourcePublication AS BEGIN SET NOCOUNT ON; IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1; DECLARE @upper datetime2(7); SELECT @upper=MAX(a.audit_at) FROM (SELECT MAX(CommittedAtUtc) AS audit_at FROM dbo.SyntheticSourceCheckpoint UNION ALL SELECT MAX(CommittedAtUtc) AS audit_at FROM dbo.SyntheticSourceBatchCommit UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Patient] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Provider] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Department] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Encounter] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Diagnosis] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Procedure] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[MedicationOrder] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[MedicationAdministration] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[LaboratoryOrder] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[LaboratoryResult] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[VitalSign] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Coverage] UNION ALL SELECT MAX([ModifiedAtUtc]) AS audit_at FROM [dbo].[Appointment]) a; DECLARE @publication datetime2(7)=SYSUTCDATETIME(); IF @publication<=@upper SET @publication=DATEADD(nanosecond,100,@upper); DECLARE @text varchar(33)=CONVERT(varchar(33),@publication,126); EXEC sys.sp_set_session_context @key=N''source_publication_at'', @value=@text,@read_only=1; END;');

EXEC(N'CREATE OR ALTER TRIGGER dbo.TR_SyntheticSourceBatchCommit_Immutable ON dbo.SyntheticSourceBatchCommit AFTER INSERT,UPDATE,DELETE AS BEGIN SET NOCOUNT ON; IF EXISTS(SELECT 1 FROM deleted) THROW 51005,''Committed source batch evidence is immutable.'',1; IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1; DECLARE @publication datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at'')); IF @publication IS NULL OR EXISTS(SELECT 1 FROM inserted WHERE CommittedAtUtc<>@publication) OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@publication) THROW 51007,''Source publication audit must advance the committed boundary.'',1; IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.SyntheticSourceCheckpoint c ON i.SourceSystem=c.SourceSystem WHERE i.CoverageStartUtc<>c.CoverageEndUtc OR i.CoverageEndUtc<c.CoverageEndUtc) THROW 51009,''Source coverage must continue from the prior committed horizon.'',1; END;');

EXEC(N'CREATE OR ALTER TRIGGER dbo.TR_SyntheticSourceCheckpoint_Integrity ON dbo.SyntheticSourceCheckpoint AFTER INSERT,UPDATE,DELETE AS BEGIN SET NOCOUNT ON; IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1; IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE i.SourceSystem=d.SourceSystem)) THROW 51005,''Committed source checkpoint deletion is prohibited.'',1; IF EXISTS(SELECT 1 FROM inserted i LEFT JOIN dbo.SyntheticSourceBatchCommit b ON i.SourceSystem=b.SourceSystem AND i.BatchName=b.BatchName WHERE b.BatchName IS NULL OR i.PopulationDigest<>b.PopulationDigest OR i.MappingDigest<>b.MappingDigest OR i.ContractDigest<>b.ContractDigest OR i.RowCount<>b.RowCount OR i.CommittedAtUtc<>b.CommittedAtUtc OR i.CoverageStartUtc<>b.CoverageStartUtc OR i.CoverageEndUtc<>b.CoverageEndUtc) THROW 51005,''Source checkpoint must match its immutable coverage ledger.'',1; IF EXISTS(SELECT 1 FROM inserted i JOIN deleted d ON i.SourceSystem=d.SourceSystem WHERE i.CommittedAtUtc<=d.CommittedAtUtc OR i.CoverageStartUtc<>d.CoverageEndUtc OR i.CoverageEndUtc<d.CoverageEndUtc) THROW 51009,''Source checkpoint coverage or audit boundary regresses.'',1; END;');

IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name=N'FK_SyntheticSourceCheckpoint_Batch' AND parent_object_id=OBJECT_ID(N'dbo.SyntheticSourceCheckpoint'))
ALTER TABLE dbo.SyntheticSourceCheckpoint WITH CHECK ADD CONSTRAINT FK_SyntheticSourceCheckpoint_Batch FOREIGN KEY(SourceSystem,BatchName) REFERENCES dbo.SyntheticSourceBatchCommit(SourceSystem,BatchName);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Patient_BirthDate_DeathDate' AND parent_object_id=OBJECT_ID(N'[dbo].[Patient]'))
 ALTER TABLE [dbo].[Patient] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Patient_BirthDate_DeathDate] CHECK ([BirthDate] IS NULL OR [DeathDate] IS NULL OR [BirthDate]<=[DeathDate]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Patient_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Patient]'))
 ALTER TABLE [dbo].[Patient] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Patient_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Patient_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Patient]'))
 ALTER TABLE [dbo].[Patient] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Patient_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Patient_Audit] ON [dbo].[Patient] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Patient_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[PatientID]=i.[PatientID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Patient] t JOIN inserted i ON t.[PatientID]=i.[PatientID] LEFT JOIN deleted d ON d.[PatientID]=i.[PatientID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Provider_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Provider]'))
 ALTER TABLE [dbo].[Provider] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Provider_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Provider_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Provider]'))
 ALTER TABLE [dbo].[Provider] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Provider_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Provider_Audit] ON [dbo].[Provider] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Provider_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[ProviderID]=i.[ProviderID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Provider] t JOIN inserted i ON t.[ProviderID]=i.[ProviderID] LEFT JOIN deleted d ON d.[ProviderID]=i.[ProviderID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Department_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Department]'))
 ALTER TABLE [dbo].[Department] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Department_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Department_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Department]'))
 ALTER TABLE [dbo].[Department] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Department_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Department_Audit] ON [dbo].[Department] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Department_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[DepartmentID]=i.[DepartmentID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Department] t JOIN inserted i ON t.[DepartmentID]=i.[DepartmentID] LEFT JOIN deleted d ON d.[DepartmentID]=i.[DepartmentID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Encounter_ArrivalAtUtc_DischargeAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Encounter]'))
 ALTER TABLE [dbo].[Encounter] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Encounter_ArrivalAtUtc_DischargeAtUtc] CHECK ([ArrivalAtUtc] IS NULL OR [DischargeAtUtc] IS NULL OR [ArrivalAtUtc]<=[DischargeAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Encounter_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Encounter]'))
 ALTER TABLE [dbo].[Encounter] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Encounter_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Encounter_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Encounter]'))
 ALTER TABLE [dbo].[Encounter] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Encounter_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Encounter_Audit] ON [dbo].[Encounter] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Encounter_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[EncounterID]=i.[EncounterID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Encounter] t JOIN inserted i ON t.[EncounterID]=i.[EncounterID] LEFT JOIN deleted d ON d.[EncounterID]=i.[EncounterID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Diagnosis_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Diagnosis]'))
 ALTER TABLE [dbo].[Diagnosis] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Diagnosis_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Diagnosis_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Diagnosis]'))
 ALTER TABLE [dbo].[Diagnosis] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Diagnosis_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Diagnosis_Sequence' AND parent_object_id=OBJECT_ID(N'[dbo].[Diagnosis]'))
 ALTER TABLE [dbo].[Diagnosis] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Diagnosis_Sequence] CHECK ([DiagnosisSequence]>0);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_Diagnosis_Sequence' AND object_id=OBJECT_ID(N'[dbo].[Diagnosis]'))
 CREATE UNIQUE INDEX [UX_Synthetic_Diagnosis_Sequence] ON [dbo].[Diagnosis] ([EncounterID],[DiagnosisSequence]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_Diagnosis_Primary' AND object_id=OBJECT_ID(N'[dbo].[Diagnosis]'))
 CREATE UNIQUE INDEX [UX_Synthetic_Diagnosis_Primary] ON [dbo].[Diagnosis] ([EncounterID]) WHERE [IsPrimary]=1 AND [IsDeleted]=0 AND [DiagnosisStatus]<>N'canceled' AND [DiagnosisStatus]<>N'cancelled' AND [DiagnosisStatus]<>N'inactive';

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Diagnosis_Audit] ON [dbo].[Diagnosis] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Diagnosis_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[DiagnosisID]=i.[DiagnosisID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Diagnosis] t JOIN inserted i ON t.[DiagnosisID]=i.[DiagnosisID] LEFT JOIN deleted d ON d.[DiagnosisID]=i.[DiagnosisID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Procedure_OrderedAtUtc_PerformedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Procedure]'))
 ALTER TABLE [dbo].[Procedure] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Procedure_OrderedAtUtc_PerformedAtUtc] CHECK ([OrderedAtUtc] IS NULL OR [PerformedAtUtc] IS NULL OR [OrderedAtUtc]<=[PerformedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Procedure_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Procedure]'))
 ALTER TABLE [dbo].[Procedure] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Procedure_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Procedure_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Procedure]'))
 ALTER TABLE [dbo].[Procedure] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Procedure_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Procedure_Audit] ON [dbo].[Procedure] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Procedure_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[ProcedureID]=i.[ProcedureID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Procedure] t JOIN inserted i ON t.[ProcedureID]=i.[ProcedureID] LEFT JOIN deleted d ON d.[ProcedureID]=i.[ProcedureID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationOrder_OrderedAtUtc_StartAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationOrder]'))
 ALTER TABLE [dbo].[MedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationOrder_OrderedAtUtc_StartAtUtc] CHECK ([OrderedAtUtc] IS NULL OR [StartAtUtc] IS NULL OR [OrderedAtUtc]<=[StartAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationOrder_StartAtUtc_EndAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationOrder]'))
 ALTER TABLE [dbo].[MedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationOrder_StartAtUtc_EndAtUtc] CHECK ([StartAtUtc] IS NULL OR [EndAtUtc] IS NULL OR [StartAtUtc]<=[EndAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationOrder_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationOrder]'))
 ALTER TABLE [dbo].[MedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationOrder_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationOrder_OrderedDose_Unit' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationOrder]'))
 ALTER TABLE [dbo].[MedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationOrder_OrderedDose_Unit] CHECK ([OrderedDose] IS NULL OR [DoseUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationOrder_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationOrder]'))
 ALTER TABLE [dbo].[MedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationOrder_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_MedicationOrder_Audit] ON [dbo].[MedicationOrder] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_MedicationOrder_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[MedicationOrderID]=i.[MedicationOrderID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[MedicationOrder] t JOIN inserted i ON t.[MedicationOrderID]=i.[MedicationOrderID] LEFT JOIN deleted d ON d.[MedicationOrderID]=i.[MedicationOrderID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationAdministration_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationAdministration]'))
 ALTER TABLE [dbo].[MedicationAdministration] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationAdministration_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationAdministration_AdministeredDose_Unit' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationAdministration]'))
 ALTER TABLE [dbo].[MedicationAdministration] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationAdministration_AdministeredDose_Unit] CHECK ([AdministeredDose] IS NULL OR [DoseUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_MedicationAdministration_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[MedicationAdministration]'))
 ALTER TABLE [dbo].[MedicationAdministration] WITH CHECK ADD CONSTRAINT [CK_Synthetic_MedicationAdministration_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_MedicationAdministration_Audit] ON [dbo].[MedicationAdministration] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_MedicationAdministration_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[MedicationAdministrationID]=i.[MedicationAdministrationID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[MedicationAdministration] t JOIN inserted i ON t.[MedicationAdministrationID]=i.[MedicationAdministrationID] LEFT JOIN deleted d ON d.[MedicationAdministrationID]=i.[MedicationAdministrationID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryOrder_OrderedAtUtc_CollectedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryOrder]'))
 ALTER TABLE [dbo].[LaboratoryOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryOrder_OrderedAtUtc_CollectedAtUtc] CHECK ([OrderedAtUtc] IS NULL OR [CollectedAtUtc] IS NULL OR [OrderedAtUtc]<=[CollectedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryOrder_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryOrder]'))
 ALTER TABLE [dbo].[LaboratoryOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryOrder_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryOrder_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryOrder]'))
 ALTER TABLE [dbo].[LaboratoryOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryOrder_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_LaboratoryOrder_Audit] ON [dbo].[LaboratoryOrder] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_LaboratoryOrder_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[LaboratoryOrderID]=i.[LaboratoryOrderID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[LaboratoryOrder] t JOIN inserted i ON t.[LaboratoryOrderID]=i.[LaboratoryOrderID] LEFT JOIN deleted d ON d.[LaboratoryOrderID]=i.[LaboratoryOrderID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryResult_ReferenceLow_ReferenceHigh' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryResult]'))
 ALTER TABLE [dbo].[LaboratoryResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryResult_ReferenceLow_ReferenceHigh] CHECK ([ReferenceLow] IS NULL OR [ReferenceHigh] IS NULL OR [ReferenceLow]<=[ReferenceHigh]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryResult_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryResult]'))
 ALTER TABLE [dbo].[LaboratoryResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryResult_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryResult_NumericValue_Unit' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryResult]'))
 ALTER TABLE [dbo].[LaboratoryResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryResult_NumericValue_Unit] CHECK ([NumericValue] IS NULL OR [ResultUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryResult_ReferenceUnit' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryResult]'))
 ALTER TABLE [dbo].[LaboratoryResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryResult_ReferenceUnit] CHECK (([ReferenceLow] IS NULL AND [ReferenceHigh] IS NULL) OR [ResultUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_LaboratoryResult_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[LaboratoryResult]'))
 ALTER TABLE [dbo].[LaboratoryResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_LaboratoryResult_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_LaboratoryResult_Audit] ON [dbo].[LaboratoryResult] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_LaboratoryResult_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[LaboratoryResultID]=i.[LaboratoryResultID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[LaboratoryResult] t JOIN inserted i ON t.[LaboratoryResultID]=i.[LaboratoryResultID] LEFT JOIN deleted d ON d.[LaboratoryResultID]=i.[LaboratoryResultID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_VitalSign_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[VitalSign]'))
 ALTER TABLE [dbo].[VitalSign] WITH CHECK ADD CONSTRAINT [CK_Synthetic_VitalSign_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_VitalSign_NumericValue_Unit' AND parent_object_id=OBJECT_ID(N'[dbo].[VitalSign]'))
 ALTER TABLE [dbo].[VitalSign] WITH CHECK ADD CONSTRAINT [CK_Synthetic_VitalSign_NumericValue_Unit] CHECK ([NumericValue] IS NULL OR [ValueUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_VitalSign_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[VitalSign]'))
 ALTER TABLE [dbo].[VitalSign] WITH CHECK ADD CONSTRAINT [CK_Synthetic_VitalSign_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_VitalSign_Audit] ON [dbo].[VitalSign] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_VitalSign_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[VitalSignID]=i.[VitalSignID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[VitalSign] t JOIN inserted i ON t.[VitalSignID]=i.[VitalSignID] LEFT JOIN deleted d ON d.[VitalSignID]=i.[VitalSignID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Coverage_EffectiveDate_TerminationDate' AND parent_object_id=OBJECT_ID(N'[dbo].[Coverage]'))
 ALTER TABLE [dbo].[Coverage] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Coverage_EffectiveDate_TerminationDate] CHECK ([EffectiveDate] IS NULL OR [TerminationDate] IS NULL OR [EffectiveDate]<=[TerminationDate]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Coverage_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Coverage]'))
 ALTER TABLE [dbo].[Coverage] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Coverage_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Coverage_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Coverage]'))
 ALTER TABLE [dbo].[Coverage] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Coverage_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Coverage_Audit] ON [dbo].[Coverage] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Coverage_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[CoverageID]=i.[CoverageID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Coverage] t JOIN inserted i ON t.[CoverageID]=i.[CoverageID] LEFT JOIN deleted d ON d.[CoverageID]=i.[CoverageID];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Appointment_ScheduledStartAtUtc_ScheduledEndAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Appointment]'))
 ALTER TABLE [dbo].[Appointment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Appointment_ScheduledStartAtUtc_ScheduledEndAtUtc] CHECK ([ScheduledStartAtUtc] IS NULL OR [ScheduledEndAtUtc] IS NULL OR [ScheduledStartAtUtc]<=[ScheduledEndAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Appointment_CreatedAtUtc_ModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[Appointment]'))
 ALTER TABLE [dbo].[Appointment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Appointment_CreatedAtUtc_ModifiedAtUtc] CHECK ([CreatedAtUtc] IS NULL OR [ModifiedAtUtc] IS NULL OR [CreatedAtUtc]<=[ModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_Appointment_Deleted' AND parent_object_id=OBJECT_ID(N'[dbo].[Appointment]'))
 ALTER TABLE [dbo].[Appointment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_Appointment_Deleted] CHECK (([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR ([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL));

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_Appointment_Encounter' AND object_id=OBJECT_ID(N'[dbo].[Appointment]'))
 CREATE UNIQUE INDEX [UX_Synthetic_Appointment_Encounter] ON [dbo].[Appointment] ([EncounterID]) WHERE [EncounterID] IS NOT NULL;

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_Appointment_Audit] ON [dbo].[Appointment] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_Appointment_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[AppointmentID]=i.[AppointmentID])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [CreatedAtUtc]=COALESCE(d.[CreatedAtUtc],@now), [ModifiedAtUtc]=@now, [DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN COALESCE(d.DeletedAtUtc,@now) ELSE NULL END FROM [dbo].[Appointment] t JOIN inserted i ON t.[AppointmentID]=i.[AppointmentID] LEFT JOIN deleted d ON d.[AppointmentID]=i.[AppointmentID];
END;');

EXEC(N'CREATE OR ALTER PROCEDURE [dbo].[ValidateSyntheticSource] AS
BEGIN
SET NOCOUNT ON;
IF EXISTS(SELECT 1 FROM [dbo].Appointment a JOIN [dbo].Encounter e ON a.EncounterID=e.EncounterID WHERE a.PatientID<>e.PatientID) THROW 51003,''Appointment encounter patient mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].Encounter e JOIN [dbo].Coverage c ON e.PrimaryCoverageID=c.CoverageID WHERE e.PatientID<>c.PatientID OR CAST(e.ArrivalAtUtc AS date)<c.EffectiveDate OR CAST(e.ArrivalAtUtc AS date)>c.TerminationDate) THROW 51003,''Encounter coverage patient or date mismatch.'',1;
END;');

EXEC [dbo].[ValidateSyntheticSource];

COMMIT TRANSACTION;
