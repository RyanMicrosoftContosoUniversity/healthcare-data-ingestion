"""Sequential, immutable PR-reviewed release publication and technical activation."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from healthcare_ingestion.configuration import ReleaseSnapshot, canonical_json, digest_json, thaw
from healthcare_ingestion.control_store import ControlError, ControlStore

_CHECKS = ("tests", "deployment", "environment_publication", "airflow_recognition")
_ARTIFACTS = {"package", "dependencies", "notebooks", "environments", "dags"}


class ReleaseManager:
    def __init__(self, store: ControlStore):
        self.store = store

    def publish_candidate(
        self,
        snapshot: ReleaseSnapshot,
        *,
        registry: Mapping[str, Mapping[str, Any]],
        review_evidence: Mapping[str, str],
    ) -> str:
        """Configuration is a complete branch/PR/code-reviewed snapshot, not a metadata hotfix."""
        snapshot.validate(registry)
        if set(review_evidence) != {"branch", "pull_request", "review", "commit"} or not all(
            review_evidence.values()
        ):
            raise ControlError("Branch, PR, review and immutable commit evidence are required")
        if _ARTIFACTS - set(snapshot.artifacts):
            raise ControlError(
                "Complete pinned package/dependencies/notebooks/environments/DAG required"
            )
        if any(not snapshot.artifacts[key] for key in _ARTIFACTS):
            raise ControlError("Pinned artifact references must not be empty")
        for key in _ARTIFACTS:
            artifact = snapshot.artifacts[key]
            if isinstance(artifact, Mapping) and (
                artifact.get("state") == "UNPUBLISHED" or artifact.get("approved_digest_required")
            ):
                raise ControlError(
                    "Unpublished template artifacts cannot become a release candidate"
                )
            if isinstance(artifact, str) and artifact.endswith(":latest"):
                raise ControlError("Mutable latest artifact tags cannot pin a framework release")
        with self.store.transaction() as tx:
            existing = tx.one(
                f"SELECT snapshot_hash,review_json FROM {tx.table('release')} WHERE version=?",
                (snapshot.version,),
            )
            review_json = canonical_json(review_evidence)
            if existing:
                if (
                    existing["snapshot_hash"] != snapshot.digest
                    or existing["review_json"] != review_json
                ):
                    raise ControlError("Release versions and review evidence are immutable")
                return snapshot.version
            versions = tx.all(f"SELECT version,queue_sequence FROM {tx.table('release')}")

            def semver(version: str) -> tuple[int, ...]:
                return tuple(int(part) for part in version.split("."))

            if any(semver(row["version"]) >= semver(snapshot.version) for row in versions):
                raise ControlError(
                    "New candidates must advance the already assigned semantic version"
                )
            sequence = max((r["queue_sequence"] for r in versions), default=0) + 1
            tx.insert(
                "release",
                version=snapshot.version,
                framework_version=snapshot.framework_version,
                snapshot_hash=snapshot.digest,
                snapshot_json=canonical_json(snapshot.to_dict()),
                review_json=review_json,
                queue_sequence=sequence,
                status="QUEUED",
                checks_json="{}",
                created_at=tx.now,
                updated_at=tx.now,
                failure_code=None,
            )
            for dataset in snapshot.datasets:
                identity = tx.one(
                    f"SELECT dataset_id,layer,[external] FROM {tx.table('identity')} "
                    "WHERE dataset_id=?",
                    (dataset.dataset_id,),
                )
                if identity and (
                    identity["dataset_id"] != dataset.dataset_id
                    or identity["layer"] != dataset.layer
                    or bool(identity["external"]) != dataset.external
                ):
                    raise ControlError(
                        "Immutable logical dataset identity/layer cannot be repurposed"
                    )
                if not identity:
                    tx.insert(
                        "identity",
                        dataset_id=dataset.dataset_id,
                        layer=dataset.layer,
                        external=int(dataset.external),
                        created_at=tx.now,
                    )
                tx.insert(
                    "dataset",
                    release_version=snapshot.version,
                    dataset_id=dataset.dataset_id,
                    name=dataset.name,
                    retired=int(dataset.retired),
                    freshness_seconds=dataset.freshness_seconds,
                )
                for environment, physical in dataset.physical_maps.items():
                    tx.insert(
                        "mapping",
                        release_version=snapshot.version,
                        dataset_id=dataset.dataset_id,
                        environment=environment,
                        physical_json=canonical_json(physical),
                    )
            previously_registered = {
                row["dataset_id"]
                for row in tx.all(f"SELECT dataset_id FROM {tx.table('identity')}")
            }
            missing = previously_registered - {d.dataset_id for d in snapshot.datasets}
            if missing:
                raise ControlError(
                    "Complete snapshots retain retired dataset identities instead of removing them"
                )
            mappings = thaw(snapshot.artifacts.get("pipeline_objects", {}))
            historical_tasks = tx.all(
                f"SELECT task_id,primary_output,scope,functions_json FROM {tx.table('task')}"
            )
            missing_tasks = {t["task_id"] for t in historical_tasks} - {
                t.task_id for t in snapshot.tasks
            }
            if missing_tasks:
                raise ControlError("Retire historical tasks logically instead of removing them")
            for task in snapshot.tasks:
                for historical in historical_tasks:
                    if historical["task_id"] != task.task_id:
                        continue
                    if (historical["primary_output"], historical["scope"]) != (
                        task.primary_output,
                        task.scope,
                    ):
                        raise ControlError(
                            "A logical task ID cannot be repurposed to another output"
                        )
                    occurrences = {
                        f["occurrence_id"]: f["function"]
                        for f in json.loads(historical["functions_json"])
                    }
                    if any(
                        f.occurrence_id in occurrences
                        and occurrences[f.occurrence_id] != f.function
                        for f in task.functions
                    ):
                        raise ControlError("Stable function occurrence IDs cannot be repurposed")
                if task.pipeline_object_id:
                    if task.pipeline_object_id not in mappings:
                        raise ControlError(
                            "Task mapping FK requires a pinned PipelineObject mapping"
                        )
                    old = tx.one(
                        f"SELECT pipeline_object_id FROM {tx.table('pipeline')} "
                        "WHERE release_version=? AND pipeline_object_id=?",
                        (snapshot.version, task.pipeline_object_id),
                    )
                    if not old:
                        mapping = mappings[task.pipeline_object_id]
                        tx.insert(
                            "pipeline",
                            release_version=snapshot.version,
                            pipeline_object_id=task.pipeline_object_id,
                            mapping_json=canonical_json(mapping),
                            legacy_pipeline_object_id=mapping.get("legacy_pipeline_object_id"),
                        )
                tx.insert(
                    "task",
                    release_version=snapshot.version,
                    task_id=task.task_id,
                    workflow=task.workflow,
                    primary_output=task.primary_output,
                    pipeline_object_id=task.pipeline_object_id,
                    scope=task.scope,
                    retired=int(task.retired),
                    functions_json=canonical_json(
                        [
                            {name: thaw(getattr(f, name)) for name in f.__dataclass_fields__}
                            for f in task.functions
                        ]
                    ),
                    overrides_json=canonical_json(task.overrides),
                )
                for item in task.inputs:
                    tx.insert(
                        "input",
                        release_version=snapshot.version,
                        task_id=task.task_id,
                        dataset_id=item.dataset_id,
                        alias=item.alias,
                        required=int(item.required),
                        freshness_seconds=item.freshness_seconds,
                        allow_stale=int(item.allow_stale),
                    )
            for task in snapshot.tasks:
                for parent in task.ordering_after:
                    tx.insert(
                        "dependency",
                        release_version=snapshot.version,
                        task_id=task.task_id,
                        predecessor_task_id=parent,
                        reason="exceptional_ordering",
                    )
            stages = {snapshot.dataset(t.primary_output).layer for t in snapshot.tasks}
            for stage in stages:
                tx.insert(
                    "policy",
                    release_version=snapshot.version,
                    stage=stage,
                    framework_defaults_json=canonical_json(snapshot.framework_defaults),
                    stage_defaults_json=canonical_json(snapshot.stage_defaults.get(stage, {})),
                )
            self.store._audit(
                tx,
                "candidate_published",
                snapshot.version,
                {"snapshot": snapshot.digest, "review_hash": digest_json(review_evidence)},
            )
            return snapshot.version

    def import_legacy_attribution(
        self,
        version: str,
        task_id: str,
        occurrence_id: str,
        legacy_transformation_step_id: int,
        *,
        import_evidence: str,
        legacy_pipeline_object_id: int | None = None,
    ) -> None:
        """Reviewed attribution import that preserves original baseline step/profiling FKs."""
        if legacy_transformation_step_id <= 0 or not import_evidence:
            raise ControlError(
                "Historical attribution requires an original step ID and review evidence"
            )
        with self.store.transaction() as tx:
            task = self.store._snapshot(tx, version).task(task_id)
            if occurrence_id not in {f.occurrence_id for f in task.functions}:
                raise ControlError("Attribution must identify an existing stable JSON occurrence")
            row = tx.one(
                f"SELECT * FROM {tx.table('legacy')} WHERE release_version=? "
                "AND task_id=? AND occurrence_id=?",
                (version, task_id, occurrence_id),
            )
            values = {
                "release_version": version,
                "task_id": task_id,
                "occurrence_id": occurrence_id,
                "legacy_transformation_step_id": legacy_transformation_step_id,
                "legacy_pipeline_object_id": legacy_pipeline_object_id,
                "import_evidence": import_evidence,
            }
            if row:
                if row != values:
                    raise ControlError("Historical attribution is immutable")
                return
            tx.insert("legacy", **values)
            self.store._audit(
                tx,
                "legacy_attribution_imported",
                task_id,
                {
                    "release": version,
                    "occurrence": occurrence_id,
                    "legacy_step": legacy_transformation_step_id,
                },
            )

    def begin_candidate(self, version: str) -> None:
        with self.store.transaction() as tx:
            candidate = tx.one(f"SELECT * FROM {tx.table('release')} WHERE version=?", (version,))
            if not candidate or candidate["status"] != "QUEUED":
                raise ControlError("Only queued candidates may begin CI/deployment")
            blocking = tx.one(
                f"SELECT version FROM {tx.table('release')} "
                "WHERE queue_sequence<? AND status IN ('QUEUED','TESTING','READY')",
                (candidate["queue_sequence"],),
            )
            if blocking:
                raise ControlError("Candidate release queue is sequential")
            tx.update("release", "version=?", (version,), status="TESTING", updated_at=tx.now)
            self.store._audit(tx, "candidate_started", version, {})

    def record_check(
        self,
        version: str,
        environment: str,
        check: str,
        *,
        passed: bool,
        evidence: str,
    ) -> None:
        if check not in _CHECKS or not evidence:
            raise ControlError("Known technical check and durable evidence reference are required")
        with self.store.transaction() as tx:
            candidate = tx.one(f"SELECT * FROM {tx.table('release')} WHERE version=?", (version,))
            if not candidate or candidate["status"] not in {"TESTING", "READY"}:
                raise ControlError(
                    "Checks belong to the executing candidate, never an active hotfix"
                )
            checks = json.loads(candidate["checks_json"])
            current = checks.setdefault(environment, {})
            result = {"passed": passed, "evidence": evidence}
            if check in current and current[check] != result:
                raise ControlError(
                    "Technical evidence is immutable; use a newer corrective release"
                )
            current[check] = result
            status = (
                "FAILED"
                if not passed
                else (
                    "READY" if all(current.get(c, {}).get("passed") for c in _CHECKS) else "TESTING"
                )
            )
            tx.update(
                "release",
                "version=?",
                (version,),
                checks_json=canonical_json(checks),
                status=status,
                updated_at=tx.now,
                failure_code=None if passed else f"{environment}:{check}",
            )
            self.store._audit(
                tx, "release_check", version, {"environment": environment, "check": check, **result}
            )

    def activate(self, version: str, environment: str) -> None:
        with self.store.transaction() as tx:
            candidate = tx.one(f"SELECT * FROM {tx.table('release')} WHERE version=?", (version,))
            if not candidate:
                raise ControlError("Unknown candidate")
            active = tx.one(
                f"SELECT * FROM {tx.table('active')} WHERE environment=?", (environment,)
            )
            if active and active["version"] == version:
                return
            checks = json.loads(candidate["checks_json"]).get(environment, {})
            if candidate["status"] != "READY" or not all(
                checks.get(check, {}).get("passed") for check in _CHECKS
            ):
                raise ControlError(
                    "Tests/deployment/environment publication/Airflow recognition required"
                )
            if tx.one(
                f"SELECT version FROM {tx.table('release')} "
                "WHERE queue_sequence<? AND status IN ('QUEUED','TESTING','READY')",
                (candidate["queue_sequence"],),
            ):
                raise ControlError("An older candidate has not finished sequential publication")
            snapshot = self.store._snapshot(tx, version)
            for dataset in snapshot.datasets:
                if not dataset.retired:
                    physical = snapshot.physical(dataset.dataset_id, environment)
                    if not dataset.external and not (
                        physical.get("path")
                        or all(
                            physical.get(k)
                            for k in ("workspace_id", "lakehouse_id", "schema", "table")
                        )
                    ):
                        raise ControlError("Fabric dataset physical mappings remain unresolved")
            activation_id = str(uuid.uuid4())
            tx.insert(
                "activation",
                activation_id=activation_id,
                environment=environment,
                version=version,
                previous_version=active["version"] if active else None,
                action="activate",
                reason="all_technical_checks_passed",
                activated_at=tx.now,
            )
            if active:
                tx.update(
                    "active",
                    "environment=?",
                    (environment,),
                    version=version,
                    activation_id=activation_id,
                    updated_at=tx.now,
                )
                tx.update(
                    "release",
                    "version=?",
                    (active["version"],),
                    status="SUPERSEDED",
                    updated_at=tx.now,
                )
            else:
                tx.insert(
                    "active",
                    environment=environment,
                    version=version,
                    activation_id=activation_id,
                    updated_at=tx.now,
                )
            tx.update("release", "version=?", (version,), status="ACTIVE", updated_at=tx.now)
            self.store._audit(tx, "release_activated", version, {"environment": environment})

    def rollback(
        self,
        environment: str,
        *,
        reason: str,
        target_version: str | None = None,
        technical_failure: bool = True,
    ) -> str:
        """Restore last-good code/environment for NEW work; never mutate in-flight pins or Delta."""
        if not technical_failure or not reason:
            raise ControlError("Quality corruption is not an automatic technical rollback")
        with self.store.transaction() as tx:
            active = tx.one(
                f"SELECT * FROM {tx.table('active')} WHERE environment=?", (environment,)
            )
            if not active:
                raise ControlError("No active release to roll back")
            activations = tx.all(
                f"SELECT * FROM {tx.table('activation')} WHERE environment=? "
                "AND action='activate' ORDER BY activated_at DESC",
                (environment,),
            )
            available = [r["version"] for r in activations if r["version"] != active["version"]]
            target = target_version or (available[0] if available else None)
            if target not in available:
                raise ControlError(
                    "Rollback requires a previously technically activated last-good release"
                )
            candidate = tx.one(
                f"SELECT checks_json FROM {tx.table('release')} WHERE version=?", (target,)
            )
            checks = json.loads(candidate["checks_json"]).get(environment, {})
            if not all(checks.get(c, {}).get("passed") for c in _CHECKS):
                raise ControlError("Matching approved environment/artifacts are not available")
            activation_id = str(uuid.uuid4())
            tx.insert(
                "activation",
                activation_id=activation_id,
                environment=environment,
                version=target,
                previous_version=active["version"],
                action="rollback",
                reason=reason,
                activated_at=tx.now,
            )
            tx.update(
                "active",
                "environment=?",
                (environment,),
                version=target,
                activation_id=activation_id,
                updated_at=tx.now,
            )
            tx.update(
                "release", "version=?", (active["version"],), status="SUPERSEDED", updated_at=tx.now
            )
            tx.update("release", "version=?", (target,), status="ACTIVE", updated_at=tx.now)
            self.store._audit(
                tx,
                "technical_rollback",
                target,
                {"environment": environment, "from": active["version"], "reason": reason},
            )
            return target

    def status(self, version: str) -> Mapping[str, Any]:
        with self.store.transaction() as tx:
            row = tx.one(
                f"SELECT version,status,queue_sequence,checks_json,failure_code "
                f"FROM {tx.table('release')} WHERE version=?",
                (version,),
            )
            if not row:
                raise ControlError("Unknown release")
            return row
