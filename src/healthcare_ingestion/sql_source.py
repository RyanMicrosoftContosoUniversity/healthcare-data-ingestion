"""Independent, serialized, transactionally checkpointed Azure SQL source loaders.

This module performs no deployment. SQL execution requires reviewed source migrations,
network access, ODBC Driver 18 and an approved managed identity. No password fallback.
"""

import re
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from healthcare_ingestion.source_ddl import _REFERENCE
from healthcare_ingestion.source_mapping import contract_digest, project_source, sql_timestamp
from healthcare_ingestion.sql_source_integrity import validate_source_rows
from healthcare_ingestion.synthetic_population import (
    PopulationStore,
    atomic_json,
    digest,
    file_lock,
    source_delta,
)

ATTEMPT_SECONDS = 45 * 60
SOURCE_APPLICATION_LOCK = "healthcare-ingestion-source"
NATIVE_PUBLICATION_SQL = "CONVERT(datetime2(7),SESSION_CONTEXT(N'source_publication_at'))"
TRANSIENT_STATES = {"08S01", "08001", "08003", "08007", "40001"}
TRANSIENT_CODES = {40197, 40501, 40613, 49918, 49919, 49920}


def acquire_source_read_lock(cursor, *, timeout_milliseconds: int = 0) -> None:
    """Hold a shared producer/extractor fence until the caller commits/rolls back.

    Invoke on the same non-autocommit connection used for live discovery, SQL extraction
    and source checkpoint capture. The exclusive loader lock cannot overlap this read.
    Do not use a separate connection or release the transaction before extraction ends.
    """
    if not isinstance(timeout_milliseconds, int) or not 0 <= timeout_milliseconds <= 2700000:
        raise ValueError("Source read-lock timeout must be bounded by the attempt budget.")
    cursor.execute("IF @@TRANCOUNT=0 BEGIN TRANSACTION;")
    cursor.execute(
        "DECLARE @result int; EXEC @result=sys.sp_getapplock "
        "@Resource=?, @LockMode='Shared', @LockOwner='Transaction', @LockTimeout=?; "
        "SELECT @result;",
        SOURCE_APPLICATION_LOCK,
        timeout_milliseconds,
    )
    if cursor.fetchone()[0] < 0:
        raise RuntimeError("Source mutation/extraction fence is unavailable.")


