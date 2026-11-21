-- No destructive DDL. Apply 0001 first; use a controlled corrective migration on failure.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0001_configuration')
    THROW 51001, 'Apply metadata configuration migration first', 1;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0002_control')
BEGIN
CREATE TABLE ops.ReleaseActivation (
    activation_id varchar(36) NOT NULL CONSTRAINT PK_ReleaseActivation PRIMARY KEY,
    environment varchar(128) NOT NULL,
    version varchar(40) NOT NULL REFERENCES cfg.FrameworkRelease(version),
    previous_version varchar(40) NULL REFERENCES cfg.FrameworkRelease(version),
    action varchar(16) NOT NULL CHECK (action IN ('activate','rollback')),
    reason nvarchar(1000) NOT NULL,
    activated_at datetime2(7) NOT NULL,
    CONSTRAINT UQ_ReleaseActivation_correlation UNIQUE (activation_id,environment,version)
);
CREATE TABLE ops.ActiveRelease (
    environment varchar(128) NOT NULL CONSTRAINT PK_ActiveRelease PRIMARY KEY,
    version varchar(40) NOT NULL,
    activation_id varchar(36) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT FK_ActiveRelease_activation FOREIGN KEY (activation_id,environment,version)
        REFERENCES ops.ReleaseActivation(activation_id,environment,version)
);
CREATE TABLE ops.TaskOperation (
    operation_id varchar(128) NOT NULL CONSTRAINT PK_TaskOperation PRIMARY KEY,
    task_id varchar(128) NOT NULL,
    dataset_id varchar(128) NOT NULL,
    environment varchar(128) NOT NULL,
    scope varchar(128) NOT NULL,
    release_version varchar(40) NOT NULL,
    snapshot_hash char(64) NOT NULL,
    -- Canonical UTC ISO text retains all seven source datetime2(7) fractional digits via DB-API.
    window_start varchar(27) NOT NULL,
    window_end varchar(27) NOT NULL,
    kind varchar(16) NOT NULL CHECK (kind IN ('daily','backfill','rerun')),
    source_mode varchar(16) NOT NULL CHECK (source_mode IN ('current','historical')),
    original_operation_id varchar(128) NULL REFERENCES ops.TaskOperation(operation_id),
    substitution_approval nvarchar(1000) NULL,
    request_hash char(64) NOT NULL,
    status varchar(32) NOT NULL CHECK (status IN
        ('QUEUED','BLOCKED_BY_DEPENDENCY','RUNNING','UNCERTAIN','SUCCEEDED','FAILED','CANCELED')),
    fence bigint NOT NULL CHECK (fence>=0),
    owner varchar(128) NULL,
    lease_until datetime2(7) NULL,
    attempt_id varchar(36) NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    last_error nvarchar(1000) NULL,
    CONSTRAINT CK_TaskOperation_window CHECK (window_start<window_end),
    CONSTRAINT FK_TaskOperation_task FOREIGN KEY (release_version,task_id,dataset_id,scope)
        REFERENCES cfg.ProcessingTask(release_version,task_id,primary_output,scope),
    CONSTRAINT UQ_TaskOperation_output_correlation
        UNIQUE (operation_id,dataset_id,environment,scope,window_start,window_end)
);
CREATE INDEX IX_TaskOperation_conflicts
    ON ops.TaskOperation(environment,scope,dataset_id,status,window_start,window_end);
CREATE TABLE ops.TaskAttempt (
    attempt_id varchar(36) NOT NULL CONSTRAINT PK_TaskAttempt PRIMARY KEY,
    operation_id varchar(128) NOT NULL REFERENCES ops.TaskOperation(operation_id),
    owner varchar(128) NOT NULL,
    fence bigint NOT NULL,
    started_at datetime2(7) NOT NULL,
    completed_at datetime2(7) NULL,
    status varchar(32) NOT NULL CHECK
        (status IN ('RUNNING','LEASE_EXPIRED','SUCCEEDED','FAILED','UNCERTAIN','CANCELED')),
    CONSTRAINT UQ_TaskAttempt_fence UNIQUE (operation_id,fence),
    CONSTRAINT UQ_TaskAttempt_correlation UNIQUE (operation_id,attempt_id)
);
ALTER TABLE ops.TaskOperation ADD CONSTRAINT FK_TaskOperation_attempt
    FOREIGN KEY (operation_id,attempt_id) REFERENCES ops.TaskAttempt(operation_id,attempt_id);
