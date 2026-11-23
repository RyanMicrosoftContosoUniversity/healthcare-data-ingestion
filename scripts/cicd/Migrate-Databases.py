"""Reviewed source/control DDL using only the pipeline's federated deployment identity."""

import json
import re
import struct
import sys
from contextlib import closing
from pathlib import Path

from azure.identity import AzureCliCredential

from healthcare_ingestion.control_store import SqlServerControlStore
from healthcare_ingestion.metadata_migrations import apply_migrations
from healthcare_ingestion.sql_source_migrations import execute_source_migration_sql


def connection_factory(endpoint):
    import pyodbc

    if set(endpoint) != {"server", "database"}:
        raise ValueError("Only actual server/database bindings are permitted; no SQL passwords")
    if not re.fullmatch(r"[a-zA-Z0-9.-]+", endpoint["server"]) or not re.fullmatch(
        r"[a-zA-Z0-9_-]+", endpoint["database"]
    ):
        raise ValueError("Invalid SQL endpoint")
    if "ODBC Driver 18 for SQL Server" not in pyodbc.drivers():
        raise RuntimeError("The deployment agent requires ODBC Driver 18 for SQL Server")

    def connect():
        token = AzureCliCredential().get_token("https://database.windows.net/.default")
        encoded = token.token.encode("utf-16-le")
        return pyodbc.connect(
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER=tcp:{endpoint['server']},1433;DATABASE={endpoint['database']};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;",
            attrs_before={1256: struct.pack("<I", len(encoded)) + encoded},
            autocommit=False,
        )

    return connect


def main():
    endpoints = json.loads(Path(sys.argv[1]).read_text())
    if set(endpoints) != {"clarity", "caboodle", "metadata"}:
        raise ValueError(
            "Supply the two approved sources and dedicated Fabric SQL metadata endpoint"
        )
    receipt_path = Path(sys.argv[2])
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"state": "IN_PROGRESS", "sources": {}, "metadata_migrations": []}

    def persist():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    persist()
    try:
        for source in ("clarity", "caboodle"):
            factory = connection_factory(endpoints[source])
            contract = json.loads(
                (Path("database") / "schema-contracts" / f"{source}.json").read_text()
            )
            with closing(factory()) as connection:
                cursor = connection.cursor()
                present = []
                for table in contract["tables"]:
                    cursor.execute(
                        "SELECT OBJECT_ID(?, N'U');",
                        f"{contract['schema']}.{table['name']}",
                    )
                    present.append(cursor.fetchone()[0] is not None)
                cursor.close()
                connection.rollback()
                if any(present) and not all(present):
                    raise RuntimeError("Partial source baseline requires recovery, not blind DDL")
                if not any(present):
                    baselines = list((Path("database") / source / "schema").glob("*.sql"))
                    if len(baselines) != 1:
                        raise RuntimeError("Expected exactly one reviewed source baseline")
                    execute_source_migration_sql(connection, baselines[0].read_text())
                for migration in sorted((Path("database") / source / "migrations").glob("*.sql")):
                    execute_source_migration_sql(connection, migration.read_text())
            receipt["sources"][source] = "BASELINE_AND_UPGRADES_VERIFIED"
            persist()
        store = SqlServerControlStore(connection_factory(endpoints["metadata"]))
        receipt["metadata_migrations"] = list(
            apply_migrations(store, Path("database") / "metadata" / "migrations")
        )
        receipt["state"] = "MIGRATIONS_APPLIED_NOT_ACTIVATED"
    except BaseException:
        receipt["state"] = "FAILED_OR_INCOMPLETE_NOT_ACTIVATED"
        persist()
        raise
    persist()


if __name__ == "__main__":
    main()
