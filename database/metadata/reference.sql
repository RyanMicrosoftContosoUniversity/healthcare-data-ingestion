-- SQLite LOCAL protocol reference only. Authoritative physical schema is migrations/*.sql.
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS cfg_FrameworkRelease (
 version TEXT PRIMARY KEY, framework_version TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
 snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
 review_json TEXT NOT NULL CHECK(json_valid(review_json)),
 queue_sequence INTEGER NOT NULL UNIQUE, status TEXT NOT NULL,
 checks_json TEXT NOT NULL CHECK(json_valid(checks_json)), created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, failure_code TEXT, CHECK(version=framework_version)
);
CREATE TABLE IF NOT EXISTS cfg_DatasetIdentity (
 dataset_id TEXT PRIMARY KEY, layer TEXT NOT NULL, external INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cfg_Dataset (
 release_version TEXT NOT NULL REFERENCES cfg_FrameworkRelease(version),
 dataset_id TEXT NOT NULL REFERENCES cfg_DatasetIdentity(dataset_id), name TEXT NOT NULL,
 retired INTEGER NOT NULL, freshness_seconds INTEGER NOT NULL CHECK(freshness_seconds>=0),
 PRIMARY KEY(release_version,dataset_id)
);
CREATE TABLE IF NOT EXISTS cfg_DatasetPhysicalMap (
 release_version TEXT NOT NULL, dataset_id TEXT NOT NULL, environment TEXT NOT NULL,
 physical_json TEXT NOT NULL CHECK(json_valid(physical_json)),
 PRIMARY KEY(release_version,dataset_id,environment),
 FOREIGN KEY(release_version,dataset_id) REFERENCES cfg_Dataset(release_version,dataset_id)
);
CREATE TABLE IF NOT EXISTS cfg_PipelineObjectMapping (
 release_version TEXT NOT NULL REFERENCES cfg_FrameworkRelease(version),
 pipeline_object_id TEXT NOT NULL, mapping_json TEXT NOT NULL CHECK(json_valid(mapping_json)),
 legacy_pipeline_object_id INTEGER, PRIMARY KEY(release_version,pipeline_object_id)
);
CREATE TABLE IF NOT EXISTS cfg_PipelineDefinitionRelease (
 release_version TEXT NOT NULL REFERENCES cfg_FrameworkRelease(version), stage TEXT NOT NULL,
 framework_defaults_json TEXT NOT NULL CHECK(json_valid(framework_defaults_json)),
 stage_defaults_json TEXT NOT NULL CHECK(json_valid(stage_defaults_json)),
 PRIMARY KEY(release_version,stage)
);
CREATE TABLE IF NOT EXISTS cfg_ProcessingTask (
 release_version TEXT NOT NULL, task_id TEXT NOT NULL, workflow TEXT NOT NULL,
 primary_output TEXT NOT NULL, pipeline_object_id TEXT, scope TEXT NOT NULL,
 retired INTEGER NOT NULL, functions_json TEXT NOT NULL CHECK(json_valid(functions_json)),
 overrides_json TEXT NOT NULL CHECK(json_valid(overrides_json)),
 PRIMARY KEY(release_version,task_id), UNIQUE(release_version,task_id,primary_output,scope),
 FOREIGN KEY(release_version,primary_output) REFERENCES cfg_Dataset(release_version,dataset_id),
 FOREIGN KEY(release_version,pipeline_object_id)
 REFERENCES cfg_PipelineObjectMapping(release_version,pipeline_object_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS UX_ProcessingTask_producer
 ON cfg_ProcessingTask(release_version,primary_output,scope) WHERE retired=0;
CREATE TABLE IF NOT EXISTS cfg_TaskInput (
 release_version TEXT NOT NULL, task_id TEXT NOT NULL, dataset_id TEXT NOT NULL,
 alias TEXT NOT NULL, required INTEGER NOT NULL, freshness_seconds INTEGER,
 allow_stale INTEGER NOT NULL, PRIMARY KEY(release_version,task_id,alias),
 FOREIGN KEY(release_version,task_id) REFERENCES cfg_ProcessingTask(release_version,task_id),
 FOREIGN KEY(release_version,dataset_id) REFERENCES cfg_Dataset(release_version,dataset_id)
);
CREATE TABLE IF NOT EXISTS cfg_TaskDependency (
 release_version TEXT NOT NULL, task_id TEXT NOT NULL, predecessor_task_id TEXT NOT NULL,
 reason TEXT NOT NULL, PRIMARY KEY(release_version,task_id,predecessor_task_id),
 CHECK(task_id<>predecessor_task_id),
 FOREIGN KEY(release_version,task_id) REFERENCES cfg_ProcessingTask(release_version,task_id),
 FOREIGN KEY(release_version,predecessor_task_id) REFERENCES cfg_ProcessingTask(release_version,task_id)
);
CREATE TABLE IF NOT EXISTS cfg_LegacyStepAttribution (
 release_version TEXT NOT NULL, task_id TEXT NOT NULL, occurrence_id TEXT NOT NULL,
 legacy_transformation_step_id INTEGER NOT NULL, legacy_pipeline_object_id INTEGER,
 import_evidence TEXT NOT NULL, PRIMARY KEY(release_version,task_id,occurrence_id),
 FOREIGN KEY(release_version,task_id) REFERENCES cfg_ProcessingTask(release_version,task_id)
);
CREATE TABLE IF NOT EXISTS ops_ReleaseActivation (
 activation_id TEXT PRIMARY KEY, environment TEXT NOT NULL,
 version TEXT NOT NULL REFERENCES cfg_FrameworkRelease(version),
 previous_version TEXT REFERENCES cfg_FrameworkRelease(version),
 action TEXT NOT NULL, reason TEXT NOT NULL, activated_at TEXT NOT NULL,
 UNIQUE(activation_id,environment,version)
);
CREATE TABLE IF NOT EXISTS ops_ActiveRelease (
 environment TEXT PRIMARY KEY, version TEXT NOT NULL, activation_id TEXT NOT NULL,
 updated_at TEXT NOT NULL, FOREIGN KEY(activation_id,environment,version)
 REFERENCES ops_ReleaseActivation(activation_id,environment,version)
);
CREATE TABLE IF NOT EXISTS ops_TaskOperation (
 operation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, dataset_id TEXT NOT NULL,
 environment TEXT NOT NULL, scope TEXT NOT NULL, release_version TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL, window_start TEXT NOT NULL, window_end TEXT NOT NULL,
 kind TEXT NOT NULL, source_mode TEXT NOT NULL,
 original_operation_id TEXT REFERENCES ops_TaskOperation(operation_id), substitution_approval TEXT,
 request_hash TEXT NOT NULL, status TEXT NOT NULL, fence INTEGER NOT NULL CHECK(fence>=0),
 owner TEXT, lease_until TEXT, attempt_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 last_error TEXT, CHECK(window_start<window_end),
 UNIQUE(operation_id,dataset_id,environment,scope,window_start,window_end),
 FOREIGN KEY(release_version,task_id,dataset_id,scope)
 REFERENCES cfg_ProcessingTask(release_version,task_id,primary_output,scope),
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id)
);
CREATE INDEX IF NOT EXISTS IX_TaskOperation_conflicts
 ON ops_TaskOperation(environment,scope,dataset_id,status,window_start,window_end);
CREATE TABLE IF NOT EXISTS ops_TaskAttempt (
 attempt_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES ops_TaskOperation(operation_id),
 owner TEXT NOT NULL, fence INTEGER NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
 status TEXT NOT NULL, UNIQUE(operation_id,fence), UNIQUE(operation_id,attempt_id)
);
CREATE TABLE IF NOT EXISTS ops_DatasetOutput (
 output_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE,
 dataset_id TEXT NOT NULL, environment TEXT NOT NULL, scope TEXT NOT NULL, delta_version TEXT NOT NULL,
 window_start TEXT NOT NULL, window_end TEXT NOT NULL,
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)), evidence_hash TEXT NOT NULL,
 committed_at TEXT NOT NULL, changed_rows INTEGER NOT NULL CHECK(changed_rows>=0),
 UNIQUE(output_id,dataset_id,environment,scope),
 FOREIGN KEY(operation_id,dataset_id,environment,scope,window_start,window_end)
 REFERENCES ops_TaskOperation(operation_id,dataset_id,environment,scope,window_start,window_end)
);
CREATE TABLE IF NOT EXISTS ops_SourceSnapshot (
 source_snapshot_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES cfg_DatasetIdentity(dataset_id),
 environment TEXT NOT NULL, scope TEXT NOT NULL, version TEXT NOT NULL,
 window_start TEXT NOT NULL, window_end TEXT NOT NULL, evidence_digest TEXT NOT NULL,
 artifact_ref TEXT NOT NULL, created_at TEXT NOT NULL, retired_at TEXT,
 UNIQUE(dataset_id,environment,scope,version,window_start,window_end), CHECK(window_start<window_end)
);
CREATE TABLE IF NOT EXISTS ops_OperationInput (
 operation_id TEXT NOT NULL REFERENCES ops_TaskOperation(operation_id),
 dataset_id TEXT NOT NULL REFERENCES cfg_DatasetIdentity(dataset_id), version TEXT NOT NULL,
 window_start TEXT NOT NULL, window_end TEXT NOT NULL,
 output_id TEXT REFERENCES ops_DatasetOutput(output_id),
 source_snapshot_id TEXT REFERENCES ops_SourceSnapshot(source_snapshot_id),
 PRIMARY KEY(operation_id,dataset_id),
 CHECK(window_start<window_end), CHECK(output_id IS NULL OR source_snapshot_id IS NULL)
);
CREATE TABLE IF NOT EXISTS ops_DatasetReadiness (
 dataset_id TEXT NOT NULL REFERENCES cfg_DatasetIdentity(dataset_id),
 environment TEXT NOT NULL, scope TEXT NOT NULL, output_id TEXT, progress_end TEXT,
 expected_operation_id TEXT REFERENCES ops_TaskOperation(operation_id), expected_end TEXT,
 expected_status TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(dataset_id,environment,scope),
 FOREIGN KEY(output_id,dataset_id,environment,scope)
 REFERENCES ops_DatasetOutput(output_id,dataset_id,environment,scope)
);
CREATE TABLE IF NOT EXISTS ops_DatasetBlock (
 block_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL,
 dataset_id TEXT NOT NULL REFERENCES cfg_DatasetIdentity(dataset_id), environment TEXT NOT NULL,
 scope TEXT NOT NULL, release_version TEXT NOT NULL REFERENCES cfg_FrameworkRelease(version),
 created_at TEXT NOT NULL, cleared_at TEXT, operator_approval TEXT, validation_digest TEXT,
 CHECK(cleared_at IS NULL OR (operator_approval IS NOT NULL AND validation_digest IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS ops_ReadinessOutbox (
 event_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, environment TEXT NOT NULL, scope TEXT NOT NULL,
 output_id TEXT NOT NULL, event_sequence INTEGER NOT NULL, progress_end TEXT NOT NULL,
 created_at TEXT NOT NULL, delivered_at TEXT, dispatch_attempts INTEGER NOT NULL,
 next_retry_at TEXT, last_error TEXT,
 UNIQUE(dataset_id,environment,scope,event_sequence),
 FOREIGN KEY(output_id,dataset_id,environment,scope)
 REFERENCES ops_DatasetOutput(output_id,dataset_id,environment,scope)
);
CREATE TABLE IF NOT EXISTS ops_EventReceipt (
 event_id TEXT NOT NULL REFERENCES ops_ReadinessOutbox(event_id), consumer_id TEXT NOT NULL,
 accepted INTEGER NOT NULL, received_at TEXT NOT NULL, PRIMARY KEY(event_id,consumer_id)
);
CREATE TABLE IF NOT EXISTS ops_ReconciliationRun (
 reconciliation_id TEXT PRIMARY KEY, environment TEXT NOT NULL, owner TEXT NOT NULL,
 release_version TEXT NOT NULL REFERENCES cfg_FrameworkRelease(version),
 snapshot_hash TEXT NOT NULL, snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
 started_at TEXT NOT NULL, lease_until TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL,
 retry_count INTEGER NOT NULL CHECK(retry_count>=0), max_retries INTEGER NOT NULL CHECK(max_retries>=0),
 next_retry_at TEXT, last_error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS UX_ReconciliationRun_owner
 ON ops_ReconciliationRun(environment) WHERE status='RUNNING';
CREATE TABLE IF NOT EXISTS ops_ReferenceHold (
 hold_id TEXT PRIMARY KEY, kind TEXT NOT NULL, reference_id TEXT NOT NULL,
 holder TEXT NOT NULL, created_at TEXT NOT NULL, released_at TEXT
);
CREATE TABLE IF NOT EXISTS ops_ControlAudit (
 audit_id TEXT PRIMARY KEY, kind TEXT NOT NULL, reference_id TEXT NOT NULL,
 detail_json TEXT NOT NULL CHECK(json_valid(detail_json)), created_at TEXT NOT NULL
);
