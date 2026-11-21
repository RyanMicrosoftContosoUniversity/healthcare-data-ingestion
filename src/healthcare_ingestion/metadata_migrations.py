"""Reviewed forward-only migration execution against the Fabric SQL transactional adapter."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from healthcare_ingestion.control_store import ControlError, SqlServerControlStore


@dataclass(frozen=True)
class MetadataMigration:
    migration_id: str
    sql: str
    script_hash: str


def load_migrations(directory: str | Path) -> tuple[MetadataMigration, ...]:
    migrations = []
    for index, path in enumerate(sorted(Path(directory).glob("*.sql")), start=1):
        if not path.stem.startswith(f"{index:04d}_"):
            raise ControlError("Metadata migrations must have a contiguous ordered version prefix")
        sql = path.read_text(encoding="utf-8")
        code = re.sub(r"--[^\n]*", "", sql)
        if re.search(r"\b(DROP|TRUNCATE|DELETE)\b", code, re.IGNORECASE):
            raise ControlError("Destructive metadata migrations are not approved")
        if not all(
            re.search(pattern, code, re.IGNORECASE)
            for pattern in (r"SET\s+XACT_ABORT\s+ON", r"BEGIN\s+TRANSACTION", r"\bCOMMIT\b")
        ):
            raise ControlError("Migration requires fail-closed explicit transactional boundaries")
        if re.search(r"^\s*GO\s*$", code, re.MULTILINE | re.IGNORECASE):
            raise ControlError("DB-API migrations must not contain client-only GO separators")
        migrations.append(
            MetadataMigration(path.stem, sql, hashlib.sha256(sql.encode()).hexdigest())
        )
    if not migrations:
        raise ControlError("No reviewed metadata migration scripts were supplied")
    return tuple(migrations)


def apply_migrations(
    store: SqlServerControlStore,
    directory: str | Path,
) -> tuple[str, ...]:
    """Explicit deployment operation, not called by runner construction or task start.

    Apply to the existing dedicated metadata database only, after review of this exact
    SQL/permissions/deployment. Never provision a third migration-test database.
    """
    if not isinstance(store, SqlServerControlStore):
        raise ControlError("Authoritative migrations require the Fabric SQL transactional adapter")
    applied = []
    for migration in load_migrations(directory):
        with store.transaction() as tx:
            exists = tx.one("SELECT OBJECT_ID(N'cfg.MetadataMigration',N'U') AS object_id")
            previous = None
            if exists["object_id"]:
                previous = tx.one(
                    "SELECT script_hash FROM cfg.MetadataMigration WHERE migration_id=?",
                    (migration.migration_id,),
                )
            if previous and previous["script_hash"]:
                if previous["script_hash"] != migration.script_hash:
                    raise ControlError(
                        "Applied migration was edited; create a corrective new version"
                    )
                continue
            tx.execute(migration.sql)
            tx.execute(
                "UPDATE cfg.MetadataMigration SET script_hash=? WHERE migration_id=?",
                (migration.script_hash, migration.migration_id),
            )
            if migration.migration_id != "0001_configuration":
                store._audit(
                    tx,
                    "metadata_migration_applied",
                    migration.migration_id,
                    {"script_hash": migration.script_hash},
                )
            applied.append(migration.migration_id)
    return tuple(applied)
