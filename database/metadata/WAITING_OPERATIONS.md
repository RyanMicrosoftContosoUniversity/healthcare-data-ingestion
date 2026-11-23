# Deferred daily operation contract

This supports the three logical workflows' daily DAG/event/reconciliation scheduling;
it does not change releases, callbacks, Delta publication or manual/backfill semantics.
There is no deployment or live Fabric SQL verification in this implementation.

## Exact APIs

Both production `SqlServerControlStore` and durable local-reference `SQLiteControlStore`
inherit these methods from `healthcare_ingestion.control_store.ControlStore`:

```python
queue_waiting_operation(
    self, *, operation_id: str, task_id: str, environment: str,
    window_start: str | datetime, window_end: str | datetime,
    release_version: str,
) -> str

bind_waiting_operation(
    self, operation_id: str, inputs: tuple[InputBinding, ...],
) -> str
```

Both return `operation_id` on success or an identical replay. `release_version` is
**mandatory**, supplied by the DAG run; the store never substitutes the currently active
release. It must have been activated/approved in the requested environment.

```python
store.queue_waiting_operation(
    operation_id="dag-run:patient-silver",
    task_id="curate.clarity.patient",
    environment="demo",
    window_start=start,
    window_end=end,
    release_version=dag_run_release,
)

# Parent resolver checks compatibility/retention and selects actual published input(s).
store.bind_waiting_operation(
    "dag-run:patient-silver",
    (
        InputBinding(
            dataset_id="bronze.clarity.patient",
            version=actual_delta_version,
            window_start=actual_committed_start,
            window_end=actual_committed_end,
            output_id=actual_output_id,
        ),
    ),
)
```

`InputBinding(dataset_id, version, window_start, window_end, output_id=None,
source_snapshot_id=None, source_coverage_start=None, source_coverage_end=None)` is the
frozen dataclass, with independent source-coverage fields appended. Versions are real strings,
coverage is normalized UTC with seven fractional digits, and the interval is half-open.
Delta inputs require an exact committed `output_id`; selected source snapshots must match
their registered dataset/environment/scope/version and coverage and remain retained.
Production current checkpoints also require verified registered source coverage; the
extractor independently verifies the actual SQL checkpoint/capture. See `SOURCE_COVERAGE.md`.
`PENDING` is not an acceptable deferred data version.

## Durable intent and read contract

Queuing atomically persists a normal daily `TaskOperation` with the pinned task, release,
snapshot hash, environment/scope and window, plus an `ops.WaitingOperation` guard containing
the exact snapshot-derived input declarations. Each declaration has:

```python
{
    "dataset_id": "...",
    "alias": "...",
    "required": True,
    "freshness_seconds": None,
    "allow_stale": False,
}
```

The initial operation/readiness expected status is `BLOCKED_BY_DEPENDENCY`; its input
bindings are **empty**, not fabricated. No attempt or data write exists.

`operation(operation_id)` keeps its existing keys and, for deferred requests only, adds:

- `binding_state`: `UNRESOLVED` or `BOUND`;
- `declared_inputs`: immutable declarations from the originally pinned snapshot;
- `binding_hash`: null until resolution, then the digest of exact canonical bindings;
- `bound_at`: null until resolution, then the durable UTC binding timestamp.

`inputs(operation_id)` returns an empty tuple before resolution and the exact frozen
bindings afterward. A complete empty binding set is distinguishable from unresolved state
by the guard; ordinary required inputs still require concrete bindings. Optional omissions
are fixed when the complete required set is bound and cannot be appended later.

The immutable original `request_hash` identifies the daily *intent*, including declarations
and pinned snapshot. It is never rewritten during binding. The separate `binding_hash`
records actual resolved versions/windows/output/source IDs.

## Binding, blocking and duplicate semantics

Binding is one short serialized SQL transaction. It requires a deferred operation with
no existing inputs, attempt/fence, execution/output or terminal execution state. All
required identities must be supplied, all supplied identities must be declared, and
dataset IDs must be unique.

No partial bindings persist. Missing requirements, insufficient coverage, stale evidence,
latest upstream failure, corruption or exceptional ordering barriers raise
`DependencyBlocked` **after persisting** BLOCKED_BY_DEPENDENCY. Invalid identities or
mismatched/nonexistent commit evidence raise `ControlError` without inserting any input.
The old blocked intent remains durable. Claiming unresolved work persists the blocked
status and raises `DependencyBlocked`; it never creates an attempt even if upstream has
subsequently committed. Only the explicit resolver binding transition unlocks execution.

Successful resolution atomically INSERTs all actual inputs, records the guard hash/time,
sets QUEUED and audits `waiting_inputs_bound`. Claim still rechecks dependencies and
existing overlap/priority/fencing rules; QUEUED does not promise immediate execution.

Concurrent identical queue/bind calls produce one intent/binding and one successful
transition audit. Identical binding acknowledgements are safe even after claim, completion
or a lost response: they return the existing operation ID without modifying anything.
Different bindings fail forever after the first successful resolution, including before
the first claim. New release activation cannot change the pinned snapshot or declarations.
Existing `queue_operation` explicit inputs and manual reruns remain immutable; their IDs
cannot be converted into deferred requests, and deferred IDs cannot be requeued through
the fixed-input API.

## Resolver and physical-schema boundary

The parent-owned scheduler/resolver calls binding only when compatible actual commits
are available, using `snapshot(operation["release_version"])`, not the active release or
the reconciliation cycle's version. The store checks logical identity, environment/scope,
exact commit/source references, coverage and existing dependency/readiness barriers;
the resolver/runner additionally validates schema, physical snapshot accessibility and
artifact compatibility. Inputs may come from a newer approved producer release when
compatible; the waiting consumer's framework/DAG version stays unchanged.

Existing reconciliation candidates include BLOCKED_BY_DEPENDENCY operations across pinned
versions. No new event callback or scheduler is introduced. Missing/lost events do not
erase deferred requests; the usual periodic resolver can retry.

Migration `0005_waiting_operations.sql` adds only `ops.WaitingOperation` (PK/FK,
JSON/size and hash/time consistency checks, unresolved index). It rewrites no existing
input/version/request data. SQLite loads matching `reference_waiting.sql`. Runtime grants
permit INSERT and column-scoped hash/time updates, not declaration changes or input UPDATE.
These are real T-SQL/DB-API artifacts, but live DDL, constraints, contention and negative
permissions remain mandatory reviewed acceptance checks.
