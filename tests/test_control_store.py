import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_configuration import protocol_path as _local_fixture
from test_release import END, START, activate

from healthcare_ingestion.configuration import FunctionSpec, InputSpec
from healthcare_ingestion.control_store import (
    CommitEvidence,
    ControlError,
    DependencyBlocked,
    InputBinding,
    LeaseLost,
    MetadataUnavailable,
    SQLiteControlStore,
    utc_text,
)
from healthcare_ingestion.function_contracts import FUNCTION_SCHEMAS
from healthcare_ingestion.operational_records import (
    SPARK_METRIC_TYPES,
    DiagnosticAttemptRecord,
    record_schema,
)
from healthcare_ingestion.release import ReleaseManager

protocol_path = _local_fixture


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 20, 15, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def control(protocol_path):
    clock = Clock()
    store = SQLiteControlStore(
        protocol_path / "control.db",
        clock=clock,
        legacy_same_window_coverage=True,
    )
    activate(store)
    return store, clock


def queue(store, op="daily-1", *, start=START, end=END, kind="daily", inputs=None, task=None, **kw):
    return store.queue_operation(
        operation_id=op,
        task_id=task or "clarity.patient",
        environment="demo",
        window_start=start,
        window_end=end,
        kind=kind,
        inputs=inputs or (InputBinding("source.patient", "checkpoint-1", start, end),),
        **kw,
    )


def evidence(store, op, *, version="7", changed=1, coverage=True):
    operation = store.operation(op)
    bindings = store.inputs(op)
    return CommitEvidence(
        op,
        operation["dataset_id"],
        version,
        operation["window_start"],
        operation["window_end"],
        {b.dataset_id: b.version for b in bindings},
        "validation-sha",
        coverage,
        changed,
        op,
        source_coverage_start=max(b.source_coverage_start or b.window_start for b in bindings),
        source_coverage_end=min(b.source_coverage_end or b.window_end for b in bindings),
    )


def publish(store, op, **kwargs):
    claim = store.claim(op, f"worker:{op}")
    result = store.publish(claim, evidence(store, op, **kwargs), lambda ev: True)
    return result


def test_concurrent_duplicate_claims_and_fenced_takeover(control):
    store, clock = control
    queue(store)
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda i: store.claim("daily-1", f"worker-{i}", 30), range(6)))
    old = next(c for c in claims if c)
    assert sum(c is not None for c in claims) == 1
    clock.advance(31)
    new = store.claim("daily-1", "replacement", 60)
    assert new.fence == old.fence + 1
    assert new.attempt_id != old.attempt_id
    with pytest.raises(LeaseLost):
        store.heartbeat(old)
    with pytest.raises(LeaseLost):
        store.publish(old, evidence(store, "daily-1"), lambda ev: True)
    store.heartbeat(new)
    store.publish(new, evidence(store, "daily-1"), lambda ev: True)
    assert len(store.output_history("bronze.patient", "demo")) == 1


def test_duplicate_operation_immutable_inputs_and_idempotent_publication(control):
    store, _ = control
    queue(store)
    queue(store)
    with pytest.raises(ControlError, match="different immutable"):
        queue(store, inputs=(InputBinding("source.patient", "another-checkpoint", START, END),))
    claim = store.claim("daily-1", "worker")
    ev = evidence(store, "daily-1")
    first = store.publish(claim, ev, lambda e: True)
    assert store.publish(claim, ev, lambda e: True) == first
    assert len(store.pending_events()) == 1
    with pytest.raises(ControlError, match="different commit"):
        store.publish(claim, replace(ev, validation_digest="different"), lambda e: True)


def test_no_change_requires_validated_coverage_and_preserves_delta_version(control):
    store, _ = control
    queue(store)
    publish(store, "daily-1")
    queue(store, "no-change", start=END, end="2026-11-20T16:00:00Z")
    claim = store.claim("no-change", "worker")
    with pytest.raises(ControlError, match="coverage"):
        store.publish(
            claim, evidence(store, "no-change", coverage=False, changed=0), lambda e: True
        )
    with pytest.raises(ControlError, match="preserve"):
        store.publish(claim, evidence(store, "no-change", version="8", changed=0), lambda e: True)
    store.publish(claim, evidence(store, "no-change", version="7", changed=0), lambda e: True)
    assert store.readiness("bronze.patient", "demo")["progress_end"] == utc_text(
        "2026-11-20T16:00:00Z"
    )
    assert [o["delta_version"] for o in store.output_history("bronze.patient", "demo")] == [
        "7",
        "7",
    ]


def test_newest_progress_not_completion_time_and_latest_failure_blocks(control):
    store, _ = control
    queue(store, "older")
    queue(store, "newer", start=END, end="2026-11-20T16:00:00Z")
    publish(store, "newer", version="8")
    latest_output = store.readiness("bronze.patient", "demo")["output_id"]
    publish(store, "older", version="7")
    assert store.readiness("bronze.patient", "demo")["output_id"] == latest_output
    queue(store, "latest", start="2026-11-20T16:00:00Z", end="2026-11-20T17:00:00Z")
    store.fail(store.claim("latest", "worker"), "SCHEMA_DRIFT")
    ready = store.readiness("bronze.patient", "demo")
    assert not ready["ready"]
    assert ready["output_id"] == latest_output
    output = store.output_history("bronze.patient", "demo")[-1]
    queue(
        store,
        "silver",
        task="patient.silver",
        start=END,
        end="2026-11-20T16:00:00Z",
        inputs=(
            InputBinding(
                "bronze.patient", "8", output["window_start"], output["window_end"], latest_output
            ),
        ),
    )
    with pytest.raises(DependencyBlocked, match="Latest expected"):
        store.claim("silver", "silver-worker")
    assert store.operation("silver")["status"] == "BLOCKED_BY_DEPENDENCY"
    queue(store, "corrected", start="2026-11-20T16:00:00Z", end="2026-11-20T17:00:00Z")
    publish(store, "corrected", version="9")
    assert store.readiness("bronze.patient", "demo")["ready"]


def test_uncertain_post_write_recovery_never_reappends_or_steals_live_owner(control):
    store, clock = control
    queue(store)
    claim = store.claim("daily-1", "worker")
    ev = evidence(store, "daily-1")
    with pytest.raises(ControlError, match="Live owner"):
        store.reconcile_commit("daily-1", ev, lambda e: True)
    store.fail(claim, "SQL_COMMIT_UNCERTAIN", uncertain=True)
    assert not store.readiness("bronze.patient", "demo")["ready"]
    assert store.claim("daily-1", "other") is None
    with pytest.raises(ControlError, match="could not verify"):
        store.reconcile_commit("daily-1", ev, lambda e: False)
    first = store.reconcile_commit("daily-1", ev, lambda e: True)
    assert store.reconcile_commit("daily-1", ev, lambda e: True) == first
    queue(store, "lost-sql", start=END, end="2026-11-20T16:00:00Z")
    store.claim("lost-sql", "worker", 30)
    clock.advance(31)
    store.reconcile_commit("lost-sql", evidence(store, "lost-sql", version="8"), lambda e: True)
    assert len(store.output_history("bronze.patient", "demo")) == 2


