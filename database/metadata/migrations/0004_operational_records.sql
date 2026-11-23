-- Additive task-grain operational evidence; all original diagnostic/profiling tables remain intact.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0003_legacy_preservation')
    THROW 51001, 'Apply metadata baseline-preservation migration first', 1;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0004_operational_records')
BEGIN
ALTER TABLE ops.TaskOperation ADD CONSTRAINT UQ_TaskOperation_release
    UNIQUE (operation_id,release_version);
CREATE TABLE ops.TaskDiagnosticAttempt (
    record_id varchar(128) NOT NULL CONSTRAINT PK_TaskDiagnosticAttempt PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_TaskDiagnosticAttempt_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    scope_key varchar(512) NOT NULL,
    collection_attempt int NOT NULL,
    max_attempts int NOT NULL CHECK (max_attempts BETWEEN 1 AND 6),
    availability varchar(32) NOT NULL,
    reason nvarchar(2048) NULL,
    spark_json nvarchar(max) NOT NULL CHECK (ISJSON(spark_json)=1),
    started_at datetime2(7) NULL,
    completed_at datetime2(7) NULL,
    CONSTRAINT CK_TaskDiagnosticAttempt_budget CHECK (collection_attempt BETWEEN 0 AND max_attempts),
    CONSTRAINT FK_TaskDiagnosticAttempt_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_TaskDiagnosticAttempt_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version),
    CONSTRAINT UQ_TaskDiagnosticAttempt_context
        UNIQUE (record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE ops.TaskDiagnosticLog (
    record_id varchar(128) NOT NULL CONSTRAINT PK_TaskDiagnosticLog PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_TaskDiagnosticLog_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    collection_id varchar(128) NOT NULL,
    kind varchar(32) NOT NULL,
    filename nvarchar(512) NOT NULL,
    source_identity nvarchar(2048) NOT NULL,
    artifact nvarchar(2048) NULL,
    bytes bigint NULL CHECK (bytes>=0),
    sha256 char(64) NULL,
    complete bit NOT NULL,
    availability varchar(32) NOT NULL,
    reason nvarchar(2048) NULL,
    source_modified_at datetime2(7) NULL,
    collected_at datetime2(7) NULL,
    retrieval_context_json nvarchar(max) NOT NULL CHECK (ISJSON(retrieval_context_json)=1),
    CONSTRAINT FK_TaskDiagnosticLog_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_TaskDiagnosticLog_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version),
    CONSTRAINT FK_TaskDiagnosticLog_collection FOREIGN KEY
        (collection_id,operation_id,attempt_id,release_version)
        REFERENCES ops.TaskDiagnosticAttempt(record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE ops.TaskSparkMetric (
    record_id varchar(128) NOT NULL CONSTRAINT PK_TaskSparkMetric PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_TaskSparkMetric_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    activity_run_id varchar(512) NOT NULL,
    workspace_id varchar(512) NOT NULL,
    item_id varchar(512) NOT NULL,
    item_type varchar(32) NOT NULL,
    livy_id varchar(512) NOT NULL,
    application_id varchar(512) NOT NULL,
    application_attempt_id varchar(512) NOT NULL,
    collected_at datetime2(7) NULL,
    execution_evidence_json nvarchar(max) NOT NULL CHECK (ISJSON(execution_evidence_json)=1),
    source_mapping_json nvarchar(max) NOT NULL CHECK (ISJSON(source_mapping_json)=1),
    -- Exact 50 nullable fields retained from docs/ingestion/spark-metric-columns.md.
    ShuffleWriteRecords bigint NULL,
    AllocatedExecutorsMin int NULL,
    AllocatedExecutorsMax int NULL,
    IsAnomalous bit NULL,
    ExpectedDuration decimal(20,6) NULL,
    PotentialCausesJson nvarchar(max) NULL CHECK (PotentialCausesJson IS NULL OR ISJSON(PotentialCausesJson)=1),
    TotalDuration decimal(20,6) NULL,
    JobCount bigint NULL,
    QueryCount bigint NULL,
    TaskCount bigint NULL,
    ReadRows bigint NULL,
    WriteRows bigint NULL,
    JoinCount bigint NULL,
    ScanCount bigint NULL,
    FilterCount bigint NULL,
    UnionCount bigint NULL,
    CollectCount bigint NULL,
    HashAggregateCount bigint NULL,
    ExchangeCount bigint NULL,
    ShuffleReadLocalBytes bigint NULL,
    ShuffleReadRemoteBytes bigint NULL,
    ShuffleWriteBytes bigint NULL,
    ReadBytes bigint NULL,
    WriteBytes bigint NULL,
    MemorySpilledBytes bigint NULL,
    DiskSpilledBytes bigint NULL,
    GCTime decimal(20,6) NULL,
    StageCount bigint NULL,
    ShuffleMapStageCount bigint NULL,
    ResultStageCount bigint NULL,
    CompilationTime decimal(20,6) NULL,
    ExecutionTime decimal(20,6) NULL,
    IdleTime decimal(20,6) NULL,
    CoreAllocation decimal(18,4) NULL,
    UtilizationPercentage decimal(9,4) NULL,
    TaskDuration decimal(20,6) NULL,
    ShuffleTime decimal(20,6) NULL,
    IOTime decimal(20,6) NULL,
    CPUTime decimal(20,6) NULL,
    ShuffleReadTime decimal(20,6) NULL,
    ShuffleWriteTime decimal(20,6) NULL,
    ReadTime decimal(20,6) NULL,
    WriteTime decimal(20,6) NULL,
    SerializationTime decimal(20,6) NULL,
    DeserializeTime decimal(20,6) NULL,
    ExecutorComputingTime decimal(20,6) NULL,
    ApplicationRunTime decimal(20,6) NULL,
    OverheadTime decimal(20,6) NULL,
    QueueingTime decimal(20,6) NULL,
    StartingTime decimal(20,6) NULL,
    CONSTRAINT FK_TaskSparkMetric_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_TaskSparkMetric_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version)
);
CREATE TABLE ops.TransformationBenchmarkTrial (
    record_id varchar(128) NOT NULL CONSTRAINT PK_TransformationBenchmarkTrial PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_TransformationBenchmarkTrial_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    run_id varchar(512) NOT NULL,
    trial int NOT NULL CHECK (trial BETWEEN 0 AND 3),
    warmup bit NOT NULL,
    input_versions_json nvarchar(max) NOT NULL CHECK (ISJSON(input_versions_json)=1),
    snapshot_context_json nvarchar(max) NOT NULL CHECK (ISJSON(snapshot_context_json)=1),
    compute_context_json nvarchar(max) NOT NULL CHECK (ISJSON(compute_context_json)=1),
    artifact nvarchar(2048) NULL,
    started_at datetime2(7) NULL,
    completed_at datetime2(7) NULL,
    CONSTRAINT CK_TransformationBenchmarkTrial_warmup
        CHECK ((trial=0 AND warmup=1) OR (trial>0 AND warmup=0)),
    CONSTRAINT FK_TransformationBenchmarkTrial_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_TransformationBenchmarkTrial_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version),
    CONSTRAINT UQ_TransformationBenchmarkTrial_context
        UNIQUE (record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE ops.TransformationBenchmarkStep (
    record_id varchar(128) NOT NULL CONSTRAINT PK_TransformationBenchmarkStep PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_TransformationBenchmarkStep_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    run_id varchar(512) NOT NULL,
    trial int NOT NULL CHECK (trial BETWEEN 0 AND 3),
    warmup bit NOT NULL,
    input_versions_json nvarchar(max) NOT NULL CHECK (ISJSON(input_versions_json)=1),
    snapshot_context_json nvarchar(max) NOT NULL CHECK (ISJSON(snapshot_context_json)=1),
    compute_context_json nvarchar(max) NOT NULL CHECK (ISJSON(compute_context_json)=1),
    artifact nvarchar(2048) NULL,
    started_at datetime2(7) NULL,
    completed_at datetime2(7) NULL,
    ordinal int NOT NULL CHECK (ordinal BETWEEN 0 AND 127),
    [function] varchar(128) NOT NULL,
    occurrence_id varchar(128) NOT NULL,
    parameters_json nvarchar(max) NOT NULL CHECK (ISJSON(parameters_json)=1),
    attempt_number int NOT NULL CHECK (attempt_number BETWEEN 1 AND 6),
    plan_seconds decimal(20,6) NULL CHECK (plan_seconds BETWEEN 0 AND 1800),
    materialization_seconds decimal(20,6) NULL CHECK (materialization_seconds BETWEEN 0 AND 1800),
    reread_seconds decimal(20,6) NULL CHECK (reread_seconds BETWEEN 0 AND 1800),
    total_seconds decimal(20,6) NULL CHECK (total_seconds BETWEEN 0 AND 1800),
    [rows] bigint NULL CHECK ([rows]>=0),
    exception_type varchar(512) NULL,
    execution_metrics_json nvarchar(max) NOT NULL CHECK (ISJSON(execution_metrics_json)=1),
    collection_status varchar(32) NOT NULL,
    trial_record_id varchar(128) NOT NULL,
    CONSTRAINT FK_TransformationBenchmarkStep_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_TransformationBenchmarkStep_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version),
    CONSTRAINT FK_TransformationBenchmarkStep_trial FOREIGN KEY
        (trial_record_id,operation_id,attempt_id,release_version)
        REFERENCES ops.TransformationBenchmarkTrial(record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE ops.TaskQualityOutcome (
    record_id varchar(128) NOT NULL CONSTRAINT PK_TaskQualityOutcome PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_TaskQualityOutcome_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL CHECK (status IN ('PASS','FAIL','UNAVAILABLE')),
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    [check] varchar(512) NOT NULL,
    evidence_digest varchar(512) NOT NULL,
    severity varchar(16) NOT NULL CHECK (severity IN ('critical','warning')),
    reason nvarchar(2048) NULL,
    expected_value decimal(38,6) NULL,
    actual_value decimal(38,6) NULL,
    artifact nvarchar(2048) NULL,
    details_json nvarchar(max) NOT NULL CHECK (ISJSON(details_json)=1),
    CONSTRAINT FK_TaskQualityOutcome_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_TaskQualityOutcome_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version),
    CONSTRAINT UQ_TaskQualityOutcome_context UNIQUE (record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE ops.TaskQuarantineManifest (
    record_id varchar(128) NOT NULL CONSTRAINT PK_TaskQuarantineManifest PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_TaskQuarantineManifest_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    quality_record_id varchar(128) NOT NULL,
    artifact nvarchar(2048) NOT NULL,
    reason_code varchar(512) NOT NULL,
    row_count bigint NOT NULL CHECK (row_count>=0),
    schema_digest varchar(512) NOT NULL,
    identifiers_manifest_ref nvarchar(2048) NULL,
    input_versions_json nvarchar(max) NOT NULL CHECK (ISJSON(input_versions_json)=1),
    CONSTRAINT FK_TaskQuarantineManifest_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_TaskQuarantineManifest_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version),
    CONSTRAINT FK_TaskQuarantineManifest_quality FOREIGN KEY
        (quality_record_id,operation_id,attempt_id,release_version)
        REFERENCES ops.TaskQualityOutcome(record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE ops.ArtifactCleanupOutcome (
    record_id varchar(128) NOT NULL CONSTRAINT PK_ArtifactCleanupOutcome PRIMARY KEY,
    natural_key char(64) NOT NULL CONSTRAINT UQ_ArtifactCleanupOutcome_key UNIQUE,
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    artifact_id varchar(512) NOT NULL,
    artifact nvarchar(2048) NULL,
    artifact_kind varchar(512) NULL,
    attempt_number int NOT NULL CHECK (attempt_number BETWEEN 1 AND 6),
    reason nvarchar(2048) NULL,
    proof_digest varchar(512) NULL,
    started_at datetime2(7) NULL,
    completed_at datetime2(7) NULL,
    CONSTRAINT FK_ArtifactCleanupOutcome_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_ArtifactCleanupOutcome_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version)
);
CREATE TABLE ops.OperationalRecordRevision (
    record_type varchar(32) NOT NULL,
    record_id varchar(128) NOT NULL,
    revision int NOT NULL CHECK (revision BETWEEN 1 AND 1000000),
    operation_id varchar(128) NOT NULL,
    attempt_id varchar(36) NOT NULL,
    release_version varchar(40) NOT NULL,
    status varchar(32) NOT NULL,
    payload_json nvarchar(max) NOT NULL CHECK (ISJSON(payload_json)=1 AND DATALENGTH(payload_json)<=131072),
    payload_hash char(64) NOT NULL,
    created_at datetime2(7) NOT NULL,
    CONSTRAINT PK_OperationalRecordRevision PRIMARY KEY (record_type,record_id,revision),
    CONSTRAINT FK_OperationalRecordRevision_attempt FOREIGN KEY (operation_id,attempt_id)
        REFERENCES ops.TaskAttempt(operation_id,attempt_id),
    CONSTRAINT FK_OperationalRecordRevision_release FOREIGN KEY (operation_id,release_version)
        REFERENCES ops.TaskOperation(operation_id,release_version)
);
CREATE INDEX IX_TaskDiagnosticAttempt_operation ON ops.TaskDiagnosticAttempt(operation_id,attempt_id,record_id);
CREATE INDEX IX_TaskDiagnosticLog_operation ON ops.TaskDiagnosticLog(operation_id,attempt_id,record_id);
CREATE INDEX IX_TaskSparkMetric_operation ON ops.TaskSparkMetric(operation_id,attempt_id,record_id);
CREATE INDEX IX_TransformationBenchmarkTrial_operation ON ops.TransformationBenchmarkTrial(operation_id,attempt_id,record_id);
CREATE INDEX IX_TransformationBenchmarkStep_operation ON ops.TransformationBenchmarkStep(operation_id,attempt_id,record_id);
CREATE INDEX IX_TaskQualityOutcome_operation ON ops.TaskQualityOutcome(operation_id,attempt_id,record_id);
CREATE INDEX IX_TaskQuarantineManifest_operation ON ops.TaskQuarantineManifest(operation_id,attempt_id,record_id);
CREATE INDEX IX_ArtifactCleanupOutcome_operation ON ops.ArtifactCleanupOutcome(operation_id,attempt_id,record_id);
INSERT cfg.MetadataMigration(migration_id,description)
VALUES ('0004_operational_records','Task-grain diagnostics, 50 nullable Spark metrics, benchmarks, quality, quarantine and cleanup audit');
END;
COMMIT;
