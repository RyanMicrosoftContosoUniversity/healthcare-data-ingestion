"""Fixed-snapshot reads and recoverable publication; SQL and Delta are not atomic."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class PublicationIntent:
    batch_id: str
    dataset_id: str
    base_version: int
    recovering: bool = False


def fixed_read(spark, path, version):
    if type(version) is not int or version < 0:
        raise ValueError("An explicit nonnegative Delta version is required.")
    return spark.read.format("delta").option("versionAsOf", version).load(path)


def history(spark, path):
    from delta.tables import DeltaTable

    if not DeltaTable.isDeltaTable(spark, path):
        return []
    return [row.asDict() for row in DeltaTable.forPath(spark, path).history().collect()]


def current_version(spark, path):
    entries = history(spark, path)
    return max((entry["version"] for entry in entries), default=-1)


def publication_evidence(entries, intent):
    matches = []
    for entry in entries:
        try:
            metadata = json.loads(entry.get("userMetadata") or "{}")
        except (ValueError, TypeError):
            continue
        if (
            metadata.get("batch_id") == intent.batch_id
            and metadata.get("dataset_id") == intent.dataset_id
        ):
            matches.append(entry["version"])
    if len(matches) > 1:
        raise ValueError("Multiple commits claim the same publication; block as corruption.")
    if matches:
        return matches[0]
    if intent.recovering:
        if not entries:
            raise ValueError("Publication history unavailable; initial recovery needs proof.")
        latest = max((entry["version"] for entry in entries), default=-1)
        versions = {entry["version"] for entry in entries}
        if latest < intent.base_version or any(
            version not in versions for version in range(intent.base_version + 1, latest + 1)
        ):
            raise ValueError("Publication history unavailable; do not blindly append again.")
    return None


def bronze_frame(frame, context, include_hash=True):
    from pyspark.sql import functions as f

    required = {
        "_ingest_batch_id",
        "_ingest_run_id",
        "_ingest_table_run_id",
        "_ingest_source_name",
        "_ingest_extracted_at_utc",
        "_ingest_landed_at_utc",
        "_ingest_capture_mode",
    }
    if set(context) != required or required.intersection(frame.columns):
        raise ValueError("Invalid Bronze technical context or source-column collision.")
    if context["_ingest_capture_mode"] not in {"FULL", "WATERMARK"}:
        raise ValueError("Invalid capture mode.")
    for name in ("_ingest_extracted_at_utc", "_ingest_landed_at_utc"):
        value = context[name]
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("Technical timestamps require timezone-aware UTC instants.")
    if include_hash:
        source = f.to_json(
            f.struct(*(f.col(c) for c in frame.columns)), options={"ignoreNullFields": "false"}
        )
        frame = frame.withColumn("_ingest_row_hash", f.sha2(source, 256))
    for name, value in context.items():
        if isinstance(value, datetime):
            value = value.astimezone(UTC)
        elif not isinstance(value, str) or not value:
            raise ValueError("Technical identities must be nonempty readable strings.")
        frame = frame.withColumn(name, f.lit(value))
    return frame


def append_bronze(frame, path, intent, fence):
    """Caller durably records intent before calling; fence checks authoritative lease."""
    spark = frame.sparkSession
    fence()
    entries = history(spark, path)
    evidence = publication_evidence(entries, intent)
    if evidence is not None:
        return evidence
    if entries:
        existing = fixed_read(spark, path, max(e["version"] for e in entries))
        if [(c.name, c.dataType) for c in existing.schema] != [
            (c.name, c.dataType) for c in frame.schema
        ]:
            raise ValueError("Bronze target schema differs; no automatic evolution.")
    if max((e["version"] for e in entries), default=-1) != intent.base_version:
        publication_evidence(
            entries,
            PublicationIntent(
                intent.batch_id, intent.dataset_id, intent.base_version, recovering=True
            ),
        )
    metadata = json.dumps(
        {"batch_id": intent.batch_id, "dataset_id": intent.dataset_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    (
        frame.write.format("delta")
        .mode("append")
        .option("mergeSchema", "false")
        .option("txnAppId", f"healthcare:{intent.dataset_id}:{intent.batch_id}")
        .option("txnVersion", 1)
        .option("userMetadata", metadata)
        .save(path)
    )
    fence()
    evidence = publication_evidence(history(spark, path), intent)
    if evidence is None:
        raise ValueError("Delta commit evidence is missing; no readiness/state advance.")
    return evidence


def merge_patient(frame, path, key, modified, intent, fence):
    from delta.tables import DeltaTable
    from pyspark.sql import functions as f

    if key not in frame.columns or modified not in frame.columns:
        raise ValueError("Patient merge requires its key and source time.")
    fence()
    session = frame.sparkSession.newSession()
    evidence = publication_evidence(history(session, path), intent)
    if evidence is not None:
        return evidence
    if not DeltaTable.isDeltaTable(session, path):
        return append_bronze(frame, path, intent, fence)
    existing = DeltaTable.forPath(session, path).toDF()
    if existing.schema != frame.schema:
        # Delta readers mark nullable fields conservatively; compare name/type, not flags.
        if [(c.name, c.dataType) for c in existing.schema] != [
            (c.name, c.dataType) for c in frame.schema
        ]:
            raise ValueError("Patient target schema differs; no automatic evolution.")
    payload = lambda prefix: f.to_json(  # noqa: E731
        f.struct(*(f.col(f"{prefix}.`{c}`") for c in frame.columns)),
        options={"ignoreNullFields": "false"},
    )
    ties = (
        frame.alias("source")
        .join(
            existing.alias("target"),
            (f.col(f"source.`{key}`") == f.col(f"target.`{key}`"))
            & (f.col(f"source.`{modified}`") == f.col(f"target.`{modified}`")),
        )
        .where(payload("source") != payload("target"))
    )
    if ties.limit(1).count():
        raise ValueError("Patient conflicts with an existing same-key/time Silver record.")
    session.conf.set(
        "spark.databricks.delta.commitInfo.userMetadata",
        json.dumps({"batch_id": intent.batch_id, "dataset_id": intent.dataset_id}, sort_keys=True),
    )
    fence()
    (
        DeltaTable.forPath(session, path)
        .alias("target")
        .merge(frame.alias("source"), f"target.`{key}` = source.`{key}`")
        .whenMatchedUpdateAll(condition=f"source.`{modified}` > target.`{modified}`")
        .whenNotMatchedInsertAll()
        .execute()
    )
    fence()
    evidence = publication_evidence(history(session, path), intent)
    if evidence is None:
        raise ValueError("Patient commit evidence missing; reconcile before readiness.")
    return evidence
