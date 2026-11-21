"""Generic fenced execution with immutable capture, intent and commit recovery proof."""

import hashlib
import threading
from datetime import UTC, datetime

from healthcare_ingestion.artifacts import encoded
from healthcare_ingestion.benchmark import artifact_path
from healthcare_ingestion.control_store import CommitEvidence, LeaseLost, MetadataUnavailable
from healthcare_ingestion.delta_io import (
    PublicationIntent,
    append_bronze,
    bronze_frame,
    current_version,
    fixed_read,
    history,
    merge_patient,
    publication_evidence,
)
from healthcare_ingestion.discovery import (
    discover,
    extraction_query,
    fingerprint,
    identifier,
    timestamp7,
)
from healthcare_ingestion.patient import REGISTRY
from healthcare_ingestion.quality import apply_task_quality
from healthcare_ingestion.spark_types import assert_schema, mapped_schema
from healthcare_ingestion.sql_source import source_checkpoint_evidence


class ExecutionLease:
    """Renew ownership during blocking Spark actions; failures fence further work."""

    def __init__(self, store, claim, spark=None, timeout_seconds=None):
        self.store, self.claim = store, claim
        self.stopped = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._renew, daemon=True)
        self.spark, self.timeout_seconds = spark, timeout_seconds
        self.expired = threading.Event()
        self.timer = None
        self.prior_properties = {}

    def _renew(self):
        while not self.stopped.wait(60):
            try:
                self.claim = self.store.heartbeat(self.claim, lease_seconds=300)
            except Exception as error:
                self.error = error
                return

    def __enter__(self):
        if self.spark is not None and self.timeout_seconds:
            context = self.spark.sparkContext
            self.prior_properties = {
                key: context.getLocalProperty(key)
                for key in (
                    "spark.jobGroup.id",
                    "spark.job.description",
                    "spark.job.interruptOnCancel",
                )
            }
            group = "healthcare-task-" + self.claim.attempt_id
            context.setJobGroup(group, "Bounded ingestion task", interruptOnCancel=True)

            def cancel():
                self.expired.set()
                try:
                    context.cancelJobGroup(group)
                except Exception:
                    pass

            self.timer = threading.Timer(self.timeout_seconds, cancel)
            self.timer.daemon = True
            self.timer.start()
        self.thread.start()
        return self

    def fence(self):
        if self.expired.is_set():
            raise RuntimeError("Pinned task execution timeout exhausted.")
        if self.error is not None:
            raise LeaseLost("Execution heartbeat unavailable.") from self.error
        return self.store.assert_fence(self.claim)

    def __exit__(self, *_):
        if self.timer:
            self.timer.cancel()
        for key, value in self.prior_properties.items():
            self.spark.sparkContext.setLocalProperty(key, value)
        self.stopped.set()
        self.thread.join(timeout=35)
        if self.thread.is_alive():
            raise LeaseLost("Heartbeat connection did not stop within its bounded timeout.")


