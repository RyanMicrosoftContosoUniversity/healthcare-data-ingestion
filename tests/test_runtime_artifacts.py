import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from healthcare_ingestion.airflow_runtime import FabricJobs
from healthcare_ingestion.artifacts import LocalArtifactStore
from healthcare_ingestion.build_artifacts import dag_specifications, notebook_definition
from healthcare_ingestion.configuration import ReleaseSnapshot
from healthcare_ingestion.quality import QualityRule, evaluate_quality
from healthcare_ingestion.runtime import sql_factory
from healthcare_ingestion.source_status import read_expected
from healthcare_ingestion.synthetic_population import digest
from healthcare_ingestion.workflow_source import WorkflowSource


def test_generated_notebooks_are_parameterized_valid_python_and_scope_bounded():
    for stage in ("bronze", "silver1"):
        notebook = notebook_definition(stage)
        assert notebook["cells"][0]["metadata"]["tags"] == ["parameters"]
        for cell in notebook["cells"]:
            assert all(line.endswith("\n") for line in cell["source"])
            ast.parse("".join(cell["source"]))
    with pytest.raises(ValueError):
        notebook_definition("gold")


def test_three_workflow_specs_preserve_cross_workflow_dependencies_and_dst():
    snapshot = ReleaseSnapshot.from_dict(
        json.loads(
            (Path(__file__).parents[1] / "metadata" / "framework" / "demo-release.json").read_text()
        )
    )
    specs = dag_specifications(snapshot)
    assert len(specs) == 3
    assert sum(len(spec["tasks"]) for spec in specs.values()) == 29
    assert all(spec["timezone"] == "America/New_York" for spec in specs.values())
    assert any(task["parents"] for spec in specs.values() for task in spec["tasks"])
    assert all(not spec["deadline_cancels_work"] for spec in specs.values())


def test_disabled_quality_introduces_no_spark_actions_and_bad_rules_fail_early():
    frame = object()
    assert evaluate_quality(frame, (), None, "", {}, None) is frame
    with pytest.raises(ValueError):
        QualityRule("name", "FirstName", "arbitrary_expression")
    with pytest.raises(ValueError):
        QualityRule("name", "FirstName", "not_blank", quarantine="false")


def test_sql_machine_token_binding_encrypts_and_bounds_queries(monkeypatch):
    import sys

    captured = {}
    connection = SimpleNamespace(timeout=None)

    def connect(value, **kwargs):
        captured.update(connection_string=value, **kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(connect=connect))
    credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token="machine-token"))
    factory = sql_factory(
        {"server": "source.database.windows.net", "database": "Clarity"},
        credential,
    )
    assert factory() is connection
    assert connection.timeout == 30
    assert "Encrypt=yes" in captured["connection_string"]
    assert captured["autocommit"] is False
    assert set(captured["attrs_before"]) == {1256}
    with pytest.raises(ValueError):
        sql_factory({"server": "evil;UID=admin", "database": "Clarity"}, credential)


def test_shared_discovery_is_once_and_evidence_loses_validity_with_transaction(monkeypatch):
    import healthcare_ingestion.workflow_source as module

    calls = []
    state = [1, 1]

    class Cursor:
        def execute(self, sql):
            calls.append(sql)

        def fetchone(self):
            return state

        def close(self):
            pass

    connection = SimpleNamespace(
        autocommit=False,
        cursor=Cursor,
        rollback=lambda: calls.append("rollback"),
        close=lambda: calls.append("close"),
    )
    monkeypatch.setattr(
        module,
        "discover",
        lambda *_: [
            SimpleNamespace(table="Patient", accepted=True),
        ],
    )
    with WorkflowSource(connection, {"tables": [{"name": "Patient"}]}, {"Patient"}) as source:
        assert "Patient" in source.workflow_discovery_results
        source.commit()
        source.rollback()
        assert "rollback" not in calls
        state[:] = [0, 0]
        with pytest.raises(ValueError, match="fence"):
            source.assert_transaction()
    assert calls[-2:] == ["rollback", "close"]


