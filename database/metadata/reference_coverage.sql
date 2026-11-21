-- SQLite initializer adds nullable TEXT coverage columns non-destructively before these guards.
CREATE TRIGGER IF NOT EXISTS coverage_output_insert BEFORE INSERT ON ops_DatasetOutput
WHEN (NEW.source_coverage_start IS NULL)<>(NEW.source_coverage_end IS NULL)
 OR NEW.source_coverage_start>=NEW.source_coverage_end
BEGIN SELECT RAISE(ABORT,'Invalid source coverage bounds'); END;
CREATE TRIGGER IF NOT EXISTS coverage_output_update BEFORE UPDATE ON ops_DatasetOutput
WHEN (NEW.source_coverage_start IS NULL)<>(NEW.source_coverage_end IS NULL)
 OR NEW.source_coverage_start>=NEW.source_coverage_end
BEGIN SELECT RAISE(ABORT,'Invalid source coverage bounds'); END;
CREATE TRIGGER IF NOT EXISTS coverage_input_insert BEFORE INSERT ON ops_OperationInput
WHEN (NEW.source_coverage_start IS NULL)<>(NEW.source_coverage_end IS NULL)
 OR NEW.source_coverage_start>=NEW.source_coverage_end
 OR (NEW.output_id IS NOT NULL AND NEW.source_coverage_start IS NOT NULL AND NOT EXISTS
   (SELECT 1 FROM ops_DatasetOutput WHERE output_id=NEW.output_id
    AND source_coverage_start=NEW.source_coverage_start AND source_coverage_end=NEW.source_coverage_end))
 OR (NEW.source_snapshot_id IS NOT NULL AND NEW.source_coverage_start IS NOT NULL AND NOT EXISTS
   (SELECT 1 FROM ops_SourceSnapshot WHERE source_snapshot_id=NEW.source_snapshot_id
    AND window_start=NEW.source_coverage_start AND window_end=NEW.source_coverage_end))
BEGIN SELECT RAISE(ABORT,'Input source coverage disagrees with authoritative evidence'); END;
CREATE TRIGGER IF NOT EXISTS coverage_input_update BEFORE UPDATE ON ops_OperationInput
WHEN (NEW.source_coverage_start IS NULL)<>(NEW.source_coverage_end IS NULL)
 OR NEW.source_coverage_start>=NEW.source_coverage_end
 OR (NEW.output_id IS NOT NULL AND NEW.source_coverage_start IS NOT NULL AND NOT EXISTS
   (SELECT 1 FROM ops_DatasetOutput WHERE output_id=NEW.output_id
    AND source_coverage_start=NEW.source_coverage_start AND source_coverage_end=NEW.source_coverage_end))
 OR (NEW.source_snapshot_id IS NOT NULL AND NEW.source_coverage_start IS NOT NULL AND NOT EXISTS
   (SELECT 1 FROM ops_SourceSnapshot WHERE source_snapshot_id=NEW.source_snapshot_id
    AND window_start=NEW.source_coverage_start AND window_end=NEW.source_coverage_end))
BEGIN SELECT RAISE(ABORT,'Input source coverage disagrees with authoritative evidence'); END;
CREATE TRIGGER IF NOT EXISTS coverage_readiness_insert BEFORE INSERT ON ops_DatasetReadiness
WHEN (NEW.source_coverage_start IS NULL)<>(NEW.source_coverage_end IS NULL)
 OR NEW.source_coverage_start>=NEW.source_coverage_end
 OR (NEW.output_id IS NOT NULL AND NEW.source_coverage_start IS NOT NULL AND NOT EXISTS
   (SELECT 1 FROM ops_DatasetOutput WHERE output_id=NEW.output_id
    AND source_coverage_start=NEW.source_coverage_start AND source_coverage_end=NEW.source_coverage_end))
BEGIN SELECT RAISE(ABORT,'Readiness source coverage disagrees with output'); END;
CREATE TRIGGER IF NOT EXISTS coverage_readiness_update BEFORE UPDATE ON ops_DatasetReadiness
WHEN (NEW.source_coverage_start IS NULL)<>(NEW.source_coverage_end IS NULL)
 OR NEW.source_coverage_start>=NEW.source_coverage_end
 OR (NEW.output_id IS NOT NULL AND NEW.source_coverage_start IS NOT NULL AND NOT EXISTS
   (SELECT 1 FROM ops_DatasetOutput WHERE output_id=NEW.output_id
    AND source_coverage_start=NEW.source_coverage_start AND source_coverage_end=NEW.source_coverage_end))
BEGIN SELECT RAISE(ABORT,'Readiness source coverage disagrees with output'); END;
