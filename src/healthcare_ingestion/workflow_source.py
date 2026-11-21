"""One live catalog pass protected by the same source transaction for a workflow."""

from healthcare_ingestion.discovery import discover

SOURCE_LOCK = (
    "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; IF @@TRANCOUNT=0 BEGIN TRANSACTION; "
    "DECLARE @r int; EXEC @r=sys.sp_getapplock "
    "@Resource=N'healthcare-ingestion-source',@LockMode=N'Shared',"
    "@LockOwner=N'Transaction',@DbPrincipal=N'public',@LockTimeout=30000; "
    "IF @r<0 THROW 51000,'Source workflow fence unavailable',1;"
)


class WorkflowSource:
    def __init__(self, connection, contract, tables):
        self.connection, self.contract = connection, contract
        self.tables = set(tables)
        self.valid = False
        self.workflow_discovery_results = {}

    @property
    def autocommit(self):
        return self.connection.autocommit

    def __enter__(self):
        if self.autocommit:
            raise ValueError("Workflow source discovery requires a transaction.")
        cursor = self.connection.cursor()
        try:
            cursor.execute(SOURCE_LOCK)
            selected = {
                **self.contract,
                "tables": [
                    table for table in self.contract["tables"] if table["name"] in self.tables
                ],
            }
            if len(selected["tables"]) != len(self.tables):
                raise ValueError("Workflow selects an unapproved source table.")
            results = discover(self.connection, selected)
            self.workflow_discovery_results = {result.table: result for result in results}
            self.valid = True
            return self
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def cursor(self):
        if not self.valid:
            raise ValueError("Shared discovery source transaction is no longer available.")
        return self.connection.cursor()

    def assert_transaction(self):
        cursor = self.cursor()
        try:
            cursor.execute("SELECT XACT_STATE(),@@TRANCOUNT")
            state, count = cursor.fetchone()
            if state != 1 or count < 1:
                self.valid = False
                raise ValueError("Shared source discovery lost its transaction fence.")
        finally:
            cursor.close()

    def commit(self):
        self.assert_transaction()

    def rollback(self):
        try:
            self.assert_transaction()
        except Exception:
            self.valid = False
            self.connection.rollback()

    def close(self):
        pass

    def __exit__(self, *_):
        self.valid = False
        try:
            self.connection.rollback()
        finally:
            self.connection.close()