@pytest.mark.parametrize("limit", [True, float("nan"), float("inf"), -0.01, 1.01])
def test_quarantine_fraction_rejects_invalid_limits_without_actions(limit):
    with pytest.raises(ValueError):
        evaluate_quality(object(), (), None, "", {}, None, max_quarantine_fraction=limit)


def generator_state(population=None, corrupt=False):
    import hashlib

    documents = {}

    def reference(name, document):
        body = json.dumps(document).encode()
        documents[name] = body
        return {
            "area": "state",
            "key": name,
            "size": len(body),
            "sha256": "0" * 64 if corrupt else hashlib.sha256(body).hexdigest(),
        }

    plan = {"batch": "daily-20261121", "at": "2026-11-21T12:00:00Z"}
    control = {
        "expected": {"batch": plan["batch"], "plan_digest": digest(plan), "status": "FAILED"},
        "batches": {plan["batch"]: {"plan_ref": reference("plan", plan)}},
        "files": {},
    }
    if population:
        control["files"][f"batches/{plan['batch']}.json"] = reference(
            "population",
            {"batch": plan["batch"], "digest": digest(population), "population": population},
        )
    documents["generator/control-v1.json"] = json.dumps(control).encode()

    def client(area, key):
        body = documents[key]
        return SimpleNamespace(
            get_blob_properties=lambda: SimpleNamespace(size=len(body)),
            download_blob=lambda length: SimpleNamespace(readall=lambda: body[:length]),
        )

    return SimpleNamespace(client=client)


def test_expected_source_preserves_independent_success_and_rejects_older_head():
    population = {"coverage": {"start": "2026-11-20T12:00:00Z", "end": "2026-11-21T12:00:00Z"}}
    expected = read_expected(generator_state(population))
    head = {
        "batch": expected.batch,
        "population_digest": digest(population),
        "coverage_start": population["coverage"]["start"],
        "coverage_end": population["coverage"]["end"],
    }
    assert expected.matches(head)  # Overall failure does not discard an independently good source.
    assert not expected.matches({**head, "batch": "daily-20261120"})
    assert read_expected(generator_state()).coverage is None
    with pytest.raises(ValueError, match="checksum"):
        read_expected(generator_state(population, corrupt=True))
    with pytest.raises(ValueError, match="limit"):
        read_expected(generator_state(population), max_bytes=1)


def test_ambiguous_job_submission_is_not_retried_in_a_later_cycle(tmp_path):
    import io
    from uuid import uuid4

    posts = []

    class Response(io.BytesIO):
        headers = {}

    def transport(request, timeout):
        if request.get_method() == "POST":
            posts.append(request)
            raise TimeoutError("Receipt unavailable")
        return Response(b'{"value":[]}')

    jobs = FabricJobs(
        SimpleNamespace(get_token=lambda *_: SimpleNamespace(token="test")),
        transport,
    )
    artifacts = LocalArtifactStore(tmp_path)
    workspace, item, operation = map(str, (uuid4(), uuid4(), uuid4()))
    parameters = {"operation_ids_json": json.dumps([operation])}
    with pytest.raises(TimeoutError):
        jobs.submit(workspace, item, parameters, artifacts, "cycle-one")
    assert jobs.submit(workspace, item, parameters, artifacts, "cycle-two") == {
        "status": "SUBMISSION_UNCERTAIN"
    }
    assert len(posts) == 1