def test_conflicting_backfills_daily_priority_and_nonconflicting_windows(control):
    store, _ = control
    queue(store, "backfill", kind="backfill")
    queue(store, "daily")
    assert store.claim("backfill", "backfill-worker") is None
    daily = store.claim("daily", "daily-worker")
    assert daily
    assert store.claim("backfill", "backfill-worker") is None
    queue(store, "different", kind="backfill", start="2026-11-18T15:00:00Z", end=START)
    assert store.claim("different", "another-worker")
    store.publish(daily, evidence(store, "daily"), lambda e: True)
    assert store.claim("backfill", "backfill-worker")


def test_corruption_descendant_blocks_require_operator_unblock(control):
    store, _ = control
    queue(store)
    output_id = publish(store, "daily-1")
    affected = store.flag_corruption("bronze.patient", "demo", "1.0.0", "incident:1")
    assert affected == ("bronze.patient", "silver.patient")
    queue(
        store,
        "silver",
        task="patient.silver",
        inputs=(InputBinding("bronze.patient", "7", START, END, output_id),),
    )
    with pytest.raises(DependencyBlocked):
        store.claim("silver", "worker")
    with pytest.raises(ControlError, match="operator"):
        store.clear_corruption(
            "incident:1", "bronze.patient", "demo", operator_approval="", validation_digest="ok"
        )
    store.clear_corruption(
        "incident:1",
        "bronze.patient",
        "demo",
        operator_approval="operator-review:42",
        validation_digest="valid",
    )
    assert store.readiness("bronze.patient", "demo")["ready"]
    with pytest.raises(DependencyBlocked, match="Output dataset"):
        store.claim("silver", "worker")
    store.clear_corruption(
        "incident:1",
        "silver.patient",
        "demo",
        operator_approval="operator-review:43",
        validation_digest="valid",
    )
    assert store.claim("silver", "worker")


def test_duplicate_lost_and_out_of_order_events_coalescing_and_reconciliation(control):
    store, clock = control
    queue(store, "old")
    queue(store, "new", start=END, end="2026-11-20T16:00:00Z")
    publish(store, "new", version="8")
    publish(store, "old", version="7")
    all_events = store.pending_events(coalesce=False)
    newest = next(e for e in all_events if e["progress_end"] == utc_text("2026-11-20T16:00:00Z"))
    older = next(e for e in all_events if e != newest)
    assert store.pending_events()[0]["event_id"] == newest["event_id"]
    assert store.consume_event(newest["event_id"], "consumer")
    assert not store.consume_event(newest["event_id"], "consumer")
    assert not store.consume_event(older["event_id"], "consumer")
    assert store.consume_event(older["event_id"], "all-updates", process_each=True)
    store.acknowledge_event(newest["event_id"], coalesced=True)
    assert store.pending_events(coalesce=False) == ()
    queue(store, "missed-event", start="2026-11-20T16:00:00Z", end="2026-11-20T17:00:00Z")
    run = store.begin_reconciliation("demo", "reconciler")
    assert store.begin_reconciliation("demo", "other") is None
    assert "missed-event" in store.reconciliation_operations(run["reconciliation_id"], "reconciler")
    assert run["snapshot_hash"] == store.snapshot("1.0.0").digest
    store.finish_reconciliation(run["reconciliation_id"], "reconciler")
    assert store.begin_reconciliation("demo", "other") is None
    clock.advance(300)
    assert store.begin_reconciliation("demo", "other")


def test_bounded_reconciliation_retry_and_expired_owner(control):
    store, clock = control
    run = store.begin_reconciliation("demo", "owner", max_retries=1, lease_seconds=300)
    store.finish_reconciliation(run["reconciliation_id"], "owner", error_code="transient")
    with pytest.raises(ControlError, match="backoff"):
        store.finish_reconciliation(run["reconciliation_id"], "owner", error_code="transient")
    clock.advance(30)
    result = store.finish_reconciliation(run["reconciliation_id"], "owner", error_code="persistent")
    assert result["status"] == "FAILED"
    clock.advance(300)
    next_run = store.begin_reconciliation("demo", "new-owner")
    with pytest.raises(LeaseLost):
        store.finish_reconciliation(run["reconciliation_id"], "owner")
    assert next_run["reconciliation_id"] != run["reconciliation_id"]


def test_historical_source_requires_available_snapshot_no_silent_current_substitution(control):
    store, _ = control
    with pytest.raises(ControlError, match="retained snapshot"):
        queue(store, kind="backfill", source_mode="historical")
    queue(store, "original")
    publish(store, "original")
    with pytest.raises(ControlError, match="explicit approval"):
        queue(
            store,
            "rerun",
            source_mode="historical",
            kind="rerun",
            original_operation_id="original",
            inputs=(InputBinding("source.patient", "current-corrected", START, END),),
        )
    assert store.operation("original")["source_mode"] == "current"


def test_available_historical_source_is_pinned_and_explicit_substitution_audited(control):
    store, _ = control
    source_id = store.register_source_snapshot(
        "source.patient",
        "demo",
        "saved-source-v1",
        START,
        END,
        evidence_digest="source-reconciliation-sha",
        artifact_ref="artifact:retained-batch",
        verify_snapshot=lambda: True,
    )
    source = InputBinding(
        "source.patient", "saved-source-v1", START, END, source_snapshot_id=source_id
    )
    queue(store, "historical", kind="backfill", source_mode="historical", inputs=(source,))
    assert store.inputs("historical")[0].source_snapshot_id == source_id
    assert store.claim("historical", "worker")
    queue(
        store,
        "approved-substitute",
        kind="backfill",
        source_mode="historical",
        original_operation_id="historical",
        authorize_substitution="operator:42",
    )
    assert store.operation("approved-substitute")["substitution_approval"] == "operator:42"
    assert store.inputs("approved-substitute")[0].version == "checkpoint-1"


def test_event_transport_lost_ack_bounded_retry_and_fallback(control):
    store, clock = control
    queue(store)
    publish(store, "daily-1")
    seen = []

    def transport(event):
        seen.append(event["event_id"])
        raise ConnectionError("transport accepted but acknowledgement was lost")

    assert store.dispatch_events(transport, max_attempts=2) == ()
    assert store.pending_events() == ()
    clock.advance(30)
    store.dispatch_events(transport, max_attempts=2)
    assert len(seen) == 2 and seen[0] == seen[1]
    clock.advance(60)
    store.dispatch_events(transport, max_attempts=2)
    assert len(seen) == 2
    assert store.consume_event(seen[0], "consumer")
    assert not store.consume_event(seen[1], "consumer")
    assert store.begin_reconciliation("demo", "fallback")


def test_source_window_seventh_fractional_digit_and_dst_elapsed_coverage(control):
    store, _ = control
    start = "2026-11-20T15:00:00.0000001"
    end = "2026-11-20T15:00:00.0000002"
    queue(store, start=start, end=end)
    assert store.operation("daily-1")["window_start"] == start
    assert utc_text("2026-11-01T01:30:00.1234567-04:00") == "2026-11-01T05:30:00.1234567"
    assert utc_text("2026-11-01T01:30:00.1234567-05:00") == "2026-11-01T06:30:00.1234567"


