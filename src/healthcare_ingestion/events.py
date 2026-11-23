"""Durable mandatory events, independent of logging verbosity and data readiness."""

import hashlib
import math
import statistics
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from healthcare_ingestion.artifacts import encoded


class EventSink:
    def __init__(self, artifacts, deliver=None):
        self.artifacts, self.deliver = artifacts, deliver

    def emit(self, event, context):
        allowed = {
            "operation_id",
            "attempt_id",
            "release_version",
            "task_id",
            "environment",
            "reason_code",
            "reconciliation_id",
            "source_coverage_end",
            "deadline_at",
        }
        if set(context) - allowed:
            raise ValueError("Mandatory event context must contain operational metadata only.")
        identity = hashlib.sha256(encoded({"event": event, "context": context})).hexdigest()
        key = f"events/{identity}.json"
        row = self.artifacts.get(key) or {
            "TimeGenerated": datetime.now(UTC).isoformat(),
            "Level": "INFO" if event in {"RunSucceeded", "ControlHeartbeat"} else "ERROR",
            "Event": event,
            "ExceptionType": "",
            "Context": {**context, "event_id": identity},
        }
        self.artifacts.put(key, row)
        pending = f"event-outbox/{identity}.json"
        delivered = f"event-delivery/{identity}.json"
        if self.artifacts.get(delivered):
            self.artifacts.discard_event(pending)
            return "DELIVERED"
        self.artifacts.put(pending, {"event": event, "context": context})
        if self.deliver is None:
            return "QUEUED"
        try:
            self.deliver(
                {
                    **row,
                    "TimeGenerated": datetime.now(UTC).isoformat(),
                    "Context": {**row["Context"], "occurred_at": row["TimeGenerated"]},
                }
            )
        except Exception:
            return "UNAVAILABLE"
        self.artifacts.put(delivered, {"event_id": identity, "status": "DELIVERED"})
        self.artifacts.discard_event(pending)
        return "DELIVERED"

    def replay(self, limit=1000):
        results = {}
        for key in self.artifacts.pending_events(limit):
            pending = self.artifacts.get(key)
            if pending:
                results[key] = self.emit(pending["event"], pending["context"])
        return results


def schedule_signals(operation, bindings, now):
    if operation["kind"] == "backfill":
        return ()
    end = datetime.fromisoformat(operation["window_end"].replace("Z", "+00:00"))
    end = end.replace(tzinfo=UTC) if end.tzinfo is None else end
    deadline = end.astimezone(ZoneInfo("America/New_York")).replace(
        hour=11, minute=0, second=0, microsecond=0
    )
    signals = []
    completed = operation.get("completed_at") or (
        operation.get("updated_at") if operation["status"] == "SUCCEEDED" else None
    )
    if completed:
        completed = datetime.fromisoformat(completed.replace("Z", "+00:00"))
        completed = completed.replace(tzinfo=UTC) if completed.tzinfo is None else completed
    if now >= deadline and (
        operation["status"] != "SUCCEEDED"
        or operation.get("corruption_blocked", False)
        or (completed is not None and completed > deadline)
    ):
        signals.append("DeadlineMissed")
    if now >= deadline:
        coverage = [binding.source_coverage_end for binding in bindings]
        if not coverage or any(value is None for value in coverage):
            signals.append("FreshnessMissed")
        else:
            for value in coverage:
                actual = datetime.fromisoformat(value.replace("Z", "+00:00"))
                actual = actual.replace(tzinfo=UTC) if actual.tzinfo is None else actual
                if (now - actual).total_seconds() > 24 * 60 * 60:
                    signals.append("FreshnessMissed")
                    break
    return tuple(signals)


def duration_regression(current, baseline, *, ratio, minimum_samples):
    if (
        type(minimum_samples) is not int
        or minimum_samples < 2
        or type(ratio) not in {int, float}
        or not math.isfinite(ratio)
        or ratio <= 1
    ):
        raise ValueError("Explicit comparable-duration alert policy is required.")
    keys = ("task_id", "compute_profile", "input_schema", "volume_group")
    values = [
        row["seconds"]
        for row in baseline
        if all(row[key] == current[key] for key in keys)
        and type(row["seconds"]) in {int, float}
        and math.isfinite(row["seconds"])
        and row["seconds"] > 0
    ]
    seconds = current["seconds"]
    return bool(
        len(values) >= minimum_samples
        and type(seconds) in {int, float}
        and math.isfinite(seconds)
        and seconds > statistics.median(values) * ratio
    )


def memory_pressure(samples, *, fraction, consecutive):
    if (
        type(fraction) not in {int, float}
        or not 0 < fraction <= 1
        or type(consecutive) is not int
        or consecutive < 2
    ):
        raise ValueError("Explicit sustained-memory alert policy is required.")
    streak = 0
    for sample in samples:
        used, allocated = sample["used_bytes"], sample["allocated_bytes"]
        if (
            type(used) not in {int, float}
            or type(allocated) not in {int, float}
            or not math.isfinite(used)
            or not math.isfinite(allocated)
            or used < 0
            or allocated <= 0
        ):
            streak = 0
            continue
        streak = streak + 1 if used / allocated >= fraction else 0
        if streak >= consecutive:
            return True
    return False
