# Immutable framework configuration

`demo-release.json` is the **complete unpublished template** for 13 Clarity Bronze tasks,
15 Caboodle Bronze tasks and only Clarity Patient Silver 1: 29 executable tasks, 57 logical
datasets, exactly `clarity_bronze`, `caboodle_bronze`, `patient_silver` workflows. No Silver 2
or Gold processing is implemented. Logical IDs are stable; names and environment-specific
physical mappings may change only through reviewed releases. Source mappings remain distinct
from tasks. Resource/artifact references are unpublished placeholders requiring actual
deployment resolution/evidence, not fabricated workspace/lakehouse IDs.

`ReleaseSnapshot.from_dict` uses the exact JSON field names in this template. Ordered
functions carry stable `occurrence_id`, registered `function`, validated `parameters` and
explicit `input_aliases`. Registry parameter validation is a closed bounded JSON-schema
subset; executable imports/code and hidden reads are not accepted. Input rows are
normalized relational records; producer edges are inferred. Explicit `ordering_after`
records are only for exceptional order, not duplicate inferred edges. Missing, ambiguous,
retired or cyclic inputs/producers are rejected before candidate publication.

Settings are resolved **framework defaults → output-stage defaults → task overrides**,
recursively field-by-field. Null means inherit; false/zero are real overrides where valid.
Scheduler retries, backoff and execution timeout live under `scheduler`. Spark startup and
runtime dictionaries live under `spark`, never mixed with scheduler retry policy.
Notebook/environment/compute-profile refs and concurrency limit live under `execution`.
Environment refs do not imply dedicated pools. Startup settings must be applied before
session creation; runtime settings afterward. Unsupported automatic profile escalation
must not be fabricated. Both settings and pinned environments change through PR/CI releases,
not in-place active environment edits.

Daily discovery/ingestion policy remains 10:00 AM `America/New_York`, 11:00 AM availability
deadline, both DST-aware; freshness is 24 elapsed hours inclusive at equality. A deadline
miss is an alert/measurement, not cancellation or the scheduler execution timeout. This
template's scheduler retry/concurrency numbers are conservative implementation defaults,
not claims of benchmark-proven throughput or supported Fabric compute capabilities.

`ReleaseManager.publish_candidate(snapshot,registry,review_evidence)` requires branch,
PR, review and immutable commit references plus a complete pinned artifact manifest.
Candidate semver is assigned before CI; DAG/framework semver must match. Candidates begin
sequentially. Tests, deployment, environment publication and Airflow recognition must all
pass with evidence for the target environment before activation. A failed candidate leaves
last-good active and lets a newer candidate proceed; no additional human approval loop is
added after the reviewed configuration passes technical gates.

Queued/in-flight operations retain their original snapshot/version. Technical rollback
selects a prior fully activated artifact/environment set for **new** work and records its
activation audit; it never mutates existing pins, clears quality corruption or undoes Delta.
Use a new corrective version rather than mutating a failed/active release's checks/config.
