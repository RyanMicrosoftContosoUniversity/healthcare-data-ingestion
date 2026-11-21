"""Opt-in isolated full-column Delta step benchmarks, never production publication."""

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Timer

from healthcare_ingestion.patient import REGISTRY


def artifact_path(root, *parts):
    if "://" in root:
        return root.rstrip("/") + "/" + "/".join(parts)
    return str(Path(root).joinpath(*parts))


def benchmark(
    frame,
    functions,
    root,
    persist,
    provenance,
    trials=3,
    warmups=1,
    timeout=1800,
    setup_persist=None,
):
    if trials != 3 or warmups != 1 or not 0 < timeout <= 1800:
        raise ValueError("The approved benchmark profile is one warm-up, three trials, <=30 min.")
    if not provenance.get("framework_version") or not provenance.get("input_versions"):
        raise ValueError("Benchmarks require fixed input versions and an immutable code release.")
    if "tables" in root.replace("\\", "/").lower().split("/") or not root:
        raise ValueError("Benchmark artifacts cannot use a production Tables path.")
    for step in functions:
        if set(step) != {"name", "parameters"} or step["name"] not in REGISTRY:
            raise ValueError("Only registered transformations may be benchmarked.")
    if not functions:
        raise ValueError("A benchmark requires at least one registered transformation.")
    run_id = str(uuid.uuid4())
    spark = frame.sparkSession
    group = f"healthcare-benchmark-{run_id}"
    prior_properties = {
        key: spark.sparkContext.getLocalProperty(key)
        for key in ("spark.jobGroup.id", "spark.job.description", "spark.job.interruptOnCancel")
    }
    spark.sparkContext.setJobGroup(
        group, "Isolated transformation benchmark", interruptOnCancel=True
    )
    timer = Timer(timeout, lambda: spark.sparkContext.cancelJobGroup(group))
    timer.daemon = True
    timer.start()
    started = time.monotonic()
    records = []

    def prepare(trial, action):
        record = {
            **provenance,
            "run_id": run_id,
            "trial": trial,
            "warmup": trial == 0,
            "status": "RUNNING",
            "started_at": datetime.now(UTC).isoformat(),
        }
        if setup_persist:
            setup_persist(record.copy())
        try:
            return action()
        except BaseException as error:
            if setup_persist:
                setup_persist(
                    {
                        **record,
                        "status": "INTERRUPTED"
                        if isinstance(error, (KeyboardInterrupt, SystemExit))
                        else "FAILED",
                        "completed_at": datetime.now(UTC).isoformat(),
                    }
                )
            raise

    try:
        frozen = artifact_path(root, run_id, "input")

        def freeze():
            frame.write.format("delta").mode("errorifexists").save(frozen)
            return spark.read.format("delta").option("versionAsOf", 0).load(frozen)

        current = prepare(0, freeze)
        for trial in range(warmups + trials):
            if trial:
                current = prepare(
                    trial, lambda: spark.read.format("delta").option("versionAsOf", 0).load(frozen)
                )
            for ordinal, step in enumerate(functions):
                record = {
                    **provenance,
                    "run_id": run_id,
                    "trial": trial,
                    "warmup": trial < warmups,
                    "ordinal": ordinal,
                    "function": step["name"],
                    "parameters": step["parameters"],
                    "status": "RUNNING",
                    "started_at": datetime.now(UTC).isoformat(),
                }
                persist(record.copy())
                plan_start = time.monotonic()
                tracker = spark.sparkContext.statusTracker()
                prior_jobs = set(tracker.getJobIdsForGroup(group))
                try:
                    if plan_start - started >= timeout:
                        raise TimeoutError("Benchmark case budget exhausted.")
                    transformed = REGISTRY[step["name"]](current, **step["parameters"])
                    planned = time.monotonic()
                    path = artifact_path(root, run_id, f"trial-{trial}", f"step-{ordinal}")
                    transformed.write.format("delta").mode("errorifexists").save(path)
                    written = time.monotonic()
                    current = spark.read.format("delta").option("versionAsOf", 0).load(path)
                    count = current.rdd.mapPartitions(lambda rows: [sum(1 for _ in rows)]).sum()
                    completed = time.monotonic()
                    record.update(
                        status="SUCCEEDED",
                        plan_seconds=planned - plan_start,
                        materialization_seconds=written - planned,
                        reread_seconds=completed - written,
                        total_seconds=completed - plan_start,
                        rows=count,
                        artifact=path,
                        execution_metrics={
                            "spark_job_ids": sorted(
                                set(tracker.getJobIdsForGroup(group)) - prior_jobs
                            ),
                            "source": "SparkStatusTracker:getJobIdsForGroup",
                        },
                    )
                except BaseException as error:
                    record.update(
                        status="INTERRUPTED"
                        if isinstance(error, (KeyboardInterrupt, SystemExit))
                        else "FAILED",
                        exception_type=type(error).__name__,
                    )
                    raise
                finally:
                    record["completed_at"] = datetime.now(UTC).isoformat()
                    persist(record.copy())
                    records.append(record)
        return records
    finally:
        timer.cancel()
        for key, value in prior_properties.items():
            spark.sparkContext.setLocalProperty(key, value)


def benchmark_task(frame, snapshot, task_id, context, input_versions, root, store):
    from healthcare_ingestion.configuration import thaw

    settings = snapshot.effective_settings(task_id)
    if not settings.get("observability", {}).get("profile_transformations", False):
        return []
    task = snapshot.task(task_id)
    anchor = {key: context[key] for key in ("operation_id", "attempt_id")}
    anchor["release_version"] = snapshot.version
    provenance = {
        **anchor,
        "framework_version": snapshot.version,
        "input_versions": input_versions,
        "snapshot_context": {"snapshot_hash": snapshot.digest},
        "compute_context": thaw(settings.get("execution", {})),
    }
    trials = {}

    def setup_persist(record):
        key = (record["run_id"], record["trial"])
        trials[key] = record
        store.record_benchmark_trial(record)

    def persist(record):
        key = (record["run_id"], record["trial"])
        if key not in trials:
            trials[key] = {
                **anchor,
                "run_id": key[0],
                "trial": key[1],
                "warmup": key[1] == 0,
                "input_versions": input_versions,
                "status": "RUNNING",
                "snapshot_context": provenance["snapshot_context"],
                "compute_context": provenance["compute_context"],
                "started_at": record["started_at"],
            }
            store.record_benchmark_trial(trials[key])
        step = task.functions[record["ordinal"]]
        store.record_benchmark_step(
            {
                **record,
                "occurrence_id": step.occurrence_id,
                "collection_status": "UNAVAILABLE",
            }
        )
        if record["status"] in {"FAILED", "INTERRUPTED"} or (
            record["status"] == "SUCCEEDED" and record["ordinal"] == len(task.functions) - 1
        ):
            trials[key].update(
                status=record["status"],
                completed_at=record["completed_at"],
            )
            store.record_benchmark_trial(trials[key])

    return benchmark(
        frame,
        [{"name": step.function, "parameters": thaw(step.parameters)} for step in task.functions],
        root,
        persist,
        provenance,
        setup_persist=setup_persist,
    )
