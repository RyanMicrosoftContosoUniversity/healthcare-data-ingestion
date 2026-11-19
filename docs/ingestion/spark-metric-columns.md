# Nullable Spark Metric Columns

These columns extend `ops.SparkApplicationRunMetric` in the proposed control-store design. All are nullable. Unsupported/delayed/not-applicable telemetry is null with an explicit reason in `SourceMappingJson`; never substitute zero. The allocated executor range has two separately stored `int` fields.

This is a storage contract, not a claim that every comparison-screen field has a supported collection API. Confirm source mapping and units before implementation.

| Field | Proposed SQL Data Type | Unit / Representation |
| --- | --- | --- |
| `ShuffleWriteRecords` | `bigint` | Records |
| `AllocatedExecutorsMin`, `AllocatedExecutorsMax` | `int` each | Executor range |
| `IsAnomalous` | `bit` | Anomaly flag |
| `ExpectedDuration` | `decimal(20,6)` | Seconds |
| `PotentialCausesJson` | `nvarchar(max)` | JSON array of causes and available estimated contribution percentages |
| `TotalDuration` | `decimal(20,6)` | Seconds |
| `JobCount` | `bigint` | Count |
| `QueryCount` | `bigint` | Count |
| `TaskCount` | `bigint` | Count |
| `ReadRows` | `bigint` | Rows |
| `WriteRows` | `bigint` | Rows |
| `JoinCount` | `bigint` | Count |
| `ScanCount` | `bigint` | Count |
| `FilterCount` | `bigint` | Count |
| `UnionCount` | `bigint` | Count |
| `CollectCount` | `bigint` | Count |
| `HashAggregateCount` | `bigint` | Count |
| `ExchangeCount` | `bigint` | Count |
| `ShuffleReadLocalBytes` | `bigint` | Bytes |
| `ShuffleReadRemoteBytes` | `bigint` | Bytes |
| `ShuffleWriteBytes` | `bigint` | Bytes |
| `ReadBytes` | `bigint` | Bytes |
| `WriteBytes` | `bigint` | Bytes |
| `MemorySpilledBytes` | `bigint` | Bytes |
| `DiskSpilledBytes` | `bigint` | Bytes |
| `GCTime` | `decimal(20,6)` | Seconds |
| `StageCount` | `bigint` | Count |
| `ShuffleMapStageCount` | `bigint` | Count |
| `ResultStageCount` | `bigint` | Count |
| `CompilationTime` | `decimal(20,6)` | Seconds |
| `ExecutionTime` | `decimal(20,6)` | Seconds |
| `IdleTime` | `decimal(20,6)` | Seconds |
| `CoreAllocation` | `decimal(18,4)` | Average allocated cores |
| `UtilizationPercentage` | `decimal(9,4)` | Percent |
| `TaskDuration` | `decimal(20,6)` | Seconds |
| `ShuffleTime` | `decimal(20,6)` | Seconds |
| `IOTime` | `decimal(20,6)` | Seconds |
| `CPUTime` | `decimal(20,6)` | Seconds |
| `ShuffleReadTime` | `decimal(20,6)` | Seconds |
| `ShuffleWriteTime` | `decimal(20,6)` | Seconds |
| `ReadTime` | `decimal(20,6)` | Seconds |
| `WriteTime` | `decimal(20,6)` | Seconds |
| `SerializationTime` | `decimal(20,6)` | Seconds |
| `DeserializeTime` | `decimal(20,6)` | Seconds |
| `ExecutorComputingTime` | `decimal(20,6)` | Seconds |
| `ApplicationRunTime` | `decimal(20,6)` | Seconds |
| `OverheadTime` | `decimal(20,6)` | Seconds |
| `QueueingTime` | `decimal(20,6)` | Seconds |
| `StartingTime` | `decimal(20,6)` | Seconds |

Reference: `https://learn.microsoft.com/en-us/fabric/data-engineering/spark-comparison-runs#comparison-metrics`.