def test_prepared_release_checks_wheel_version_and_generates_executable_dags(tmp_path):
    from zipfile import ZipFile

    from healthcare_ingestion.build_artifacts import prepare_release

    root = Path(__file__).parents[1]
    snapshot = ReleaseSnapshot.from_dict(
        json.loads((root / "metadata" / "framework" / "demo-release.json").read_text())
    )
    contracts = {
        source: json.loads((root / "database" / "schema-contracts" / f"{source}.json").read_text())
        for source in ("clarity", "caboodle")
    }
    wheel = tmp_path / "healthcare_ingestion.whl"

    def build(version):
        with ZipFile(wheel, "w") as archive:
            archive.writestr(
                "healthcare_ingestion.dist-info/METADATA",
                f"Name: healthcare-ingestion\nVersion: {version}\n",
            )
            for name in (
                "__init__",
                "airflow_runtime",
                "runtime",
                "configuration",
                "control_store",
                "execution",
            ):
                archive.writestr(f"healthcare_ingestion/{name}.py", "pass\n")

    build("99.0.0")
    with pytest.raises(ValueError, match="version"):
        prepare_release(snapshot, contracts, wheel, root / "uv.lock", tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()
    build(snapshot.version)
    prepared = prepare_release(snapshot, contracts, wheel, root / "uv.lock", tmp_path / "bundle")
    assert prepared.artifacts["notebooks"]["state"] == "UNPUBLISHED"
    for source in (tmp_path / "bundle").glob("*.py"):
        ast.parse(source.read_text())
    assert len(list((tmp_path / "bundle").glob("*.py"))) == 4
    requests = json.loads((tmp_path / "bundle" / "deployment-requests.json").read_text())
    assert any(row.get("body_file") == "reconciliation.py" for row in requests["requests"])
    prepare_release(snapshot, contracts, wheel, root / "uv.lock", tmp_path / "bundle")


def test_fixed_delta_input_uses_producer_mapping_after_logical_remap():
    from healthcare_ingestion.control_store import InputBinding
    from healthcare_ingestion.execution import bound_delta_path

    producer = SimpleNamespace(physical=lambda *_: {"path": "original-retained-path"})
    current = SimpleNamespace(physical=lambda *_: {"path": "different-current-path"})
    store = SimpleNamespace(
        output_history=lambda *_: [
            {"output_id": "output", "operation_id": "producer", "delta_version": "7"}
        ],
        operation=lambda *_: {"release_version": "0.1.0"},
        snapshot=lambda *_: producer,
    )
    binding = InputBinding(
        "bronze",
        "7",
        "2026-11-20T00:00:00",
        "2026-11-21T00:00:00",
        output_id="output",
    )
    assert bound_delta_path(store, current, binding, "demo") == "original-retained-path"


def test_current_backfill_resolves_fresh_coverage_not_highest_stale_delta_version():
    from healthcare_ingestion.coordinator import resolve_waiting

    selected = []
    snapshot = SimpleNamespace(
        task=lambda *_: SimpleNamespace(inputs=(SimpleNamespace(dataset_id="bronze"),)),
        dataset=lambda *_: SimpleNamespace(external=False),
    )
    fresh = {
        "output_id": "fresh",
        "delta_version": "7",
        "window_start": "2026-11-20T00:00:00",
        "window_end": "2026-11-21T00:00:00",
        "source_coverage_start": "2026-11-20T00:00:00",
        "source_coverage_end": "2026-11-21T00:00:00",
    }
    stale = {
        **fresh,
        "output_id": "stale",
        "delta_version": "20",
        "source_coverage_end": "2026-11-20T12:00:00",
    }
    store = SimpleNamespace(
        inputs=lambda *_: (),
        operation=lambda *_: {
            "release_version": "0.1.0",
            "task_id": "silver",
            "environment": "demo",
            "kind": "backfill",
            "source_mode": "current",
            "window_start": "2026-10-01T00:00:00",
            "window_end": "2026-10-02T00:00:00",
        },
        snapshot=lambda *_: snapshot,
        output_history=lambda *_: (stale, fresh),
        bind_waiting_operation=lambda _, bindings: selected.extend(bindings),
    )
    assert resolve_waiting(store, "operation", None)
    assert selected[0].output_id == "fresh"


def test_mandatory_events_survive_delivery_failure_and_unsupported_health_data(tmp_path):
    from healthcare_ingestion.events import EventSink, duration_regression, memory_pressure

    sent = []
    artifacts = LocalArtifactStore(tmp_path)
    sink = EventSink(artifacts, lambda _: (_ for _ in ()).throw(TimeoutError()))
    context = {"operation_id": "operation", "attempt_id": "attempt", "release_version": "0.1.0"}
    assert sink.emit("RunFailed", context) == "UNAVAILABLE"
    sink.deliver = sent.append
    assert sink.emit("RunFailed", context) == "DELIVERED"
    assert len(list((tmp_path / "events").glob("*.json"))) == 1
    assert not list((tmp_path / "event-outbox").glob("*.json"))
    assert sent[0]["Context"]["occurred_at"]
    assert not memory_pressure(
        [{"used_bytes": None, "allocated_bytes": None}], fraction=0.9, consecutive=2
    )
    assert memory_pressure(
        [{"used_bytes": 95, "allocated_bytes": 100}] * 2, fraction=0.9, consecutive=2
    )
    current = {
        "task_id": "patient",
        "compute_profile": "small",
        "input_schema": "schema",
        "volume_group": "demo",
        "seconds": 50,
    }
    assert duration_regression(
        current, [{**current, "seconds": 20}] * 3, ratio=1.5, minimum_samples=3
    )
    assert not duration_regression(
        current,
        [{**current, "compute_profile": "other", "seconds": 20}] * 3,
        ratio=1.5,
        minimum_samples=3,
    )


def test_workflow_retry_preserves_original_release_and_operation_origins(tmp_path):
    from healthcare_ingestion.coordinator import queue_workflow

    current = ["0.1.0"]
    queued = []
    store = SimpleNamespace(
        active_version=lambda _: current[0],
        snapshot=lambda _: SimpleNamespace(
            tasks=[SimpleNamespace(task_id="patient", workflow="clarity", retired=False)]
        ),
        queue_waiting_operation=lambda **kwargs: queued.append(kwargs),
    )
    artifacts = LocalArtifactStore(tmp_path)
    arguments = (store, "clarity", "demo", "scheduled__run", "start", "end")
    original = queue_workflow(*arguments, artifacts=artifacts)
    current[0] = "0.2.0"
    assert queue_workflow(*arguments, artifacts=artifacts) == original
    assert all(row["release_version"] == "0.1.0" for row in queued)
    assert artifacts.get(f"operation-runs/{original[0]}.json")["dag_run_id"] == "scheduled__run"


def test_expected_schedule_is_dst_aware_and_does_not_start_before_ten(monkeypatch):
    from datetime import UTC, datetime

    import healthcare_ingestion.airflow_runtime as module

    queued = []
    worker = SimpleNamespace(
        artifacts=object(),
        store=SimpleNamespace(
            active_version=lambda _: "0.1.0",
            snapshot=lambda _: SimpleNamespace(
                tasks=[SimpleNamespace(workflow="clarity", retired=False)]
            ),
        ),
    )
    monkeypatch.setattr(module, "queue_workflow", lambda *args, **kwargs: queued.append(args))
    module._expected_daily(worker, {"environment": "demo"}, datetime(2026, 11, 1, 14, tzinfo=UTC))
    assert not queued
    module._expected_daily(worker, {"environment": "demo"}, datetime(2026, 11, 1, 16, tzinfo=UTC))
    start, end = map(datetime.fromisoformat, queued[0][4:6])
    assert (end - start).total_seconds() == 25 * 3600


def test_schedule_health_keeps_late_success_failure_and_ignores_backfills():
    from datetime import UTC, datetime

    from healthcare_ingestion.control_store import InputBinding
    from healthcare_ingestion.events import schedule_signals

    operation = {
        "kind": "daily",
        "status": "SUCCEEDED",
        "window_end": "2026-11-21T15:00:00",
        "completed_at": "2026-11-21T16:01:00",
    }
    bindings = [
        InputBinding(
            "source",
            "batch",
            "2026-11-20T12:00:00",
            "2026-11-21T12:00:00",
            source_coverage_start="2026-11-20T12:00:00",
            source_coverage_end="2026-11-21T12:00:00",
        )
    ]
    now = datetime(2026, 11, 21, 17, tzinfo=UTC)
    assert schedule_signals(operation, bindings, now) == ("DeadlineMissed",)
    assert not schedule_signals({**operation, "kind": "backfill"}, bindings, now)
    assert schedule_signals(
        {**operation, "completed_at": "2026-11-21T15:30:00", "corruption_blocked": True},
        bindings,
        now,
    ) == ("DeadlineMissed",)


def test_schedule_monitor_does_not_alert_on_old_coverage_when_latest_is_fresh():
    from datetime import UTC, datetime

    from healthcare_ingestion.airflow_runtime import _schedule_health
    from healthcare_ingestion.control_store import InputBinding

    sent = []
    old = {
        "operation_id": "old",
        "task_id": "patient",
        "environment": "demo",
        "release_version": "0.1.0",
        "kind": "daily",
        "status": "SUCCEEDED",
        "window_end": "2026-11-20T15:00:00",
        "completed_at": "2026-11-20T15:30:00",
    }
    latest = {
        **old,
        "operation_id": "latest",
        "window_end": "2026-11-21T15:00:00",
        "completed_at": "2026-11-21T15:30:00",
    }
    worker = SimpleNamespace(
        store=SimpleNamespace(
            scheduled_operations=lambda *_: (old, latest),
            inputs=lambda operation: [
                InputBinding(
                    "source",
                    "batch",
                    "2026-11-19T12:00:00",
                    "2026-11-21T12:00:00",
                    source_coverage_start="2026-11-19T12:00:00",
                    source_coverage_end="2026-11-20T12:00:00"
                    if operation == "old"
                    else "2026-11-21T12:00:00",
                )
            ],
        ),
        events=SimpleNamespace(emit=lambda *args: sent.append(args)),
    )
    _schedule_health(worker, {"environment": "demo"}, datetime(2026, 11, 21, 17, tzinfo=UTC))
    assert not sent


def test_event_outbox_replay_recovers_delivery_and_only_removes_confirmed_markers(tmp_path):
    from healthcare_ingestion.events import EventSink

    artifacts = LocalArtifactStore(tmp_path)
    sink = EventSink(artifacts)
    assert sink.emit("RunFailed", {"operation_id": "operation"}) == "QUEUED"
    sent = []
    sink.deliver = sent.append
    assert list(sink.replay().values()) == ["DELIVERED"]
    assert len(sent) == 1
    assert sink.replay() == {}
    with pytest.raises(ValueError):
        artifacts.discard_event("events/proof.json")


def test_lazy_credentials_only_load_used_role_once(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    import healthcare_ingestion.runtime as module

    loaded = []
    monkeypatch.setattr(
        module,
        "certificate_identity",
        lambda config: (
            loaded.append(config["role"]) or SimpleNamespace(get_token=lambda *_: "token")
        ),
    )
    credential = module.ConfiguredCredential({"role": "source"})
    module.ConfiguredCredential({"role": "optional-diagnostics"})
    assert not loaded
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: credential.get_token("scope"), range(8))) == ["token"] * 8
    assert loaded == ["source"]


