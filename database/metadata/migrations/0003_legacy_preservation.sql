-- Preservation is intentional: cfg.TransformationStep and all baseline ops FKs stay intact.
-- No baseline run/step data is rewritten. Import mappings only after reviewed attribution.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0002_control')
    THROW 51001, 'Apply metadata control migration first', 1;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0003_legacy_preservation')
BEGIN
IF OBJECT_ID(N'cfg.TransformationStep', N'U') IS NOT NULL
    EXEC(N'CREATE OR ALTER VIEW cfg.LegacyTransformationStepArchive AS
        SELECT * FROM cfg.TransformationStep');
-- The view keeps historical identity/ordinal/parameters queryable without a destructive archive.
-- Old IngestionTransformationRun.TransformationStepID attribution remains authoritative.
INSERT cfg.MetadataMigration(migration_id,description)
VALUES ('0003_legacy_preservation','Keep baseline steps/profiling and optional read-only archive view');
END;
COMMIT;
