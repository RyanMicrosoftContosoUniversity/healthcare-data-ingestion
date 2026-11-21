"""Independent, attempt-bound diagnostic collection and typed evidence persistence."""

import hashlib
from datetime import UTC, datetime

from healthcare_ingestion.observability import collect_log
from healthcare_ingestion.spark_metrics import collect_metrics


def collect_attempt(
    store,
    client,
    attempt,
    context,
    files,
    save,
    collection_attempt=0,
    max_attempts=3,
):
    anchor = {key: context[key] for key in ("operation_id", "attempt_id", "release_version")}
    if attempt.attempt_id == "latest":
        raise ValueError("Historical collection requires an exact Spark application attempt.")
    scope = hashlib.sha256(attempt.route().encode()).hexdigest()
    record = {
        **anchor,
        "scope_key": scope,
        "status": "RUNNING",
        "collection_attempt": collection_attempt,
        "max_attempts": max_attempts,
        "spark": attempt.__dict__,
        "started_at": datetime.now(UTC).isoformat(),
    }
    collection_id = store.record_diagnostic_attempt(record)
    try:
        return _collect(store, client, attempt, context, files, save, record, collection_id)
    except BaseException as error:
        store.record_diagnostic_attempt(
            {
                **record,
                "status": "INTERRUPTED"
                if isinstance(error, (KeyboardInterrupt, SystemExit))
                else "FAILED",
                "availability": "UNAVAILABLE",
                "reason": "EVIDENCE_COLLECTION_FAILED",
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        raise


def _collect(store, client, attempt, context, files, save, record, collection_id):
    anchor = {key: context[key] for key in ("operation_id", "attempt_id", "release_version")}
    logs = []
    for file in files:
        body_digest = {}

        def save_content(content):
            body_digest["sha256"] = hashlib.sha256(content).hexdigest()
            return save(file, content)

        log = collect_log(
            client,
            attempt,
            file["kind"],
            file["filename"],
            save_content,
            container_id=file.get("container_id"),
        )
        kind = "rolling_driver" if file["kind"] == "rollingdriver" else file["kind"]
        identity = hashlib.sha256(
            (
                attempt.route()
                + ":"
                + str(sorted(file.items()))
                + ":"
                + body_digest.get("sha256", "unavailable")
            ).encode()
        ).hexdigest()
        store.record_diagnostic_log(
            {
                **anchor,
                "collection_id": collection_id,
                "kind": kind,
                "filename": file["filename"],
                "source_identity": identity,
                "status": "SUCCEEDED" if log["status"] == "COLLECTED" else "UNAVAILABLE",
                "availability": "AVAILABLE" if log["status"] == "COLLECTED" else "UNAVAILABLE",
                "reason": log.get("reason"),
                "artifact": log.get("artifact"),
                "bytes": log.get("bytes"),
                "sha256": body_digest.get("sha256"),
                "collected_at": log["collected_at"],
                "retrieval_context": attempt.__dict__,
            }
        )
        logs.append(log)
    metrics = collect_metrics(client, attempt)
    store.record_spark_metric(
        {
            **anchor,
            "activity_run_id": context["activity_run_id"],
            "workspace_id": attempt.workspace_id,
            "item_id": attempt.item_id,
            "item_type": attempt.item_type,
            "livy_id": attempt.livy_id,
            "application_id": attempt.application_id,
            "application_attempt_id": attempt.attempt_id,
            "metrics": metrics["metrics"],
            "status": metrics["status"],
            "execution_evidence": {"failures": metrics["failures"]},
            "collected_at": datetime.now(UTC).isoformat(),
        }
    )
    failed = bool(metrics["failures"]) or any(log["status"] == "UNAVAILABLE" for log in logs)
    store.record_diagnostic_attempt(
        {
            **record,
            "status": "UNAVAILABLE" if failed else "SUCCEEDED",
            "availability": "UNAVAILABLE" if failed else "AVAILABLE",
            "reason": "EVIDENCE_COLLECTION_UNAVAILABLE" if failed else None,
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    return {"collection_id": collection_id, "logs": logs, "metrics": metrics}
