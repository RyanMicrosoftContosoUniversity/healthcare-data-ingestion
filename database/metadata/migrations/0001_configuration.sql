-- Fabric SQL Database TRANSACTIONAL endpoint. Additive; baseline tables remain untouched.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF SCHEMA_ID(N'cfg') IS NULL EXEC(N'CREATE SCHEMA cfg');
IF SCHEMA_ID(N'ops') IS NULL EXEC(N'CREATE SCHEMA ops');
IF OBJECT_ID(N'cfg.MetadataMigration', N'U') IS NULL
CREATE TABLE cfg.MetadataMigration (
    migration_id varchar(40) NOT NULL CONSTRAINT PK_MetadataMigration PRIMARY KEY,
    applied_at datetime2(7) NOT NULL DEFAULT SYSUTCDATETIME(),
    description nvarchar(1000) NOT NULL
    , script_hash char(64) NULL
);
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0001_configuration')
BEGIN
CREATE TABLE cfg.FrameworkRelease (
    version varchar(40) NOT NULL CONSTRAINT PK_FrameworkRelease PRIMARY KEY,
    framework_version varchar(40) NOT NULL,
    snapshot_hash char(64) NOT NULL,
    snapshot_json nvarchar(max) NOT NULL CHECK (ISJSON(snapshot_json)=1),
    review_json nvarchar(max) NOT NULL CHECK (ISJSON(review_json)=1),
    queue_sequence bigint NOT NULL CONSTRAINT UQ_FrameworkRelease_queue UNIQUE,
    status varchar(16) NOT NULL CHECK
        (status IN ('QUEUED','TESTING','READY','FAILED','ACTIVE','SUPERSEDED')),
    checks_json nvarchar(max) NOT NULL CHECK (ISJSON(checks_json)=1),
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    failure_code nvarchar(1000) NULL,
    CONSTRAINT CK_FrameworkDagVersion CHECK (version=framework_version)
);
CREATE TABLE cfg.DatasetIdentity (
    dataset_id varchar(128) NOT NULL CONSTRAINT PK_DatasetIdentity PRIMARY KEY,
    layer varchar(16) NOT NULL CHECK (layer IN ('source','bronze','silver1','silver2','gold')),
    [external] bit NOT NULL,
    created_at datetime2(7) NOT NULL
);
CREATE TABLE cfg.Dataset (
    release_version varchar(40) NOT NULL,
    dataset_id varchar(128) NOT NULL,
    name nvarchar(256) NOT NULL,
    retired bit NOT NULL,
    freshness_seconds bigint NOT NULL CHECK (freshness_seconds>=0),
    CONSTRAINT PK_Dataset PRIMARY KEY (release_version,dataset_id),
    CONSTRAINT FK_Dataset_release FOREIGN KEY (release_version) REFERENCES cfg.FrameworkRelease(version),
    CONSTRAINT FK_Dataset_identity FOREIGN KEY (dataset_id) REFERENCES cfg.DatasetIdentity(dataset_id)
);
CREATE TABLE cfg.DatasetPhysicalMap (
    release_version varchar(40) NOT NULL,
    dataset_id varchar(128) NOT NULL,
    environment varchar(128) NOT NULL,
    physical_json nvarchar(max) NOT NULL CHECK (ISJSON(physical_json)=1),
    CONSTRAINT PK_DatasetPhysicalMap PRIMARY KEY (release_version,dataset_id,environment),
    CONSTRAINT FK_PhysicalMap_dataset FOREIGN KEY (release_version,dataset_id)
        REFERENCES cfg.Dataset(release_version,dataset_id)
);
-- Release-local mapping bridge. Do not replace or reinterpret baseline cfg.PipelineObject.
CREATE TABLE cfg.PipelineObjectMapping (
    release_version varchar(40) NOT NULL,
    pipeline_object_id varchar(128) NOT NULL,
    mapping_json nvarchar(max) NOT NULL CHECK (ISJSON(mapping_json)=1),
    legacy_pipeline_object_id bigint NULL,
    CONSTRAINT PK_PipelineObjectMapping PRIMARY KEY (release_version,pipeline_object_id),
    CONSTRAINT FK_PipelineObjectMapping_release FOREIGN KEY (release_version)
        REFERENCES cfg.FrameworkRelease(version)
);
-- Revised shared/stage policies have no baseline InputLayer or OutputLayer fields.
CREATE TABLE cfg.PipelineDefinitionRelease (
    release_version varchar(40) NOT NULL,
    stage varchar(16) NOT NULL,
    framework_defaults_json nvarchar(max) NOT NULL CHECK (ISJSON(framework_defaults_json)=1),
    stage_defaults_json nvarchar(max) NOT NULL CHECK (ISJSON(stage_defaults_json)=1),
    CONSTRAINT PK_PipelineDefinitionRelease PRIMARY KEY (release_version,stage),
    CONSTRAINT FK_PipelineDefinitionRelease_release FOREIGN KEY (release_version)
        REFERENCES cfg.FrameworkRelease(version)
);
CREATE TABLE cfg.ProcessingTask (
    release_version varchar(40) NOT NULL,
    task_id varchar(128) NOT NULL,
    workflow varchar(128) NOT NULL,
    primary_output varchar(128) NOT NULL,
    pipeline_object_id varchar(128) NULL,
    scope varchar(128) NOT NULL,
    retired bit NOT NULL,
    functions_json nvarchar(max) NOT NULL CHECK (ISJSON(functions_json)=1),
    overrides_json nvarchar(max) NOT NULL CHECK (ISJSON(overrides_json)=1),
    CONSTRAINT PK_ProcessingTask PRIMARY KEY (release_version,task_id),
    CONSTRAINT FK_ProcessingTask_dataset FOREIGN KEY (release_version,primary_output)
        REFERENCES cfg.Dataset(release_version,dataset_id),
    CONSTRAINT FK_ProcessingTask_mapping FOREIGN KEY (release_version,pipeline_object_id)
        REFERENCES cfg.PipelineObjectMapping(release_version,pipeline_object_id),
    CONSTRAINT UQ_ProcessingTask_correlation UNIQUE (release_version,task_id,primary_output,scope)
);
CREATE UNIQUE INDEX UX_ProcessingTask_producer
    ON cfg.ProcessingTask(release_version,primary_output,scope) WHERE retired=0;
