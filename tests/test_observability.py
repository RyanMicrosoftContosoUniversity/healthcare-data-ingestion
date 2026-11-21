from datetime import UTC, datetime

import pytest

from healthcare_ingestion.observability import (
    FabricReadClient,
    SparkAttempt,
    cleanup_candidates,
    collect_log,
    metric,
)
from healthcare_ingestion.spark_metrics import collect_metrics


def test_cleanup_protects_uncommitted_referenced_and_indefinite_data():
    artifacts = [
        {"id": "eligible", "kind": "staging", "committed": True},
        {"id": "held", "kind": "staging", "committed": True},
        {"id": "active", "kind": "staging", "committed": False},
        {"id": "bronze", "kind": "bronze", "committed": True},
        {"id": "population", "kind": "population", "committed": True},
    ]
    for artifact in artifacts:
        artifact["committed_at"] = "2026-11-10T12:00:00+00:00"
    assert [
        a["id"] for a in cleanup_candidates(artifacts, {"held"}, datetime(2026, 11, 20, tzinfo=UTC))
    ] == ["eligible"]


def test_collector_never_sends_tokens_to_continuation_other_origin():
    client = FabricReadClient(lambda: "secret", transport=lambda *a, **k: None)
    with pytest.raises(ValueError, match="another origin"):
        client.get("https://unexpected.example/logs")
    assert metric(reason="Unsupported by API")["value"] is None


def test_livy_event_and_executor_routes_bind_correct_evidence():
    import json

    attempt = SparkAttempt("workspace", "item", "notebooks", "session", "application", "1")
    routes = []

    class Client:
        def get(self, route, **_):
            routes.append(route)
            if "type=livy&meta=true" in route:
                return json.dumps({"fileName": "livy.log", "length": 3}).encode()
            if "type=executor&meta=true" in route:
                return json.dumps(
                    [
                        {
                            "containerId": "container-one",
                            "containerLogMeta": [{"fileName": "stderr", "fileSize": "3"}],
                        }
                    ]
                ).encode()
            return b"log"

    def save(_):
        return "protected-artifact"

    assert collect_log(Client(), attempt, "livy", "livy.log", save)["status"] == "COLLECTED"
    assert "/applications/none/logs?type=livy" in routes[-1]
    assert collect_log(Client(), attempt, "event", "events.zip", save)["status"] == "COLLECTED"
    assert routes[-1].endswith("/application/1/logs")
    assert (
        collect_log(Client(), attempt, "executor", "stderr", save, container_id="container-one")[
            "status"
        ]
        == "COLLECTED"
    )
    assert "containerId=container-one" in routes[-1]
    assert collect_log(Client(), attempt, "executor", "stderr", save)["status"] == "UNAVAILABLE"


def test_metric_units_and_unsupported_fields_are_not_fabricated():
    import json

    class Client:
        def get(self, route):
            if route.endswith("/stages"):
                return json.dumps([{"jvmGcTime": 2500, "executorCpuTime": 1_000_000_000}]).encode()
            if route.endswith("/resourceUsage"):
                return json.dumps(
                    {"duration": 1000, "idleTime": 100, "coreEfficiency": 0.5}
                ).encode()
            return b"[]"

    values = collect_metrics(Client(), SparkAttempt("w", "i", "notebooks", "l", "a", "1"))[
        "metrics"
    ]
    assert values["GCTime"]["value"] == 2.5
    assert values["CPUTime"]["value"] == 1
    assert values["UtilizationPercentage"]["value"] == 50
    assert values["ExpectedDuration"]["value"] is None
    assert values["ReadBytes"]["value"] is None
