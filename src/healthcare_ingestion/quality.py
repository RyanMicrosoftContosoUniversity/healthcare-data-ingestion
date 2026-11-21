"""Registered severity rules, bounded quarantine and lineage-preserving replay inputs."""

import hashlib
import math
from dataclasses import dataclass

from healthcare_ingestion.artifacts import encoded
from healthcare_ingestion.benchmark import artifact_path
from healthcare_ingestion.delta_io import fixed_read


@dataclass(frozen=True)
class QualityRule:
    name: str
    column: str
    operator: str
    severity: str = "warning"
    quarantine: bool = False
    values: tuple = ()

    def __post_init__(self):
        if (
            not self.name
            or not self.column
            or self.severity not in {"critical", "warning"}
            or type(self.quarantine) is not bool
            or self.operator not in {"not_null", "not_blank", "in_set", "nonnegative"}
            or (self.operator == "in_set" and not self.values)
        ):
            raise ValueError("Invalid registered quality rule.")

    def condition(self, frame):
        from pyspark.sql import functions as f

        if self.column not in frame.columns or self.severity not in {"critical", "warning"}:
            raise ValueError("Invalid registered quality column/severity.")
        value = f.col(f"`{self.column}`")
        if self.operator == "not_null":
            return value.isNotNull()
        if self.operator == "not_blank":
            return value.isNotNull() & (f.length(f.trim(value)) > 0)
        if self.operator == "in_set" and self.values:
            return value.isNotNull() & value.isin(*self.values)
        if self.operator == "nonnegative":
            return value.isNotNull() & (value >= 0)
        raise ValueError("Unregistered quality operator.")


def evaluate_quality(
    frame,
    rules,
    persist,
    quarantine_root,
    context,
    store,
    max_quarantine_rows=0,
    max_quarantine_fraction=0.0,
    preserve_raw=False,
    artifacts=None,
):
    if (
        type(max_quarantine_rows) is not int
        or max_quarantine_rows < 0
        or type(max_quarantine_fraction) not in {int, float}
        or not math.isfinite(max_quarantine_fraction)
        or not 0 <= max_quarantine_fraction <= 1
    ):
        raise ValueError("Quarantine limits must be nonnegative and explicitly configured.")
    if not rules:
        return frame
    from pyspark.sql import functions as f

    anchor = {key: context[key] for key in ("operation_id", "attempt_id", "release_version")}
    total = frame.count()
    invalid = f.lit(False)
    quality_ids = []
    critical = False
    names = set()
    for rule in rules:
        if not rule.name or rule.name in names:
            raise ValueError("Quality rule occurrence names must be unique.")
        names.add(rule.name)
        bad = ~f.coalesce(rule.condition(frame), f.lit(False))
        count = frame.where(bad).count()
        details = {"rows": count, "total": total, "operator": rule.operator, "column": rule.column}
        quality_id = persist(
            {
                **anchor,
                "check": rule.name,
                "severity": rule.severity,
                "status": "FAIL" if count else "PASS",
                "reason": "REGISTERED_QUALITY_RULE" if count else None,
                "evidence_digest": hashlib.sha256(encoded(details)).hexdigest(),
                "details": details,
            }
        )
        if count and rule.quarantine:
            invalid = invalid | bad
            quality_ids.append(quality_id)
        critical = critical or (count > 0 and rule.severity == "critical")
    quarantined = frame.where(invalid)
    count = quarantined.count() if quality_ids else 0
    if (
        critical
        or count > max_quarantine_rows
        or (total and count / total > max_quarantine_fraction)
    ):
        raise ValueError("Critical quality failure or configured quarantine limit exceeded.")
    if count:
        if artifacts is None:
            raise ValueError("Quarantine requires protected content evidence for replay.")
        path = artifact_path(
            quarantine_root,
            context["operation_id"],
            context["attempt_id"],
            "records",
        )
        quarantined.write.format("delta").mode("errorifexists").save(path)
        content_key = f"quarantine/{context['operation_id']}/{context['attempt_id']}/content.json"
        artifacts.put(
            content_key,
            {
                "artifact": path,
                "version": 0,
                "content_digest": content_digest(fixed_read(frame.sparkSession, path, 0)),
            },
        )
        store.hold_reference("artifact", path, "quarantine:" + context["operation_id"])
        store.hold_reference("artifact", content_key, "quarantine:" + context["operation_id"])
        store.record_quarantine_manifest(
            {
                **anchor,
                "status": "PENDING",
                "quality_record_id": quality_ids[0],
                "artifact": path,
                "reason_code": "REGISTERED_QUALITY_RULE",
                "row_count": count,
                "schema_digest": hashlib.sha256(frame.schema.json().encode()).hexdigest(),
                "input_versions": context.get("input_versions", {}),
                "identifiers_manifest_ref": content_key,
            }
        )
    return frame if preserve_raw else frame.where(~invalid)


def content_digest(frame):
    from pyspark.sql import functions as f

    columns = [f.col("`" + name.replace("`", "``") + "`") for name in frame.columns]
    rows = (
        frame.select(
            f.sha2(f.to_json(f.struct(*columns), {"ignoreNullFields": "false"}), 256).alias(
                "row_digest"
            )
        )
        .groupBy("row_digest")
        .count()
        .orderBy("row_digest")
    )
    digest = hashlib.sha256()
    for row in rows.toLocalIterator():
        digest.update(f"{row.row_digest}:{row['count']}\n".encode())
    return digest.hexdigest()


def replay_input(spark, manifest, expected_operation_id, artifacts=None):
    if manifest["operation_id"] != expected_operation_id or manifest["status"] not in {
        "PENDING",
        "SUCCEEDED",
    }:
        raise ValueError("Quarantine replay must retain its original operation lineage.")
    frame = fixed_read(spark, manifest["artifact"], 0)
    if hashlib.sha256(frame.schema.json().encode()).hexdigest() != manifest["schema_digest"]:
        raise ValueError("Quarantine replay schema differs from its sealed manifest.")
    if frame.count() != manifest["row_count"]:
        raise ValueError("Quarantine replay row count differs; full reprocessing is required.")
    proof = (
        artifacts.get(manifest["identifiers_manifest_ref"])
        if artifacts and manifest.get("identifiers_manifest_ref")
        else None
    )
    if (
        not proof
        or proof["artifact"] != manifest["artifact"]
        or proof["version"] != 0
        or proof["content_digest"] != content_digest(frame)
    ):
        raise ValueError("Replay content cannot be proven; full reprocessing is required.")
    return frame


def apply_task_quality(
    frame, snapshot, task_id, claim, root, store, input_versions, artifacts=None
):
    policy = snapshot.artifacts.get("quality_policies", {}).get(task_id, {})
    allowed = {"rules", "max_quarantine_rows", "max_quarantine_fraction"}
    if set(policy) - allowed:
        raise ValueError("Unknown central quality policy settings.")
    rules = tuple(QualityRule(**rule) for rule in policy.get("rules", ()))
    task = snapshot.task(task_id)
    return evaluate_quality(
        frame,
        rules,
        store.record_quality_outcome,
        root,
        {
            "operation_id": claim.operation_id,
            "attempt_id": claim.attempt_id,
            "release_version": snapshot.version,
            "input_versions": input_versions,
        },
        store,
        policy.get("max_quarantine_rows", 0),
        policy.get("max_quarantine_fraction", 0.0),
        preserve_raw=snapshot.dataset(task.primary_output).layer == "bronze",
        artifacts=artifacts,
    )