def source_checkpoint_evidence(cursor, source: str, batch: str | None = None) -> dict | None:
    """Read committed-batch evidence while holding the same extraction transaction."""
    if source not in {"Clarity", "Caboodle"}:
        raise ValueError("Unknown source checkpoint identity.")
    table = "SyntheticSourceBatchCommit" if batch is not None else "SyntheticSourceCheckpoint"
    sql = (
        "SELECT BatchName, PopulationDigest, MappingDigest, ContractDigest, RowCount, "
        "CONVERT(varchar(33), CommittedAtUtc,126), "
        "CONVERT(varchar(33), CoverageStartUtc,126), CONVERT(varchar(33), CoverageEndUtc,126) "
        f"FROM dbo.{table} WHERE SourceSystem=?"
    )
    cursor.execute(
        sql + (" AND BatchName=?;" if batch is not None else ";"),
        *([source, batch] if batch is not None else [source]),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    evidence = dict(
        zip(
            (
                "batch",
                "population_digest",
                "mapping_digest",
                "contract_digest",
                "row_count",
                "committed_at",
                "coverage_start",
                "coverage_end",
            ),
            row,
            strict=True,
        )
    )
    for field in ("committed_at", "coverage_start", "coverage_end"):
        if evidence[field] is None:
            raise ValueError("Committed source coverage/publication evidence is incomplete.")
        evidence[field] = sql_timestamp(evidence[field])
    if evidence["coverage_start"] > evidence["coverage_end"]:
        raise ValueError("Committed source coverage is reversed.")
    return evidence


@dataclass(frozen=True)
class SqlSourceConnection:
    server: str
    database: str
    managed_identity_client_id: str | None = None

    def connect(self):
        if not re.fullmatch(r"[A-Za-z0-9.-]+\.database\.windows\.net", self.server):
            raise ValueError("An explicit approved Azure SQL server hostname is required.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.database):
            raise ValueError("Invalid source database name.")
        try:
            import pyodbc

            # Each attempt must own a fresh session, including its read-only publication clock.
            pyodbc.pooling = False
            from azure.identity import ManagedIdentityCredential
        except ImportError:
            raise RuntimeError(
                "SQL loading requires the optional cloud extra (azure-identity, pyodbc)."
            ) from None
        credential = ManagedIdentityCredential(client_id=self.managed_identity_client_id)
        try:
            token = credential.get_token("https://database.windows.net/.default").token.encode(
                "utf-16-le"
            )
        finally:
            credential.close()
        packed = struct.pack(f"<I{len(token)}s", len(token), token)
        return pyodbc.connect(
            f"Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{self.server},1433;"
            f"Database={self.database};Encrypt=yes;TrustServerCertificate=no;",
            attrs_before={1256: packed},
            autocommit=False,
            timeout=30,
        )


def dependency_order(contract: dict) -> list[dict]:
    tables = {t["name"]: t for t in contract["tables"]}
    pending = {}
    for name, table in tables.items():
        pending[name] = {
            ref[1]
            for c in table["columns"]
            if (ref := _REFERENCE.match(c["purpose"])) is not None and ref[1] != name
        }
    ordered = []
    while pending:
        ready = sorted(name for name, parents in pending.items() if not parents)
        if not ready:
            raise ValueError("Source dependency graph contains a cycle.")
        for name in ready:
            ordered.append(tables[name])
            del pending[name]
        for parents in pending.values():
            parents.difference_update(ready)
    return ordered


def upsert_statement(table: dict, schema: str = "dbo") -> tuple[str, list[str]]:
    """Identifiers only come from the validated approved contract; values are parameters."""
    keys = table["primary_key"]
    columns = [c["name"] for c in table["columns"]]
    if any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name)
        for name in [schema, table["name"], *columns, *keys]
    ):
        raise ValueError("SQL identifiers must come from a validated source contract.")
    publication = {"CreatedAtUtc", "ModifiedAtUtc", "EtlCreatedAtUtc", "EtlModifiedAtUtc"}
    mutable = [
        name
        for name in columns
        if name not in keys and name not in {"CreatedAtUtc", "EtlCreatedAtUtc"}
    ]
    qualified = f"[{schema}].[{table['name']}]"
    assignments = ", ".join(
        f"[{name}]=" + (NATIVE_PUBLICATION_SQL if name in publication else "?") for name in mutable
    )
    where = " AND ".join(f"[{name}]=?" for name in keys)
    insert_values = ", ".join(
        NATIVE_PUBLICATION_SQL if name in publication else "?" for name in columns
    )
    statement = (
        f"UPDATE {qualified} WITH (UPDLOCK, SERIALIZABLE) SET {assignments} WHERE {where}; "
        f"IF @@ROWCOUNT=0 INSERT INTO {qualified} "
        f"({', '.join('[' + name + ']' for name in columns)}) "
        f"VALUES ({insert_values});"
    )
    return statement, (
        [name for name in mutable if name not in publication]
        + keys
        + [name for name in columns if name not in publication]
    )