def test_durable_restart_and_referenced_audit_retention(control):
    store, clock = control
    queue(store)
    output = publish(store, "daily-1")
    restarted = SQLiteControlStore(store.path, clock=clock)
    assert restarted.readiness("bronze.patient", "demo")["output_id"] == output
    assert not restarted.can_cleanup_output(output)
    with pytest.raises(ControlError, match="seven years"):
        restarted.can_cleanup_output(output, audit_years=1)
    clock.advance(8 * 366 * 86400)
    assert not restarted.can_cleanup_output(output)  # Current output reference is a hold.


def test_scheduler_retries_bounded_keep_bindings_and_require_intervention(control):
    store, _ = control
    queue(store)
    original_inputs = store.inputs("daily-1")
    for index in range(3):
        claim = store.claim("daily-1", f"worker:{index}")
        store.fail(claim, "TRANSIENT")
        if index < 2:
            store.retry_operation("daily-1")
    with pytest.raises(ControlError, match="exhausted"):
        store.retry_operation("daily-1")
    store.retry_operation("daily-1", operator_approval="operator:42")
    assert store.inputs("daily-1") == original_inputs
    assert store.claim("daily-1", "approved-worker").fence == 4


def test_outage_blocks_new_start_and_defers_safe_inflight_commit_until_reconciliation(control):
    store, clock = control
    queue(store, "inflight")
    claim = store.claim("inflight", "worker")
    ev = evidence(store, "inflight")
    queue(store, "new", start=END, end="2026-11-20T16:00:00Z")
    original_path = store.path
    store.path = str(Path(original_path).parent / "unavailable" / "control.db")
    with pytest.raises(MetadataUnavailable):
        store.claim("new", "new-worker")
    with pytest.raises(MetadataUnavailable):
        store.publish(claim, ev, lambda e: True)
    store.path = original_path
    assert not store.readiness("bronze.patient", "demo")["ready"]
    clock.advance(301)
    store.reconcile_commit("inflight", ev, lambda e: True)
    assert store.readiness("bronze.patient", "demo")["output_id"]


def test_same_window_old_retry_cannot_replace_newer_corrected_current_output(control):
    store, _ = control
    queue(store, "old")
    store.fail(store.claim("old", "worker"), "ROUTINE_FAILURE")
    queue(store, "corrected")
    latest = publish(store, "corrected", version="8")
    store.retry_operation("old")
    publish(store, "old", version="7")
    assert store.readiness("bronze.patient", "demo")["output_id"] == latest


def operational_context(store, operation_id="observed"):
    queue(store, operation_id)
    claim = store.claim(operation_id, "worker")
    return {
        "operation_id": operation_id,
        "attempt_id": claim.attempt_id,
        "release_version": store.operation(operation_id)["release_version"],
    }, claim


def test_registered_historical_snapshot_lookup_is_exact_frozen_and_no_fallback(control):
    store, _ = control
    snapshot_id = store.register_source_snapshot(
        "source.patient",
        "demo",
        "historical-v7",
        START,
        END,
        evidence_digest="verified-source-sha",
        artifact_ref="artifact:immutable-saved-capture",
        verify_snapshot=lambda: True,
    )
    snapshot = store.source_snapshot_info(snapshot_id)
    assert snapshot["version"] == "historical-v7"
    assert snapshot["dataset_id"] == "source.patient"
    assert snapshot["environment"] == "demo" and snapshot["scope"] == "default"
    assert snapshot["artifact_ref"] == "artifact:immutable-saved-capture"
    assert snapshot["window_start"] == START and snapshot["window_end"] == END
    with pytest.raises(TypeError):
        snapshot["version"] = "current"
    with pytest.raises(ControlError, match="unavailable"):
        store.source_snapshot_info("missing")