CREATE TABLE ops.DatasetOutput (
    output_id varchar(36) NOT NULL CONSTRAINT PK_DatasetOutput PRIMARY KEY,
    operation_id varchar(128) NOT NULL CONSTRAINT UQ_DatasetOutput_operation UNIQUE,
    dataset_id varchar(128) NOT NULL,
    environment varchar(128) NOT NULL,
    scope varchar(128) NOT NULL,
    delta_version varchar(128) NOT NULL,
    window_start varchar(27) NOT NULL,
    window_end varchar(27) NOT NULL,
    evidence_json nvarchar(max) NOT NULL CHECK (ISJSON(evidence_json)=1),
    evidence_hash char(64) NOT NULL,
    committed_at datetime2(7) NOT NULL,
    changed_rows bigint NOT NULL CHECK (changed_rows>=0),
    CONSTRAINT FK_DatasetOutput_operation FOREIGN KEY
        (operation_id,dataset_id,environment,scope,window_start,window_end)
        REFERENCES ops.TaskOperation(operation_id,dataset_id,environment,scope,window_start,window_end),
    CONSTRAINT UQ_DatasetOutput_correlation UNIQUE (output_id,dataset_id,environment,scope),
    CONSTRAINT UQ_DatasetOutput_input_version
        UNIQUE (output_id,dataset_id,environment,scope,delta_version)
);
CREATE INDEX IX_DatasetOutput_history ON ops.DatasetOutput(environment,dataset_id,scope,window_end);
CREATE TABLE ops.SourceSnapshot (
    source_snapshot_id varchar(36) NOT NULL CONSTRAINT PK_SourceSnapshot PRIMARY KEY,
    dataset_id varchar(128) NOT NULL REFERENCES cfg.DatasetIdentity(dataset_id),
    environment varchar(128) NOT NULL,
    scope varchar(128) NOT NULL,
    version varchar(128) NOT NULL,
    window_start varchar(27) NOT NULL,
    window_end varchar(27) NOT NULL,
    evidence_digest varchar(128) NOT NULL,
    artifact_ref nvarchar(1000) NOT NULL,
    created_at datetime2(7) NOT NULL,
    retired_at datetime2(7) NULL,
    CONSTRAINT CK_SourceSnapshot_window CHECK (window_start<window_end),
    CONSTRAINT UQ_SourceSnapshot_version
        UNIQUE (dataset_id,environment,scope,version,window_start,window_end)
);
CREATE TABLE ops.OperationInput (
    operation_id varchar(128) NOT NULL REFERENCES ops.TaskOperation(operation_id),
    dataset_id varchar(128) NOT NULL REFERENCES cfg.DatasetIdentity(dataset_id),
    version varchar(128) NOT NULL,
    window_start varchar(27) NOT NULL,
    window_end varchar(27) NOT NULL,
    output_id varchar(36) NULL REFERENCES ops.DatasetOutput(output_id),
    source_snapshot_id varchar(36) NULL REFERENCES ops.SourceSnapshot(source_snapshot_id),
    CONSTRAINT PK_OperationInput PRIMARY KEY (operation_id,dataset_id),
    CONSTRAINT CK_OperationInput_window CHECK (window_start<window_end),
    CONSTRAINT CK_OperationInput_binding CHECK (output_id IS NULL OR source_snapshot_id IS NULL)
);
CREATE TABLE ops.DatasetReadiness (
    dataset_id varchar(128) NOT NULL REFERENCES cfg.DatasetIdentity(dataset_id),
    environment varchar(128) NOT NULL,
    scope varchar(128) NOT NULL,
    output_id varchar(36) NULL,
    progress_end varchar(27) NULL,
    expected_operation_id varchar(128) NULL REFERENCES ops.TaskOperation(operation_id),
    expected_end varchar(27) NULL,
    expected_status varchar(32) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT PK_DatasetReadiness PRIMARY KEY (dataset_id,environment,scope),
    CONSTRAINT FK_DatasetReadiness_output FOREIGN KEY (output_id,dataset_id,environment,scope)
        REFERENCES ops.DatasetOutput(output_id,dataset_id,environment,scope)
);
CREATE TABLE ops.DatasetBlock (
    block_id varchar(512) NOT NULL CONSTRAINT PK_DatasetBlock PRIMARY KEY,
    incident_id varchar(128) NOT NULL,
    dataset_id varchar(128) NOT NULL REFERENCES cfg.DatasetIdentity(dataset_id),
    environment varchar(128) NOT NULL,
    scope varchar(128) NOT NULL,
    release_version varchar(40) NOT NULL REFERENCES cfg.FrameworkRelease(version),
    created_at datetime2(7) NOT NULL,
    cleared_at datetime2(7) NULL,
    operator_approval nvarchar(1000) NULL,
    validation_digest varchar(128) NULL,
    CONSTRAINT CK_DatasetBlock_clear CHECK
        (cleared_at IS NULL OR (operator_approval IS NOT NULL AND validation_digest IS NOT NULL))
);
CREATE INDEX IX_DatasetBlock_active ON ops.DatasetBlock(environment,scope,dataset_id,cleared_at);
CREATE TABLE ops.ReadinessOutbox (
    event_id varchar(128) NOT NULL CONSTRAINT PK_ReadinessOutbox PRIMARY KEY,
    dataset_id varchar(128) NOT NULL,
    environment varchar(128) NOT NULL,
    scope varchar(128) NOT NULL,
    output_id varchar(36) NOT NULL,
    event_sequence bigint NOT NULL,
    progress_end varchar(27) NOT NULL,
    created_at datetime2(7) NOT NULL,
    delivered_at datetime2(7) NULL,
    dispatch_attempts int NOT NULL CHECK (dispatch_attempts>=0),
    next_retry_at datetime2(7) NULL,
    last_error nvarchar(1000) NULL,
    CONSTRAINT FK_ReadinessOutbox_output FOREIGN KEY (output_id,dataset_id,environment,scope)
        REFERENCES ops.DatasetOutput(output_id,dataset_id,environment,scope),
    CONSTRAINT UQ_ReadinessOutbox_sequence UNIQUE (dataset_id,environment,scope,event_sequence)
);
CREATE INDEX IX_ReadinessOutbox_pending ON ops.ReadinessOutbox(delivered_at,created_at);
CREATE TABLE ops.EventReceipt (
    event_id varchar(128) NOT NULL REFERENCES ops.ReadinessOutbox(event_id),
    consumer_id varchar(128) NOT NULL,
    accepted bit NOT NULL,
    received_at datetime2(7) NOT NULL,
    CONSTRAINT PK_EventReceipt PRIMARY KEY (event_id,consumer_id)
);
CREATE TABLE ops.ReconciliationRun (
    reconciliation_id varchar(36) NOT NULL CONSTRAINT PK_ReconciliationRun PRIMARY KEY,
    environment varchar(128) NOT NULL,
    owner varchar(128) NOT NULL,
    release_version varchar(40) NOT NULL REFERENCES cfg.FrameworkRelease(version),
    snapshot_hash char(64) NOT NULL,
    snapshot_json nvarchar(max) NOT NULL CHECK (ISJSON(snapshot_json)=1),
    started_at datetime2(7) NOT NULL,
    lease_until datetime2(7) NOT NULL,
    completed_at datetime2(7) NULL,
    status varchar(32) NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED','LEASE_EXPIRED')),
    retry_count int NOT NULL CHECK (retry_count>=0),
    max_retries int NOT NULL CHECK (max_retries>=0),
    next_retry_at datetime2(7) NULL,
    last_error nvarchar(1000) NULL
);
CREATE UNIQUE INDEX UX_ReconciliationRun_owner
    ON ops.ReconciliationRun(environment) WHERE status='RUNNING';
CREATE TABLE ops.ReferenceHold (
    hold_id char(64) NOT NULL CONSTRAINT PK_ReferenceHold PRIMARY KEY,
    kind varchar(16) NOT NULL CHECK (kind IN ('delta','output','release','operation','artifact')),
    reference_id varchar(256) NOT NULL,
    holder varchar(128) NOT NULL,
    created_at datetime2(7) NOT NULL,
    released_at datetime2(7) NULL
);
CREATE INDEX IX_ReferenceHold_active ON ops.ReferenceHold(reference_id,released_at);
CREATE TABLE ops.ControlAudit (
    audit_id varchar(36) NOT NULL CONSTRAINT PK_ControlAudit PRIMARY KEY,
    kind varchar(64) NOT NULL,
    reference_id varchar(256) NOT NULL,
    detail_json nvarchar(max) NOT NULL CHECK (ISJSON(detail_json)=1),
    created_at datetime2(7) NOT NULL
);
CREATE INDEX IX_ControlAudit_retention ON ops.ControlAudit(created_at,reference_id);
INSERT cfg.MetadataMigration(migration_id,description)
VALUES ('0002_control','Fenced operations, immutable bindings, output history, readiness and reliable outbox');
END;
COMMIT;
