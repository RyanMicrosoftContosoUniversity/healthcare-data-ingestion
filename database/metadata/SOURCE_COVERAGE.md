# Verified source coverage versus processing windows

## Exact revised dataclasses

Imports remain `healthcare_ingestion.control_store.InputBinding` and `CommitEvidence`.
New fields are appended, so the preceding positional arguments retain their meanings:

```python
InputBinding(
    dataset_id: str, version: str, window_start: str, window_end: str,
    output_id: str | None = None, source_snapshot_id: str | None = None,
    source_coverage_start: str | None = None,
    source_coverage_end: str | None = None,
)

CommitEvidence(
    operation_id: str, dataset_id: str, delta_version: str,
    window_start: str, window_end: str, input_versions: Mapping[str, str],
    validation_digest: str, coverage_verified: bool, changed_rows: int,
    commit_token: str,
    source_coverage_start: str | None = None,
    source_coverage_end: str | None = None,
)
```

All bounds normalize to half-open UTC intervals with seven fractional digits. Source
bounds must be supplied together and start<end. These frozen dataclasses serialize both
new fields in `to_dict()`. CommitEvidence `window_start/window_end` remain exactly the
operation's **PROCESSING** window, never a stand-in for source coverage.

`queue_operation`, `queue_waiting_operation`, `bind_waiting_operation`, `claim`, `publish`
and `reconcile_commit` retain their signatures. Production publication/reconciliation
requires explicit nonnull CommitEvidence source bounds plus the real external commit
verifier. The verifier must validate those bounds against durable capture/validation proof,
not simply notebook success, nominal time or publication time.

## Provenance and immutable binding

For external source input, register a real retained source snapshot using the existing:

```python
store.register_source_snapshot(
    dataset_id,
    environment,
    version,
    actual_source_start,
    actual_source_end,
    evidence_digest=verified_generator_or_capture_digest,
    artifact_ref=immutable_capture_ref,
    verify_snapshot=real_snapshot_verifier,
    scope=scope,
)
```

Its `window_start/window_end` are verified generator/capture source coverage. Registration
supports current **and** historical snapshots; it does not label a current capture historical.
The resulting snapshot ID belongs in InputBinding `source_snapshot_id`. Its actual source
coverage need not equal the input's or operation's processing window.

For Delta input, bind an exact committed `output_id` and version. InputBinding processing
bounds must match that output's recorded processing bounds. Omitted input source bounds
are resolved from the source snapshot/upstream output **before** freezing inputs; supplied
bounds must match that authoritative coverage exactly. Forged newer or different input
coverage is rejected during queue/bind and checked again during claim.

Normal daily/historical processing-window containment rules remain independent of source
freshness. Immutable versions, output/source IDs, original DAG/framework release and
already bound inputs are not changed when coverage becomes stale. Identical deferred
binding replays can omit source bounds and acknowledge the already stored bounds without
re-reading/substituting live source. A different binding is still forbidden.

## Current full-source versus historical backfill

For explicitly requested `kind="backfill", source_mode="current"`, use a fresh real
**full captured current snapshot**, not the last daily-watermark increment. The parent
extractor/runner owns full-capture selection and its verifier. A current generator interval
that starts after an older requested processing window is not rejected as missing historical
coverage. For this approved current-backfill mode only, input processing-window containment
of the older request is waived; identity/version/committed-output matching and actual
coverage provenance/freshness still apply.

Consequently a Bronze backfill processing October can carry verified November source
coverage/current source version. Its Silver consumer inherits that coverage from the exact
fixed Bronze output; October is not written over November as the source coverage.
This represents current corrected input applied to an old processing request, **not** an
assertion that a historical October source snapshot exists.

`source_mode="historical"` still requires retained explicitly selected originals and normal
window compatibility. Original-operation reruns cannot change those inputs without recorded
substitution approval. Missing historical snapshots never fall back to current capture.
Historical freshness exemption remains explicit; it does not turn old source time into fresh
dataset readiness or clear latest expected failure/corruption blocks.

## Publication, readiness and recovery

Output coverage cannot exceed the common verified input interval
`[max(input source starts), min(input source ends))`. Explicit conservative sub-intervals
are allowed only with real verifier evidence; a claimed newer end or earlier start is
rejected. Silver normally publishes the inherited interval unchanged.

`DatasetOutput`, `OperationInput` and `DatasetReadiness` have durable
`source_coverage_start/source_coverage_end` columns. Output evidence JSON includes them
and its immutable hash covers them. Readiness/output-history reads expose these columns.
`progress_end` and `expected_end` remain independent logical processing progress/expectation;
event `progress_end` remains processing-order metadata, not source freshness.

Claim/bind compute freshness from actual pinned source coverage end, including external
source input and exceptional ordering barriers, never from processing end or publication.
Default dataset/input policy remains 24 hours, with existing explicit stale-input and
historical policies unchanged. Latest expected FAILED/UNCERTAIN/CORRUPT blocking remains
independent of the retained last-good output.

Readiness selects the newest verified source end first; processing progress is a separate
monotonic maximum/tie-breaker. A late old-source commit cannot manufacture freshness or
replace a newer verified source pointer merely because its processing/publication time is
later. Verified post-Delta/pre-SQL reconciliation can still persist a stale commit safely:
its actual old coverage remains stale, and fresh upstream data is not silently substituted.

## Migration and compatibility boundary

`0006_source_coverage.sql` adds nullable coverage columns, interval checks, correlated
input-source/output and readiness-output FKs. It does **not** UPDATE historical rows or
backfill source coverage from nominal windows. Existing NULL coverage is unknown/unready
and cannot be consumed as verified upstream coverage in strict mode.

SQLite adds these columns non-destructively and loads `reference_coverage.sql` interval/
provenance guards. Production Fabric SQL always uses strict coverage rules. Local legacy
same-window protocol fixtures alone may explicitly opt in:

```python
SQLiteControlStore(path, *, clock=None, legacy_same_window_coverage=False)
```

Setting the flag True allows old local fixtures to use same-window coverage for an
unregistered checkpoint or missing CommitEvidence coverage; supplied authoritative
snapshot/output coverage still wins and forged bounds still fail. This is not available
for the SQL Server/Fabric transaction adapter and is not production evidence.

The never-deployed migration 0005 ledger insert was also corrected to supply its required
description. No applied migration was edited. Live Fabric SQL DDL/FKs, transactional
contention, identities/negative permissions and real Delta/source capture proof remain
unverified reviewed acceptance requirements.