def test_spark_settings_restore_task_overrides_even_after_failure():
    from healthcare_ingestion.runtime import spark_settings

    values = {"spark.sql.shuffle.partitions": "200"}
    spark = SimpleNamespace(
        sparkContext=SimpleNamespace(getConf=lambda: SimpleNamespace(get=lambda *args: None)),
        conf=SimpleNamespace(
            get=lambda key, default: values.get(key, default),
            set=lambda key, value: values.update({key: str(value)}),
            unset=lambda key: values.pop(key),
        ),
    )
    with pytest.raises(RuntimeError):
        with spark_settings(spark, {"runtime": {"spark.sql.shuffle.partitions": 4}}):
            assert values["spark.sql.shuffle.partitions"] == "4"
            raise RuntimeError()
    assert values["spark.sql.shuffle.partitions"] == "200"
    with pytest.raises(ValueError, match="startup"):
        with spark_settings(spark, {"startup": {"spark.executor.memory": "8g"}}):
            pytest.fail("Unsupported startup configuration was accepted.")


def test_diagnostic_unexpected_failure_closes_running_collection(monkeypatch):
    import healthcare_ingestion.diagnostics as module

    records = []
    monkeypatch.setattr(module, "collect_metrics", lambda *_: (_ for _ in ()).throw(RuntimeError()))
    store = SimpleNamespace(
        record_diagnostic_attempt=lambda row: records.append(row) or "collection"
    )
    attempt = SimpleNamespace(attempt_id="0", route=lambda: "actual-attempt")
    context = {"operation_id": "op", "attempt_id": "sql-attempt", "release_version": "0.1.0"}
    with pytest.raises(RuntimeError):
        module.collect_attempt(store, object(), attempt, context, [], None)
    assert [row["status"] for row in records] == ["RUNNING", "FAILED"]
    assert records[-1]["completed_at"]


