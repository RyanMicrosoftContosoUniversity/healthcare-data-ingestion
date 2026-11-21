import copy
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from healthcare_ingestion.generator import _inputs
from healthcare_ingestion.source_mapping import project_source
from healthcare_ingestion.sql_source import (
    SOURCE_APPLICATION_LOCK,
    PyodbcSourceAdapter,
    SqlSourceConnection,
    acquire_source_read_lock,
    dependency_order,
    load_source,
    source_checkpoint_evidence,
    upsert_statement,
)
from healthcare_ingestion.sql_source_migrations import render_source_migration
from healthcare_ingestion.synthetic_population import (
    PopulationStore,
    change_population,
    local_demo_population,
)

ROOT = Path(__file__).resolve().parents[2]
START, AT = "2025-11-01T00:00:00Z", "2026-11-01T23:59:59Z"


@pytest.fixture
def workspace():
    path = ROOT / (".source-test-state-" + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


class TransactionalAdapter:
    """Transaction double: only commit persists rows/checkpoints across attempts."""

    def __init__(self, failure=None):
        self.database, self.committed = {}, None
        self.ledger = {}
        self.attempt_rows = None
        self.write_calls, self.begin_calls, self.commits = [], 0, 0
        self.failure = failure

    def begin(self, source, batch_id, timeout_seconds):
        self.begin_calls += 1
        assert timeout_seconds == 2700
        self.attempt_rows = copy.deepcopy(self.database)

    def checkpoint(self, source):
        return copy.deepcopy(self.committed)

    def batch_commit(self, source, batch):
        return copy.deepcopy(self.ledger.get(batch))

    def assert_empty_source(self, contract):
        if self.database or self.ledger:
            raise RuntimeError("Nonempty source without checkpoint cannot be seeded.")

    def write(self, table, rows, schema):
        self.write_calls.append((table["name"], len(rows)))
        for row in rows:
            key = tuple(row[k] for k in table["primary_key"])
            self.attempt_rows.setdefault(table["name"], {})[key] = copy.deepcopy(row)
        if self.failure == "before-commit":
            self.failure = None
            raise RuntimeError("08S01", "simulated transient connection failure")

    def commit_checkpoint(self, source, evidence):
        self.database = self.attempt_rows
        self.committed = {**evidence, "committed_at": "2026-11-02T12:00:00.1234567"}
        self.ledger[evidence["batch"]] = copy.deepcopy(self.committed)
        self.commits += 1
        if self.failure == "after-commit":
            self.failure = None
            raise RuntimeError("08S01", "simulated committed acknowledgement failure")
        return self.checkpoint(source)

    def rollback(self):
        self.attempt_rows = None

    def close(self):
        pass


def load(store, batch, source, adapter, workspace):
    contract, mapping = _inputs(ROOT, source)
    return load_source(
        store=store,
        batch=batch,
        contract=contract,
        mapping=mapping,
        adapter=adapter,
        checkpoint_directory=workspace / "source-checkpoints",
        retry_delay_seconds=0,
    )


def test_independent_loaders_idempotent_rerun_and_zero_checkpoint(workspace):
    population = local_demo_population(patients=12, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    store.publish("baseline", population)
    clarity, caboodle = TransactionalAdapter(), TransactionalAdapter()
    first = load(store, "baseline", "Clarity", clarity, workspace)
    assert caboodle.committed is None
    writes = len(clarity.write_calls)
    assert load(store, "baseline", "Clarity", clarity, workspace)["recovered"]
    assert len(clarity.write_calls) == writes
    load(store, "baseline", "Caboodle", caboodle, workspace)
    assert len(clarity.database) == 13 and len(caboodle.database) == 15
    zero = change_population(population, batch="zero", at="2026-11-02T12:00:00Z", profile="zero")
    store.publish("zero", zero, "baseline")
    evidence = load(store, "zero", "Clarity", clarity, workspace)
    assert evidence["row_count"] == 0
    assert evidence["batch"] == "zero" and caboodle.committed["batch"] == "baseline"
    assert evidence["population_digest"] != first["population_digest"]
    writes = len(clarity.write_calls)
    prior = load(store, "baseline", "Clarity", clarity, workspace)
    assert prior["batch"] == "baseline" and prior["recovered"]
    assert clarity.committed["batch"] == "zero"
    assert len(clarity.write_calls) == writes
    assert (
        json.loads((workspace / "source-checkpoints" / "clarity.json").read_text())["batch"]
        == "zero"
    )
    assert json.loads((workspace / "source-checkpoints" / "clarity.json").read_text())[
        "committed_at"
    ].endswith("1234567")


@pytest.mark.parametrize("failure", ["before-commit", "after-commit"])
def test_transient_retry_rolls_back_or_recovers_actual_commit(workspace, failure):
    population = local_demo_population(patients=2, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    store.publish("baseline", population)
    adapter = TransactionalAdapter(failure)
    evidence = load(store, "baseline", "Clarity", adapter, workspace)
    assert adapter.begin_calls == 2
    assert adapter.commits == 1
    assert evidence["recovered"] == (failure == "after-commit")
    assert len(adapter.database["Patient"]) == 2


def test_stale_source_batch_and_changed_mapping_do_not_write(workspace):
    population = local_demo_population(patients=2, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    store.publish("baseline", population)
    adapter = TransactionalAdapter()
    load(store, "baseline", "Clarity", adapter, workspace)
    day1 = change_population(population, batch="day1", at="2026-11-02T12:00:00Z", profile="zero")
    store.publish("day1", day1, "baseline")
    day2 = change_population(day1, batch="day2", at="2026-11-03T12:00:00Z", profile="zero")
    store.publish("day2", day2, "day1")
    calls = len(adapter.write_calls)
    with pytest.raises(ValueError, match="skipped"):
        load(store, "day2", "Clarity", adapter, workspace)
    assert len(adapter.write_calls) == calls
    adapter.committed["mapping_digest"] = "changed"
    with pytest.raises(ValueError, match="migration"):
        load(store, "day1", "Clarity", adapter, workspace)
    assert len(adapter.write_calls) == calls


@pytest.mark.parametrize("transient,attempts", [(False, 1), (True, 2)])
def test_failed_source_attempts_never_publish_a_checkpoint_or_block_other_source(
    workspace, transient, attempts
):
    class FailingAdapter(TransactionalAdapter):
        def write(self, table, rows, schema):
            super().write(table, rows, schema)
            raise RuntimeError("08S01" if transient else "invalid-source-state")

    population = local_demo_population(patients=2, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    store.publish("baseline", population)
    adapter = FailingAdapter()
    with pytest.raises(RuntimeError):
        load(store, "baseline", "Clarity", adapter, workspace)
    assert adapter.begin_calls == attempts
    assert adapter.database == {} and adapter.committed is None
    assert not (workspace / "source-checkpoints" / "clarity.json").exists()
    independent = TransactionalAdapter()
    assert load(store, "baseline", "Caboodle", independent, workspace)["row_count"] > 0


def test_incremental_corrections_soft_deletes_and_dimension_expiration_are_loaded(workspace):
    population = local_demo_population(patients=12, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    store.publish("baseline", population)
    adapter = TransactionalAdapter()
    load(store, "baseline", "Caboodle", adapter, workspace)
    old_keys = set(adapter.database["FactLabResult"])
    changed = change_population(population, batch="day1", at="2026-11-02T12:00:00Z")
    store.publish("day1", changed, "baseline")
    load(store, "day1", "Caboodle", adapter, workspace)
    assert old_keys <= adapter.database["FactLabResult"].keys()
    assert (
        sum(r["ResultStatus"] == "corrected" for r in adapter.database["FactLabResult"].values())
        == 4
    )
    assert sum(r["IsDeleted"] for r in adapter.database["FactLabResult"].values()) == 2
    assert sum(not r["IsCurrent"] for r in adapter.database["DimPatient"].values()) == 10


def test_every_upsert_is_parameterized_and_orders_dependencies():
    for source in ("Clarity", "Caboodle"):
        contract, _ = _inputs(ROOT, source)
        order = dependency_order(contract)
        seen = []
        for table in order:
            sql, fields = upsert_statement(table)
            assert sql.count("?") == len(fields)
            assert "SESSION_CONTEXT(N'source_publication_at')" in sql
            assert "CreatedAtUtc" not in fields and "EtlCreatedAtUtc" not in fields
            assert "'Synthetic'" not in sql
            seen.append(table["name"])
        if source == "Clarity":
            assert seen.index("Coverage") < seen.index("Encounter") < seen.index("Diagnosis")
            assert seen.index("LaboratoryOrder") < seen.index("LaboratoryResult")
        else:
            assert seen.index("DimDate") < seen.index("FactEncounter")
            assert seen.index("DimMedication") < seen.index("FactMedicationAdministration")
    contract, _ = _inputs(ROOT, "Clarity")
    with pytest.raises(ValueError, match="identifiers"):
        upsert_statement(contract["tables"][0], schema="dbo];DROP TABLE Patient;--")


def test_sql_adapter_commits_before_readback_and_validates_before_checkpoint():
    class Cursor:
        __slots__ = ("sql",)

        def close(self):
            pass

        def execute(self, sql, *parameters):
            events.append(("execute", sql, parameters))
            self.sql = sql
            return self

        def fetchone(self):
            if "SELECT @result" in self.sql:
                return (0,)
            if "SourceSystem<>" in self.sql:
                return None
            if connection.committed:
                return (
                    "baseline",
                    "p" * 64,
                    "m" * 64,
                    "c" * 64,
                    1,
                    "2026-11-02T12:00:00.1234567",
                    "2025-11-01T00:00:00.0000000",
                    "2026-11-01T23:59:59.0000000",
                )
            return None

    class Connection:
        committed = False

        def cursor(self):
            return Cursor()

        def commit(self):
            events.append(("commit",))
            self.committed = True

        def rollback(self):
            events.append(("rollback",))

        def close(self):
            pass

    class Configuration:
        def connect(self):
            return connection

    events, connection = [], Connection()
    adapter = PyodbcSourceAdapter(Configuration())
    adapter.begin("Clarity", "0b3ab8b6-696c-4c92-9072-d5931a65e763", 2700)
    assert adapter.checkpoint("Clarity") is None
    evidence = adapter.commit_checkpoint(
        "Clarity",
        {
            "batch": "baseline",
            "population_digest": "p" * 64,
            "mapping_digest": "m" * 64,
            "contract_digest": "c" * 64,
            "row_count": 1,
            "coverage_start": "2025-11-01T00:00:00.0000000",
            "coverage_end": "2026-11-01T23:59:59.0000000",
        },
    )
    assert evidence["committed_at"].endswith(".1234567")
    integrity = next(
        i
        for i, event in enumerate(events)
        if len(event) > 1 and "ValidateSyntheticSource" in event[1]
    )
    checkpoint = next(
        i
        for i, event in enumerate(events)
        if len(event) > 1 and "UPDATE dbo.SyntheticSourceCheckpoint" in event[1]
    )
    commit = next(i for i, event in enumerate(events) if event[0] == "commit")
    assert integrity < checkpoint < commit < len(events) - 1
    assert "LockOwner='Transaction'" in events[1][1]
    assert all("baseline" not in event[1] for event in events if event[0] == "execute")


def test_connection_strings_reject_password_or_identifier_injection():
    with pytest.raises(ValueError):
        SqlSourceConnection("server.database.windows.net;Pwd=secret", "source").connect()
    with pytest.raises(ValueError):
        SqlSourceConnection("server.database.windows.net", "source;UID=bad").connect()


def test_read_and_write_fences_share_resource_and_transaction_checkpoint_capture():
    class Cursor:
        def execute(self, sql, *parameters):
            calls.append((sql, parameters))
            self.sql = sql

        def fetchone(self):
            if "SELECT @result" in self.sql:
                return (0,)
            return (
                "baseline",
                "p" * 64,
                "m" * 64,
                "c" * 64,
                1,
                "2026-11-02T12:00:00.1234567",
                "2025-11-01T00:00:00.0000000",
                "2026-11-01T23:59:59.0000000",
            )

    calls, cursor = [], Cursor()
    acquire_source_read_lock(cursor)
    evidence = source_checkpoint_evidence(cursor, "Clarity")
    ledger = source_checkpoint_evidence(cursor, "Clarity", "baseline")
    assert evidence == ledger
    assert set(evidence) == {
        "batch",
        "population_digest",
        "mapping_digest",
        "contract_digest",
        "row_count",
        "committed_at",
        "coverage_start",
        "coverage_end",
    }
    assert calls[1][1] == (SOURCE_APPLICATION_LOCK, 0)
    assert "LockMode='Shared'" in calls[1][0] and "LockOwner='Transaction'" in calls[1][0]
    assert evidence["committed_at"].endswith(".1234567")
    assert all("COMMIT" not in sql and "sp_releaseapplock" not in sql for sql, _ in calls)

    class FailedCursor(Cursor):
        def fetchone(self):
            return (-1,)

    with pytest.raises(RuntimeError, match="fence"):
        acquire_source_read_lock(FailedCursor())


def test_odbc_budget_refreshes_connection_timeout_on_a_new_cursor(monkeypatch):
    from types import SimpleNamespace

    import healthcare_ingestion.sql_source as module

    clock = [0]

    class Cursor:
        __slots__ = ("sql", "closed", "query_timeout")

        def __init__(self, query_timeout):
            self.closed, self.query_timeout = False, query_timeout

        def close(self):
            self.closed = True

        def execute(self, sql, *args):
            self.sql = sql

        def fetchone(self):
            return (0,) if "SELECT @result" in self.sql else None

    class Connection:
        timeout = 0

        def cursor(self):
            return Cursor(self.timeout)

    connection = Connection()
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    adapter = PyodbcSourceAdapter(SimpleNamespace(connect=lambda: connection))
    adapter.begin("Clarity", "batch-id", 30)
    first = adapter.cursor
    clock[0] = 10.1
    adapter._budget()
    assert first.closed and adapter.cursor is not first
    assert connection.timeout == adapter.cursor.query_timeout == 19


@pytest.mark.parametrize("source", ["Clarity", "Caboodle"])
def test_native_audits_capture_same_at_corrections_and_zero_keeps_rows_unchanged(source):
    """Driver double executes the native clock/parameter paths of the real SQL adapter."""
    from healthcare_ingestion.sql_source import NATIVE_PUBLICATION_SQL

    contract, mapping = _inputs(ROOT, source)
    name = "Patient" if source == "Clarity" else "DimPatient"
    audit = "ModifiedAtUtc" if source == "Clarity" else "EtlModifiedAtUtc"
    creation = "CreatedAtUtc" if source == "Clarity" else "EtlCreatedAtUtc"
    table = next(t for t in contract["tables"] if t["name"] == name)
    statement, fields = upsert_statement(table)
    # An existing different table can have a higher audit than wall-clock/checkpoint.
    state = {"rows": {}, "head": None, "ledger": {}, "other_audit": "2026-11-21T12:00:00.1234600"}
    clock = "2026-11-21T12:00:00.1234567"

    def tick(value):
        base, fraction = value.split(".")
        return base + "." + f"{int(fraction) + 1:07d}"

    class Cursor:
        def __init__(self, connection):
            self.connection, self.result = connection, None

        def close(self):
            pass

        def execute(self, sql, *parameters):
            self.result = None
            if "SELECT @result" in sql:
                self.result = (0,)
            elif sql == "EXEC dbo.PrepareSyntheticSourcePublication;":
                upper = max(
                    [
                        state["other_audit"],
                        *[row[audit] for row in state["rows"].values()],
                        *([state["head"]["committed_at"]] if state["head"] else []),
                    ]
                )
                self.connection.publication = clock if clock > upper else tick(upper)
            elif sql == statement:
                values = dict(zip(fields, parameters, strict=True))
                key = tuple(values[k] for k in table["primary_key"])
                stamp = self.connection.publication if NATIVE_PUBLICATION_SQL in sql else clock
                prior = self.connection.rows.get(key)
                values[creation] = prior[creation] if prior else stamp
                values[audit] = stamp
                self.connection.rows[key] = values
            elif "INSERT dbo.SyntheticSourceBatchCommit" in sql:
                self.connection.pending = dict(
                    zip(
                        (
                            "batch",
                            "population_digest",
                            "mapping_digest",
                            "contract_digest",
                            "row_count",
                            "coverage_start",
                            "coverage_end",
                        ),
                        parameters[1:8],
                        strict=True,
                    )
                )
                self.connection.pending["committed_at"] = self.connection.publication
            elif "SELECT BatchName" in sql:
                evidence = (
                    state["ledger"].get(parameters[1])
                    if "AND BatchName=?" in sql
                    else state["head"]
                )
                if evidence:
                    self.result = tuple(
                        evidence[k]
                        for k in (
                            "batch",
                            "population_digest",
                            "mapping_digest",
                            "contract_digest",
                            "row_count",
                            "committed_at",
                            "coverage_start",
                            "coverage_end",
                        )
                    )

        def fetchone(self):
            return self.result

    class Connection:
        def __init__(self):
            self.rows, self.pending = copy.deepcopy(state["rows"]), None
            self.publication = clock

        def cursor(self):
            return Cursor(self)

        def commit(self):
            state["rows"] = self.rows
            state["head"] = copy.deepcopy(self.pending)
            state["ledger"][self.pending["batch"]] = copy.deepcopy(self.pending)

        def rollback(self):
            pass

        def close(self):
            pass

    class Configuration:
        def connect(self):
            return Connection()

    population = local_demo_population(patients=2, history_start=START, publication_at=AT)
    adapter = PyodbcSourceAdapter(Configuration())
    previous_upper = state["other_audit"]
    for batch, city in (
        ("seed", "Original"),
        ("correction-one", "One"),
        ("correction-two", "Two"),
        ("zero", None),
        ("after-zero", "Three"),
    ):
        # Both corrections have identical supplied clinical/publication time.
        row = project_source(population, contract, mapping)[name][0]
        row["City"] = city or "Two"
        floor = max(previous_upper, state["head"]["committed_at"] if state["head"] else clock)
        adapter.begin(source, population["publication"]["batch_id"], 2700)
        before_zero = copy.deepcopy(state["rows"])
        if city is not None:
            adapter.write(table, [row], contract["schema"])
        end = "2026-11-02T23:59:59.0000000" if city is None else population["coverage"]["end"]
        if state["head"]:
            end = max(end, state["head"]["coverage_end"])
        evidence = adapter.commit_checkpoint(
            source,
            {
                "batch": batch,
                "population_digest": "p" * 64,
                "mapping_digest": "m" * 64,
                "contract_digest": "c" * 64,
                "row_count": int(city is not None),
                "coverage_start": (
                    state["head"]["coverage_end"]
                    if state["head"]
                    else population["coverage"]["start"]
                ),
                "coverage_end": end,
            },
        )
        current_upper = max(r[audit] for r in state["rows"].values())
        captured = [r for r in state["rows"].values() if previous_upper < r[audit] <= current_upper]
        if city is not None:
            assert len(captured) == 1 and captured[0]["City"] == city
            assert current_upper == tick(floor)
        else:
            assert state["rows"] == before_zero and not captured
            assert evidence["coverage_end"] == end
        assert evidence["committed_at"] > previous_upper
        assert evidence["coverage_end"] != evidence["committed_at"]
        assert adapter.checkpoint(source) == adapter.batch_commit(source, batch)
        previous_upper = current_upper
        adapter.close()


def test_coverage_is_generation_horizon_not_late_commit_and_zero_advances_it(workspace):
    population = local_demo_population(patients=2, history_start=START, publication_at=AT)
    store = PopulationStore(workspace)
    store.publish("old-seed", population)
    adapter = TransactionalAdapter()
    seed = load(store, "old-seed", "Clarity", adapter, workspace)
    assert seed["coverage_start"] == population["coverage"]["start"]
    assert seed["coverage_end"] == population["coverage"]["end"]
    assert seed["committed_at"] > seed["coverage_end"]  # Late publication is still old coverage.
    changed = change_population(population, batch="zero", at="2026-11-02T23:59:59Z", profile="zero")
    store.publish("zero", changed, "old-seed")
    old_rows = copy.deepcopy(adapter.database)
    zero = load(store, "zero", "Clarity", adapter, workspace)
    assert zero["coverage_start"] == seed["coverage_end"]
    assert zero["coverage_end"] == changed["coverage"]["end"]
    assert zero["row_count"] == 0 and adapter.database == old_rows
    damaged = copy.deepcopy(changed)
    del damaged["coverage"]
    store.publish("unverified", damaged, "zero")
    with pytest.raises(ValueError, match="no clock fallback"):
        load(store, "unverified", "Clarity", adapter, workspace)


def test_migration_admin_path_fences_baseline_ddl_and_rolls_back_without_admin_permission():
    from healthcare_ingestion.sql_source_migrations import execute_source_migration_sql

    class Cursor:
        def execute(self, sql):
            events.append(sql)
            if "sp_getapplock" in sql and getattr(connection, "shared_held", False):
                raise RuntimeError("source discovery shared fence is held")

        def fetchone(self):
            return (int(connection.admin),)

        def close(self):
            events.append("close")

    class Connection:
        autocommit, admin = False, True

        def cursor(self):
            return Cursor()

        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    events, connection = [], Connection()
    script = "BEGIN TRANSACTION; CREATE TABLE dbo.SourceFixture(id int); COMMIT TRANSACTION;"
    execute_source_migration_sql(connection, script)
    fence = next(i for i, sql in enumerate(events) if "sp_getapplock" in sql)
    ddl = events.index(script)
    assert fence < ddl < events.index("commit")
    assert all(
        s in events[fence]
        for s in (
            "healthcare-ingestion-source",
            "@DbPrincipal=N'public'",
            "@LockMode='Exclusive'",
            "@LockOwner='Transaction'",
        )
    )
    for source in ("Clarity", "Caboodle"):
        sql = render_source_migration(_inputs(ROOT, source)[0])
        assert sql.index("sp_getapplock") < sql.index("CREATE TABLE dbo.SyntheticSourceCheckpoint")
    events.clear()
    connection.admin = False
    with pytest.raises(PermissionError):
        execute_source_migration_sql(connection, script)
    assert "rollback" in events and script not in events
    events.clear()
    connection.admin, connection.shared_held = True, True
    with pytest.raises(RuntimeError, match="shared fence"):
        execute_source_migration_sql(connection, script)
    assert "rollback" in events and script not in events


def test_checked_in_source_upgrades_match_renderer_and_cover_write_path_gaps():
    for source in ("Clarity", "Caboodle"):
        contract, _ = _inputs(ROOT, source)
        sql = render_source_migration(contract)
        checked = (
            ROOT
            / "database"
            / source.lower()
            / "migrations"
            / ("002-synthetic-integrity-and-write-path.sql")
        )
        assert checked.read_text(encoding="utf-8") == sql
        assert "CREATE OR ALTER PROCEDURE [dbo].[ValidateSyntheticSource]" in sql
        assert "Physical deletes and primary-key changes are prohibited." in sql
        assert "SYSUTCDATETIME()" in sql
        assert "Source writes require the exclusive extraction fence." in sql
        assert "CREATE DATABASE" not in sql
        if source == "Clarity":
            assert "WHERE [EncounterID] IS NOT NULL" in sql
            assert "Appointment encounter patient mismatch" in sql
        else:
            assert "WHERE [IsCurrent]=1" in sql
            assert "DimPatient validity overlap" in sql
            assert "FactLabResult event-time dimension mismatch" in sql
            assert "SourceMedicationOrderID=o.SourceMedicationOrderID" in sql