def test_diagnostic_finalization_duplicate_replays_and_cleanup_do_not_change_readiness(control):
    store, _ = control
    context, claim = operational_context(store)
    store.publish(claim, evidence(store, "observed"), lambda e: True)
    readiness = store.readiness("bronze.patient", "demo")
    record = {
        **context,
        "status": "RUNNING",
        "scope_key": "spark-app/driver",
        "collection_attempt": 0,
    }
    record_id = store.record_diagnostic_attempt(DiagnosticAttemptRecord(**record))
    terminal = {**record, "status": "UNAVAILABLE", "reason": "PROVIDER_LOG_EXPIRED"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert (
            list(pool.map(lambda _: store.record_diagnostic_attempt(terminal), range(4)))
            == [
                record_id,
            ]
            * 4
        )
    assert store.record_diagnostic_attempt(record) == record_id  # Lost old acknowledgement.
    history = store.operational_record_revisions("diagnostic_attempt", record_id)
    assert [item["status"] for item in history] == ["RUNNING", "UNAVAILABLE"]
    assert [
        item["status"]
        for item in store.operational_record_revisions(
            "diagnostic_attempt", record_id, after_revision=1
        )
    ] == ["UNAVAILABLE"]
    with pytest.raises(ControlError, match="cursor"):
        store.operational_record_revisions("diagnostic_attempt", record_id, after_revision=True)
    assert store.operational_record("diagnostic_attempt", record_id)["status"] == "UNAVAILABLE"
    with pytest.raises(ControlError, match="immutable"):
        store.record_diagnostic_attempt({**terminal, "reason": "CHANGED_TERMINAL_REASON"})
    cleanup = {**context, "artifact_id": "artifact:expired-diagnostic", "status": "RUNNING"}
    cleanup_id = store.record_cleanup_outcome(cleanup)
    store.record_cleanup_outcome(
        {**cleanup, "status": "FAILED", "reason": "DELETE_PERMISSION_DENIED"}
    )
    assert store.operational_record("cleanup_outcome", cleanup_id)["status"] == "FAILED"
    assert store.readiness("bronze.patient", "demo") == readiness
    restarted = SQLiteControlStore(store.path)
    assert restarted.operational_record("cleanup_outcome", cleanup_id)["reason"] == (
        "DELETE_PERMISSION_DENIED"
    )


def test_diagnostic_artifact_revision_context_and_record_budgets_are_enforced(control):
    store, _ = control
    context, _ = operational_context(store)
    collection_id = store.record_diagnostic_attempt(
        {
            **context,
            "scope_key": "provider-attempt-1",
            "status": "RUNNING",
        }
    )
    log = {
        **context,
        "collection_id": collection_id,
        "kind": "driver",
        "filename": "driver.log",
        "source_identity": "provider-attempt-1/driver.log/revision-1",
        "status": "COLLECTED",
        "artifact": "artifact:restricted-driver-log",
        "bytes": 12,
        "sha256": "a" * 64,
        "complete": True,
        "retrieval_context": {"offset": 0, "limit": 8192},
    }
    log_id = store.record_diagnostic_log(log)
    assert store.record_diagnostic_log(log) == log_id
    assert store.operational_record("diagnostic_log", log_id)["availability"] == "AVAILABLE"
    partial_id = store.record_diagnostic_log(
        {**log, "source_identity": "provider-attempt-1/partial", "complete": False}
    )
    partial = store.operational_record("diagnostic_log", partial_id)
    assert partial["status"] == "PARTIAL" and not partial["complete"]
    with pytest.raises(ControlError, match="different immutable identity"):
        store.record_diagnostic_log(
            {**log, "record_id": log_id, "source_identity": "different-source"}
        )
    with pytest.raises(ControlError, match="immutable"):
        store.record_diagnostic_log({**log, "bytes": 13})
    assert store.record_diagnostic_log(
        {**log, "source_identity": "provider-attempt-1/revision-2"}
    ) != (log_id)
    with pytest.raises(ControlError, match="Unknown or missing"):
        store.record_diagnostic_log({**log, "raw_log_body": "not metadata"})
    with pytest.raises(ControlError, match="budget"):
        store.record_diagnostic_attempt(
            {**context, "scope_key": "x", "status": "RUNNING", "spark": {"large": "x" * 65536}}
        )
    with pytest.raises(ControlError, match="integer"):
        store.record_cleanup_outcome(
            {**context, "artifact_id": "x", "status": "RUNNING", "attempt_number": 7}
        )
    with pytest.raises(ControlError, match="protected artifacts"):
        store.record_diagnostic_attempt(
            {
                **context,
                "scope_key": "raw",
                "status": "RUNNING",
                "spark": {"body": "unrestricted raw log content"},
            }
        )
    with pytest.raises(ControlError, match="lineage"):
        store.record_diagnostic_log({**log, "attempt_id": "foreign-attempt"})
    assert "scope_key" in record_schema("diagnostic_attempt")["fields"]
    assert record_schema("diagnostic_attempt")["fields"]["scope_key"]["required"]


def metric_record(context, **updates):
    return {
        **context,
        "status": "UNAVAILABLE",
        "activity_run_id": "activity-1",
        "workspace_id": "workspace-1",
        "item_id": "notebook-1",
        "item_type": "notebooks",
        "livy_id": "livy-1",
        "application_id": "application-1",
        "application_attempt_id": "0",
        **updates,
    }


def test_all_nullable_spark_metrics_preserve_availability_and_newest_revision(control):
    store, _ = control
    context, _ = operational_context(store)
    unavailable = metric_record(context)
    record_id = store.record_spark_metric(unavailable)
    loaded = store.operational_record("spark_metric", record_id)
    assert len(loaded["metrics"]) == len(SPARK_METRIC_TYPES) == 50
    assert all(
        m["value"] is None and m["reason"] == "NOT_COLLECTED" for m in loaded["metrics"].values()
    )
    metrics = {
        "CPUTime": {"value": "1.1234567", "availability": "AVAILABLE", "source": "verified:api"},
        "AllocatedExecutorsMin": {
            "value": 0,
            "availability": "AVAILABLE",
            "source": "verified:api",
        },
        "AllocatedExecutorsMax": {
            "value": 2,
            "availability": "AVAILABLE",
            "source": "verified:api",
        },
        "ReadRows": {"value": None, "availability": "UNAVAILABLE", "reason": "NOT_EXPOSED"},
    }
    newer = metric_record(context, status="PARTIAL", metrics=metrics, revision=2)
    assert store.record_spark_metric(newer) == record_id
    assert (
        store.record_spark_metric(unavailable) == record_id
    )  # Earlier callback cannot erase values.
    loaded = store.operational_record("spark_metric", record_id)
    assert loaded["revision"] == 2 and loaded["metrics"]["CPUTime"]["value"] == "1.123457"
    with closing(sqlite3.connect(store.path)) as db:
        row = db.execute(
            "SELECT CPUTime,ReadRows,AllocatedExecutorsMin FROM ops_TaskSparkMetric "
            "WHERE record_id=?",
            (record_id,),
        ).fetchone()
        assert row == ("1.123457", None, 0)
    with pytest.raises(ControlError, match="Stale"):
        store.record_spark_metric(
            metric_record(context, status="COMPLETE", revision=1, metrics=metrics)
        )
    with pytest.raises(ControlError, match="source attribution"):
        store.record_spark_metric(
            metric_record(
                context,
                metrics={
                    "CPUTime": {"value": 0, "availability": "AVAILABLE"},
                },
            )
        )
    with pytest.raises(ControlError, match="bounded strings"):
        store.record_spark_metric(
            metric_record(
                context,
                metrics={
                    "CPUTime": {
                        "value": None,
                        "availability": "UNAVAILABLE",
                        "reason": {"not": "a sanitized reason code"},
                    },
                },
            )
        )
    with pytest.raises(ControlError, match="null measurements|Null measurements"):
        store.record_spark_metric(
            metric_record(
                context,
                metrics={
                    "CPUTime": {"value": None, "availability": "UNAVAILABLE"},
                },
            )
        )
    with pytest.raises(ControlError, match="minimum exceeds"):
        store.record_spark_metric(
            metric_record(
                context,
                metrics={
                    "AllocatedExecutorsMin": {
                        "value": 3,
                        "availability": "AVAILABLE",
                        "source": "api",
                    },
                    "AllocatedExecutorsMax": {
                        "value": 2,
                        "availability": "AVAILABLE",
                        "source": "api",
                    },
                },
            )
        )


def test_shared_application_metric_totals_cannot_be_copied_to_another_operation(control):
    store, _ = control
    context, _ = operational_context(store)
    store.record_spark_metric(metric_record(context))
    queue(store, "another", start=END, end="2026-11-20T16:00:00Z")
    another = store.claim("another", "worker")
    foreign = {**context, "operation_id": "another", "attempt_id": another.attempt_id}
    with pytest.raises(ControlError, match="copied/re-attributed"):
        store.record_spark_metric(metric_record(foreign))
    with pytest.raises(ControlError, match="copied/re-attributed"):
        store.record_spark_metric(
            metric_record(foreign, activity_run_id="another-activity", item_id="another-notebook")
        )


def test_quality_outcome_quarantine_lineage_and_critical_publication_gate(control):
    store, _ = control
    context, claim = operational_context(store)
    failed = {
        **context,
        "check": "PATIENT_CONFLICTING_TIES",
        "status": "FAIL",
        "severity": "critical",
        "evidence_digest": "validated-conflict-sha",
        "reason": "CONFLICTING_KEY_TIME_PAYLOAD",
        "expected_value": 0,
        "actual_value": 2,
    }
    quality_id = store.record_quality_outcome(failed)
    quarantine = {
        **context,
        "quality_record_id": quality_id,
        "status": "RECORDED",
        "artifact": "artifact:restricted-quarantine",
        "reason_code": "CONFLICTING_KEY_TIME_PAYLOAD",
        "row_count": 2,
        "schema_digest": "source-schema-sha",
        "identifiers_manifest_ref": "artifact:restricted-identifier-and-cause-manifest",
    }
    quarantine_id = store.record_quarantine_manifest(quarantine)
    assert store.record_quarantine_manifest(quarantine) == quarantine_id
    manifest = store.operational_record("quarantine_manifest", quarantine_id)
    assert manifest["input_versions"] == {"source.patient": "checkpoint-1"}
    with pytest.raises(ControlError, match="critical"):
        store.publish(claim, evidence(store, "observed"), lambda e: True)
    assert not store.output_history("bronze.patient", "demo")
    with pytest.raises(ControlError, match="substitute"):
        store.record_quarantine_manifest(
            {**quarantine, "input_versions": {"source.patient": "new"}}
        )
    pass_id = store.record_quality_outcome(
        {
            **context,
            "check": "OTHER_CHECK",
            "status": "PASS",
            "evidence_digest": "pass-sha",
        }
    )
    with pytest.raises(ControlError, match="failed quality"):
        store.record_quarantine_manifest({**quarantine, "quality_record_id": pass_id})
    queue(store, "unrelated", start=END, end="2026-11-20T16:00:00Z")
    unrelated = store.claim("unrelated", "worker")
    store.record_quality_outcome(
        {
            "operation_id": "unrelated",
            "attempt_id": unrelated.attempt_id,
            "release_version": "1.0.0",
            "check": "NONCRITICAL_COUNT",
            "status": "FAIL",
            "severity": "warning",
            "evidence_digest": "warning-sha",
            "reason": "REVIEW_COUNT",
        }
    )
    store.publish(unrelated, evidence(store, "unrelated", version="8"), lambda e: True)
    assert store.readiness("bronze.patient", "demo")["ready"]


def test_benchmark_trial_steps_preserve_function_occurrences_fixed_inputs_and_isolation(control):
    from test_configuration import make_snapshot
    from test_release import REVIEW

    store, _ = control
    functions = (
        FunctionSpec("names.trim", "normalize_names", {"columns": ["FirstName", "LastName"]}),
        FunctionSpec(
            "state.latest",
            "latest_patient",
            {
                "key": "PatientID",
                "modified": "ModifiedAtUtc",
                "business_columns": [
                    "PatientID",
                    "FirstName",
                    "LastName",
                    "ModifiedAtUtc",
                    "IsDeleted",
                ],
            },
        ),
    )
    manager = ReleaseManager(store)
    manager.publish_candidate(
        make_snapshot("1.1.0", functions=functions),
        registry=FUNCTION_SCHEMAS,
        review_evidence=REVIEW,
    )
    manager.begin_candidate("1.1.0")
    for check in ("tests", "deployment", "environment_publication", "airflow_recognition"):
        manager.record_check("1.1.0", "demo", check, passed=True, evidence="verified:" + check)
    manager.activate("1.1.0", "demo")
    queue(store, "bronze")
    output = publish(store, "bronze")
    queue(
        store,
        "curated",
        task="patient.silver",
        inputs=(InputBinding("bronze.patient", "7", START, END, output),),
    )
    claim = store.claim("curated", "worker")
    context = {
        "operation_id": "curated",
        "attempt_id": claim.attempt_id,
        "release_version": "1.1.0",
    }
    readiness = store.readiness("silver.patient", "demo")
    step = {
        **context,
        "run_id": "benchmark-1",
        "trial": 1,
        "warmup": False,
        "ordinal": 0,
        "function": "normalize_names",
        "status": "RUNNING",
        "started_at": END,
        "compute_context": {"workers": 4, "cores": 8},
    }
    step_id = store.record_benchmark_step(step)
    final = {
        **step,
        "status": "SUCCEEDED",
        "completed_at": "2026-11-20T15:00:01Z",
        "plan_seconds": 0.1,
        "materialization_seconds": 0.4,
        "reread_seconds": 0.5,
        "total_seconds": 1,
        "rows": 20,
        "artifact": "artifact:benchmark/trial-1/step-0",
    }
    assert store.record_benchmark_step(final) == step_id
    assert store.record_benchmark_step(step) == step_id
    first = store.operational_record("benchmark_step", step_id)
    assert first["occurrence_id"] == "names.trim"
    assert first["parameters"] == {"columns": ("FirstName", "LastName")}
    assert first["input_versions"] == {"bronze.patient": "7"}
    assert first["execution_metrics"]["availability"] == "UNAVAILABLE"
    second = {
        **context,
        "run_id": "benchmark-1",
        "trial": 1,
        "warmup": False,
        "ordinal": 1,
        "function": "latest_patient",
        "status": "SUCCEEDED",
        "artifact": "artifact:benchmark/trial-1/step-1",
        "total_seconds": 1,
    }
    store.record_benchmark_step(second)
    trials = store.operational_records("benchmark_trial", "curated")
    assert trials[0]["status"] == "SUCCEEDED"
    assert trials[0]["compute_context"] == {"workers": 4, "cores": 8}
    assert store.readiness("silver.patient", "demo") == readiness
    assert store.operation("curated")["status"] == "RUNNING"
    with pytest.raises(ControlError, match="function/occurrence/parameters"):
        store.record_benchmark_step({**step, "run_id": "bad", "function": "unregistered"})
    with pytest.raises(ControlError, match="frozen trial context"):
        store.record_benchmark_step({**step, "compute_context": {"workers": 5, "cores": 8}})
    with pytest.raises(ControlError, match="substitute"):
        store.record_benchmark_step({**step, "input_versions": {"bronze.patient": "current"}})
    with pytest.raises(ControlError, match="production Tables"):
        store.record_benchmark_step(
            {**step, "artifact": "abfss://workspace/lakehouse/Tables/Patient"}
        )
    with pytest.raises(ControlError, match="bounded benchmark"):
        store.record_benchmark_step({**step, "total_seconds": 1801})


def test_operational_record_reads_are_bounded_and_paginated(control):
    store, _ = control
    context, _ = operational_context(store)
    for index in range(3):
        store.record_cleanup_outcome(
            {
                **context,
                "artifact_id": f"artifact-{index}",
                "status": "SKIPPED",
                "reason": "REFERENCE_HOLD",
            }
        )
    first = store.operational_records("cleanup_outcome", "observed", limit=2)
    second = store.operational_records(
        "cleanup_outcome", "observed", limit=2, after_record_id=first[-1]["record_id"]
    )
    assert len(first) == 2 and len(second) == 1
    assert not {r["record_id"] for r in first} & {r["record_id"] for r in second}
    with pytest.raises(ControlError, match="read budget"):
        store.operational_records("cleanup_outcome", "observed", limit=1001)
    with pytest.raises(ControlError, match="Unknown"):
        store.operational_record("untrusted_sql_identifier", "x")


def queue_waiting(store, operation_id="waiting", *, release_version="1.0.0", **kwargs):
    return store.queue_waiting_operation(
        operation_id=operation_id,
        task_id="patient.silver",
        environment="demo",
        window_start=START,
        window_end=END,
        release_version=release_version,
        **kwargs,
    )


def test_waiting_daily_pins_release_before_upstream_exists_and_survives_restart(control):
    from test_configuration import make_snapshot

    store, clock = control
    queue_waiting(store)
    original = store.operation("waiting")
    assert original["binding_state"] == "UNRESOLVED"
    assert original["declared_inputs"][0]["dataset_id"] == "bronze.patient"
    assert original["declared_inputs"][0]["alias"] == "patient"
    assert store.inputs("waiting") == ()
    with pytest.raises(DependencyBlocked, match="unresolved"):
        store.claim("waiting", "too-early")
    assert store.operation("waiting")["attempt_id"] is None
    assert store.operation("waiting")["status"] == "BLOCKED_BY_DEPENDENCY"
    newer = make_snapshot("1.1.0")
    newer_task = replace(
        newer.tasks[1],
        inputs=(*newer.tasks[1].inputs, InputSpec("source.patient", "newly_required")),
    )
    activate(store, replace(newer, tasks=(newer.tasks[0], newer_task)))
    cycle = store.begin_reconciliation("demo", "reconciler")
    assert cycle["release_version"] == "1.1.0"
    assert "waiting" in store.reconciliation_operations(cycle["reconciliation_id"], "reconciler")
    queue(store, "upstream-new-release")
    output_id = publish(store, "upstream-new-release")
    inputs = (InputBinding("bronze.patient", "7", START, END, output_id),)
    restarted = SQLiteControlStore(store.path, clock=clock)
    assert queue_waiting(restarted) == "waiting"
    with pytest.raises(ControlError, match="different immutable"):
        queue_waiting(restarted, release_version="1.1.0")
    assert restarted.bind_waiting_operation("waiting", inputs) == "waiting"
    bound = restarted.operation("waiting")
    assert bound["release_version"] == "1.0.0"
    assert bound["snapshot_hash"] == original["snapshot_hash"]
    assert bound["request_hash"] == original["request_hash"]
    assert bound["binding_state"] == "BOUND" and bound["binding_hash"]
    assert bound["status"] == "QUEUED"
    claim = restarted.claim("waiting", "pinned-worker")
    assert claim and restarted.operation("waiting")["release_version"] == "1.0.0"
    assert restarted.bind_waiting_operation("waiting", inputs) == "waiting"
    restarted.publish(claim, evidence(restarted, "waiting"), lambda ev: True)
    assert restarted.bind_waiting_operation("waiting", inputs) == "waiting"


def test_waiting_missing_input_never_freezes_partial_bindings_or_starts(control):
    from test_configuration import make_snapshot

    store, _ = control
    snapshot = make_snapshot("1.1.0")
    task = replace(
        snapshot.tasks[1],
        inputs=(*snapshot.tasks[1].inputs, InputSpec("source.patient", "source")),
    )
    activate(store, replace(snapshot, tasks=(snapshot.tasks[0], task)))
    queue_waiting(store, release_version="1.1.0")
    queue(store, "upstream")
    output_id = publish(store, "upstream")
    partial = (InputBinding("bronze.patient", "7", START, END, output_id),)
    with pytest.raises(DependencyBlocked, match="unresolved"):
        store.bind_waiting_operation("waiting", partial)
    assert store.inputs("waiting") == ()
    with pytest.raises(DependencyBlocked, match="unresolved"):
        store.claim("waiting", "no-partial-start")
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM ops_TaskAttempt WHERE operation_id='waiting'"
        ).fetchone() == (0,)
        assert db.execute(
            "SELECT COUNT(*) FROM ops_OperationInput WHERE operation_id='waiting'"
        ).fetchone() == (0,)
    assert store.operation("waiting")["binding_state"] == "UNRESOLVED"
    completed = (*partial, InputBinding("source.patient", "validated-checkpoint-2", START, END))
    store.bind_waiting_operation("waiting", completed)
    assert store.claim("waiting", "complete-start")