class PyodbcSourceAdapter:
    """One fresh connection per attempt; the DB checkpoint is the commit authority."""

    def __init__(self, connection: SqlSourceConnection):
        self.configuration = connection
        self.connection = None
        self.cursor = None
        self._cursor_timeout = None
        self.deadline = None

    def begin(self, source: str, batch_id: str, timeout_seconds: int):
        self.deadline = time.monotonic() + timeout_seconds
        self.connection = self.configuration.connect()
        self._budget()
        self.cursor.execute(
            "SET XACT_ABORT ON; SET NOCOUNT ON; IF @@TRANCOUNT=0 BEGIN TRANSACTION;"
        )
        self.cursor.execute(
            "DECLARE @result int; EXEC @result=sys.sp_getapplock "
            "@Resource=?, @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=0; "
            "SELECT @result;",
            SOURCE_APPLICATION_LOCK,
        )
        if self.cursor.fetchone()[0] < 0:
            raise RuntimeError("Another source loader holds the exclusive database write lock.")
        self.cursor.execute(
            "EXEC sys.sp_set_session_context @key=N'source_batch_id', @value=?;", batch_id
        )
        self._budget()
        self.cursor.execute("EXEC dbo.PrepareSyntheticSourcePublication;")
        self.cursor.execute(
            "SELECT SourceSystem FROM dbo.SyntheticSourceCheckpoint WHERE SourceSystem<>?;", source
        )
        if self.cursor.fetchone() is not None:
            raise RuntimeError("A source database cannot host checkpoints for another source.")

    def checkpoint(self, source: str):
        self._budget()
        return source_checkpoint_evidence(self.cursor, source)

    def batch_commit(self, source: str, batch: str):
        self._budget()
        return source_checkpoint_evidence(self.cursor, source, batch=batch)

    def assert_empty_source(self, contract: dict):
        self._budget()
        self.cursor.execute(
            "IF EXISTS(SELECT 1 FROM dbo.SyntheticSourceBatchCommit) "
            "THROW 51006,'Source commit history requires checkpoint reconciliation.',1;"
        )
        for table in contract["tables"]:
            self._budget()
            self.cursor.execute(
                f"IF EXISTS(SELECT 1 FROM [{contract['schema']}].[{table['name']}]) "
                "THROW 51006,'Nonempty source without committed checkpoint cannot be seeded.',1;"
            )

    def write(self, table: dict, rows: list[dict], schema: str):
        sql, fields = upsert_statement(table, schema)
        # Expire old Type 2 versions before inserting the new current version.
        if "IsCurrent" in fields:
            rows = sorted(rows, key=lambda r: (r["IsCurrent"], r["EffectiveFromUtc"]))
        for row in rows:
            self._budget()
            self.cursor.execute(sql, *[row[field] for field in fields])

    def commit_checkpoint(self, source: str, evidence: dict):
        self._budget()
        self.cursor.execute("EXEC dbo.ValidateSyntheticSource;")
        self._budget()
        self.cursor.execute(
            f"DECLARE @publication datetime2(7)={NATIVE_PUBLICATION_SQL}; "
            "INSERT dbo.SyntheticSourceBatchCommit "
            "(SourceSystem,BatchName,PopulationDigest,MappingDigest,ContractDigest,RowCount,"
            "CommittedAtUtc,CoverageStartUtc,CoverageEndUtc) "
            "VALUES (?,?,?,?,?,?,@publication,?,?); "
            "UPDATE dbo.SyntheticSourceCheckpoint SET BatchName=?, PopulationDigest=?, "
            "MappingDigest=?, ContractDigest=?, RowCount=?, CommittedAtUtc=@publication, "
            "CoverageStartUtc=?, CoverageEndUtc=? "
            "WHERE SourceSystem=?; "
            "IF @@ROWCOUNT=0 INSERT dbo.SyntheticSourceCheckpoint "
            "(SourceSystem,BatchName,PopulationDigest,MappingDigest,ContractDigest,RowCount,"
            "CommittedAtUtc,CoverageStartUtc,CoverageEndUtc) "
            "VALUES (?,?,?,?,?,?,@publication,?,?);",
            source,
            evidence["batch"],
            evidence["population_digest"],
            evidence["mapping_digest"],
            evidence["contract_digest"],
            evidence["row_count"],
            evidence["coverage_start"],
            evidence["coverage_end"],
            evidence["batch"],
            evidence["population_digest"],
            evidence["mapping_digest"],
            evidence["contract_digest"],
            evidence["row_count"],
            evidence["coverage_start"],
            evidence["coverage_end"],
            source,
            source,
            evidence["batch"],
            evidence["population_digest"],
            evidence["mapping_digest"],
            evidence["contract_digest"],
            evidence["row_count"],
            evidence["coverage_start"],
            evidence["coverage_end"],
        )
        self._budget()
        self.connection.commit()
        # Read only after the actual commit. If this read fails, next attempt recovers by
        # authoritative checkpoint; the local mirror is never used to assert a SQL commit.
        return self.batch_commit(source, evidence["batch"])

    def rollback(self):
        if self.connection is not None:
            self.connection.rollback()

    def close(self):
        if self.connection is not None:
            self.connection.close()
        self.cursor, self.connection = None, None
        self._cursor_timeout = None

    def _budget(self):
        remaining = int(self.deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Source load exceeded its 45-minute attempt budget.")
        # pyodbc exposes query timeout on Connection, inherited by newly created cursors.
        if self.cursor is None or self._cursor_timeout != remaining:
            self.connection.timeout = remaining
            if self.cursor is not None:
                self.cursor.close()
            self.cursor = self.connection.cursor()
            self._cursor_timeout = remaining


def is_transient(error: Exception) -> bool:
    # Classification inspects errors but never emits messages that may contain source data.
    arguments = getattr(error, "args", ())
    state = str(arguments[0]) if arguments else ""
    codes = {int(v) for v in re.findall(r"\((\d+)\)", " ".join(map(str, arguments)))}
    return state in TRANSIENT_STATES or bool(codes & TRANSIENT_CODES)


def load_source(
    *,
    store: PopulationStore,
    batch: str,
    contract: dict,
    mapping: dict,
    adapter,
    checkpoint_directory: Path,
    retry_delay_seconds: int = 5,
) -> dict:
    """Load exactly one source; reruns/recovery rely on committed SQL evidence.

    The complete current/previous projections are validated offline. SQL writes and the
    authoritative source checkpoint commit atomically. A post-commit crash is recovered
    without row rewrites; Clarity and Caboodle advance independently.
    """
    document = store.read_batch(batch)
    source = contract["source_system"]
    coverage = document["population"].get("coverage")
    if not coverage:
        raise ValueError("Verified generation coverage metadata is required; no clock fallback.")
    coverage_start, coverage_end = (sql_timestamp(coverage[field]) for field in ("start", "end"))
    if coverage_start > coverage_end:
        raise ValueError("Generation coverage is reversed.")
    current = project_source(document["population"], contract, mapping)
    validate_source_rows(current, contract)
    expected = {
        "batch": batch,
        "population_digest": document["digest"],
        "mapping_digest": digest(mapping),
        "contract_digest": contract_digest(contract),
        "coverage_end": coverage_end,
    }
    directory = Path(checkpoint_directory)
    with file_lock(directory / "source-loaders.lock"):
        for attempt in range(2):
            try:
                adapter.begin(
                    source, document["population"]["publication"]["batch_id"], ATTEMPT_SECONDS
                )
                committed = adapter.checkpoint(source)
                if committed:
                    head_commit = adapter.batch_commit(source, committed["batch"])
                    if head_commit != committed:
                        raise ValueError(
                            "Source checkpoint/ledger mismatch requires a corrective migration."
                        )
                prior_commit = adapter.batch_commit(source, batch)
                if prior_commit:
                    predecessor_commit = (
                        adapter.batch_commit(source, document["predecessor"])
                        if document["predecessor"]
                        else None
                    )
                    expected["coverage_start"] = (
                        predecessor_commit["coverage_end"] if predecessor_commit else coverage_start
                    )
                    if any(prior_commit.get(key) != value for key, value in expected.items()):
                        raise ValueError("Committed source batch conflicts with requested inputs.")
                    if committed is None:
                        raise RuntimeError(
                            "Immutable commit exists without a source checkpoint head."
                        )
                    adapter.rollback()
                    atomic_json(directory / f"{source.lower()}.json", committed)
                    return {**prior_commit, "recovered": True}
                if committed and committed["batch"] == batch:
                    raise RuntimeError(
                        "Source checkpoint lacks immutable committed-batch evidence."
                    )
                if committed:
                    if not coverage_start <= committed["coverage_end"] <= coverage_end:
                        raise ValueError("Source coverage regresses or breaks cohort continuity.")
                    expected["coverage_start"] = committed["coverage_end"]
                    if committed["batch"] != document["predecessor"]:
                        raise ValueError(
                            "Source checkpoint predecessor is stale or a batch was skipped."
                        )
                    if committed["mapping_digest"] != expected["mapping_digest"] or (
                        committed["contract_digest"] != expected["contract_digest"]
                    ):
                        raise ValueError(
                            "Mapping/contract changes require a reviewed migration/rebase."
                        )
                    old_document = store.read_batch(committed["batch"])
                    if old_document["digest"] != committed["population_digest"]:
                        raise ValueError("Previous committed population evidence was altered.")
                    previous = project_source(old_document["population"], contract, mapping)
                else:
                    expected["coverage_start"] = coverage_start
                    # A newly initialized independent source may seed the complete latest
                    # population, including its retained dimension history.
                    adapter.assert_empty_source(contract)
                    previous = None
                delta = source_delta(current, previous, contract)
                for table in dependency_order(contract):
                    adapter.write(table, delta[table["name"]], contract["schema"])
                evidence = {**expected, "row_count": sum(map(len, delta.values()))}
                committed = adapter.commit_checkpoint(source, evidence)
                if (
                    committed is None
                    or any(committed.get(key) != value for key, value in evidence.items())
                    or not committed.get("committed_at")
                ):
                    raise RuntimeError(
                        "SQL committed checkpoint evidence is unavailable or inconsistent."
                    )
                atomic_json(directory / f"{source.lower()}.json", committed)
                return {**committed, "recovered": False}
            except Exception as error:
                try:
                    adapter.rollback()
                except Exception:
                    pass  # Never replace the original narrowly scoped failure.
                if attempt == 1 or not is_transient(error):
                    raise
                time.sleep(retry_delay_seconds)
            finally:
                adapter.close()
    raise RuntimeError("Source load exhausted its single transient retry.")