def test_transient_retries_require_matching_attempt_and_elapsed_delay(tmp_path):
    from datetime import UTC, datetime

    from healthcare_ingestion.airflow_runtime import _retry_failed

    artifacts = LocalArtifactStore(tmp_path)
    artifacts.put("op/transient-attempt.json", {"attempt_id": "attempt"})
    operation = {
        "operation_id": "op",
        "attempt_id": "attempt",
        "status": "FAILED",
        "updated_at": "2026-11-21T15:00:00",
        "release_version": "0.1.0",
        "task_id": "patient",
    }
    retried = []
    worker = SimpleNamespace(
        artifacts=artifacts,
        store=SimpleNamespace(
            snapshot=lambda _: SimpleNamespace(
                effective_settings=lambda _: {"scheduler": {"retry_delay_seconds": 30}},
            ),
            operation=lambda _: operation,
            retry_operation=retried.append,
        ),
    )
    _retry_failed(worker, [operation], datetime(2026, 11, 21, 15, 0, 29, tzinfo=UTC))
    assert not retried
    _retry_failed(
        worker, [{**operation, "attempt_id": "other"}], datetime(2026, 11, 21, 16, tzinfo=UTC)
    )
    assert not retried
    _retry_failed(worker, [operation], datetime(2026, 11, 21, 15, 0, 31, tzinfo=UTC))
    assert retried == ["op"]