def test_waiting_bindings_validate_commits_and_remain_frozen_before_and_after_claim(control):
    store, _ = control
    queue_waiting(store)
    queue(store, "upstream")
    output_id = publish(store, "upstream")
    with pytest.raises(ControlError, match="committed output"):
        store.bind_waiting_operation("waiting", (InputBinding("bronze.patient", "7", START, END),))
    with pytest.raises(ControlError, match="mismatched"):
        store.bind_waiting_operation(
            "waiting", (InputBinding("bronze.patient", "99", START, END, output_id),)
        )
    with pytest.raises(ControlError, match="placeholders"):
        store.bind_waiting_operation(
            "waiting", (InputBinding("bronze.patient", "PENDING", START, END),)
        )
    inputs = (InputBinding("bronze.patient", "7", START, END, output_id),)
    store.bind_waiting_operation("waiting", inputs)
    queue(store, "corrected")
    corrected_id = publish(store, "corrected", version="8")
    changed = (InputBinding("bronze.patient", "8", START, END, corrected_id),)
    with pytest.raises(ControlError, match="cannot be rebound"):
        store.bind_waiting_operation("waiting", changed)
    assert store.inputs("waiting") == (
        replace(inputs[0], source_coverage_start=START, source_coverage_end=END),
    )
    store.claim("waiting", "worker")
    with pytest.raises(ControlError, match="cannot be rebound"):
        store.bind_waiting_operation("waiting", changed)
    with pytest.raises(ControlError, match="deferred daily"):
        store.bind_waiting_operation("corrected", store.inputs("corrected"))
    with pytest.raises(ControlError, match="different immutable"):
        queue(store, "waiting", task="patient.silver", inputs=inputs)