def capture_sql(
    spark,
    connection,
    contract,
    table,
    path,
    expected_batch,
    watermark_lower,
    fence,
    expected_coverage_end=None,
    record_discovery=None,
    expected_coverage_start=None,
):
    """One bounded source cursor; a shared transaction lock excludes the approved loader."""
    schema = mapped_schema(table)
    cursor = connection.cursor()
    version, rows = -1, 0
    try:
        if getattr(connection, "autocommit", False):
            raise ValueError("Source capture requires a non-autocommit connection.")
        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; IF @@TRANCOUNT=0 BEGIN TRANSACTION; "
            "DECLARE @r int; EXEC @r=sys.sp_getapplock "
            "@Resource=N'healthcare-ingestion-source',@LockMode=N'Shared',"
            "@LockOwner=N'Transaction',@DbPrincipal=N'public',@LockTimeout=30000; "
            "IF @r<0 THROW 51000,'Source capture lock unavailable',1;"
        )
        source = contract["source_system"]
        head = source_checkpoint_evidence(cursor, source)
        committed = source_checkpoint_evidence(cursor, source, expected_batch)
        if not head or not committed or head != committed or head.get("batch") != expected_batch:
            raise ValueError("Expected source batch is missing, failed or no longer current.")
        coverage_end = timestamp7(head["coverage_end"])
        coverage_start = timestamp7(head["coverage_start"])
        if not coverage_start or not coverage_end or coverage_start > coverage_end:
            raise ValueError("Verified source coverage boundaries are required.")
        if expected_coverage_end and coverage_end != timestamp7(expected_coverage_end):
            raise ValueError("Source coverage differs from the pinned committed boundary.")
        if expected_coverage_start and coverage_start != timestamp7(expected_coverage_start):
            raise ValueError("Source coverage starts outside the pinned committed boundary.")
        selected = {**contract, "tables": [table]}
        shared = getattr(connection, "workflow_discovery_results", None)
        if shared is not None:
            connection.assert_transaction()
            result = shared[table["name"]]
        else:
            result = discover(connection, selected)[0]
        if record_discovery:
            record_discovery(result)
        if not result.accepted:
            raise ValueError("Strict live source schema validation failed.")
        names = [c["name"] for c in table["columns"]]
        watermark = "EtlModifiedAtUtc" if source == "Caboodle" else "ModifiedAtUtc"
        if watermark not in names:
            raise ValueError("Capture requires the approved source audit watermark.")
        cursor.execute(
            f"SELECT CONVERT(varchar(33),MAX({identifier(watermark)}),126) "
            f"FROM {identifier(contract['schema'])}.{identifier(table['name'])}"
        )
        watermark_upper = timestamp7(cursor.fetchone()[0])
        watermark_lower = timestamp7(watermark_lower)
        if watermark_lower and (not watermark_upper or watermark_upper < watermark_lower):
            raise ValueError("Source row watermark regressed; source reset needs review.")
        incremental = watermark_lower is not None
        sql = extraction_query(contract["schema"], table, watermark if incremental else None)
        parameters = (watermark_lower, watermark_upper) if incremental else ()
        fence()
        cursor.execute(sql, *parameters)
        timestamp_indices = [
            i for i, c in enumerate(table["columns"]) if c["sql_type"].startswith("datetime2")
        ]
        while True:
            batch = cursor.fetchmany(5000)
            if not batch:
                break
            values = [list(row) for row in batch]
            for row in values:
                for index in timestamp_indices:
                    row[index] = timestamp7(row[index])
            frame = spark.createDataFrame([tuple(row) for row in values], schema)
            assert_schema(frame, schema)
            fence()
            (
                frame.write.format("delta")
                .mode("errorifexists" if version < 0 else "append")
                .option("mergeSchema", "false")
                .save(path)
            )
            rows += len(batch)
            version += 1
        if version < 0:
            spark.createDataFrame([], schema).write.format("delta").mode("errorifexists").save(path)
            version = 0
        connection.commit()
        return {
            "path": path,
            "version": version,
            "rows": rows,
            "contract_hash": fingerprint(selected),
            "schema_hash": result.expected_hash,
            "capture_mode": "WATERMARK" if incremental else "FULL",
            "approved_table": table,
            "watermark_column": watermark,
            "watermark_lower": watermark_lower,
            "watermark_upper": watermark_upper,
            "source_name": f"{source}.{contract['schema']}.{table['name']}",
            "coverage": {
                "complete": True,
                "checkpoint": head,
                "window_start": coverage_start,
                "window_end": coverage_end,
            },
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def run_operation(
    store,
    snapshot,
    operation_id,
    task_id,
    environment,
    owner,
    spark,
    artifacts,
    staging_root,
    source_factory=None,
    contracts=None,
    coverage_proof=None,
    dag_run_id=None,
    historical_capture=None,
    event_sink=None,
):
    """Run an already queued/pinned task; no implicit publication or input substitution."""
    operation = store.operation(operation_id)
    if (
        operation["task_id"] != task_id
        or operation["environment"] != environment
        or operation["snapshot_hash"] != snapshot.digest
        or operation["release_version"] != snapshot.version
    ):
        raise ValueError("Operation does not belong to the pinned task/environment/release.")
    task = snapshot.task(task_id)
    output = snapshot.dataset(task.primary_output)
    mapping = snapshot.physical(output.dataset_id, environment)
    target = mapping["path"]
    bindings = store.inputs(operation_id)
    claim = store.claim(operation_id, owner, lease_seconds=300)
    if claim is None:
        return None
    if len(bindings) != 1 or len(task.inputs) != 1:
        store.fail(claim, "INPUT_BINDING_INVALID")
        raise ValueError("This release supports one primary input per Bronze/Patient task.")
    binding = bindings[0]
    if binding.dataset_id != task.inputs[0].dataset_id:
        store.fail(claim, "INPUT_BINDING_INVALID")
        raise ValueError("Pinned binding does not match the task input.")
    timeout = snapshot.effective_settings(task_id)["scheduler"]["timeout_seconds"]
    with ExecutionLease(store, claim, spark, timeout) as lease:
        try:
            result = _execute(
                store,
                snapshot,
                operation,
                task,
                output,
                binding,
                target,
                lease,
                spark,
                artifacts,
                staging_root,
                source_factory,
                contracts,
                dag_run_id or operation_id,
                historical_capture,
            )
        except Exception:
            if event_sink:
                _emit(event_sink, "RunFailed", operation, claim)
            raise
        if event_sink:
            _emit(event_sink, "RunSucceeded", operation, claim)
        return result


def _emit(sink, event, operation, claim):
    try:
        sink.emit(
            event,
            {
                "operation_id": operation["operation_id"],
                "attempt_id": claim.attempt_id,
                "release_version": operation["release_version"],
                "task_id": operation["task_id"],
                "environment": operation["environment"],
            },
        )
    except Exception:
        # Diagnostic transport cannot reverse an independently committed publication.
        pass


def bound_delta_path(store, snapshot, binding, environment):
    if not binding.output_id:
        raise ValueError("Delta reads require the exact committed output identity.")
    outputs = store.output_history(binding.dataset_id, environment)
    output = next((value for value in outputs if value["output_id"] == binding.output_id), None)
    if not output or str(output["delta_version"]) != str(binding.version):
        raise ValueError("The pinned committed Delta input is unavailable.")
    producer = store.operation(output["operation_id"])
    producer_snapshot = store.snapshot(producer["release_version"])
    return producer_snapshot.physical(binding.dataset_id, environment)["path"]


def _execute(
    store,
    snapshot,
    operation,
    task,
    output,
    binding,
    target,
    lease,
    spark,
    artifacts,
    staging_root,
    source_factory,
    contracts,
    dag_run_id,
    historical_capture,
):
    operation_id = operation["operation_id"]
    environment = operation["environment"]
    fence = lease.fence

    key = operation_id + "/capture.json"
    commit_key = operation_id + "/commit.json"
    write_key = operation_id + "/write-started.json"
    write_started = False
    quality_context = {
        "operation_id": operation_id,
        "attempt_id": lease.claim.attempt_id,
        "release_version": snapshot.version,
    }

    def verify_and_record(evidence):
        valid = verify_commit(spark, artifacts, evidence)
        store.record_quality_outcome(
            {
                **quality_context,
                "check": "post_write_reconciliation",
                "status": "PASS" if valid else "FAIL",
                "reason": None if valid else "DATA_RECONCILIATION_MISMATCH",
                "evidence_digest": evidence.validation_digest,
            }
        )
        return valid

    def record_discovery(result):
        discovery_key = operation_id + "/discovery-" + lease.claim.attempt_id + ".json"
        digest = artifacts.put(
            discovery_key,
            {
                "table": result.table,
                "expected_hash": result.expected_hash,
                "actual_hash": result.actual_hash,
                "differences": list(result.differences),
                "release_hash": snapshot.digest,
            },
        )
        store.hold_reference("artifact", discovery_key, operation_id)
        store.record_quality_outcome(
            {
                **quality_context,
                "check": "strict_schema_discovery",
                "status": "PASS" if result.accepted else "FAIL",
                "reason": None if result.accepted else "SCHEMA_DRIFT",
                "evidence_digest": digest,
                "artifact": discovery_key,
            }
        )

    try:
        saved_commit = artifacts.get(commit_key)
        if saved_commit:
            evidence = CommitEvidence(**saved_commit)
            fence()
            return store.publish(lease.claim, evidence, verify_and_record)
        proof = artifacts.get(key)
        recovering = artifacts.get(write_key) is not None
        if proof is None:
            input_dataset = snapshot.dataset(binding.dataset_id)
            if input_dataset.layer == "source":
                source_mapping = snapshot.physical(binding.dataset_id, environment)
                if not contracts:
                    raise ValueError("A pinned approved source contract is required.")
                contract = contracts[source_mapping["connection_ref"]]
                table = next(t for t in contract["tables"] if t["name"] == source_mapping["table"])
                previous = store.output_history(output.dataset_id, environment)
                previous_proof = None
                if (
                    previous
                    and operation["source_mode"] == "current"
                    and (operation["kind"] != "backfill")
                ):
                    latest = max(previous, key=lambda entry: entry["window_end"])
                    previous_proof = artifacts.get(latest["operation_id"] + "/capture.json")
                    if not previous_proof or "watermark_upper" not in previous_proof:
                        raise ValueError("Last committed row watermark proof is unavailable.")
                if operation["source_mode"] == "historical":
                    if not binding.source_snapshot_id or not historical_capture:
                        raise ValueError("Historical capture unavailable; no current substitution.")
                    captured = historical_capture(binding.source_snapshot_id)
                    if (
                        captured.get("source_snapshot_id") != binding.source_snapshot_id
                        or captured.get("source_version") != binding.version
                        or captured.get("contract_hash")
                        != fingerprint({**contract, "tables": [table]})
                        or timestamp7(captured["coverage"]["window_start"])
                        != (binding.source_coverage_start or binding.window_start)
                        or timestamp7(captured["coverage"]["window_end"])
                        != (binding.source_coverage_end or binding.window_end)
                    ):
                        raise ValueError("Historical capture does not match the pinned input.")
                    assert_schema(
                        fixed_read(spark, captured["path"], captured["version"]),
                        mapped_schema(table),
                    )
                else:
                    if not source_factory:
                        raise ValueError("A verified source connection is required.")
                    connection = source_factory(source_mapping["connection_ref"])
                    try:
                        captured = capture_sql(
                            spark,
                            connection,
                            contract,
                            table,
                            artifact_path(staging_root, operation_id, lease.claim.attempt_id),
                            binding.version,
                            (
                                previous_proof["watermark_upper"]
                                if previous_proof and operation["kind"] != "backfill"
                                else None
                            ),
                            fence,
                            expected_coverage_end=binding.source_coverage_end or binding.window_end,
                            record_discovery=record_discovery,
                            expected_coverage_start=(
                                binding.source_coverage_start or binding.window_start
                            ),
                        )
                    finally:
                        connection.close()
                if (
                    not previous
                    and table["name"] in {"Patient", "DimPatient", "PatientDim"}
                    and captured["rows"] == 0
                ):
                    raise ValueError("Initial Patient/DimPatient must be nonempty.")
                proof = dict(captured)
            else:
                frame = fixed_read(
                    spark,
                    bound_delta_path(store, snapshot, binding, environment),
                    int(binding.version),
                )
                for function in task.functions:
                    if function.function not in REGISTRY:
                        raise ValueError("Unregistered transformation.")
                    frame = REGISTRY[function.function](frame, **function.parameters)
                frame = apply_task_quality(
                    frame,
                    snapshot,
                    task.task_id,
                    lease.claim,
                    artifact_path(staging_root, "quarantine"),
                    store,
                    {binding.dataset_id: binding.version},
                    artifacts=artifacts,
                )
                path = artifact_path(staging_root, operation_id, lease.claim.attempt_id)
                frame.write.format("delta").mode("errorifexists").save(path)
                proof = {"path": path, "version": 0, "rows": frame.count()}
            proof.update(
                operation_id=operation_id,
                release_hash=snapshot.digest,
                input_versions={binding.dataset_id: binding.version},
                dataset_id=output.dataset_id,
                target_path=target,
                base_version=current_version(spark, target),
                window_start=operation["window_start"],
                window_end=operation["window_end"],
                input_coverage={
                    binding.dataset_id: {
                        "window_start": binding.source_coverage_start or binding.window_start,
                        "window_end": binding.source_coverage_end or binding.window_end,
                    },
                },
                source_coverage_start=binding.source_coverage_start or binding.window_start,
                source_coverage_end=binding.source_coverage_end or binding.window_end,
                extracted_at=datetime.now(UTC).isoformat(),
                dag_run_id=dag_run_id,
                output_layer=output.layer,
            )
            fence()
            artifacts.put(key, proof)
            store.hold_reference("artifact", key, operation_id)
            store.hold_reference("artifact", proof["path"], operation_id)
        if (
            proof["release_hash"] != snapshot.digest
            or proof["input_versions"] != {binding.dataset_id: binding.version}
            or proof["dataset_id"] != output.dataset_id
            or proof["operation_id"] != operation_id
            or proof["target_path"] != target
            or proof["window_start"] != operation["window_start"]
            or proof["window_end"] != operation["window_end"]
        ):
            raise ValueError("Saved capture belongs to another release/input/output.")
        frame = fixed_read(spark, proof["path"], proof["version"])
        if output.layer == "bronze":
            assert_schema(frame, mapped_schema(proof["approved_table"]))
            apply_task_quality(
                frame,
                snapshot,
                task.task_id,
                lease.claim,
                artifact_path(staging_root, "quarantine"),
                store,
                {binding.dataset_id: binding.version},
                artifacts=artifacts,
            )
        intent = PublicationIntent(
            operation_id, output.dataset_id, proof["base_version"], recovering
        )
        fence()
        artifacts.put(write_key, {"capture_digest": hashlib.sha256(encoded(proof)).hexdigest()})
        write_started = True
        if output.layer == "bronze":
            context = {
                "_ingest_batch_id": operation_id,
                "_ingest_run_id": proof["dag_run_id"],
                "_ingest_table_run_id": lease.claim.attempt_id,
                "_ingest_source_name": proof["source_name"],
                "_ingest_extracted_at_utc": datetime.fromisoformat(proof["extracted_at"]),
                "_ingest_landed_at_utc": datetime.now(UTC),
                "_ingest_capture_mode": proof["capture_mode"],
            }
            version = append_bronze(bronze_frame(frame, context), target, intent, fence)
        elif output.layer == "silver1":
            version = merge_patient(frame, target, "PatientID", "ModifiedAtUtc", intent, fence)
        else:
            raise ValueError("No downstream business layers are authorized.")
        evidence = CommitEvidence(
            operation_id=operation_id,
            dataset_id=output.dataset_id,
            delta_version=str(version),
            window_start=operation["window_start"],
            window_end=operation["window_end"],
            input_versions=proof["input_versions"],
            validation_digest=hashlib.sha256(encoded(proof)).hexdigest(),
            coverage_verified=True,
            changed_rows=proof["rows"],
            commit_token=operation_id,
            source_coverage_start=proof["source_coverage_start"],
            source_coverage_end=proof["source_coverage_end"],
        )
        artifacts.put(commit_key, evidence.to_dict())
        fence()
        output_id = store.publish(lease.claim, evidence, verify_and_record)
        store.release_reference("artifact", proof["path"], operation_id)
        return output_id
    except Exception as error:
        try:
            if (
                not write_started
                and not lease.expired.is_set()
                and (
                    isinstance(error, (TimeoutError, ConnectionError))
                    or type(error).__name__ in {"ServiceRequestError", "ServiceResponseError"}
                    or (
                        type(error).__module__ == "pyodbc"
                        and error.args
                        and str(error.args[0])
                        in {"08001", "08003", "08007", "08S01", "40001", "HYT00", "HYT01"}
                    )
                )
            ):
                artifacts.put(
                    f"{operation_id}/transient-{lease.claim.attempt_id}.json",
                    {
                        "attempt_id": lease.claim.attempt_id,
                        "reason_code": "TRANSIENT_TRANSPORT_FAILURE",
                    },
                )
            store.fail(
                lease.claim,
                "EXECUTION_UNCERTAIN"
                if write_started
                else ("TASK_TIMEOUT" if lease.expired.is_set() else "EXECUTION_FAILED"),
                uncertain=write_started,
            )
        except (MetadataUnavailable, LeaseLost):
            pass
        raise


def verify_commit(spark, artifacts, evidence):
    proof = artifacts.get(evidence.operation_id + "/capture.json")
    if not proof or hashlib.sha256(encoded(proof)).hexdigest() != evidence.validation_digest:
        return False
    if proof["input_versions"] != dict(evidence.input_versions):
        return False
    # Target binding is saved independently of mutable names or current physical mappings.
    target = proof.get("target_path")
    if not target:
        return False
    intent = PublicationIntent(
        evidence.operation_id, evidence.dataset_id, proof["base_version"], True
    )
    version = publication_evidence(history(spark, target), intent)
    if version != int(evidence.delta_version):
        return False
    from pyspark.sql import functions as f

    frame = fixed_read(spark, target, version)
    source = fixed_read(spark, proof["path"], proof["version"])
    if proof["output_layer"] == "bronze":
        assert_schema(source, mapped_schema(proof["approved_table"]))
    if source.count() != proof["rows"] or evidence.changed_rows != proof["rows"]:
        return False
    if proof["output_layer"] == "bronze":
        actual = frame.where(f.col("_ingest_batch_id") == evidence.operation_id)
        expected = source
        actual = actual.select(*expected.columns)
    elif proof["output_layer"] == "silver1":
        key, modified = "PatientID", "ModifiedAtUtc"
        if source.groupBy(key).count().where("count > 1").limit(1).count():
            return False
        if frame.groupBy(key).count().where("count > 1").limit(1).count():
            return False
        expected = source
        if version > 0:
            prior = fixed_read(spark, target, version - 1)
            combined = source.alias("s").join(
                prior.alias("p"), f.col(f"s.`{key}`") == f.col(f"p.`{key}`"), "full_outer"
            )
            newer = f.col(f"s.`{key}`").isNotNull() & (
                f.col(f"p.`{key}`").isNull() | (f.col(f"s.`{modified}`") > f.col(f"p.`{modified}`"))
            )
            expected = combined.select(
                *(
                    f.when(newer, f.col(f"s.`{c}`")).otherwise(f.col(f"p.`{c}`")).alias(c)
                    for c in source.columns
                )
            )
        actual = frame.select(*source.columns)
    else:
        return False
    if actual.exceptAll(expected).limit(1).count() or expected.exceptAll(actual).limit(1).count():
        return False
    return (
        evidence.commit_token == evidence.operation_id
        and evidence.coverage_verified
        and proof["window_start"] == evidence.window_start
        and proof["window_end"] == evidence.window_end
        and proof["source_coverage_start"] == evidence.source_coverage_start
        and proof["source_coverage_end"] == evidence.source_coverage_end
    )


def reconcile_operation(store, operation_id, spark, artifacts):
    """Recover a sealed Delta receipt without recapturing or executing transformations."""
    saved = artifacts.get(operation_id + "/commit.json")
    if saved is None:
        proof = artifacts.get(operation_id + "/capture.json")
        write = artifacts.get(operation_id + "/write-started.json")
        if not proof or not write:
            return None
        digest = hashlib.sha256(encoded(proof)).hexdigest()
        if write.get("capture_digest") != digest:
            raise ValueError("Write intent differs from the sealed capture.")
        if current_version(spark, proof["target_path"]) < 0:
            return None
        version = publication_evidence(
            history(spark, proof["target_path"]),
            PublicationIntent(
                operation_id,
                proof["dataset_id"],
                proof["base_version"],
                True,
            ),
        )
        if version is None:
            return None
        recovered = CommitEvidence(
            operation_id=operation_id,
            dataset_id=proof["dataset_id"],
            delta_version=str(version),
            window_start=proof["window_start"],
            window_end=proof["window_end"],
            input_versions=proof["input_versions"],
            validation_digest=digest,
            coverage_verified=True,
            changed_rows=proof["rows"],
            commit_token=operation_id,
            source_coverage_start=proof["source_coverage_start"],
            source_coverage_end=proof["source_coverage_end"],
        )
        if not verify_commit(spark, artifacts, recovered):
            raise ValueError("Actual Delta data does not match the sealed write intent.")
        artifacts.put(operation_id + "/commit.json", recovered.to_dict())
        saved = recovered.to_dict()
    evidence = CommitEvidence(**saved)
    output_id = store.reconcile_commit(
        operation_id, evidence, lambda entry: verify_commit(spark, artifacts, entry)
    )
    proof = artifacts.get(operation_id + "/capture.json")
    store.release_reference("artifact", proof["path"], operation_id)
    return output_id
