-- REVIEWED DEPLOYMENT INPUT ONLY: no principals/members or credentials are provisioned here.
-- Run after metadata migrations with the authorized database deployment identity.
-- Native SQL/Fabric endpoint role and negative-permission tests remain mandatory.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF DATABASE_PRINCIPAL_ID(N'ingestion_runtime') IS NULL CREATE ROLE ingestion_runtime;
IF DATABASE_PRINCIPAL_ID(N'ingestion_publisher') IS NULL CREATE ROLE ingestion_publisher;
IF DATABASE_PRINCIPAL_ID(N'ingestion_operator') IS NULL CREATE ROLE ingestion_operator;
IF DATABASE_PRINCIPAL_ID(N'ingestion_auditor') IS NULL CREATE ROLE ingestion_auditor;
GRANT SELECT ON SCHEMA::cfg TO ingestion_runtime;
GRANT SELECT ON SCHEMA::ops TO ingestion_runtime;
DENY INSERT, UPDATE, DELETE ON SCHEMA::cfg TO ingestion_runtime;
DENY DELETE ON SCHEMA::ops TO ingestion_runtime;
GRANT INSERT ON ops.TaskOperation TO ingestion_runtime;
GRANT UPDATE ON ops.TaskOperation(status,fence,owner,lease_until,attempt_id,updated_at,last_error)
    TO ingestion_runtime;
GRANT INSERT ON ops.TaskAttempt TO ingestion_runtime;
GRANT UPDATE ON ops.TaskAttempt(status,completed_at) TO ingestion_runtime;
GRANT INSERT ON ops.OperationInput TO ingestion_runtime;
GRANT INSERT ON ops.WaitingOperation TO ingestion_runtime;
GRANT UPDATE ON ops.WaitingOperation(binding_hash,bound_at,updated_at) TO ingestion_runtime;
GRANT INSERT ON ops.SourceSnapshot TO ingestion_runtime;
GRANT INSERT ON ops.DatasetOutput TO ingestion_runtime;
GRANT INSERT ON ops.DatasetReadiness TO ingestion_runtime;
GRANT UPDATE ON ops.DatasetReadiness
    (output_id,progress_end,source_coverage_start,source_coverage_end,
     expected_operation_id,expected_end,expected_status,updated_at)
    TO ingestion_runtime;
GRANT INSERT ON ops.DatasetBlock TO ingestion_runtime;
-- No runtime UPDATE grant on corruption blocks: clearing belongs to the operator.
GRANT INSERT ON ops.ReadinessOutbox TO ingestion_runtime;
GRANT UPDATE ON ops.ReadinessOutbox(delivered_at,dispatch_attempts,next_retry_at,last_error)
    TO ingestion_runtime;
GRANT INSERT ON ops.EventReceipt TO ingestion_runtime;
GRANT INSERT ON ops.ReconciliationRun TO ingestion_runtime;
GRANT UPDATE ON ops.ReconciliationRun
    (lease_until,completed_at,status,retry_count,next_retry_at,last_error) TO ingestion_runtime;
GRANT INSERT ON ops.ReferenceHold TO ingestion_runtime;
GRANT INSERT ON ops.ControlAudit TO ingestion_runtime;
-- Versioned task-grain operational records never publish readiness through telemetry.
GRANT INSERT, UPDATE ON ops.TaskDiagnosticAttempt TO ingestion_runtime;
GRANT INSERT, UPDATE ON ops.TaskDiagnosticLog TO ingestion_runtime;
GRANT INSERT, UPDATE ON ops.TaskSparkMetric TO ingestion_runtime;
GRANT INSERT, UPDATE ON ops.TransformationBenchmarkTrial TO ingestion_runtime;
GRANT INSERT, UPDATE ON ops.TransformationBenchmarkStep TO ingestion_runtime;
GRANT INSERT, UPDATE ON ops.TaskQualityOutcome TO ingestion_runtime;
GRANT INSERT, UPDATE ON ops.TaskQuarantineManifest TO ingestion_runtime;
GRANT INSERT, UPDATE ON ops.ArtifactCleanupOutcome TO ingestion_runtime;
GRANT INSERT ON ops.OperationalRecordRevision TO ingestion_runtime;
GRANT EXECUTE ON sys.sp_getapplock TO ingestion_runtime;

GRANT SELECT ON SCHEMA::cfg TO ingestion_publisher;
GRANT SELECT ON SCHEMA::ops TO ingestion_publisher;
GRANT INSERT ON cfg.FrameworkRelease TO ingestion_publisher;
GRANT INSERT ON cfg.DatasetIdentity TO ingestion_publisher;
GRANT INSERT ON cfg.Dataset TO ingestion_publisher;
GRANT INSERT ON cfg.DatasetPhysicalMap TO ingestion_publisher;
GRANT INSERT ON cfg.PipelineObjectMapping TO ingestion_publisher;
GRANT INSERT ON cfg.PipelineDefinitionRelease TO ingestion_publisher;
GRANT INSERT ON cfg.ProcessingTask TO ingestion_publisher;
GRANT INSERT ON cfg.TaskInput TO ingestion_publisher;
GRANT INSERT ON cfg.TaskDependency TO ingestion_publisher;
GRANT INSERT ON cfg.LegacyStepAttribution TO ingestion_publisher;
DENY DELETE ON SCHEMA::cfg TO ingestion_publisher;
GRANT UPDATE ON cfg.FrameworkRelease(status,checks_json,updated_at,failure_code)
    TO ingestion_publisher;
GRANT INSERT ON ops.ReleaseActivation TO ingestion_publisher;
GRANT INSERT, UPDATE ON ops.ActiveRelease TO ingestion_publisher;
GRANT INSERT ON ops.ControlAudit TO ingestion_publisher;
GRANT EXECUTE ON sys.sp_getapplock TO ingestion_publisher;
-- Publisher has no UPDATE grant on snapshots, function arrays, identities, mappings or inputs.

GRANT SELECT ON SCHEMA::cfg TO ingestion_operator;
GRANT SELECT ON SCHEMA::ops TO ingestion_operator;
GRANT INSERT ON ops.DatasetBlock TO ingestion_operator;
GRANT UPDATE ON ops.DatasetBlock(cleared_at,operator_approval,validation_digest)
    TO ingestion_operator;
GRANT UPDATE ON ops.ReferenceHold(released_at) TO ingestion_operator;
GRANT UPDATE ON ops.TaskOperation(status,owner,lease_until,updated_at) TO ingestion_operator;
GRANT INSERT ON ops.ControlAudit TO ingestion_operator;
GRANT EXECUTE ON sys.sp_getapplock TO ingestion_operator;
DENY INSERT, UPDATE, DELETE ON SCHEMA::cfg TO ingestion_operator;
GRANT SELECT ON SCHEMA::cfg TO ingestion_auditor;
GRANT SELECT ON SCHEMA::ops TO ingestion_auditor;
DENY INSERT, UPDATE, DELETE ON SCHEMA::cfg TO ingestion_auditor;
DENY INSERT, UPDATE, DELETE ON SCHEMA::ops TO ingestion_auditor;
COMMIT;