def test_waiting_queue_and_binding_duplicates_are_serialized_and_audited_once(control):
    store, _ = control
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(lambda _: queue_waiting(store), range(6))) == ["waiting"] * 6
    queue(store, "upstream")
    output_id = publish(store, "upstream")
    inputs = (InputBinding("bronze.patient", "7", START, END, output_id),)
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert (
            list(pool.map(lambda _: store.bind_waiting_operation("waiting", inputs), range(6)))
            == ["waiting"] * 6
        )
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute(
            "SELECT kind,COUNT(*) FROM ops_ControlAudit WHERE reference_id='waiting' "
            "AND kind IN ('waiting_queued','waiting_inputs_bound') GROUP BY kind ORDER BY kind"
        ).fetchall() == [("waiting_inputs_bound", 1), ("waiting_queued", 1)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda i: store.claim("waiting", f"worker-{i}"), range(6)))
    assert sum(claim is not None for claim in claims) == 1
    assert store.bind_waiting_operation("waiting", inputs) == "waiting"
    queue_waiting(store, "competing-bindings")
    queue(store, "upstream-correction")
    corrected_id = publish(store, "upstream-correction", version="8")
    corrected = (InputBinding("bronze.patient", "8", START, END, corrected_id),)

    def compete(candidate):
        try:
            return store.bind_waiting_operation("competing-bindings", candidate)
        except ControlError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, (inputs, corrected)))
    assert results.count("competing-bindings") == 1
    assert results.count(None) == 1
    assert tuple(binding.version for binding in store.inputs("competing-bindings")) in (
        ("7",),
        ("8",),
    )


def test_waiting_does_not_bind_last_good_output_while_latest_upstream_failed(control):
    store, _ = control
    queue_waiting(store)
    queue(store, "upstream")
    output_id = publish(store, "upstream")
    queue(store, "failed-upstream")
    store.fail(store.claim("failed-upstream", "worker"), "SOURCE_VALIDATION_FAILED")
    with pytest.raises(DependencyBlocked, match="Latest expected upstream failure"):
        store.bind_waiting_operation(
            "waiting", (InputBinding("bronze.patient", "7", START, END, output_id),)
        )
    assert store.inputs("waiting") == ()
    assert store.operation("waiting")["binding_state"] == "UNRESOLVED"
    queue(store, "corrected-upstream")
    corrected_id = publish(store, "corrected-upstream", version="8")
    store.bind_waiting_operation(
        "waiting", (InputBinding("bronze.patient", "8", START, END, corrected_id),)
    )
    assert store.claim("waiting", "validated-correction")


