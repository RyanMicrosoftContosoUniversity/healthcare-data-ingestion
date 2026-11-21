"""Machine-authenticated coordination; ambiguous job submissions are never retried blindly."""

import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from healthcare_ingestion.artifacts import encoded
from healthcare_ingestion.configuration import thaw
from healthcare_ingestion.control_store import ControlError
from healthcare_ingestion.coordinator import queue_workflow
from healthcare_ingestion.observability import FABRIC_ENDPOINT, FabricReadClient, SameOriginRedirect
from healthcare_ingestion.runtime import ConfiguredCredential, bootstrap


class FabricJobs:
    def __init__(self, credential, transport=None):
        self.token = lambda: credential.get_token("https://api.fabric.microsoft.com/.default").token
        self.read = FabricReadClient(self.token, transport=transport)
        self.transport = transport or urllib.request.build_opener(SameOriginRedirect()).open

    def submit(self, workspace, item, parameters, artifacts, key, now=None):
        UUID(workspace)
        UUID(item)
        now = now or datetime.now(UTC)
        receipt = artifacts.get(key + "/receipt.json")
        if receipt:
            return receipt
        route = f"workspaces/{workspace}/items/{item}/jobs/instances"
        if artifacts.get(key + "/intent.json"):
            return {"status": "SUBMISSION_UNCERTAIN"}
        markers = []
        for operation in json.loads(parameters.get("operation_ids_json", "[]")):
            UUID(operation)
            for sequence in range(1, 65):
                marker = f"dispatch-operations/{operation}/{sequence}.json"
                prior = artifacts.get(marker)
                if prior is None:
                    markers.append(marker)
                    break
                previous = artifacts.get(prior["dispatch_key"] + "/receipt.json")
                if previous is None:
                    return {"status": "SUBMISSION_UNCERTAIN"}
                if previous["workspace_id"] != workspace or previous["item_id"] != item:
                    raise ValueError("A pinned operation cannot switch its deployed notebook.")
                job = json.loads(self.read.get(route + "/" + previous["job_id"]))
                if job["status"] not in {"Completed", "Failed", "Cancelled", "Deduped"}:
                    return {"status": "ALREADY_RUNNING", "job_id": previous["job_id"]}
            else:
                return {"status": "DISPATCH_LIMIT_REQUIRES_OPERATOR"}
        for page in self.read.pages(route):
            for job in page.get("value", []):
                started = datetime.fromisoformat(job["startTimeUtc"].replace("Z", "+00:00"))
                if started >= now - timedelta(minutes=5) or job["status"] in {
                    "NotStarted",
                    "InProgress",
                }:
                    return {"status": "RECENT_JOB_REQUIRES_CORRELATION", "job_id": job["id"]}
        body = encoded(
            {
                "executionData": {
                    "parameters": {
                        name: {"value": value, "type": "string"}
                        for name, value in parameters.items()
                    }
                }
            }
        )
        for marker in markers:
            artifacts.put(marker, {"dispatch_key": key})
        artifacts.put(
            key + "/intent.json",
            {
                "workspace_id": workspace,
                "item_id": item,
                "parameters_digest": hashlib.sha256(body).hexdigest(),
                "requested_at": now.isoformat(),
            },
        )
        request = urllib.request.Request(
            FABRIC_ENDPOINT + route + "?jobType=RunNotebook",
            body,
            {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"},
            method="POST",
        )
        # Deliberately no POST retries, even on a timeout or lost receipt.
        with self.transport(request, timeout=30) as response:
            location = response.headers["Location"]
            parsed = urllib.parse.urlsplit(location)
            if parsed.scheme != "https" or parsed.netloc != "api.fabric.microsoft.com":
                raise ValueError("Unexpected Fabric job receipt origin.")
            identity = parsed.path.rstrip("/").split("/")[-1]
            UUID(identity)
        receipt = {
            "job_id": identity,
            "workspace_id": workspace,
            "item_id": item,
            "status": "SUBMITTED",
        }
        artifacts.put(key + "/receipt.json", receipt)
        return receipt


def _config():
    return json.loads(Path(os.environ["HC_RUNTIME_CONFIG_PATH"]).read_text())


def execution_signature(snapshot, task_id):
    settings = snapshot.effective_settings(task_id)
    return {
        "execution": {
            key: settings["execution"][key]
            for key in ("notebook_ref", "environment_ref", "compute_profile_ref")
        },
        "spark": thaw(settings.get("spark", {})),
    }


def _submit_group(worker, config, client, operations, cycle):
    first = worker.store.operation(operations[0])
    snapshot = worker.store.snapshot(first["release_version"])
    workflow = snapshot.task(first["task_id"]).workflow
    signature = execution_signature(snapshot, first["task_id"])
    if any(
        worker.store.operation(identity)["release_version"] != snapshot.version
        or execution_signature(snapshot, worker.store.operation(identity)["task_id"]) != signature
        for identity in operations
    ):
        raise ValueError("Different pinned execution profiles require separate submissions.")
    profile = hashlib.sha256(encoded(signature)).hexdigest()
    binding = config.get("execution_bindings", {}).get(f"{snapshot.version}:{profile}")
    if binding:
        if binding["signature"] != signature:
            raise ValueError("The deployed notebook binding differs from its execution profile.")
        item = binding["notebook_id"]
    else:
        task = snapshot.task(first["task_id"])
        stage = snapshot.dataset(task.primary_output).layer
        defaults = {
            **thaw(snapshot.framework_defaults.get("execution", {})),
            **thaw(snapshot.stage_defaults.get(stage, {}).get("execution", {})),
        }
        if signature["execution"] != {
            key: defaults.get(key) for key in signature["execution"]
        } or any(signature["spark"].values()):
            raise ValueError("Execution overrides require an explicit deployed profile binding.")
        item = config["release_notebooks"][f"{snapshot.version}-{workflow}"]
    identity = str(uuid5(NAMESPACE_URL, "|".join((*sorted(operations), cycle))))
    origin = worker.artifacts.get(f"operation-runs/{operations[0]}.json")
    return client.submit(
        config["data_workspace_id"],
        item,
        {
            "runtime_config_json": json.dumps(config),
            "operation_ids_json": json.dumps(operations),
            "owner": "airflow-" + identity,
            "dag_run_id": origin["dag_run_id"] if origin else first.get("dag_run_id") or cycle,
        },
        worker.artifacts,
        "dispatch/" + identity,
    )


def run_workflow(workflow, **context):
    config = _config()
    worker = bootstrap(config, None)
    credential = ConfiguredCredential(config["identities"]["orchestrator"])
    cycle = context["dag_run"].run_id
    operations = queue_workflow(
        worker.store,
        workflow,
        config["environment"],
        cycle,
        context["data_interval_start"].astimezone(UTC).isoformat(),
        context["data_interval_end"].astimezone(UTC).isoformat(),
        artifacts=worker.artifacts,
    )
    groups = {}
    for identity in operations:
        operation = worker.store.operation(identity)
        snapshot = worker.store.snapshot(operation["release_version"])
        signature = encoded(execution_signature(snapshot, operation["task_id"]))
        groups.setdefault(signature, []).append(identity)
    client = FabricJobs(credential)
    return {
        hashlib.sha256(signature).hexdigest(): _submit_group(worker, config, client, group, cycle)
        for signature, group in groups.items()
    }


def coordinate_pending(config=None):
    config = config or _config()
    worker = bootstrap(config, None)
    credential = ConfiguredCredential(config["identities"]["orchestrator"])
    owner = "airflow-reconciliation"
    run = worker.store.begin_reconciliation(config["environment"], owner)
    if run is None:
        return {}
    identity = run["reconciliation_id"]
    outcomes = {}
    try:
        _expected_daily(worker, config)
        worker.events.replay()
        records = _schedule_health(worker, config)
        _retry_failed(worker, records)
        groups = {}
        for operation_id in worker.store.reconciliation_operations(identity, owner):
            worker.store.heartbeat_reconciliation(identity, owner)
            operation = worker.store.operation(operation_id)
            if operation["status"] not in {"QUEUED", "BLOCKED_BY_DEPENDENCY", "UNCERTAIN"}:
                continue
            snapshot = worker.store.snapshot(operation["release_version"])
            origin = worker.artifacts.get(f"operation-runs/{operation_id}.json")
            key = (
                snapshot.version,
                snapshot.task(operation["task_id"]).workflow,
                origin["dag_run_id"] if origin else operation.get("dag_run_id") or operation_id,
                hashlib.sha256(
                    encoded(execution_signature(snapshot, operation["task_id"]))
                ).hexdigest(),
            )
            groups.setdefault(key, []).append(operation_id)
        client = FabricJobs(credential)
        for key, operations in groups.items():
            outcomes["/".join(key)] = _submit_group(worker, config, client, operations, identity)
        worker.store.finish_reconciliation(identity, owner)
        worker.events.emit(
            "ControlHeartbeat",
            {"environment": config["environment"], "reconciliation_id": identity},
        )
    except Exception:
        worker.store.finish_reconciliation(identity, owner, error_code="RECONCILIATION_FAILED")
        raise
    return outcomes


def _expected_daily(worker, config, now=None):
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo("America/New_York"))
    end = local.replace(hour=10, minute=0, second=0, microsecond=0)
    if local < end:
        return
    start = end - timedelta(days=1)
    snapshot = worker.store.snapshot(worker.store.active_version(config["environment"]))
    cycle = "scheduled__" + start.astimezone(UTC).isoformat()
    for workflow in sorted({task.workflow for task in snapshot.tasks if not task.retired}):
        queue_workflow(
            worker.store,
            workflow,
            config["environment"],
            cycle,
            start.astimezone(UTC).isoformat(),
            end.astimezone(UTC).isoformat(),
            artifacts=worker.artifacts,
        )


