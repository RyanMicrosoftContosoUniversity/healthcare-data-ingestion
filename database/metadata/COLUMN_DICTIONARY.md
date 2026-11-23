# Fabric SQL physical column dictionary

Generated from the versioned, additive T-SQL migrations. These definitions are
reviewable implementation artifacts, not evidence of live deployment.
All runtime timestamps are UTC `datetime2(7)`; coverage windows are canonical
UTC ISO `varchar(27)` so DB-API does not truncate the seventh fractional digit.
Keys, composite correlation FKs, constraints and indexes are authoritative in SQL.
No FK cascade deletion is permitted. JSON also requires application validation.

## `cfg.MetadataMigration`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `migration_id` | `varchar(40)` | No |
| `applied_at` | `datetime2(7)` | No |
| `description` | `nvarchar(1000)` | No |
| `script_hash` | `char(64)` | Yes |

## `cfg.FrameworkRelease`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `version` | `varchar(40)` | No |
| `framework_version` | `varchar(40)` | No |
| `snapshot_hash` | `char(64)` | No |
| `snapshot_json` | `nvarchar(max)` | No |
| `review_json` | `nvarchar(max)` | No |
| `queue_sequence` | `bigint` | No |
| `status` | `varchar(16)` | No |
| `checks_json` | `nvarchar(max)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `failure_code` | `nvarchar(1000)` | Yes |

## `cfg.DatasetIdentity`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `dataset_id` | `varchar(128)` | No |
| `layer` | `varchar(16)` | No |
| `external` | `bit` | No |
| `created_at` | `datetime2(7)` | No |

## `cfg.Dataset`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `dataset_id` | `varchar(128)` | No |
| `name` | `nvarchar(256)` | No |
| `retired` | `bit` | No |
| `freshness_seconds` | `bigint` | No |

## `cfg.DatasetPhysicalMap`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `dataset_id` | `varchar(128)` | No |
| `environment` | `varchar(128)` | No |
| `physical_json` | `nvarchar(max)` | No |

## `cfg.PipelineObjectMapping`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `pipeline_object_id` | `varchar(128)` | No |
| `mapping_json` | `nvarchar(max)` | No |
| `legacy_pipeline_object_id` | `bigint` | Yes |

## `cfg.PipelineDefinitionRelease`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `stage` | `varchar(16)` | No |
| `framework_defaults_json` | `nvarchar(max)` | No |
| `stage_defaults_json` | `nvarchar(max)` | No |

## `cfg.ProcessingTask`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `task_id` | `varchar(128)` | No |
| `workflow` | `varchar(128)` | No |
| `primary_output` | `varchar(128)` | No |
| `pipeline_object_id` | `varchar(128)` | Yes |
| `scope` | `varchar(128)` | No |
| `retired` | `bit` | No |
| `functions_json` | `nvarchar(max)` | No |
| `overrides_json` | `nvarchar(max)` | No |

## `cfg.TaskInput`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `task_id` | `varchar(128)` | No |
| `dataset_id` | `varchar(128)` | No |
| `alias` | `varchar(128)` | No |
| `required` | `bit` | No |
| `freshness_seconds` | `bigint` | Yes |
| `allow_stale` | `bit` | No |

## `cfg.TaskDependency`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `task_id` | `varchar(128)` | No |
| `predecessor_task_id` | `varchar(128)` | No |
| `reason` | `nvarchar(1000)` | No |

## `cfg.LegacyStepAttribution`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `release_version` | `varchar(40)` | No |
| `task_id` | `varchar(128)` | No |
| `occurrence_id` | `varchar(128)` | No |
| `legacy_transformation_step_id` | `bigint` | No |
| `legacy_pipeline_object_id` | `bigint` | Yes |
| `import_evidence` | `nvarchar(1000)` | No |

## `ops.ReleaseActivation`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `activation_id` | `varchar(36)` | No |
| `environment` | `varchar(128)` | No |
| `version` | `varchar(40)` | No |
| `previous_version` | `varchar(40)` | Yes |
| `action` | `varchar(16)` | No |
| `reason` | `nvarchar(1000)` | No |
| `activated_at` | `datetime2(7)` | No |

## `ops.ActiveRelease`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `environment` | `varchar(128)` | No |
| `version` | `varchar(40)` | No |
| `activation_id` | `varchar(36)` | No |
| `updated_at` | `datetime2(7)` | No |

## `ops.TaskOperation`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `operation_id` | `varchar(128)` | No |
| `task_id` | `varchar(128)` | No |
| `dataset_id` | `varchar(128)` | No |
| `environment` | `varchar(128)` | No |
| `scope` | `varchar(128)` | No |
| `release_version` | `varchar(40)` | No |
| `snapshot_hash` | `char(64)` | No |
| `window_start` | `varchar(27)` | No |
| `window_end` | `varchar(27)` | No |
| `kind` | `varchar(16)` | No |
| `source_mode` | `varchar(16)` | No |
| `original_operation_id` | `varchar(128)` | Yes |
| `substitution_approval` | `nvarchar(1000)` | Yes |
| `request_hash` | `char(64)` | No |
| `status` | `varchar(32)` | No |
| `fence` | `bigint` | No |
| `owner` | `varchar(128)` | Yes |
| `lease_until` | `datetime2(7)` | Yes |
| `attempt_id` | `varchar(36)` | Yes |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `last_error` | `nvarchar(1000)` | Yes |

## `ops.TaskAttempt`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `attempt_id` | `varchar(36)` | No |
| `operation_id` | `varchar(128)` | No |
| `owner` | `varchar(128)` | No |
| `fence` | `bigint` | No |
| `started_at` | `datetime2(7)` | No |
| `completed_at` | `datetime2(7)` | Yes |
| `status` | `varchar(32)` | No |

## `ops.DatasetOutput`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `output_id` | `varchar(36)` | No |
| `operation_id` | `varchar(128)` | No |
| `dataset_id` | `varchar(128)` | No |
| `environment` | `varchar(128)` | No |
| `scope` | `varchar(128)` | No |
| `delta_version` | `varchar(128)` | No |
| `window_start` | `varchar(27)` | No |
| `window_end` | `varchar(27)` | No |
| `evidence_json` | `nvarchar(max)` | No |
| `evidence_hash` | `char(64)` | No |
| `committed_at` | `datetime2(7)` | No |
| `changed_rows` | `bigint` | No |
| `source_coverage_start` | `varchar(27)` | Yes |
| `source_coverage_end` | `varchar(27)` | Yes |

## `ops.SourceSnapshot`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `source_snapshot_id` | `varchar(36)` | No |
| `dataset_id` | `varchar(128)` | No |
| `environment` | `varchar(128)` | No |
| `scope` | `varchar(128)` | No |
| `version` | `varchar(128)` | No |
| `window_start` | `varchar(27)` | No |
| `window_end` | `varchar(27)` | No |
| `evidence_digest` | `varchar(128)` | No |
| `artifact_ref` | `nvarchar(1000)` | No |
| `created_at` | `datetime2(7)` | No |
| `retired_at` | `datetime2(7)` | Yes |

## `ops.OperationInput`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `operation_id` | `varchar(128)` | No |
| `dataset_id` | `varchar(128)` | No |
| `version` | `varchar(128)` | No |
| `window_start` | `varchar(27)` | No |
| `window_end` | `varchar(27)` | No |
| `output_id` | `varchar(36)` | Yes |
| `source_snapshot_id` | `varchar(36)` | Yes |
| `source_coverage_start` | `varchar(27)` | Yes |
| `source_coverage_end` | `varchar(27)` | Yes |

## `ops.DatasetReadiness`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `dataset_id` | `varchar(128)` | No |
| `environment` | `varchar(128)` | No |
| `scope` | `varchar(128)` | No |
| `output_id` | `varchar(36)` | Yes |
| `progress_end` | `varchar(27)` | Yes |
| `expected_operation_id` | `varchar(128)` | Yes |
| `expected_end` | `varchar(27)` | Yes |
| `expected_status` | `varchar(32)` | No |
| `updated_at` | `datetime2(7)` | No |
| `source_coverage_start` | `varchar(27)` | Yes |
| `source_coverage_end` | `varchar(27)` | Yes |

## `ops.DatasetBlock`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `block_id` | `varchar(512)` | No |
| `incident_id` | `varchar(128)` | No |
| `dataset_id` | `varchar(128)` | No |
| `environment` | `varchar(128)` | No |
| `scope` | `varchar(128)` | No |
| `release_version` | `varchar(40)` | No |
| `created_at` | `datetime2(7)` | No |
| `cleared_at` | `datetime2(7)` | Yes |
| `operator_approval` | `nvarchar(1000)` | Yes |
| `validation_digest` | `varchar(128)` | Yes |

## `ops.ReadinessOutbox`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `event_id` | `varchar(128)` | No |
| `dataset_id` | `varchar(128)` | No |
| `environment` | `varchar(128)` | No |
| `scope` | `varchar(128)` | No |
| `output_id` | `varchar(36)` | No |
| `event_sequence` | `bigint` | No |
| `progress_end` | `varchar(27)` | No |
| `created_at` | `datetime2(7)` | No |
| `delivered_at` | `datetime2(7)` | Yes |
| `dispatch_attempts` | `int` | No |
| `next_retry_at` | `datetime2(7)` | Yes |
| `last_error` | `nvarchar(1000)` | Yes |

## `ops.EventReceipt`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `event_id` | `varchar(128)` | No |
| `consumer_id` | `varchar(128)` | No |
| `accepted` | `bit` | No |
| `received_at` | `datetime2(7)` | No |

## `ops.ReconciliationRun`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `reconciliation_id` | `varchar(36)` | No |
| `environment` | `varchar(128)` | No |
| `owner` | `varchar(128)` | No |
| `release_version` | `varchar(40)` | No |
| `snapshot_hash` | `char(64)` | No |
| `snapshot_json` | `nvarchar(max)` | No |
| `started_at` | `datetime2(7)` | No |
| `lease_until` | `datetime2(7)` | No |
| `completed_at` | `datetime2(7)` | Yes |
| `status` | `varchar(32)` | No |
| `retry_count` | `int` | No |
| `max_retries` | `int` | No |
| `next_retry_at` | `datetime2(7)` | Yes |
| `last_error` | `nvarchar(1000)` | Yes |

## `ops.ReferenceHold`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `hold_id` | `char(64)` | No |
| `kind` | `varchar(16)` | No |
| `reference_id` | `varchar(256)` | No |
| `holder` | `varchar(128)` | No |
| `created_at` | `datetime2(7)` | No |
| `released_at` | `datetime2(7)` | Yes |

## `ops.ControlAudit`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `audit_id` | `varchar(36)` | No |
| `kind` | `varchar(64)` | No |
| `reference_id` | `varchar(256)` | No |
| `detail_json` | `nvarchar(max)` | No |
| `created_at` | `datetime2(7)` | No |

## `ops.TaskDiagnosticAttempt`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `scope_key` | `varchar(512)` | No |
| `collection_attempt` | `int` | No |
| `max_attempts` | `int` | No |
| `availability` | `varchar(32)` | No |
| `reason` | `nvarchar(2048)` | Yes |
| `spark_json` | `nvarchar(max)` | No |
| `started_at` | `datetime2(7)` | Yes |
| `completed_at` | `datetime2(7)` | Yes |

## `ops.TaskDiagnosticLog`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `collection_id` | `varchar(128)` | No |
| `kind` | `varchar(32)` | No |
| `filename` | `nvarchar(512)` | No |
| `source_identity` | `nvarchar(2048)` | No |
| `artifact` | `nvarchar(2048)` | Yes |
| `bytes` | `bigint` | Yes |
| `sha256` | `char(64)` | Yes |
| `complete` | `bit` | No |
| `availability` | `varchar(32)` | No |
| `reason` | `nvarchar(2048)` | Yes |
| `source_modified_at` | `datetime2(7)` | Yes |
| `collected_at` | `datetime2(7)` | Yes |
| `retrieval_context_json` | `nvarchar(max)` | No |

## `ops.TaskSparkMetric`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `activity_run_id` | `varchar(512)` | No |
| `workspace_id` | `varchar(512)` | No |
| `item_id` | `varchar(512)` | No |
| `item_type` | `varchar(32)` | No |
| `livy_id` | `varchar(512)` | No |
| `application_id` | `varchar(512)` | No |
| `application_attempt_id` | `varchar(512)` | No |
| `collected_at` | `datetime2(7)` | Yes |
| `execution_evidence_json` | `nvarchar(max)` | No |
| `source_mapping_json` | `nvarchar(max)` | No |
| `ShuffleWriteRecords` | `bigint` | Yes |
| `AllocatedExecutorsMin` | `int` | Yes |
| `AllocatedExecutorsMax` | `int` | Yes |
| `IsAnomalous` | `bit` | Yes |
| `ExpectedDuration` | `decimal(20,6)` | Yes |
| `PotentialCausesJson` | `nvarchar(max)` | Yes |
| `TotalDuration` | `decimal(20,6)` | Yes |
| `JobCount` | `bigint` | Yes |
| `QueryCount` | `bigint` | Yes |
| `TaskCount` | `bigint` | Yes |
| `ReadRows` | `bigint` | Yes |
| `WriteRows` | `bigint` | Yes |
| `JoinCount` | `bigint` | Yes |
| `ScanCount` | `bigint` | Yes |
| `FilterCount` | `bigint` | Yes |
| `UnionCount` | `bigint` | Yes |
| `CollectCount` | `bigint` | Yes |
| `HashAggregateCount` | `bigint` | Yes |
| `ExchangeCount` | `bigint` | Yes |
| `ShuffleReadLocalBytes` | `bigint` | Yes |
| `ShuffleReadRemoteBytes` | `bigint` | Yes |
| `ShuffleWriteBytes` | `bigint` | Yes |
| `ReadBytes` | `bigint` | Yes |
| `WriteBytes` | `bigint` | Yes |
| `MemorySpilledBytes` | `bigint` | Yes |
| `DiskSpilledBytes` | `bigint` | Yes |
| `GCTime` | `decimal(20,6)` | Yes |
| `StageCount` | `bigint` | Yes |
| `ShuffleMapStageCount` | `bigint` | Yes |
| `ResultStageCount` | `bigint` | Yes |
| `CompilationTime` | `decimal(20,6)` | Yes |
| `ExecutionTime` | `decimal(20,6)` | Yes |
| `IdleTime` | `decimal(20,6)` | Yes |
| `CoreAllocation` | `decimal(18,4)` | Yes |
| `UtilizationPercentage` | `decimal(9,4)` | Yes |
| `TaskDuration` | `decimal(20,6)` | Yes |
| `ShuffleTime` | `decimal(20,6)` | Yes |
| `IOTime` | `decimal(20,6)` | Yes |
| `CPUTime` | `decimal(20,6)` | Yes |
| `ShuffleReadTime` | `decimal(20,6)` | Yes |
| `ShuffleWriteTime` | `decimal(20,6)` | Yes |
| `ReadTime` | `decimal(20,6)` | Yes |
| `WriteTime` | `decimal(20,6)` | Yes |
| `SerializationTime` | `decimal(20,6)` | Yes |
| `DeserializeTime` | `decimal(20,6)` | Yes |
| `ExecutorComputingTime` | `decimal(20,6)` | Yes |
| `ApplicationRunTime` | `decimal(20,6)` | Yes |
| `OverheadTime` | `decimal(20,6)` | Yes |
| `QueueingTime` | `decimal(20,6)` | Yes |
| `StartingTime` | `decimal(20,6)` | Yes |

## `ops.TransformationBenchmarkTrial`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `run_id` | `varchar(512)` | No |
| `trial` | `int` | No |
| `warmup` | `bit` | No |
| `input_versions_json` | `nvarchar(max)` | No |
| `snapshot_context_json` | `nvarchar(max)` | No |
| `compute_context_json` | `nvarchar(max)` | No |
| `artifact` | `nvarchar(2048)` | Yes |
| `started_at` | `datetime2(7)` | Yes |
| `completed_at` | `datetime2(7)` | Yes |

## `ops.TransformationBenchmarkStep`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `run_id` | `varchar(512)` | No |
| `trial` | `int` | No |
| `warmup` | `bit` | No |
| `input_versions_json` | `nvarchar(max)` | No |
| `snapshot_context_json` | `nvarchar(max)` | No |
| `compute_context_json` | `nvarchar(max)` | No |
| `artifact` | `nvarchar(2048)` | Yes |
| `started_at` | `datetime2(7)` | Yes |
| `completed_at` | `datetime2(7)` | Yes |
| `ordinal` | `int` | No |
| `function` | `varchar(128)` | No |
| `occurrence_id` | `varchar(128)` | No |
| `parameters_json` | `nvarchar(max)` | No |
| `attempt_number` | `int` | No |
| `plan_seconds` | `decimal(20,6)` | Yes |
| `materialization_seconds` | `decimal(20,6)` | Yes |
| `reread_seconds` | `decimal(20,6)` | Yes |
| `total_seconds` | `decimal(20,6)` | Yes |
| `rows` | `bigint` | Yes |
| `exception_type` | `varchar(512)` | Yes |
| `execution_metrics_json` | `nvarchar(max)` | No |
| `collection_status` | `varchar(32)` | No |
| `trial_record_id` | `varchar(128)` | No |

## `ops.TaskQualityOutcome`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `check` | `varchar(512)` | No |
| `evidence_digest` | `varchar(512)` | No |
| `severity` | `varchar(16)` | No |
| `reason` | `nvarchar(2048)` | Yes |
| `expected_value` | `decimal(38,6)` | Yes |
| `actual_value` | `decimal(38,6)` | Yes |
| `artifact` | `nvarchar(2048)` | Yes |
| `details_json` | `nvarchar(max)` | No |

## `ops.TaskQuarantineManifest`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `quality_record_id` | `varchar(128)` | No |
| `artifact` | `nvarchar(2048)` | No |
| `reason_code` | `varchar(512)` | No |
| `row_count` | `bigint` | No |
| `schema_digest` | `varchar(512)` | No |
| `identifiers_manifest_ref` | `nvarchar(2048)` | Yes |
| `input_versions_json` | `nvarchar(max)` | No |

## `ops.ArtifactCleanupOutcome`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_id` | `varchar(128)` | No |
| `natural_key` | `char(64)` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `revision` | `int` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |
| `artifact_id` | `varchar(512)` | No |
| `artifact` | `nvarchar(2048)` | Yes |
| `artifact_kind` | `varchar(512)` | Yes |
| `attempt_number` | `int` | No |
| `reason` | `nvarchar(2048)` | Yes |
| `proof_digest` | `varchar(512)` | Yes |
| `started_at` | `datetime2(7)` | Yes |
| `completed_at` | `datetime2(7)` | Yes |

## `ops.OperationalRecordRevision`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `record_type` | `varchar(32)` | No |
| `record_id` | `varchar(128)` | No |
| `revision` | `int` | No |
| `operation_id` | `varchar(128)` | No |
| `attempt_id` | `varchar(36)` | No |
| `release_version` | `varchar(40)` | No |
| `status` | `varchar(32)` | No |
| `payload_json` | `nvarchar(max)` | No |
| `payload_hash` | `char(64)` | No |
| `created_at` | `datetime2(7)` | No |

## `ops.WaitingOperation`

| Column | SQL type | Nullable |
| --- | --- | --- |
| `operation_id` | `varchar(128)` | No |
| `declared_inputs_json` | `nvarchar(max)` | No |
| `binding_hash` | `char(64)` | Yes |
| `bound_at` | `datetime2(7)` | Yes |
| `created_at` | `datetime2(7)` | No |
| `updated_at` | `datetime2(7)` | No |