def test_waiting_bind_rejects_any_prior_attempt_even_without_operation_attempt_pointer(control):
    store, _ = control
    queue_waiting(store)
    queue(store, "upstream")
    output_id = publish(store, "upstream")
    with store.transaction() as tx:
        tx.insert(
            "attempt",
            attempt_id="prior-attempt",
            operation_id="waiting",
            owner="prior",
            fence=1,
            started_at=tx.now,
            completed_at=tx.now,
            status="LEASE_EXPIRED",
        )
    with pytest.raises(ControlError, match="previous attempt"):
        store.bind_waiting_operation(
            "waiting", (InputBinding("bronze.patient", "7", START, END, output_id),)
        )
    assert store.inputs("waiting") == ()
    assert store.operation("waiting")["binding_state"] == "UNRESOLVED"


@pytest.fixture
def coverage_control(protocol_path):
    clock = Clock()
    store = SQLiteControlStore(protocol_path / "coverage.db", clock=clock)
    activate(store)
    return store, clock


def covered_source(store, version, start, end):
    return store.register_source_snapshot(
        "source.patient",
        "demo",
        version,
        start,
        end,
        evidence_digest="verified-generator:" + version,
        artifact_ref="artifact:immutable-source:" + version,
        verify_snapshot=lambda: True,
    )


def test_processing_window_does_not_create_source_freshness_and_silver_inherits(coverage_control):
    store, clock = coverage_control
    source_start = "2026-11-20T13:00:00.0000000"
    source_end = END
    nominal_end = "2026-11-20T20:00:00.0000000"
    snapshot_id = covered_source(store, "real-v1", source_start, source_end)
    source = InputBinding(
        "source.patient",
        "real-v1",
        START,
        nominal_end,
        source_snapshot_id=snapshot_id,
    )
    queue(store, "bronze", end=nominal_end, inputs=(source,))
    assert store.inputs("bronze")[0].source_coverage_end == source_end
    claim = store.claim("bronze", "worker")
    actual = evidence(store, "bronze")
    with pytest.raises(ControlError, match="forged"):
        store.publish(
            claim,
            replace(actual, source_coverage_end=nominal_end),
            lambda ev: True,
        )

    output_id = store.publish(claim, actual, lambda ev: True)
    ready = store.readiness("bronze.patient", "demo")
    assert ready["progress_end"] == nominal_end
    assert ready["source_coverage_end"] == source_end and ready["ready"]
    bronze = InputBinding("bronze.patient", "7", START, nominal_end, output_id)
    queue(store, "silver", task="patient.silver", end=nominal_end, inputs=(bronze,))
    publish(store, "silver")
    silver = store.output_history("silver.patient", "demo")[0]
    assert silver["window_end"] == nominal_end
    assert silver["source_coverage_start"] == source_start
    assert silver["source_coverage_end"] == source_end
    with pytest.raises(ControlError, match="forged"):
        queue(
            store,
            "forged-binding",
            task="patient.silver",
            end=nominal_end,
            inputs=(
                replace(
                    bronze,
                    source_coverage_start=source_start,
                    source_coverage_end=nominal_end,
                ),
            ),
        )
    clock.advance(25 * 3600)
    assert not store.readiness("bronze.patient", "demo")["ready"]
    assert not store.readiness("silver.patient", "demo")["ready"]
    queue(store, "stale-fixed", task="patient.silver", end=nominal_end, inputs=(bronze,))
    with pytest.raises(DependencyBlocked, match="Stale committed coverage"):
        store.claim("stale-fixed", "worker")
    store.queue_waiting_operation(
        operation_id="stale-waiting",
        task_id="patient.silver",
        environment="demo",
        window_start=START,
        window_end=nominal_end,
        release_version="1.0.0",
    )
    with pytest.raises(DependencyBlocked, match="Stale committed coverage"):
        store.bind_waiting_operation("stale-waiting", (bronze,))
    assert store.inputs("stale-waiting") == ()


def test_late_old_source_reconciliation_is_not_fresh_and_does_not_outrank_new_source(
    coverage_control,
):
    store, clock = coverage_control
    old_source_start = "2026-11-20T13:00:00.0000000"
    old_id = covered_source(store, "old-real", old_source_start, END)
    nominal_start = "2026-11-21T22:00:00.0000000"
    nominal_end = "2026-11-22T22:00:00.0000000"
    old = InputBinding(
        "source.patient",
        "old-real",
        nominal_start,
        nominal_end,
        source_snapshot_id=old_id,
    )
    queue(store, "late", start=nominal_start, end=nominal_end, inputs=(old,))
    claim = store.claim("late", "old-worker")
    old_evidence = evidence(store, "late")
    store.fail(claim, "POST_DELTA_PRE_SQL", uncertain=True)
    clock.advance(25 * 3600)
    old_output = store.reconcile_commit("late", old_evidence, lambda ev: True)
    ready = store.readiness("bronze.patient", "demo")
    assert not ready["ready"] and ready["reason"] == "stale_coverage"
    assert ready["progress_end"] == nominal_end
    assert ready["source_coverage_end"] == END
    new_start = "2026-11-21T14:00:00.0000000"
    new_end = "2026-11-21T16:00:00.0000000"
    new_id = covered_source(store, "new-real", new_start, new_end)
    new = InputBinding("source.patient", "new-real", END, new_end, source_snapshot_id=new_id)
    queue(store, "fresh", start=END, end=new_end, inputs=(new,))
    fresh_output = publish(store, "fresh", version="8")
    ready = store.readiness("bronze.patient", "demo")
    assert ready["ready"] and ready["output_id"] == fresh_output
    assert ready["source_coverage_end"] == new_end
    assert ready["progress_end"] == nominal_end  # Logical processing progress is independent.
    assert store.reconcile_commit("late", old_evidence, lambda ev: True) == old_output
    assert store.readiness("bronze.patient", "demo")["output_id"] == fresh_output


def test_current_source_backfill_uses_fresh_full_snapshot_and_silver_keeps_coverage(
    coverage_control,
):
    store, _ = coverage_control
    old_start = "2026-10-01T00:00:00.0000000"
    old_end = "2026-10-02T00:00:00.0000000"
    current_start = "2026-11-20T13:00:00.0000000"
    current_id = covered_source(store, "current-real-v2", current_start, END)
    current = InputBinding(
        "source.patient",
        "current-real-v2",
        current_start,
        END,
        source_snapshot_id=current_id,
        source_coverage_start=current_start,
        source_coverage_end=END,
    )
    queue(
        store,
        "backfill",
        start=old_start,
        end=old_end,
        kind="backfill",
        source_mode="current",
        inputs=(current,),
    )
    output_id = publish(store, "backfill")
    bound = store.inputs("backfill")[0]
    assert bound.version == "current-real-v2" and bound.source_coverage_start == current_start
    bronze = InputBinding("bronze.patient", "7", old_start, old_end, output_id)
    queue(
        store,
        "backfill-silver",
        task="patient.silver",
        start=old_start,
        end=old_end,
        kind="backfill",
        source_mode="current",
        inputs=(bronze,),
    )
    publish(store, "backfill-silver")
    ready = store.readiness("silver.patient", "demo")
    assert ready["ready"] and ready["progress_end"] == old_end
    assert ready["source_coverage_start"] == current_start
    assert ready["source_coverage_end"] == END
    historical_id = covered_source(store, "original-v1", old_start, old_end)
    historical = InputBinding(
        "source.patient",
        "original-v1",
        old_start,
        old_end,
        source_snapshot_id=historical_id,
    )
    queue(
        store,
        "historical-original",
        start=old_start,
        end=old_end,
        kind="backfill",
        source_mode="historical",
        inputs=(historical,),
    )
    publish(store, "historical-original", version="8")
    with pytest.raises(ControlError, match="explicit approval"):
        queue(
            store,
            "silent-substitute",
            start=old_start,
            end=old_end,
            kind="backfill",
            source_mode="historical",
            original_operation_id="historical-original",
            inputs=(current,),
        )
    with pytest.raises(ControlError, match="retained snapshot"):
        queue(
            store,
            "missing-history",
            start=old_start,
            end=old_end,
            kind="backfill",
            source_mode="historical",
            inputs=(InputBinding("source.patient", "original-v1", old_start, old_end),),
        )
    assert store.readiness("bronze.patient", "demo")["source_coverage_end"] == END