def _schedule_health(worker, config, now=None):
    from healthcare_ingestion.events import schedule_signals

    now = now or datetime.now(UTC)
    operations = worker.store.scheduled_operations(
        config["environment"],
        (now - timedelta(days=7)).isoformat(),
        now.isoformat(),
    )
    latest = {}
    for operation in operations:
        key = operation["task_id"]
        latest[key] = max(latest.get(key, operation["window_end"]), operation["window_end"])
    for operation in operations:
        for signal in schedule_signals(
            operation, worker.store.inputs(operation["operation_id"]), now
        ):
            if (
                signal == "FreshnessMissed"
                and operation["window_end"] != latest[operation["task_id"]]
            ):
                continue
            worker.events.emit(
                signal,
                {
                    "operation_id": operation["operation_id"],
                    "release_version": operation["release_version"],
                    "task_id": operation["task_id"],
                    "environment": operation["environment"],
                },
            )
    return operations


def _retry_failed(worker, operations, now=None):
    now = now or datetime.now(UTC)
    for operation in operations:
        if operation["status"] != "FAILED" or not operation.get("attempt_id"):
            continue
        marker = worker.artifacts.get(
            f"{operation['operation_id']}/transient-{operation['attempt_id']}.json"
        )
        if not marker or marker["attempt_id"] != operation["attempt_id"]:
            continue
        snapshot = worker.store.snapshot(operation["release_version"])
        delay = snapshot.effective_settings(operation["task_id"])["scheduler"][
            "retry_delay_seconds"
        ]
        failed = datetime.fromisoformat(operation["updated_at"].replace("Z", "+00:00"))
        failed = failed.replace(tzinfo=UTC) if failed.tzinfo is None else failed
        if now < failed + timedelta(seconds=delay):
            continue
        current = worker.store.operation(operation["operation_id"])
        if current["status"] != "FAILED" or current["attempt_id"] != operation["attempt_id"]:
            continue
        try:
            worker.store.retry_operation(operation["operation_id"])
        except ControlError:
            continue  # The authoritative retry budget or approval gate remains in force.
