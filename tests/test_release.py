from dataclasses import replace
from datetime import UTC, datetime

import pytest
from test_configuration import make_snapshot
from test_configuration import protocol_path as _local_fixture

from healthcare_ingestion.configuration import FunctionSpec
from healthcare_ingestion.control_store import ControlError, InputBinding, SQLiteControlStore
from healthcare_ingestion.release import ReleaseManager

protocol_path = _local_fixture

REVIEW = {
    "branch": "release-config",
    "pull_request": "pr:42",
    "review": "approved-review-sha",
    "commit": "commit-sha",
}
START = "2026-11-19T15:00:00.0000000"
END = "2026-11-20T15:00:00.0000000"


def activate(store, snapshot=None):
    snapshot = snapshot or make_snapshot()
    manager = ReleaseManager(store)
    manager.publish_candidate(snapshot, registry={}, review_evidence=REVIEW)
    manager.begin_candidate(snapshot.version)
    for check in ("tests", "deployment", "environment_publication", "airflow_recognition"):
        manager.record_check(
            snapshot.version,
            "demo",
            check,
            passed=True,
            evidence=f"{snapshot.version}:{check}:verified",
        )
    manager.activate(snapshot.version, "demo")
    return manager


def test_failed_candidate_keeps_active_and_newer_candidate_can_advance(protocol_path):
    store = SQLiteControlStore(protocol_path / "control.db")
    manager = activate(store)
    manager.publish_candidate(make_snapshot("1.1.0"), registry={}, review_evidence=REVIEW)
    manager.publish_candidate(make_snapshot("1.1.1"), registry={}, review_evidence=REVIEW)
    with pytest.raises(ControlError, match="sequential"):
        manager.begin_candidate("1.1.1")
    manager.begin_candidate("1.1.0")
    manager.record_check("1.1.0", "demo", "tests", passed=False, evidence="failed-tests")
    assert store.active_version("demo") == "1.0.0"
    manager.begin_candidate("1.1.1")
    for check in ("tests", "deployment", "environment_publication"):
        manager.record_check("1.1.1", "demo", check, passed=True, evidence=check)
    with pytest.raises(ControlError, match="recognition required"):
        manager.activate("1.1.1", "demo")
    manager.record_check("1.1.1", "demo", "airflow_recognition", passed=True, evidence="airflow")
    manager.activate("1.1.1", "demo")
    assert store.active_version("demo") == "1.1.1"


def test_immutable_release_no_hotfix_and_logical_identity_repurpose(protocol_path):
    store = SQLiteControlStore(protocol_path / "control.db")
    manager = activate(store)
    with pytest.raises(ControlError, match="immutable"):
        manager.publish_candidate(
            replace(
                make_snapshot(),
                artifacts={
                    **make_snapshot().artifacts,
                    "package": "different",
                },
            ),
            registry={},
            review_evidence=REVIEW,
        )
    with pytest.raises(ControlError, match="Branch, PR"):
        manager.publish_candidate(
            make_snapshot("1.1.0"), registry={}, review_evidence={"commit": "x"}
        )
    snapshot = make_snapshot("1.1.0")
    repurposed = replace(
        snapshot,
        datasets=(
            snapshot.datasets[0],
            replace(snapshot.datasets[1], layer="silver1"),
            snapshot.datasets[2],
        ),
    )
    with pytest.raises(ControlError, match="cannot be repurposed"):
        manager.publish_candidate(repurposed, registry={}, review_evidence=REVIEW)
    assert manager.status("1.0.0")["status"] == "ACTIVE"
    with pytest.raises(ControlError, match="Unknown release"):
        manager.status("1.1.0")  # Publication rolled back as one transaction.


def test_rollback_pins_queued_inflight_and_manual_original_default(protocol_path):
    now = datetime(2026, 11, 20, 15, tzinfo=UTC)
    store = SQLiteControlStore(
        protocol_path / "control.db",
        clock=lambda: now,
        legacy_same_window_coverage=True,
    )
    manager = activate(store)
    source = (InputBinding("source.patient", "source-checkpoint-1", START, END),)
    store.queue_operation(
        operation_id="original",
        task_id="clarity.patient",
        environment="demo",
        window_start=START,
        window_end=END,
        inputs=source,
    )
    first = store.claim("original", "worker")
    activate(store, make_snapshot("1.1.0"))
    store.queue_operation(
        operation_id="queued-new",
        task_id="clarity.patient",
        environment="demo",
        window_start=START,
        window_end=END,
        inputs=source,
    )
    assert manager.rollback("demo", reason="technical deployment regression") == "1.0.0"
    assert store.operation("queued-new")["release_version"] == "1.1.0"
    assert store.operation("original")["release_version"] == "1.0.0"
    store.assert_fence(first)
    store.queue_operation(
        operation_id="rerun",
        task_id="clarity.patient",
        environment="demo",
        window_start=START,
        window_end=END,
        inputs=source,
        kind="rerun",
        original_operation_id="queued-new",
    )
    assert store.operation("rerun")["release_version"] == "1.1.0"
    with pytest.raises(ControlError, match="not an automatic technical"):
        manager.rollback("demo", reason="suspected corrupted data", technical_failure=False)


def test_json_occurrence_legacy_bridge_is_immutable_and_history_not_repurposed(protocol_path):
    store = SQLiteControlStore(protocol_path / "control.db")
    manager = ReleaseManager(store)
    snapshot = make_snapshot(functions=(FunctionSpec("names.trim.v1", "trim"),))
    schema = {"type": "object", "additionalProperties": False}
    manager.publish_candidate(snapshot, registry={"trim": schema}, review_evidence=REVIEW)
    manager.import_legacy_attribution(
        "1.0.0",
        "patient.silver",
        "names.trim.v1",
        42,
        import_evidence="reviewed-step-import",
    )
    manager.import_legacy_attribution(
        "1.0.0",
        "patient.silver",
        "names.trim.v1",
        42,
        import_evidence="reviewed-step-import",
    )
    with pytest.raises(ControlError, match="immutable"):
        manager.import_legacy_attribution(
            "1.0.0",
            "patient.silver",
            "names.trim.v1",
            43,
            import_evidence="changed-original",
        )
    repurposed = make_snapshot("1.1.0", functions=(FunctionSpec("names.trim.v1", "different"),))
    with pytest.raises(ControlError, match="occurrence IDs cannot be repurposed"):
        manager.publish_candidate(
            repurposed, registry={"different": schema}, review_evidence=REVIEW
        )
