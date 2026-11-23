-- SQLite LOCAL reference only; migrations/0005_waiting_operations.sql is authoritative.
CREATE TABLE IF NOT EXISTS ops_WaitingOperation (
 operation_id TEXT PRIMARY KEY REFERENCES ops_TaskOperation(operation_id),
 declared_inputs_json TEXT NOT NULL
   CHECK(json_valid(declared_inputs_json) AND json_type(declared_inputs_json)='array'
     AND length(CAST(declared_inputs_json AS BLOB))<=65536),
 binding_hash TEXT, bound_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 CHECK((binding_hash IS NULL AND bound_at IS NULL)
   OR (binding_hash IS NOT NULL AND bound_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS IX_WaitingOperation_unresolved
 ON ops_WaitingOperation(operation_id) WHERE bound_at IS NULL;
