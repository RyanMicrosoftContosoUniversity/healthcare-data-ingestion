-- Source-only upgrade 002. Offline-generated; review before Azure SQL execution.

-- No third database. Requires the approved 001 baseline in this source database.

SET XACT_ABORT ON;
SET NOCOUNT ON;
BEGIN TRANSACTION;

DECLARE @result int; EXEC @result=sys.sp_getapplock @Resource=N'healthcare-ingestion-source', @DbPrincipal=N'public', @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=0; IF @result<0 THROW 51004,'Source DDL requires the exclusive extraction fence.',1;

IF OBJECT_ID(N'[dbo].[DimPatient]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[DimProvider]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[DimDepartment]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[DimDate]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[DimDiagnosis]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[DimProcedure]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[DimMedication]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[DimCoverage]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[FactEncounter]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[FactDiagnosis]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[FactProcedure]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[FactMedicationOrder]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[FactMedicationAdministration]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[FactLabResult]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'[dbo].[FactAppointment]',N'U') IS NULL THROW 51000,'Approved source baseline is missing.',1;

IF OBJECT_ID(N'dbo.SyntheticSourceCheckpoint',N'U') IS NULL
CREATE TABLE dbo.SyntheticSourceCheckpoint (
 SourceSystem varchar(30) NOT NULL PRIMARY KEY,
 BatchName varchar(80) NOT NULL, PopulationDigest char(64) NOT NULL,
 MappingDigest char(64) NOT NULL, ContractDigest char(64) NOT NULL,
 RowCount bigint NOT NULL CHECK(RowCount>=0), CommittedAtUtc datetime2(7) NOT NULL,
 CoverageStartUtc datetime2(7) NOT NULL, CoverageEndUtc datetime2(7) NOT NULL,
 CONSTRAINT CK_SyntheticSourceIdentity CHECK(SourceSystem='Caboodle')
);

IF OBJECT_ID(N'dbo.SyntheticSourceBatchCommit',N'U') IS NULL
CREATE TABLE dbo.SyntheticSourceBatchCommit (
 SourceSystem varchar(30) NOT NULL, BatchName varchar(80) NOT NULL,
 PopulationDigest char(64) NOT NULL, MappingDigest char(64) NOT NULL,
 ContractDigest char(64) NOT NULL, RowCount bigint NOT NULL CHECK(RowCount>=0),
 CommittedAtUtc datetime2(7) NOT NULL,
 CoverageStartUtc datetime2(7) NOT NULL, CoverageEndUtc datetime2(7) NOT NULL,
 CONSTRAINT PK_SyntheticSourceBatchCommit PRIMARY KEY(SourceSystem,BatchName),
 CONSTRAINT CK_SyntheticBatchSource CHECK(SourceSystem='Caboodle')
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

EXEC(N'CREATE OR ALTER PROCEDURE dbo.PrepareSyntheticSourcePublication AS BEGIN SET NOCOUNT ON; IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1; DECLARE @upper datetime2(7); SELECT @upper=MAX(a.audit_at) FROM (SELECT MAX(CommittedAtUtc) AS audit_at FROM dbo.SyntheticSourceCheckpoint UNION ALL SELECT MAX(CommittedAtUtc) AS audit_at FROM dbo.SyntheticSourceBatchCommit UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimPatient] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimProvider] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimDepartment] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimDate] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimDiagnosis] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimProcedure] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimMedication] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[DimCoverage] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[FactEncounter] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[FactDiagnosis] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[FactProcedure] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[FactMedicationOrder] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[FactMedicationAdministration] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[FactLabResult] UNION ALL SELECT MAX([EtlModifiedAtUtc]) AS audit_at FROM [dbo].[FactAppointment]) a; DECLARE @publication datetime2(7)=SYSUTCDATETIME(); IF @publication<=@upper SET @publication=DATEADD(nanosecond,100,@upper); DECLARE @text varchar(33)=CONVERT(varchar(33),@publication,126); EXEC sys.sp_set_session_context @key=N''source_publication_at'', @value=@text,@read_only=1; END;');

EXEC(N'CREATE OR ALTER TRIGGER dbo.TR_SyntheticSourceBatchCommit_Immutable ON dbo.SyntheticSourceBatchCommit AFTER INSERT,UPDATE,DELETE AS BEGIN SET NOCOUNT ON; IF EXISTS(SELECT 1 FROM deleted) THROW 51005,''Committed source batch evidence is immutable.'',1; IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1; DECLARE @publication datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at'')); IF @publication IS NULL OR EXISTS(SELECT 1 FROM inserted WHERE CommittedAtUtc<>@publication) OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@publication) THROW 51007,''Source publication audit must advance the committed boundary.'',1; IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.SyntheticSourceCheckpoint c ON i.SourceSystem=c.SourceSystem WHERE i.CoverageStartUtc<>c.CoverageEndUtc OR i.CoverageEndUtc<c.CoverageEndUtc) THROW 51009,''Source coverage must continue from the prior committed horizon.'',1; END;');

EXEC(N'CREATE OR ALTER TRIGGER dbo.TR_SyntheticSourceCheckpoint_Integrity ON dbo.SyntheticSourceCheckpoint AFTER INSERT,UPDATE,DELETE AS BEGIN SET NOCOUNT ON; IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1; IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE i.SourceSystem=d.SourceSystem)) THROW 51005,''Committed source checkpoint deletion is prohibited.'',1; IF EXISTS(SELECT 1 FROM inserted i LEFT JOIN dbo.SyntheticSourceBatchCommit b ON i.SourceSystem=b.SourceSystem AND i.BatchName=b.BatchName WHERE b.BatchName IS NULL OR i.PopulationDigest<>b.PopulationDigest OR i.MappingDigest<>b.MappingDigest OR i.ContractDigest<>b.ContractDigest OR i.RowCount<>b.RowCount OR i.CommittedAtUtc<>b.CommittedAtUtc OR i.CoverageStartUtc<>b.CoverageStartUtc OR i.CoverageEndUtc<>b.CoverageEndUtc) THROW 51005,''Source checkpoint must match its immutable coverage ledger.'',1; IF EXISTS(SELECT 1 FROM inserted i JOIN deleted d ON i.SourceSystem=d.SourceSystem WHERE i.CommittedAtUtc<=d.CommittedAtUtc OR i.CoverageStartUtc<>d.CoverageEndUtc OR i.CoverageEndUtc<d.CoverageEndUtc) THROW 51009,''Source checkpoint coverage or audit boundary regresses.'',1; END;');

IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name=N'FK_SyntheticSourceCheckpoint_Batch' AND parent_object_id=OBJECT_ID(N'dbo.SyntheticSourceCheckpoint'))
ALTER TABLE dbo.SyntheticSourceCheckpoint WITH CHECK ADD CONSTRAINT FK_SyntheticSourceCheckpoint_Batch FOREIGN KEY(SourceSystem,BatchName) REFERENCES dbo.SyntheticSourceBatchCommit(SourceSystem,BatchName);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimPatient_BirthDate_DeathDate' AND parent_object_id=OBJECT_ID(N'[dbo].[DimPatient]'))
 ALTER TABLE [dbo].[DimPatient] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimPatient_BirthDate_DeathDate] CHECK ([BirthDate] IS NULL OR [DeathDate] IS NULL OR [BirthDate]<=[DeathDate]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimPatient_EffectiveFromUtc_EffectiveToUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimPatient]'))
 ALTER TABLE [dbo].[DimPatient] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimPatient_EffectiveFromUtc_EffectiveToUtc] CHECK ([EffectiveFromUtc] IS NULL OR [EffectiveToUtc] IS NULL OR [EffectiveFromUtc]<[EffectiveToUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimPatient_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimPatient]'))
 ALTER TABLE [dbo].[DimPatient] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimPatient_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimPatient_Current' AND parent_object_id=OBJECT_ID(N'[dbo].[DimPatient]'))
 ALTER TABLE [dbo].[DimPatient] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimPatient_Current] CHECK (([IsCurrent]=1 AND [EffectiveToUtc] IS NULL) OR ([IsCurrent]=0 AND [EffectiveToUtc] IS NOT NULL));

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimPatient_Current' AND object_id=OBJECT_ID(N'[dbo].[DimPatient]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimPatient_Current] ON [dbo].[DimPatient] ([OriginSystem],[SourcePatientID]) WHERE [IsCurrent]=1;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimPatient_Version' AND object_id=OBJECT_ID(N'[dbo].[DimPatient]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimPatient_Version] ON [dbo].[DimPatient] ([OriginSystem],[SourcePatientID],[EffectiveFromUtc]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimPatient_Audit] ON [dbo].[DimPatient] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimPatient_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[PatientKey]=i.[PatientKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimPatient] t JOIN inserted i ON t.[PatientKey]=i.[PatientKey] LEFT JOIN deleted d ON d.[PatientKey]=i.[PatientKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimProvider_EffectiveFromUtc_EffectiveToUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimProvider]'))
 ALTER TABLE [dbo].[DimProvider] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimProvider_EffectiveFromUtc_EffectiveToUtc] CHECK ([EffectiveFromUtc] IS NULL OR [EffectiveToUtc] IS NULL OR [EffectiveFromUtc]<[EffectiveToUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimProvider_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimProvider]'))
 ALTER TABLE [dbo].[DimProvider] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimProvider_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimProvider_Current' AND parent_object_id=OBJECT_ID(N'[dbo].[DimProvider]'))
 ALTER TABLE [dbo].[DimProvider] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimProvider_Current] CHECK (([IsCurrent]=1 AND [EffectiveToUtc] IS NULL) OR ([IsCurrent]=0 AND [EffectiveToUtc] IS NOT NULL));

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimProvider_Current' AND object_id=OBJECT_ID(N'[dbo].[DimProvider]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimProvider_Current] ON [dbo].[DimProvider] ([OriginSystem],[SourceProviderID]) WHERE [IsCurrent]=1;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimProvider_Version' AND object_id=OBJECT_ID(N'[dbo].[DimProvider]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimProvider_Version] ON [dbo].[DimProvider] ([OriginSystem],[SourceProviderID],[EffectiveFromUtc]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimProvider_Audit] ON [dbo].[DimProvider] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimProvider_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[ProviderKey]=i.[ProviderKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimProvider] t JOIN inserted i ON t.[ProviderKey]=i.[ProviderKey] LEFT JOIN deleted d ON d.[ProviderKey]=i.[ProviderKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimDepartment_EffectiveFromUtc_EffectiveToUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimDepartment]'))
 ALTER TABLE [dbo].[DimDepartment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimDepartment_EffectiveFromUtc_EffectiveToUtc] CHECK ([EffectiveFromUtc] IS NULL OR [EffectiveToUtc] IS NULL OR [EffectiveFromUtc]<[EffectiveToUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimDepartment_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimDepartment]'))
 ALTER TABLE [dbo].[DimDepartment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimDepartment_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimDepartment_Current' AND parent_object_id=OBJECT_ID(N'[dbo].[DimDepartment]'))
 ALTER TABLE [dbo].[DimDepartment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimDepartment_Current] CHECK (([IsCurrent]=1 AND [EffectiveToUtc] IS NULL) OR ([IsCurrent]=0 AND [EffectiveToUtc] IS NOT NULL));

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimDepartment_Current' AND object_id=OBJECT_ID(N'[dbo].[DimDepartment]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimDepartment_Current] ON [dbo].[DimDepartment] ([OriginSystem],[SourceDepartmentID]) WHERE [IsCurrent]=1;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimDepartment_Version' AND object_id=OBJECT_ID(N'[dbo].[DimDepartment]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimDepartment_Version] ON [dbo].[DimDepartment] ([OriginSystem],[SourceDepartmentID],[EffectiveFromUtc]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimDepartment_Audit] ON [dbo].[DimDepartment] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimDepartment_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[DepartmentKey]=i.[DepartmentKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimDepartment] t JOIN inserted i ON t.[DepartmentKey]=i.[DepartmentKey] LEFT JOIN deleted d ON d.[DepartmentKey]=i.[DepartmentKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimDate_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimDate]'))
 ALTER TABLE [dbo].[DimDate] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimDate_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimDate_Audit] ON [dbo].[DimDate] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimDate_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[DateKey]=i.[DateKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimDate] t JOIN inserted i ON t.[DateKey]=i.[DateKey] LEFT JOIN deleted d ON d.[DateKey]=i.[DateKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimDiagnosis_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimDiagnosis]'))
 ALTER TABLE [dbo].[DimDiagnosis] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimDiagnosis_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimDiagnosis_Catalog' AND object_id=OBJECT_ID(N'[dbo].[DimDiagnosis]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimDiagnosis_Catalog] ON [dbo].[DimDiagnosis] ([OriginSystem],[DiagnosisCodeSystem],[DiagnosisCode]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimDiagnosis_Audit] ON [dbo].[DimDiagnosis] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimDiagnosis_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[DiagnosisKey]=i.[DiagnosisKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimDiagnosis] t JOIN inserted i ON t.[DiagnosisKey]=i.[DiagnosisKey] LEFT JOIN deleted d ON d.[DiagnosisKey]=i.[DiagnosisKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimProcedure_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimProcedure]'))
 ALTER TABLE [dbo].[DimProcedure] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimProcedure_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimProcedure_Catalog' AND object_id=OBJECT_ID(N'[dbo].[DimProcedure]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimProcedure_Catalog] ON [dbo].[DimProcedure] ([OriginSystem],[ProcedureCodeSystem],[ProcedureCode]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimProcedure_Audit] ON [dbo].[DimProcedure] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimProcedure_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[ProcedureKey]=i.[ProcedureKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimProcedure] t JOIN inserted i ON t.[ProcedureKey]=i.[ProcedureKey] LEFT JOIN deleted d ON d.[ProcedureKey]=i.[ProcedureKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimMedication_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimMedication]'))
 ALTER TABLE [dbo].[DimMedication] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimMedication_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimMedication_Catalog' AND object_id=OBJECT_ID(N'[dbo].[DimMedication]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimMedication_Catalog] ON [dbo].[DimMedication] ([OriginSystem],[MedicationCodeSystem],[MedicationCode]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimMedication_Audit] ON [dbo].[DimMedication] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimMedication_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[MedicationKey]=i.[MedicationKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimMedication] t JOIN inserted i ON t.[MedicationKey]=i.[MedicationKey] LEFT JOIN deleted d ON d.[MedicationKey]=i.[MedicationKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimCoverage_EffectiveDate_TerminationDate' AND parent_object_id=OBJECT_ID(N'[dbo].[DimCoverage]'))
 ALTER TABLE [dbo].[DimCoverage] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimCoverage_EffectiveDate_TerminationDate] CHECK ([EffectiveDate] IS NULL OR [TerminationDate] IS NULL OR [EffectiveDate]<=[TerminationDate]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimCoverage_EffectiveFromUtc_EffectiveToUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimCoverage]'))
 ALTER TABLE [dbo].[DimCoverage] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimCoverage_EffectiveFromUtc_EffectiveToUtc] CHECK ([EffectiveFromUtc] IS NULL OR [EffectiveToUtc] IS NULL OR [EffectiveFromUtc]<[EffectiveToUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimCoverage_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[DimCoverage]'))
 ALTER TABLE [dbo].[DimCoverage] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimCoverage_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_DimCoverage_Current' AND parent_object_id=OBJECT_ID(N'[dbo].[DimCoverage]'))
 ALTER TABLE [dbo].[DimCoverage] WITH CHECK ADD CONSTRAINT [CK_Synthetic_DimCoverage_Current] CHECK (([IsCurrent]=1 AND [EffectiveToUtc] IS NULL) OR ([IsCurrent]=0 AND [EffectiveToUtc] IS NOT NULL));

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimCoverage_Current' AND object_id=OBJECT_ID(N'[dbo].[DimCoverage]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimCoverage_Current] ON [dbo].[DimCoverage] ([OriginSystem],[SourceCoverageID]) WHERE [IsCurrent]=1;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_DimCoverage_Version' AND object_id=OBJECT_ID(N'[dbo].[DimCoverage]'))
 CREATE UNIQUE INDEX [UX_Synthetic_DimCoverage_Version] ON [dbo].[DimCoverage] ([OriginSystem],[SourceCoverageID],[EffectiveFromUtc]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_DimCoverage_Audit] ON [dbo].[DimCoverage] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_DimCoverage_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[CoverageKey]=i.[CoverageKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[DimCoverage] t JOIN inserted i ON t.[CoverageKey]=i.[CoverageKey] LEFT JOIN deleted d ON d.[CoverageKey]=i.[CoverageKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactEncounter_ArrivalAtUtc_DischargeAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactEncounter]'))
 ALTER TABLE [dbo].[FactEncounter] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactEncounter_ArrivalAtUtc_DischargeAtUtc] CHECK ([ArrivalAtUtc] IS NULL OR [DischargeAtUtc] IS NULL OR [ArrivalAtUtc]<=[DischargeAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactEncounter_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactEncounter]'))
 ALTER TABLE [dbo].[FactEncounter] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactEncounter_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactEncounter_SourceEvent' AND object_id=OBJECT_ID(N'[dbo].[FactEncounter]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactEncounter_SourceEvent] ON [dbo].[FactEncounter] ([OriginSystem],[SourceEncounterID]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_FactEncounter_Audit] ON [dbo].[FactEncounter] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_FactEncounter_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[EncounterKey]=i.[EncounterKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[FactEncounter] t JOIN inserted i ON t.[EncounterKey]=i.[EncounterKey] LEFT JOIN deleted d ON d.[EncounterKey]=i.[EncounterKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactDiagnosis_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactDiagnosis]'))
 ALTER TABLE [dbo].[FactDiagnosis] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactDiagnosis_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactDiagnosis_Sequence' AND parent_object_id=OBJECT_ID(N'[dbo].[FactDiagnosis]'))
 ALTER TABLE [dbo].[FactDiagnosis] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactDiagnosis_Sequence] CHECK ([DiagnosisSequence]>0);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactDiagnosis_SourceEvent' AND object_id=OBJECT_ID(N'[dbo].[FactDiagnosis]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactDiagnosis_SourceEvent] ON [dbo].[FactDiagnosis] ([OriginSystem],[SourceDiagnosisID]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactDiagnosis_Sequence' AND object_id=OBJECT_ID(N'[dbo].[FactDiagnosis]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactDiagnosis_Sequence] ON [dbo].[FactDiagnosis] ([SourceEncounterID],[DiagnosisSequence]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactDiagnosis_Primary' AND object_id=OBJECT_ID(N'[dbo].[FactDiagnosis]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactDiagnosis_Primary] ON [dbo].[FactDiagnosis] ([SourceEncounterID]) WHERE [IsPrimary]=1 AND [IsDeleted]=0 AND [DiagnosisStatus]<>N'canceled' AND [DiagnosisStatus]<>N'cancelled' AND [DiagnosisStatus]<>N'inactive';

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_FactDiagnosis_Audit] ON [dbo].[FactDiagnosis] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_FactDiagnosis_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[DiagnosisFactKey]=i.[DiagnosisFactKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[FactDiagnosis] t JOIN inserted i ON t.[DiagnosisFactKey]=i.[DiagnosisFactKey] LEFT JOIN deleted d ON d.[DiagnosisFactKey]=i.[DiagnosisFactKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactProcedure_OrderedAtUtc_PerformedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactProcedure]'))
 ALTER TABLE [dbo].[FactProcedure] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactProcedure_OrderedAtUtc_PerformedAtUtc] CHECK ([OrderedAtUtc] IS NULL OR [PerformedAtUtc] IS NULL OR [OrderedAtUtc]<=[PerformedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactProcedure_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactProcedure]'))
 ALTER TABLE [dbo].[FactProcedure] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactProcedure_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactProcedure_SourceEvent' AND object_id=OBJECT_ID(N'[dbo].[FactProcedure]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactProcedure_SourceEvent] ON [dbo].[FactProcedure] ([OriginSystem],[SourceProcedureID]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_FactProcedure_Audit] ON [dbo].[FactProcedure] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_FactProcedure_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[ProcedureFactKey]=i.[ProcedureFactKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[FactProcedure] t JOIN inserted i ON t.[ProcedureFactKey]=i.[ProcedureFactKey] LEFT JOIN deleted d ON d.[ProcedureFactKey]=i.[ProcedureFactKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactMedicationOrder_OrderedAtUtc_StartAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactMedicationOrder]'))
 ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactMedicationOrder_OrderedAtUtc_StartAtUtc] CHECK ([OrderedAtUtc] IS NULL OR [StartAtUtc] IS NULL OR [OrderedAtUtc]<=[StartAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactMedicationOrder_StartAtUtc_EndAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactMedicationOrder]'))
 ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactMedicationOrder_StartAtUtc_EndAtUtc] CHECK ([StartAtUtc] IS NULL OR [EndAtUtc] IS NULL OR [StartAtUtc]<=[EndAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactMedicationOrder_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactMedicationOrder]'))
 ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactMedicationOrder_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactMedicationOrder_OrderedDose_Unit' AND parent_object_id=OBJECT_ID(N'[dbo].[FactMedicationOrder]'))
 ALTER TABLE [dbo].[FactMedicationOrder] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactMedicationOrder_OrderedDose_Unit] CHECK ([OrderedDose] IS NULL OR [DoseUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactMedicationOrder_SourceEvent' AND object_id=OBJECT_ID(N'[dbo].[FactMedicationOrder]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactMedicationOrder_SourceEvent] ON [dbo].[FactMedicationOrder] ([OriginSystem],[SourceMedicationOrderID]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_FactMedicationOrder_Audit] ON [dbo].[FactMedicationOrder] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_FactMedicationOrder_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[MedicationOrderKey]=i.[MedicationOrderKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[FactMedicationOrder] t JOIN inserted i ON t.[MedicationOrderKey]=i.[MedicationOrderKey] LEFT JOIN deleted d ON d.[MedicationOrderKey]=i.[MedicationOrderKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactMedicationAdministration_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactMedicationAdministration]'))
 ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactMedicationAdministration_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactMedicationAdministration_AdministeredDose_Unit' AND parent_object_id=OBJECT_ID(N'[dbo].[FactMedicationAdministration]'))
 ALTER TABLE [dbo].[FactMedicationAdministration] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactMedicationAdministration_AdministeredDose_Unit] CHECK ([AdministeredDose] IS NULL OR [DoseUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactMedicationAdministration_SourceEvent' AND object_id=OBJECT_ID(N'[dbo].[FactMedicationAdministration]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactMedicationAdministration_SourceEvent] ON [dbo].[FactMedicationAdministration] ([OriginSystem],[SourceMedicationAdministrationID]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_FactMedicationAdministration_Audit] ON [dbo].[FactMedicationAdministration] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_FactMedicationAdministration_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[MedicationAdministrationKey]=i.[MedicationAdministrationKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[FactMedicationAdministration] t JOIN inserted i ON t.[MedicationAdministrationKey]=i.[MedicationAdministrationKey] LEFT JOIN deleted d ON d.[MedicationAdministrationKey]=i.[MedicationAdministrationKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactLabResult_ReferenceLow_ReferenceHigh' AND parent_object_id=OBJECT_ID(N'[dbo].[FactLabResult]'))
 ALTER TABLE [dbo].[FactLabResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactLabResult_ReferenceLow_ReferenceHigh] CHECK ([ReferenceLow] IS NULL OR [ReferenceHigh] IS NULL OR [ReferenceLow]<=[ReferenceHigh]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactLabResult_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactLabResult]'))
 ALTER TABLE [dbo].[FactLabResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactLabResult_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactLabResult_NumericValue_Unit' AND parent_object_id=OBJECT_ID(N'[dbo].[FactLabResult]'))
 ALTER TABLE [dbo].[FactLabResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactLabResult_NumericValue_Unit] CHECK ([NumericValue] IS NULL OR [ResultUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactLabResult_ReferenceUnit' AND parent_object_id=OBJECT_ID(N'[dbo].[FactLabResult]'))
 ALTER TABLE [dbo].[FactLabResult] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactLabResult_ReferenceUnit] CHECK (([ReferenceLow] IS NULL AND [ReferenceHigh] IS NULL) OR [ResultUnit] IS NOT NULL);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactLabResult_SourceEvent' AND object_id=OBJECT_ID(N'[dbo].[FactLabResult]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactLabResult_SourceEvent] ON [dbo].[FactLabResult] ([OriginSystem],[SourceLaboratoryResultID]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_FactLabResult_Audit] ON [dbo].[FactLabResult] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_FactLabResult_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[LabResultKey]=i.[LabResultKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[FactLabResult] t JOIN inserted i ON t.[LabResultKey]=i.[LabResultKey] LEFT JOIN deleted d ON d.[LabResultKey]=i.[LabResultKey];
END;');

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactAppointment_ScheduledStartAtUtc_ScheduledEndAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactAppointment]'))
 ALTER TABLE [dbo].[FactAppointment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactAppointment_ScheduledStartAtUtc_ScheduledEndAtUtc] CHECK ([ScheduledStartAtUtc] IS NULL OR [ScheduledEndAtUtc] IS NULL OR [ScheduledStartAtUtc]<=[ScheduledEndAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Synthetic_FactAppointment_EtlCreatedAtUtc_EtlModifiedAtUtc' AND parent_object_id=OBJECT_ID(N'[dbo].[FactAppointment]'))
 ALTER TABLE [dbo].[FactAppointment] WITH CHECK ADD CONSTRAINT [CK_Synthetic_FactAppointment_EtlCreatedAtUtc_EtlModifiedAtUtc] CHECK ([EtlCreatedAtUtc] IS NULL OR [EtlModifiedAtUtc] IS NULL OR [EtlCreatedAtUtc]<=[EtlModifiedAtUtc]);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'UX_Synthetic_FactAppointment_SourceEvent' AND object_id=OBJECT_ID(N'[dbo].[FactAppointment]'))
 CREATE UNIQUE INDEX [UX_Synthetic_FactAppointment_SourceEvent] ON [dbo].[FactAppointment] ([OriginSystem],[SourceAppointmentID]);

EXEC(N'CREATE OR ALTER TRIGGER [dbo].[TR_Synthetic_FactAppointment_Audit] ON [dbo].[FactAppointment] AFTER INSERT,UPDATE,DELETE AS
BEGIN
SET NOCOUNT ON;
IF TRIGGER_NESTLEVEL(OBJECT_ID(N''[dbo].[TR_Synthetic_FactAppointment_Audit]''),''AFTER'',''DML'')>1 RETURN;
IF APPLOCK_MODE(N''public'',N''healthcare-ingestion-source'',N''Transaction'')<>N''Exclusive'' THROW 51004,''Source writes require the exclusive extraction fence.'',1;
IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE d.[AppointmentKey]=i.[AppointmentKey])) THROW 51002,''Physical deletes and primary-key changes are prohibited.'',1;
IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id''))) OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''source_batch_id'')) IS NULL THROW 51001,''Caboodle writes require approved loader batch context.'',1;
DECLARE @now datetime2(7)=TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N''source_publication_at''));
IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@now) THROW 51007,''Source publication audit must advance the committed boundary.'',1;
UPDATE t SET [EtlCreatedAtUtc]=COALESCE(d.[EtlCreatedAtUtc],@now), [EtlModifiedAtUtc]=@now FROM [dbo].[FactAppointment] t JOIN inserted i ON t.[AppointmentKey]=i.[AppointmentKey] LEFT JOIN deleted d ON d.[AppointmentKey]=i.[AppointmentKey];
END;');