def test_strict_store_rejects_unregistered_coverage_and_missing_publication_bounds(
    coverage_control,
):
    store, _ = coverage_control
    with pytest.raises(ControlError, match="registered source snapshot"):
        queue(store, inputs=(InputBinding("source.patient", "unverified", START, END),))
    source_id = covered_source(store, "real", START, END)
    queue(
        store,
        inputs=(InputBinding("source.patient", "real", START, END, source_snapshot_id=source_id),),
    )
    claim = store.claim("daily-1", "worker")
    with pytest.raises(ControlError, match="explicit verified source coverage"):
        store.publish(
            claim,
            replace(
                evidence(store, "daily-1"),
                source_coverage_start=None,
                source_coverage_end=None,
            ),
            lambda ev: True,
        )


def test_unknown_legacy_output_coverage_is_never_inferred_from_processing_time(coverage_control):
    store, _ = coverage_control
    source_id = covered_source(store, "real", START, END)
    queue(
        store,
        "legacy",
        inputs=(InputBinding("source.patient", "real", START, END, source_snapshot_id=source_id),),
    )
    with store.transaction() as tx:
        tx.insert(
            "output",
            output_id="legacy-output",
            operation_id="legacy",
            dataset_id="bronze.patient",
            environment="demo",
            scope="default",
            delta_version="7",
            window_start=START,
            window_end=END,
            evidence_json='{"legacy":true}',
            evidence_hash="legacy-evidence",
            committed_at=tx.now,
            changed_rows=1,
        )
        tx.update(
            "readiness",
            "dataset_id=? AND environment=? AND scope=?",
            ("bronze.patient", "demo", "default"),
            output_id="legacy-output",
            progress_end=END,
            expected_status="SUCCEEDED",
        )
    ready = store.readiness("bronze.patient", "demo")
    assert not ready["ready"] and ready["reason"] == "unverified_source_coverage"
    with pytest.raises(DependencyBlocked, match="unverified"):
        queue(
            store,
            "cannot-infer",
            task="patient.silver",
            inputs=(InputBinding("bronze.patient", "7", START, END, "legacy-output"),),
        )


def test_schedule_health_includes_failed_uncertain_blocked_running_and_success(control):
    store, _ = control
    queue(store, "succeeded")
    publish(store, "succeeded")
    queue(store, "failed")
    store.fail(store.claim("failed", "worker"), "VALIDATION_FAILED")
    queue(store, "uncertain")
    store.fail(store.claim("uncertain", "worker"), "POST_WRITE_UNKNOWN", uncertain=True)
    queue(store, "running", start=END, end="2026-11-20T16:00:00Z")
    store.claim("running", "worker")
    queue(store, "queued", start="2026-11-20T16:00:00Z", end="2026-11-20T17:00:00Z")
    queue_waiting(store, "blocked")
    identifiers = ("succeeded", "failed", "uncertain", "running", "queued", "blocked")
    before = {identifier: store.operation(identifier) for identifier in identifiers}
    with store.transaction() as tx:
        audit_count = tx.one(f"SELECT COUNT(*) AS count FROM {tx.table('audit')}")["count"]
    rows = store.scheduled_operations("demo", START, "2026-11-20T18:00:00Z")
    assert {row["status"] for row in rows} == {
        "SUCCEEDED",
        "FAILED",
        "UNCERTAIN",
        "RUNNING",
        "QUEUED",
        "BLOCKED_BY_DEPENDENCY",
    }
    assert {row["operation_id"] for row in rows} == set(identifiers)
    assert next(row for row in rows if row["operation_id"] == "blocked")["binding_state"] == (
        "UNRESOLVED"
    )
    assert all(row["health_status"] == row["status"] for row in rows)
    assert all(row["release_version"] == "1.0.0" for row in rows)
    assert {identifier: store.operation(identifier) for identifier in identifiers} == before
    with store.transaction() as tx:
        assert tx.one(f"SELECT COUNT(*) AS count FROM {tx.table('audit')}")["count"] == audit_count
    store.flag_corruption("bronze.patient", "demo", "1.0.0", "confirmed-corruption")
    corrupted = store.scheduled_operations("demo", START, "2026-11-20T18:00:00Z")
    assert all(row["corruption_blocked"] and row["health_status"] == "CORRUPT" for row in corrupted)
    assert {row["operation_id"]: row["status"] for row in corrupted} == {
        identifier: operation["status"] for identifier, operation in before.items()
    }


def test_schedule_health_range_kind_order_budget_and_parameters(control):
    store, _ = control
    queue(store, "b-inside")
    queue(store, "a-inside")
    queue(store, "ends-at-start", start="2026-11-19T14:00:00Z", end=START)
    queue(store, "starts-at-end", start=END, end="2026-11-20T16:00:00Z")
    queue(store, "manual-backfill", kind="backfill")
    queue(store, "manual-rerun", kind="rerun")
    rows = store.scheduled_operations(
        "demo",
        "2026-11-19T10:00:00-05:00",
        "2026-11-20T10:00:00-05:00",
    )
    assert [row["operation_id"] for row in rows] == ["a-inside", "b-inside"]
    assert store.scheduled_operations("demo", START, END, 1) == rows[:1]
    assert store.scheduled_operations("different-environment", START, END) == ()
    assert store.scheduled_operations("demo' OR 1=1 --", START, END) == ()
    for invalid in (0, 1001, True, 1.5, "2"):
        with pytest.raises(ValueError, match="read budget"):
            store.scheduled_operations("demo", START, END, invalid)
    with pytest.raises(ValueError, match="positive"):
        store.scheduled_operations("demo", END, START)
    with pytest.raises(ValueError, match="positive"):
        store.scheduled_operations("demo", START, START)


def test_schedule_health_returns_actual_output_coverage_not_nominal_end(coverage_control):
    store, _ = coverage_control
    source_start = "2026-11-20T13:00:00.0000000"
    nominal_end = "2026-11-20T20:00:00.0000000"
    snapshot_id = covered_source(store, "real", source_start, END)
    queue(
        store,
        "scheduled",
        end=nominal_end,
        inputs=(
            InputBinding(
                "source.patient", "real", START, nominal_end, source_snapshot_id=snapshot_id
            ),
        ),
    )
    publish(store, "scheduled")
    (row,) = store.scheduled_operations("demo", START, nominal_end)
    assert row["window_end"] == nominal_end
    assert row["source_coverage_start"] == source_start
    assert row["source_coverage_end"] == END
    with pytest.raises(TypeError):
        row["status"] = "HIDDEN"
