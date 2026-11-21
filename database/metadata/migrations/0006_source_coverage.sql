-- Source coverage is independent of processing windows. Unknown legacy coverage stays NULL.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0005_waiting_operations')
    THROW 51001, 'Apply waiting operations migration first', 1;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0006_source_coverage')
BEGIN
ALTER TABLE ops.DatasetOutput ADD
    source_coverage_start varchar(27) NULL,
    source_coverage_end varchar(27) NULL;
ALTER TABLE ops.OperationInput ADD
    source_coverage_start varchar(27) NULL,
    source_coverage_end varchar(27) NULL;
ALTER TABLE ops.DatasetReadiness ADD
    source_coverage_start varchar(27) NULL,
    source_coverage_end varchar(27) NULL;
ALTER TABLE ops.DatasetOutput ADD CONSTRAINT CK_DatasetOutput_source_coverage CHECK
    ((source_coverage_start IS NULL AND source_coverage_end IS NULL)
     OR (source_coverage_start IS NOT NULL AND source_coverage_end IS NOT NULL
         AND source_coverage_start<source_coverage_end));
ALTER TABLE ops.OperationInput ADD CONSTRAINT CK_OperationInput_source_coverage CHECK
    ((source_coverage_start IS NULL AND source_coverage_end IS NULL)
     OR (source_coverage_start IS NOT NULL AND source_coverage_end IS NOT NULL
         AND source_coverage_start<source_coverage_end));
ALTER TABLE ops.DatasetReadiness ADD CONSTRAINT CK_DatasetReadiness_source_coverage CHECK
    ((source_coverage_start IS NULL AND source_coverage_end IS NULL)
     OR (source_coverage_start IS NOT NULL AND source_coverage_end IS NOT NULL
         AND source_coverage_start<source_coverage_end));
ALTER TABLE ops.DatasetOutput ADD CONSTRAINT UQ_DatasetOutput_source_coverage
    UNIQUE(output_id,source_coverage_start,source_coverage_end);
ALTER TABLE ops.SourceSnapshot ADD CONSTRAINT UQ_SourceSnapshot_source_coverage
    UNIQUE(source_snapshot_id,window_start,window_end);
ALTER TABLE ops.OperationInput ADD CONSTRAINT FK_OperationInput_output_source_coverage
    FOREIGN KEY(output_id,source_coverage_start,source_coverage_end)
    REFERENCES ops.DatasetOutput(output_id,source_coverage_start,source_coverage_end);
ALTER TABLE ops.OperationInput ADD CONSTRAINT FK_OperationInput_snapshot_source_coverage
    FOREIGN KEY(source_snapshot_id,source_coverage_start,source_coverage_end)
    REFERENCES ops.SourceSnapshot(source_snapshot_id,window_start,window_end);
ALTER TABLE ops.DatasetReadiness ADD CONSTRAINT FK_DatasetReadiness_source_coverage
    FOREIGN KEY(output_id,source_coverage_start,source_coverage_end)
    REFERENCES ops.DatasetOutput(output_id,source_coverage_start,source_coverage_end);
INSERT cfg.MetadataMigration(migration_id,description)
VALUES('0006_source_coverage','Verified source coverage separate from processing progress and freshness');
END;
COMMIT;
