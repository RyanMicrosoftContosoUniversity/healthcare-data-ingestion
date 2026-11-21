-- Durable LOCAL reference only; authoritative types/constraints are migration 0004.
CREATE UNIQUE INDEX IF NOT EXISTS UQ_TaskOperation_release
 ON ops_TaskOperation(operation_id,release_version);
CREATE TABLE IF NOT EXISTS ops_TaskDiagnosticAttempt (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, scope_key TEXT NOT NULL,
 collection_attempt INTEGER NOT NULL, max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 6),
 availability TEXT NOT NULL, reason TEXT, spark_json TEXT NOT NULL CHECK(json_valid(spark_json)),
 started_at TEXT, completed_at TEXT, CHECK(collection_attempt BETWEEN 0 AND max_attempts),
 UNIQUE(record_id,operation_id,attempt_id,release_version),
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_TaskDiagnosticLog (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, collection_id TEXT NOT NULL,
 kind TEXT NOT NULL, filename TEXT NOT NULL, source_identity TEXT NOT NULL, artifact TEXT,
 bytes INTEGER CHECK(bytes>=0), sha256 TEXT, complete INTEGER NOT NULL, availability TEXT NOT NULL,
 reason TEXT, source_modified_at TEXT, collected_at TEXT,
 retrieval_context_json TEXT NOT NULL CHECK(json_valid(retrieval_context_json)),
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version),
 FOREIGN KEY(collection_id,operation_id,attempt_id,release_version)
 REFERENCES ops_TaskDiagnosticAttempt(record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_TaskSparkMetric (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, activity_run_id TEXT NOT NULL,
 workspace_id TEXT NOT NULL, item_id TEXT NOT NULL, item_type TEXT NOT NULL, livy_id TEXT NOT NULL,
 application_id TEXT NOT NULL, application_attempt_id TEXT NOT NULL, collected_at TEXT,
 execution_evidence_json TEXT NOT NULL CHECK(json_valid(execution_evidence_json)),
 source_mapping_json TEXT NOT NULL CHECK(json_valid(source_mapping_json)),
 ShuffleWriteRecords INTEGER, AllocatedExecutorsMin INTEGER, AllocatedExecutorsMax INTEGER,
 IsAnomalous INTEGER, ExpectedDuration TEXT, PotentialCausesJson TEXT, TotalDuration TEXT,
 JobCount INTEGER, QueryCount INTEGER, TaskCount INTEGER, ReadRows INTEGER, WriteRows INTEGER,
 JoinCount INTEGER, ScanCount INTEGER, FilterCount INTEGER, UnionCount INTEGER, CollectCount INTEGER,
 HashAggregateCount INTEGER, ExchangeCount INTEGER, ShuffleReadLocalBytes INTEGER,
 ShuffleReadRemoteBytes INTEGER, ShuffleWriteBytes INTEGER, ReadBytes INTEGER, WriteBytes INTEGER,
 MemorySpilledBytes INTEGER, DiskSpilledBytes INTEGER, GCTime TEXT, StageCount INTEGER,
 ShuffleMapStageCount INTEGER, ResultStageCount INTEGER, CompilationTime TEXT, ExecutionTime TEXT,
 IdleTime TEXT, CoreAllocation TEXT, UtilizationPercentage TEXT, TaskDuration TEXT, ShuffleTime TEXT,
 IOTime TEXT, CPUTime TEXT, ShuffleReadTime TEXT, ShuffleWriteTime TEXT, ReadTime TEXT, WriteTime TEXT,
 SerializationTime TEXT, DeserializeTime TEXT, ExecutorComputingTime TEXT, ApplicationRunTime TEXT,
 OverheadTime TEXT, QueueingTime TEXT, StartingTime TEXT,
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_TransformationBenchmarkTrial (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, run_id TEXT NOT NULL,
 trial INTEGER NOT NULL CHECK(trial BETWEEN 0 AND 3), warmup INTEGER NOT NULL,
 input_versions_json TEXT NOT NULL CHECK(json_valid(input_versions_json)),
 snapshot_context_json TEXT NOT NULL CHECK(json_valid(snapshot_context_json)),
 compute_context_json TEXT NOT NULL CHECK(json_valid(compute_context_json)), artifact TEXT,
 started_at TEXT, completed_at TEXT, CHECK((trial=0 AND warmup=1) OR (trial>0 AND warmup=0)),
 UNIQUE(record_id,operation_id,attempt_id,release_version),
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_TransformationBenchmarkStep (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, run_id TEXT NOT NULL,
 trial INTEGER NOT NULL CHECK(trial BETWEEN 0 AND 3), warmup INTEGER NOT NULL,
 input_versions_json TEXT NOT NULL CHECK(json_valid(input_versions_json)),
 snapshot_context_json TEXT NOT NULL CHECK(json_valid(snapshot_context_json)),
 compute_context_json TEXT NOT NULL CHECK(json_valid(compute_context_json)), artifact TEXT,
 started_at TEXT, completed_at TEXT, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 127),
 function TEXT NOT NULL, occurrence_id TEXT NOT NULL,
 parameters_json TEXT NOT NULL CHECK(json_valid(parameters_json)),
 attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 6),
 plan_seconds TEXT, materialization_seconds TEXT, reread_seconds TEXT, total_seconds TEXT,
 rows INTEGER CHECK(rows>=0), exception_type TEXT,
 execution_metrics_json TEXT NOT NULL CHECK(json_valid(execution_metrics_json)),
 collection_status TEXT NOT NULL, trial_record_id TEXT NOT NULL,
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version),
 FOREIGN KEY(trial_record_id,operation_id,attempt_id,release_version)
 REFERENCES ops_TransformationBenchmarkTrial(record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_TaskQualityOutcome (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL,
 revision INTEGER NOT NULL, payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 payload_hash TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 [check] TEXT NOT NULL, evidence_digest TEXT NOT NULL,
 severity TEXT NOT NULL CHECK(severity IN ('critical','warning')), reason TEXT,
 expected_value TEXT, actual_value TEXT, artifact TEXT,
 details_json TEXT NOT NULL CHECK(json_valid(details_json)),
 CHECK(status IN ('PASS','FAIL','UNAVAILABLE')),
 UNIQUE(record_id,operation_id,attempt_id,release_version),
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_TaskQuarantineManifest (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, quality_record_id TEXT NOT NULL,
 artifact TEXT NOT NULL, reason_code TEXT NOT NULL, row_count INTEGER NOT NULL CHECK(row_count>=0),
 schema_digest TEXT NOT NULL, identifiers_manifest_ref TEXT,
 input_versions_json TEXT NOT NULL CHECK(json_valid(input_versions_json)),
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version),
 FOREIGN KEY(quality_record_id,operation_id,attempt_id,release_version)
 REFERENCES ops_TaskQualityOutcome(record_id,operation_id,attempt_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_ArtifactCleanupOutcome (
 record_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, artifact_id TEXT NOT NULL,
 artifact TEXT, artifact_kind TEXT, attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 6),
 reason TEXT, proof_digest TEXT, started_at TEXT, completed_at TEXT,
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version)
);
CREATE TABLE IF NOT EXISTS ops_OperationalRecordRevision (
 record_type TEXT NOT NULL, record_id TEXT NOT NULL, revision INTEGER NOT NULL, operation_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, release_version TEXT NOT NULL, status TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(record_type,record_id,revision),
 FOREIGN KEY(operation_id,attempt_id) REFERENCES ops_TaskAttempt(operation_id,attempt_id),
 FOREIGN KEY(operation_id,release_version) REFERENCES ops_TaskOperation(operation_id,release_version)
);