def test_execution_override_requires_exact_deployed_profile_binding(tmp_path):
    from healthcare_ingestion.airflow_runtime import _submit_group

    raw = json.loads(
        (Path(__file__).parents[1] / "metadata" / "framework" / "demo-release.json").read_text()
    )
    raw["tasks"][0]["overrides"] = {"execution": {"compute_profile_ref": "special-profile"}}
    snapshot = ReleaseSnapshot.from_dict(raw)
    task = snapshot.tasks[0]
    worker = SimpleNamespace(
        artifacts=LocalArtifactStore(tmp_path),
        store=SimpleNamespace(
            operation=lambda _: {"release_version": snapshot.version, "task_id": task.task_id},
            snapshot=lambda _: snapshot,
        ),
    )
    config = {"release_notebooks": {f"{snapshot.version}-{task.workflow}": "default"}}
    with pytest.raises(ValueError, match="explicit deployed"):
        _submit_group(worker, config, object(), ["op"], "cycle")


def test_benchmark_freeze_failure_records_terminal_setup_trial_and_restores_context():
    from healthcare_ingestion.benchmark import benchmark
    from healthcare_ingestion.patient import REGISTRY

    records = []
    restored = []
    spark = SimpleNamespace(
        sparkContext=SimpleNamespace(
            getLocalProperty=lambda _: None,
            setJobGroup=lambda *args, **kwargs: None,
            cancelJobGroup=lambda _: None,
            setLocalProperty=lambda *args: restored.append(args),
        )
    )
    writer = SimpleNamespace(
        format=lambda _: writer,
        mode=lambda _: writer,
        save=lambda _: (_ for _ in ()).throw(TimeoutError()),
    )
    frame = SimpleNamespace(sparkSession=spark, write=writer)
    with pytest.raises(TimeoutError):
        benchmark(
            frame,
            [{"name": next(iter(REGISTRY)), "parameters": {}}],
            "benchmarks",
            lambda _: None,
            {"framework_version": "0.1.0", "input_versions": {"source": "1"}},
            setup_persist=records.append,
        )
    assert [row["status"] for row in records] == ["RUNNING", "FAILED"]
    assert records[-1]["warmup"] and records[-1]["completed_at"]
    assert len(restored) == 3