EXEC(N'CREATE OR ALTER PROCEDURE [dbo].[ValidateSyntheticSource] AS
BEGIN
SET NOCOUNT ON;
IF EXISTS(SELECT 1 FROM [dbo].[DimPatient] a JOIN [dbo].[DimPatient] b ON a.OriginSystem=b.OriginSystem AND a.[SourcePatientID]=b.[SourcePatientID] AND a.[PatientKey]<b.[PatientKey] WHERE (a.EffectiveToUtc IS NULL OR b.EffectiveFromUtc<a.EffectiveToUtc) AND (b.EffectiveToUtc IS NULL OR a.EffectiveFromUtc<b.EffectiveToUtc)) THROW 51003,''DimPatient validity overlap.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[DimPatient] GROUP BY OriginSystem,[SourcePatientID] HAVING SUM(CASE WHEN IsCurrent=1 THEN 1 ELSE 0 END)<>1) THROW 51003,''DimPatient current version missing or ambiguous.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[DimProvider] a JOIN [dbo].[DimProvider] b ON a.OriginSystem=b.OriginSystem AND a.[SourceProviderID]=b.[SourceProviderID] AND a.[ProviderKey]<b.[ProviderKey] WHERE (a.EffectiveToUtc IS NULL OR b.EffectiveFromUtc<a.EffectiveToUtc) AND (b.EffectiveToUtc IS NULL OR a.EffectiveFromUtc<b.EffectiveToUtc)) THROW 51003,''DimProvider validity overlap.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[DimProvider] GROUP BY OriginSystem,[SourceProviderID] HAVING SUM(CASE WHEN IsCurrent=1 THEN 1 ELSE 0 END)<>1) THROW 51003,''DimProvider current version missing or ambiguous.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[DimDepartment] a JOIN [dbo].[DimDepartment] b ON a.OriginSystem=b.OriginSystem AND a.[SourceDepartmentID]=b.[SourceDepartmentID] AND a.[DepartmentKey]<b.[DepartmentKey] WHERE (a.EffectiveToUtc IS NULL OR b.EffectiveFromUtc<a.EffectiveToUtc) AND (b.EffectiveToUtc IS NULL OR a.EffectiveFromUtc<b.EffectiveToUtc)) THROW 51003,''DimDepartment validity overlap.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[DimDepartment] GROUP BY OriginSystem,[SourceDepartmentID] HAVING SUM(CASE WHEN IsCurrent=1 THEN 1 ELSE 0 END)<>1) THROW 51003,''DimDepartment current version missing or ambiguous.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[DimCoverage] a JOIN [dbo].[DimCoverage] b ON a.OriginSystem=b.OriginSystem AND a.[SourceCoverageID]=b.[SourceCoverageID] AND a.[CoverageKey]<b.[CoverageKey] WHERE (a.EffectiveToUtc IS NULL OR b.EffectiveFromUtc<a.EffectiveToUtc) AND (b.EffectiveToUtc IS NULL OR a.EffectiveFromUtc<b.EffectiveToUtc)) THROW 51003,''DimCoverage validity overlap.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[DimCoverage] GROUP BY OriginSystem,[SourceCoverageID] HAVING SUM(CASE WHEN IsCurrent=1 THEN 1 ELSE 0 END)<>1) THROW 51003,''DimCoverage current version missing or ambiguous.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactEncounter] f JOIN [dbo].[DimPatient] d ON f.[PatientKey]=d.[PatientKey] WHERE f.[ArrivalAtUtc]<d.EffectiveFromUtc OR f.[ArrivalAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactEncounter event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactEncounter] f JOIN [dbo].[DimDepartment] d ON f.[DepartmentKey]=d.[DepartmentKey] WHERE f.[ArrivalAtUtc]<d.EffectiveFromUtc OR f.[ArrivalAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactEncounter event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactEncounter] f JOIN [dbo].[DimCoverage] d ON f.[CoverageKey]=d.[CoverageKey] WHERE f.[ArrivalAtUtc]<d.EffectiveFromUtc OR f.[ArrivalAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactEncounter event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactEncounter] f JOIN [dbo].[DimProvider] d ON f.[AttendingProviderKey]=d.[ProviderKey] WHERE f.[ArrivalAtUtc]<d.EffectiveFromUtc OR f.[ArrivalAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactEncounter event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactEncounter] WHERE ([ArrivalDateKey] IS NULL AND [ArrivalAtUtc] IS NOT NULL) OR ([ArrivalDateKey] IS NOT NULL AND [ArrivalAtUtc] IS NULL) OR [ArrivalDateKey]<>CONVERT(int,CONVERT(char(8),[ArrivalAtUtc],112))) THROW 51003,''FactEncounter date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactEncounter] WHERE ([DischargeDateKey] IS NULL AND [DischargeAtUtc] IS NOT NULL) OR ([DischargeDateKey] IS NOT NULL AND [DischargeAtUtc] IS NULL) OR [DischargeDateKey]<>CONVERT(int,CONVERT(char(8),[DischargeAtUtc],112))) THROW 51003,''FactEncounter date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactDiagnosis] f JOIN [dbo].[DimPatient] d ON f.[PatientKey]=d.[PatientKey] WHERE f.[DiagnosedAtUtc]<d.EffectiveFromUtc OR f.[DiagnosedAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactDiagnosis event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactDiagnosis] f JOIN [dbo].[DimDepartment] d ON f.[DepartmentKey]=d.[DepartmentKey] WHERE f.[DiagnosedAtUtc]<d.EffectiveFromUtc OR f.[DiagnosedAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactDiagnosis event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactDiagnosis] f JOIN [dbo].[DimProvider] d ON f.[DiagnosingProviderKey]=d.[ProviderKey] WHERE f.[DiagnosedAtUtc]<d.EffectiveFromUtc OR f.[DiagnosedAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactDiagnosis event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactDiagnosis] WHERE ([DiagnosisDateKey] IS NULL AND [DiagnosedAtUtc] IS NOT NULL) OR ([DiagnosisDateKey] IS NOT NULL AND [DiagnosedAtUtc] IS NULL) OR [DiagnosisDateKey]<>CONVERT(int,CONVERT(char(8),[DiagnosedAtUtc],112))) THROW 51003,''FactDiagnosis date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactDiagnosis] f LEFT JOIN [dbo].FactEncounter e ON f.SourceEncounterID=e.SourceEncounterID AND f.OriginSystem=e.OriginSystem JOIN [dbo].DimPatient p ON f.PatientKey=p.PatientKey LEFT JOIN [dbo].DimPatient q ON e.PatientKey=q.PatientKey WHERE e.EncounterKey IS NULL OR p.SourcePatientID<>q.SourcePatientID OR f.IsDeleted<e.IsDeleted) THROW 51003,''FactDiagnosis encounter lineage or parent deletion mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactProcedure] f JOIN [dbo].[DimPatient] d ON f.[PatientKey]=d.[PatientKey] WHERE COALESCE(f.[PerformedAtUtc],f.[OrderedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[PerformedAtUtc],f.[OrderedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactProcedure event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactProcedure] f JOIN [dbo].[DimDepartment] d ON f.[DepartmentKey]=d.[DepartmentKey] WHERE COALESCE(f.[PerformedAtUtc],f.[OrderedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[PerformedAtUtc],f.[OrderedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactProcedure event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactProcedure] f JOIN [dbo].[DimProvider] d ON f.[PerformingProviderKey]=d.[ProviderKey] WHERE COALESCE(f.[PerformedAtUtc],f.[OrderedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[PerformedAtUtc],f.[OrderedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactProcedure event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactProcedure] WHERE ([OrderedDateKey] IS NULL AND [OrderedAtUtc] IS NOT NULL) OR ([OrderedDateKey] IS NOT NULL AND [OrderedAtUtc] IS NULL) OR [OrderedDateKey]<>CONVERT(int,CONVERT(char(8),[OrderedAtUtc],112))) THROW 51003,''FactProcedure date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactProcedure] WHERE ([PerformedDateKey] IS NULL AND [PerformedAtUtc] IS NOT NULL) OR ([PerformedDateKey] IS NOT NULL AND [PerformedAtUtc] IS NULL) OR [PerformedDateKey]<>CONVERT(int,CONVERT(char(8),[PerformedAtUtc],112))) THROW 51003,''FactProcedure date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactProcedure] f LEFT JOIN [dbo].FactEncounter e ON f.SourceEncounterID=e.SourceEncounterID AND f.OriginSystem=e.OriginSystem JOIN [dbo].DimPatient p ON f.PatientKey=p.PatientKey LEFT JOIN [dbo].DimPatient q ON e.PatientKey=q.PatientKey WHERE e.EncounterKey IS NULL OR p.SourcePatientID<>q.SourcePatientID OR f.IsDeleted<e.IsDeleted) THROW 51003,''FactProcedure encounter lineage or parent deletion mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationOrder] f JOIN [dbo].[DimPatient] d ON f.[PatientKey]=d.[PatientKey] WHERE f.[OrderedAtUtc]<d.EffectiveFromUtc OR f.[OrderedAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactMedicationOrder event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationOrder] f JOIN [dbo].[DimDepartment] d ON f.[DepartmentKey]=d.[DepartmentKey] WHERE f.[OrderedAtUtc]<d.EffectiveFromUtc OR f.[OrderedAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactMedicationOrder event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationOrder] f JOIN [dbo].[DimProvider] d ON f.[OrderingProviderKey]=d.[ProviderKey] WHERE f.[OrderedAtUtc]<d.EffectiveFromUtc OR f.[OrderedAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactMedicationOrder event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationOrder] WHERE ([OrderedDateKey] IS NULL AND [OrderedAtUtc] IS NOT NULL) OR ([OrderedDateKey] IS NOT NULL AND [OrderedAtUtc] IS NULL) OR [OrderedDateKey]<>CONVERT(int,CONVERT(char(8),[OrderedAtUtc],112))) THROW 51003,''FactMedicationOrder date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationOrder] f LEFT JOIN [dbo].FactEncounter e ON f.SourceEncounterID=e.SourceEncounterID AND f.OriginSystem=e.OriginSystem JOIN [dbo].DimPatient p ON f.PatientKey=p.PatientKey LEFT JOIN [dbo].DimPatient q ON e.PatientKey=q.PatientKey WHERE e.EncounterKey IS NULL OR p.SourcePatientID<>q.SourcePatientID OR f.IsDeleted<e.IsDeleted) THROW 51003,''FactMedicationOrder encounter lineage or parent deletion mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationAdministration] f JOIN [dbo].[DimPatient] d ON f.[PatientKey]=d.[PatientKey] WHERE COALESCE(f.[AdministeredAtUtc],f.[RecordedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[AdministeredAtUtc],f.[RecordedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactMedicationAdministration event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationAdministration] f JOIN [dbo].[DimDepartment] d ON f.[DepartmentKey]=d.[DepartmentKey] WHERE COALESCE(f.[AdministeredAtUtc],f.[RecordedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[AdministeredAtUtc],f.[RecordedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactMedicationAdministration event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationAdministration] f JOIN [dbo].[DimProvider] d ON f.[AdministeringProviderKey]=d.[ProviderKey] WHERE COALESCE(f.[AdministeredAtUtc],f.[RecordedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[AdministeredAtUtc],f.[RecordedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactMedicationAdministration event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationAdministration] WHERE ([AdministrationDateKey] IS NULL AND [AdministeredAtUtc] IS NOT NULL) OR ([AdministrationDateKey] IS NOT NULL AND [AdministeredAtUtc] IS NULL) OR [AdministrationDateKey]<>CONVERT(int,CONVERT(char(8),[AdministeredAtUtc],112))) THROW 51003,''FactMedicationAdministration date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationAdministration] WHERE ([RecordedDateKey] IS NULL AND [RecordedAtUtc] IS NOT NULL) OR ([RecordedDateKey] IS NOT NULL AND [RecordedAtUtc] IS NULL) OR [RecordedDateKey]<>CONVERT(int,CONVERT(char(8),[RecordedAtUtc],112))) THROW 51003,''FactMedicationAdministration date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactMedicationAdministration] f LEFT JOIN [dbo].FactEncounter e ON f.SourceEncounterID=e.SourceEncounterID AND f.OriginSystem=e.OriginSystem JOIN [dbo].DimPatient p ON f.PatientKey=p.PatientKey LEFT JOIN [dbo].DimPatient q ON e.PatientKey=q.PatientKey WHERE e.EncounterKey IS NULL OR p.SourcePatientID<>q.SourcePatientID OR f.IsDeleted<e.IsDeleted) THROW 51003,''FactMedicationAdministration encounter lineage or parent deletion mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactLabResult] f JOIN [dbo].[DimPatient] d ON f.[PatientKey]=d.[PatientKey] WHERE COALESCE(f.[ResultedAtUtc],f.[OrderedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[ResultedAtUtc],f.[OrderedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactLabResult event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactLabResult] f JOIN [dbo].[DimDepartment] d ON f.[DepartmentKey]=d.[DepartmentKey] WHERE COALESCE(f.[ResultedAtUtc],f.[OrderedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[ResultedAtUtc],f.[OrderedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactLabResult event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactLabResult] f JOIN [dbo].[DimProvider] d ON f.[OrderingProviderKey]=d.[ProviderKey] WHERE COALESCE(f.[ResultedAtUtc],f.[OrderedAtUtc])<d.EffectiveFromUtc OR COALESCE(f.[ResultedAtUtc],f.[OrderedAtUtc])>=d.EffectiveToUtc) THROW 51003,''FactLabResult event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactLabResult] WHERE ([OrderedDateKey] IS NULL AND [OrderedAtUtc] IS NOT NULL) OR ([OrderedDateKey] IS NOT NULL AND [OrderedAtUtc] IS NULL) OR [OrderedDateKey]<>CONVERT(int,CONVERT(char(8),[OrderedAtUtc],112))) THROW 51003,''FactLabResult date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactLabResult] WHERE ([ResultDateKey] IS NULL AND [ResultedAtUtc] IS NOT NULL) OR ([ResultDateKey] IS NOT NULL AND [ResultedAtUtc] IS NULL) OR [ResultDateKey]<>CONVERT(int,CONVERT(char(8),[ResultedAtUtc],112))) THROW 51003,''FactLabResult date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactLabResult] f LEFT JOIN [dbo].FactEncounter e ON f.SourceEncounterID=e.SourceEncounterID AND f.OriginSystem=e.OriginSystem JOIN [dbo].DimPatient p ON f.PatientKey=p.PatientKey LEFT JOIN [dbo].DimPatient q ON e.PatientKey=q.PatientKey WHERE e.EncounterKey IS NULL OR p.SourcePatientID<>q.SourcePatientID OR f.IsDeleted<e.IsDeleted) THROW 51003,''FactLabResult encounter lineage or parent deletion mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactAppointment] f JOIN [dbo].[DimPatient] d ON f.[PatientKey]=d.[PatientKey] WHERE f.[ScheduledStartAtUtc]<d.EffectiveFromUtc OR f.[ScheduledStartAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactAppointment event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactAppointment] f JOIN [dbo].[DimDepartment] d ON f.[DepartmentKey]=d.[DepartmentKey] WHERE f.[ScheduledStartAtUtc]<d.EffectiveFromUtc OR f.[ScheduledStartAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactAppointment event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactAppointment] f JOIN [dbo].[DimProvider] d ON f.[ProviderKey]=d.[ProviderKey] WHERE f.[ScheduledStartAtUtc]<d.EffectiveFromUtc OR f.[ScheduledStartAtUtc]>=d.EffectiveToUtc) THROW 51003,''FactAppointment event-time dimension mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].[FactAppointment] WHERE ([ScheduledDateKey] IS NULL AND [ScheduledStartAtUtc] IS NOT NULL) OR ([ScheduledDateKey] IS NOT NULL AND [ScheduledStartAtUtc] IS NULL) OR [ScheduledDateKey]<>CONVERT(int,CONVERT(char(8),[ScheduledStartAtUtc],112))) THROW 51003,''FactAppointment date key mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].FactEncounter e JOIN [dbo].DimCoverage c ON e.CoverageKey=c.CoverageKey JOIN [dbo].DimPatient p ON e.PatientKey=p.PatientKey WHERE c.SourcePatientID<>p.SourcePatientID OR CAST(e.ArrivalAtUtc AS date)<c.EffectiveDate OR CAST(e.ArrivalAtUtc AS date)>c.TerminationDate) THROW 51003,''FactEncounter enrollment mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].FactMedicationAdministration a LEFT JOIN [dbo].FactMedicationOrder o ON a.SourceMedicationOrderID=o.SourceMedicationOrderID AND a.OriginSystem=o.OriginSystem WHERE o.MedicationOrderKey IS NULL OR a.SourceEncounterID<>o.SourceEncounterID OR a.MedicationKey<>o.MedicationKey OR a.IsDeleted<o.IsDeleted) THROW 51003,''Administration corrected order mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].FactEncounter WHERE (DischargeAtUtc IS NULL AND LengthOfStayMinutes IS NOT NULL) OR (DischargeAtUtc IS NOT NULL AND LengthOfStayMinutes IS NULL) OR LengthOfStayMinutes<>ROUND(CAST((DATEDIFF_BIG(day,[ArrivalAtUtc],[DischargeAtUtc])*CAST(864000000000 AS bigint) + DATEDIFF_BIG(nanosecond,CAST([DischargeAtUtc] AS date),[DischargeAtUtc])/100 - DATEDIFF_BIG(nanosecond,CAST([ArrivalAtUtc] AS date),[ArrivalAtUtc])/100) AS decimal(28,0))/CAST(600000000 AS decimal(9,0)),2)) THROW 51003,''Encounter derived length of stay mismatch.'',1;
IF EXISTS(SELECT 1 FROM [dbo].FactAppointment WHERE ScheduledDurationMinutes<>ROUND(CAST((DATEDIFF_BIG(day,[ScheduledStartAtUtc],[ScheduledEndAtUtc])*CAST(864000000000 AS bigint) + DATEDIFF_BIG(nanosecond,CAST([ScheduledEndAtUtc] AS date),[ScheduledEndAtUtc])/100 - DATEDIFF_BIG(nanosecond,CAST([ScheduledStartAtUtc] AS date),[ScheduledStartAtUtc])/100) AS decimal(28,0))/CAST(600000000 AS decimal(9,0)),2)) THROW 51003,''Appointment derived duration mismatch.'',1;
END;');

EXEC [dbo].[ValidateSyntheticSource];

COMMIT TRANSACTION;