CREATE TABLE cfg.TaskInput (
    release_version varchar(40) NOT NULL,
    task_id varchar(128) NOT NULL,
    dataset_id varchar(128) NOT NULL,
    alias varchar(128) NOT NULL,
    required bit NOT NULL,
    freshness_seconds bigint NULL CHECK (freshness_seconds>=0),
    allow_stale bit NOT NULL,
    CONSTRAINT PK_TaskInput PRIMARY KEY (release_version,task_id,alias),
    CONSTRAINT FK_TaskInput_task FOREIGN KEY (release_version,task_id)
        REFERENCES cfg.ProcessingTask(release_version,task_id),
    CONSTRAINT FK_TaskInput_dataset FOREIGN KEY (release_version,dataset_id)
        REFERENCES cfg.Dataset(release_version,dataset_id)
);
CREATE INDEX IX_TaskInput_consumers ON cfg.TaskInput(release_version,dataset_id);
CREATE TABLE cfg.TaskDependency (
    release_version varchar(40) NOT NULL,
    task_id varchar(128) NOT NULL,
    predecessor_task_id varchar(128) NOT NULL,
    reason nvarchar(1000) NOT NULL,
    CONSTRAINT PK_TaskDependency PRIMARY KEY (release_version,task_id,predecessor_task_id),
    CONSTRAINT CK_TaskDependency_self CHECK (task_id<>predecessor_task_id),
    CONSTRAINT FK_TaskDependency_task FOREIGN KEY (release_version,task_id)
        REFERENCES cfg.ProcessingTask(release_version,task_id),
    CONSTRAINT FK_TaskDependency_parent FOREIGN KEY (release_version,predecessor_task_id)
        REFERENCES cfg.ProcessingTask(release_version,task_id)
);
-- Reviewed import may attach old profiling IDs to stable JSON occurrences without changing old FKs.
CREATE TABLE cfg.LegacyStepAttribution (
    release_version varchar(40) NOT NULL,
    task_id varchar(128) NOT NULL,
    occurrence_id varchar(128) NOT NULL,
    legacy_transformation_step_id bigint NOT NULL,
    legacy_pipeline_object_id bigint NULL,
    import_evidence nvarchar(1000) NOT NULL,
    CONSTRAINT PK_LegacyStepAttribution PRIMARY KEY (release_version,task_id,occurrence_id),
    CONSTRAINT FK_LegacyStepAttribution_task FOREIGN KEY (release_version,task_id)
        REFERENCES cfg.ProcessingTask(release_version,task_id)
);
INSERT cfg.MetadataMigration(migration_id,description)
VALUES ('0001_configuration','Immutable release-local configuration; preserve original baseline');
END;
COMMIT;
