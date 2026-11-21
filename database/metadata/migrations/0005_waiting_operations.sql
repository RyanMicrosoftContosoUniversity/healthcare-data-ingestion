-- Additive deferred daily intent; existing explicit OperationInput rows are never rewritten.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0004_operational_records')
    THROW 51001, 'Apply operational records migration first', 1;
IF NOT EXISTS (SELECT 1 FROM cfg.MetadataMigration WHERE migration_id='0005_waiting_operations')
BEGIN
CREATE TABLE ops.WaitingOperation (
    operation_id varchar(128) NOT NULL CONSTRAINT PK_WaitingOperation PRIMARY KEY,
    declared_inputs_json nvarchar(max) NOT NULL
        CHECK (ISJSON(declared_inputs_json)=1 AND LEFT(LTRIM(declared_inputs_json),1)=N'['
            AND DATALENGTH(declared_inputs_json)<=131072),
    binding_hash char(64) NULL,
    bound_at datetime2(7) NULL,
    created_at datetime2(7) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT FK_WaitingOperation_operation FOREIGN KEY (operation_id)
        REFERENCES ops.TaskOperation(operation_id),
    CONSTRAINT CK_WaitingOperation_bound CHECK
        ((binding_hash IS NULL AND bound_at IS NULL)
            OR (binding_hash IS NOT NULL AND bound_at IS NOT NULL))
);
CREATE INDEX IX_WaitingOperation_unresolved
    ON ops.WaitingOperation(operation_id) WHERE bound_at IS NULL;
INSERT cfg.MetadataMigration(migration_id,description)
VALUES('0005_waiting_operations','Deferred daily declarations and one-time immutable input binding');
END;
COMMIT;