def test_workflow_freezes_verified_expected_source_under_one_source_transaction(
    monkeypatch, tmp_path
):
    import healthcare_ingestion.runtime as module

    root = Path(__file__).parents[1]
    raw = json.loads((root / "metadata" / "framework" / "demo-release.json").read_text())
    raw["artifacts"]["source_contracts"] = {
        source: json.loads((root / "database" / "schema-contracts" / f"{source}.json").read_text())
        for source in ("clarity", "caboodle")
    }
    snapshot = ReleaseSnapshot.from_dict(raw)
    task = snapshot.tasks[0]
    population = {"coverage": {"start": "2026-11-20T12:00:00Z", "end": "2026-11-21T12:00:00Z"}}
    expected = read_expected(generator_state(population))
    head = {
        "batch": expected.batch,
        "population_digest": expected.population_digest,
        "coverage_start": population["coverage"]["start"],
        "coverage_end": population["coverage"]["end"],
    }
    entered, registered, bound = [], [], []

    class Source:
        def __init__(self, *args):
            entered.append(args)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def assert_transaction(self):
            pass

        def cursor(self):
            return SimpleNamespace(close=lambda: None)

    operation = {
        "operation_id": "op",
        "release_version": snapshot.version,
        "task_id": task.task_id,
        "environment": "demo",
        "status": "BLOCKED_BY_DEPENDENCY",
        "kind": "daily",
        "window_start": "2026-11-20T15:00:00",
        "window_end": "2026-11-21T15:00:00",
    }

    def register(*args, **kwargs):
        assert kwargs["verify_snapshot"]()
        registered.append((args, kwargs))
        return "source-snapshot"

    store = SimpleNamespace(
        operation=lambda _: operation,
        snapshot=lambda _: snapshot,
        inputs=lambda _: tuple(bound),
        register_source_snapshot=register,
        bind_waiting_operation=lambda _, values: bound.extend(values),
    )
    monkeypatch.setattr(module, "WorkflowSource", Source)
    monkeypatch.setattr(module, "source_checkpoint_evidence", lambda *args: head)
    monkeypatch.setattr(module.Worker, "execute", lambda *args: "output")
    worker = module.Worker(
        store,
        LocalArtifactStore(tmp_path),
        None,
        "staging",
        lambda _: None,
        expected_source=lambda: expected,
    )
    assert worker.execute_workflow(["op"], "owner", "dag") == {"op": {"output_id": "output"}}
    assert len(entered) == 1
    assert registered[0][1]["scope"] == task.scope
    assert bound[0].source_snapshot_id == "source-snapshot"
    assert bound[0].source_coverage_end.startswith("2026-11-21T12:00:00")
    assert bound[0].window_end.startswith("2026-11-21T15:00:00")


def test_generator_acknowledgement_rejects_blocked_corrupt_readiness():
    from healthcare_ingestion.runtime import Worker

    root = Path(__file__).parents[1]
    raw = json.loads((root / "metadata" / "framework" / "demo-release.json").read_text())
    raw["artifacts"]["source_contracts"] = {
        source: json.loads((root / "database" / "schema-contracts" / f"{source}.json").read_text())
        for source in ("clarity", "caboodle")
    }
    snapshot = ReleaseSnapshot.from_dict(raw)
    store = SimpleNamespace(
        snapshot=lambda _: snapshot,
        readiness=lambda *args: {"ready": False, "reason": "corruption"},
    )
    worker = Worker(store, None, None, "staging", None)
    assert worker.acknowledge_generator(object(), object(), "demo", snapshot.version) is False


def test_task_timeout_cancels_only_its_group_fences_publication_and_restores_context():
    from healthcare_ingestion.execution import ExecutionLease

    properties = {"spark.jobGroup.id": "previous"}
    cancelled = []
    spark = SimpleNamespace(
        sparkContext=SimpleNamespace(
            getLocalProperty=lambda key: properties.get(key),
            setJobGroup=lambda group, *args, **kwargs: properties.update(
                {"spark.jobGroup.id": group}
            ),
            setLocalProperty=lambda key, value: properties.update({key: value}),
            cancelJobGroup=cancelled.append,
        )
    )
    store = SimpleNamespace(assert_fence=lambda _: True)
    with ExecutionLease(store, SimpleNamespace(attempt_id="attempt"), spark, 3600) as lease:
        assert lease.fence()
        lease.timer.function()
        with pytest.raises(RuntimeError, match="timeout"):
            lease.fence()
    assert cancelled == ["healthcare-task-attempt"]
    assert properties["spark.jobGroup.id"] == "previous"
