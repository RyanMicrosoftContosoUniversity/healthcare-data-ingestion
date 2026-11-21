"""Explicitly sourced application-attempt metrics; unavailable comparison fields stay null."""

import json
import math

from healthcare_ingestion.observability import metric

METRIC_FIELDS = (
    "ShuffleWriteRecords",
    "AllocatedExecutorsMin",
    "AllocatedExecutorsMax",
    "IsAnomalous",
    "ExpectedDuration",
    "PotentialCausesJson",
    "TotalDuration",
    "JobCount",
    "QueryCount",
    "TaskCount",
    "ReadRows",
    "WriteRows",
    "JoinCount",
    "ScanCount",
    "FilterCount",
    "UnionCount",
    "CollectCount",
    "HashAggregateCount",
    "ExchangeCount",
    "ShuffleReadLocalBytes",
    "ShuffleReadRemoteBytes",
    "ShuffleWriteBytes",
    "ReadBytes",
    "WriteBytes",
    "MemorySpilledBytes",
    "DiskSpilledBytes",
    "GCTime",
    "StageCount",
    "ShuffleMapStageCount",
    "ResultStageCount",
    "CompilationTime",
    "ExecutionTime",
    "IdleTime",
    "CoreAllocation",
    "UtilizationPercentage",
    "TaskDuration",
    "ShuffleTime",
    "IOTime",
    "CPUTime",
    "ShuffleReadTime",
    "ShuffleWriteTime",
    "ReadTime",
    "WriteTime",
    "SerializationTime",
    "DeserializeTime",
    "ExecutorComputingTime",
    "ApplicationRunTime",
    "OverheadTime",
    "QueueingTime",
    "StartingTime",
)

STAGE_FIELDS = {
    "TaskCount": ("numTasks", 1),
    "ShuffleWriteRecords": ("shuffleWriteRecords", 1),
    "ShuffleReadLocalBytes": ("shuffleReadLocalBytes", 1),
    "ShuffleReadRemoteBytes": ("shuffleReadRemoteBytes", 1),
    "ShuffleWriteBytes": ("shuffleWriteBytes", 1),
    "ReadBytes": ("inputBytes", 1),
    "WriteBytes": ("outputBytes", 1),
    "ReadRows": ("inputRecords", 1),
    "WriteRows": ("outputRecords", 1),
    "MemorySpilledBytes": ("memoryBytesSpilled", 1),
    "DiskSpilledBytes": ("diskBytesSpilled", 1),
    "GCTime": ("jvmGcTime", 1000),
    "CPUTime": ("executorCpuTime", 1_000_000_000),
    "ShuffleReadTime": ("shuffleReadFetchWaitTime", 1000),
    "ShuffleWriteTime": ("shuffleWriteTime", 1_000_000_000),
    "ExecutorComputingTime": ("executorRunTime", 1000),
}


def collect_metrics(client, attempt):
    values = {field: metric(reason="No verified comparable API field") for field in METRIC_FIELDS}
    failures = {}

    def number(value):
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        )

    def read(endpoint):
        try:
            return json.loads(client.get(attempt.route() + endpoint))
        except (OSError, ValueError) as error:
            failures[endpoint] = type(error).__name__
            return None

    jobs, queries, stages = read("/jobs"), read("/sql"), read("/stages")
    for field, records, endpoint in (
        ("JobCount", jobs, "/jobs"),
        ("QueryCount", queries, "/sql"),
        ("StageCount", stages, "/stages"),
    ):
        if isinstance(records, list) and all(isinstance(row, dict) for row in records):
            values[field] = metric(len(records), source=endpoint + ":count")
        elif records is not None:
            failures[endpoint] = "INVALID_RESPONSE_SHAPE"
    if isinstance(stages, list):
        for field, (key, divisor) in STAGE_FIELDS.items():
            if all(isinstance(row, dict) and number(row.get(key)) for row in stages):
                total = sum(row[key] for row in stages)
                values[field] = metric(
                    total if divisor == 1 else total / divisor,
                    source=f"/stages:{key}:sum/divide-by-{divisor}",
                )
    resources = read("/resourceUsage")
    if isinstance(resources, dict):
        for field, key, divisor in (
            ("TotalDuration", "duration", 1000),
            ("ApplicationRunTime", "duration", 1000),
            ("IdleTime", "idleTime", 1000),
        ):
            if number(resources.get(key)):
                values[field] = metric(resources[key] / divisor, source="/resourceUsage:" + key)
        if number(resources.get("coreEfficiency")) and resources["coreEfficiency"] <= 1:
            values["UtilizationPercentage"] = metric(
                resources["coreEfficiency"] * 100,
                source="/resourceUsage:coreEfficiency*100",
            )
        data = resources.get("data", {})
        if not isinstance(data, dict):
            failures["/resourceUsage"] = "INVALID_RESPONSE_SHAPE"
            data = {}
        partials = data.get("isPartials", [])
        times, cores = data.get("timestamps", []), data.get("allocatedCores", [])
        if (
            isinstance(times, list)
            and isinstance(cores, list)
            and isinstance(partials, list)
            and len(times) > 1
            and len(times) == len(cores) == len(partials)
            and all(type(value) is bool for value in partials)
            and not any(partials)
            and all(number(value) for value in times + cores)
            and all(b > a for a, b in zip(times, times[1:]))
        ):
            integral = sum(cores[i] * (times[i + 1] - times[i]) for i in range(len(times) - 1))
            values["CoreAllocation"] = metric(
                integral / (times[-1] - times[0]),
                source="/resourceUsage:allocatedCores:left-sample-time-weighted-average",
            )
    elif resources is not None:
        failures["/resourceUsage"] = "INVALID_RESPONSE_SHAPE"
    return {
        **attempt.__dict__,
        "metrics": values,
        "failures": failures,
        "status": "PARTIAL"
        if failures or any(value["availability"] == "UNAVAILABLE" for value in values.values())
        else "COMPLETE",
    }
