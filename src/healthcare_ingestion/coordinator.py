"""Pinned daily queuing and bounded event/reconciliation coordination."""

from uuid import NAMESPACE_URL, uuid5

from healthcare_ingestion.control_store import ControlError, InputBinding
from healthcare_ingestion.execution import reconcile_operation


def queue_workflow(
    store, workflow, environment, dag_run_id, window_start, window_end, artifacts=None
):
    run_key = (
        "workflow-runs/"
        + str(uuid5(NAMESPACE_URL, "|".join((environment, workflow, dag_run_id))))
        + ".json"
    )
    pinned = artifacts.get(run_key) if artifacts else None
    version = pinned["release_version"] if pinned else store.active_version(environment)
    if artifacts and not pinned:
        artifacts.put(run_key, {"release_version": version, "dag_run_id": dag_run_id})
    snapshot = store.snapshot(version)
    selected = [task for task in snapshot.tasks if task.workflow == workflow and not task.retired]
    if not selected:
        raise ValueError("Unknown active logical workflow.")
    operations = []
    for task in selected:
        identity = str(
            uuid5(
                NAMESPACE_URL,
                "|".join((environment, version, workflow, dag_run_id, task.task_id)),
            )
        )
        if artifacts:
            artifacts.put(
                f"operation-runs/{identity}.json",
                {"dag_run_id": dag_run_id, "release_version": version},
            )
        store.queue_waiting_operation(
            operation_id=identity,
            task_id=task.task_id,
            environment=environment,
            window_start=window_start,
            window_end=window_end,
            release_version=version,
        )
        operations.append(identity)
    return tuple(operations)


def resolve_waiting(store, operation_id, source_binding):
    if store.inputs(operation_id):
        return True
    operation = store.operation(operation_id)
    snapshot = store.snapshot(operation["release_version"])
    task = snapshot.task(operation["task_id"])
    bindings = []
    for spec in task.inputs:
        dataset = snapshot.dataset(spec.dataset_id)
        if dataset.external:
            binding = source_binding(operation, spec)
            if binding is None:
                return False
        else:
            outputs = store.output_history(spec.dataset_id, operation["environment"])
            outputs = [
                output
                for output in outputs
                if output["source_coverage_start"]
                and output["source_coverage_end"]
                and (
                    (operation["kind"] == "backfill" and operation["source_mode"] == "current")
                    or (
                        output["window_start"] <= operation["window_start"]
                        and output["window_end"] >= operation["window_end"]
                    )
                )
            ]
            if not outputs:
                return False
            latest = max(
                outputs,
                key=lambda output: (output["source_coverage_end"], int(output["delta_version"])),
            )
            binding = InputBinding(
                spec.dataset_id,
                latest["delta_version"],
                latest["window_start"],
                latest["window_end"],
                output_id=latest["output_id"],
                source_coverage_start=latest["source_coverage_start"],
                source_coverage_end=latest["source_coverage_end"],
            )
        if binding.dataset_id != spec.dataset_id:
            raise ValueError("Resolver returned another logical input.")
        bindings.append(binding)
    try:
        store.bind_waiting_operation(operation_id, tuple(bindings))
    except ControlError:
        return False
    return True


def reconcile_cycle(store, environment, owner, spark, artifacts, source_binding, submit):
    """No live-owner stealing; submit callbacks own bounded worker invocation."""
    run = store.begin_reconciliation(environment, owner)
    if run is None:
        return None
    identity = run["reconciliation_id"]
    outcomes = {}
    try:
        for operation_id in store.reconciliation_operations(identity, owner):
            store.heartbeat_reconciliation(identity, owner)
            operation = store.operation(operation_id)
            if operation["status"] == "RUNNING":
                continue
            if operation["status"] == "UNCERTAIN":
                outcomes[operation_id] = reconcile_operation(store, operation_id, spark, artifacts)
                continue
            if operation["status"] in {"QUEUED", "BLOCKED_BY_DEPENDENCY"} and resolve_waiting(
                store,
                operation_id,
                source_binding,
            ):
                outcomes[operation_id] = submit(operation_id)
        store.finish_reconciliation(identity, owner)
    except Exception:
        store.finish_reconciliation(identity, owner, error_code="RECONCILIATION_FAILED")
        raise
    return outcomes


def dispatch_events(store, handle):
    return store.dispatch_events(handle, coalesce=True, max_attempts=3, retry_delay_seconds=30)
