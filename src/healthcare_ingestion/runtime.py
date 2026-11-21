"""Generic notebook worker with explicit machine credentials and pinned execution."""

import hashlib
import os
import re
import struct
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from threading import Lock
from uuid import UUID

from healthcare_ingestion.artifacts import BlobArtifactStore, encoded
from healthcare_ingestion.configuration import thaw
from healthcare_ingestion.control_store import InputBinding, SqlServerControlStore
from healthcare_ingestion.coordinator import resolve_waiting
from healthcare_ingestion.execution import reconcile_operation, run_operation
from healthcare_ingestion.source_contracts import bind_source_contracts
from healthcare_ingestion.source_status import utc_coverage_time
from healthcare_ingestion.sql_source import source_checkpoint_evidence
from healthcare_ingestion.workflow_source import WorkflowSource


def sql_factory(endpoint, credential):
    server, database = endpoint["server"], endpoint["database"]
    if (
        not re.fullmatch(r"[a-zA-Z0-9.-]+", server)
        or not re.fullmatch(r"[a-zA-Z0-9_-]+", database)
        or not server.endswith((".database.windows.net", ".database.fabric.microsoft.com"))
    ):
        raise ValueError("Resolved SQL data-plane server and database names are required.")

    def connect():
        import pyodbc

        token = credential.get_token("https://database.windows.net/.default").token
        data = token.encode("utf-16-le")
        connection = pyodbc.connect(
            f"Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{server},1433;"
            f"Database={database};Encrypt=yes;TrustServerCertificate=no;",
            attrs_before={1256: struct.pack("<I", len(data)) + data},
            autocommit=False,
            timeout=30,
        )
        connection.timeout = 30
        return connection

    return connect


def certificate_identity(config):
    from azure.identity import CertificateCredential

    UUID(config["tenant_id"])
    UUID(config["client_id"])
    variable = config["certificate_path_env"]
    if not re.fullmatch(r"HC_[A-Z0-9_]+", variable):
        raise ValueError("Machine certificates require an explicit driver environment reference.")
    path = os.environ.get(variable)
    if not path or not Path(path).is_file():
        raise ValueError("Required scoped machine certificate is unavailable.")
    return CertificateCredential(
        config["tenant_id"],
        config["client_id"],
        certificate_path=path,
    )


class ConfiguredCredential:
    """Load only the credential actually used by a dependent operation."""

    def __init__(self, config):
        self.config, self.credential = config, None
        self.lock = Lock()

    def get_token(self, *scopes, **kwargs):
        with self.lock:
            if self.credential is None:
                self.credential = certificate_identity(self.config)
        return self.credential.get_token(*scopes, **kwargs)


@contextmanager
def spark_settings(spark, settings):
    for key, expected in settings.get("startup", {}).items():
        if spark.sparkContext.getConf().get(key, None) != str(expected):
            raise ValueError("The running Spark session differs from the pinned startup profile.")
    prior = {}
    try:
        for key, value in settings.get("runtime", {}).items():
            prior[key] = spark.conf.get(key, None)
            spark.conf.set(key, value)
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                spark.conf.unset(key)
            else:
                spark.conf.set(key, value)


@dataclass
class Worker:
    store: object
    artifacts: object
    spark: object
    staging_root: str
    source_factory: object
    expected_source: object = None
    historical_capture: object = None
    events: object = None
    dispatch: object = None

    def evaluate_health(self, context, current, baseline, memory_samples, policy):
        from healthcare_ingestion.events import duration_regression, memory_pressure

        signals = []
        if policy.get("duration") and duration_regression(current, baseline, **policy["duration"]):
            signals.append("DurationRegression")
        if policy.get("memory") and memory_pressure(memory_samples, **policy["memory"]):
            signals.append("MemoryPressure")
        if self.events:
            for signal in signals:
                self.events.emit(signal, context)
        return tuple(signals)

    def acknowledge_generator(self, state, expected, environment, release_version):
        from healthcare_ingestion.control_store import CommitEvidence
        from healthcare_ingestion.execution import verify_commit

        snapshot = self.store.snapshot(release_version)
        contracts = bind_source_contracts(snapshot, thaw(snapshot.artifacts["source_contracts"]))
        tables = {"Clarity": [], "Caboodle": []}
        for task in snapshot.tasks:
            if task.retired or snapshot.dataset(task.primary_output).layer != "bronze":
                continue
            source_mapping = snapshot.physical(task.inputs[0].dataset_id, environment)
            source = contracts[source_mapping["connection_ref"]]["source_system"]
            if not self.store.readiness(task.primary_output, environment, task.scope)["ready"]:
                return False
            candidates = self.store.output_history(task.primary_output, environment)
            consumed = False
            for output in candidates:
                inputs = self.store.inputs(output["operation_id"])
                if not inputs or inputs[0].version != expected.batch:
                    continue
                receipt = self.artifacts.get(output["operation_id"] + "/commit.json")
                if receipt and verify_commit(self.spark, self.artifacts, CommitEvidence(**receipt)):
                    consumed = True
                    break
            if not consumed:
                return False
            tables[source].append(source_mapping["table"])
        approved = {
            contract["source_system"]: sorted(table["name"] for table in contract["tables"])
            for contract in contracts.values()
        }
        if {source: sorted(names) for source, names in tables.items()} != approved:
            raise ValueError("Consumption acknowledgement requires all approved 28 tables.")
        if expected.population_digest is None:
            return False
        with state.exclusive():
            state.acknowledge_batch(
                expected.batch,
                plan_digest=expected.plan_digest,
                source_digests={source: expected.population_digest for source in tables},
                tables={source: sorted(names) for source, names in tables.items()},
            )
        return True

    def retained_capture(self, source_snapshot_id):
        from healthcare_ingestion.delta_io import fixed_read
        from healthcare_ingestion.quality import content_digest

        info = self.store.source_snapshot_info(source_snapshot_id)
        proof = self.artifacts.get(info["artifact_ref"])
        if (
            not proof
            or hashlib.sha256(encoded(proof)).hexdigest() != info["evidence_digest"]
            or not {"path", "version", "rows", "coverage", "source_version", "content_digest"}
            <= set(proof)
            or proof["source_version"] != info["version"]
            or utc_coverage_time(proof["coverage"]["window_start"]) != info["window_start"]
            or utc_coverage_time(proof["coverage"]["window_end"]) != info["window_end"]
        ):
            raise ValueError("Retained historical capture is unavailable or mismatched.")
        frame = fixed_read(self.spark, proof["path"], proof["version"])
        if frame.count() != proof["rows"] or content_digest(frame) != proof["content_digest"]:
            raise ValueError("Retained historical data differs; no current-source substitution.")
        return {
            **proof,
            "source_snapshot_id": source_snapshot_id,
            "coverage": {key: utc_coverage_time(value) for key, value in proof["coverage"].items()},
        }

    def benchmark(self, operation_id, attempt_id, root):
        from healthcare_ingestion.benchmark import benchmark_task
        from healthcare_ingestion.delta_io import fixed_read
        from healthcare_ingestion.execution import bound_delta_path

        operation = self.store.operation(operation_id)
        snapshot = self.store.snapshot(operation["release_version"])
        task = snapshot.task(operation["task_id"])
        if (
            not snapshot.effective_settings(task.task_id)
            .get("observability", {})
            .get("profile_transformations", False)
        ):
            return []
        if snapshot.dataset(task.primary_output).layer != "silver1":
            raise ValueError("Only the approved Patient transformation benchmark exists.")
        bindings = self.store.inputs(operation_id)
        if len(bindings) != 1:
            raise ValueError("Benchmarks require one immutable primary input.")
        binding = bindings[0]
        return benchmark_task(
            fixed_read(
                self.spark,
                bound_delta_path(self.store, snapshot, binding, operation["environment"]),
                int(binding.version),
            ),
            snapshot,
            task.task_id,
            {"operation_id": operation_id, "attempt_id": attempt_id},
            {binding.dataset_id: binding.version},
            root,
            self.store,
        )

    def collect_diagnostics(
        self,
        operation_id,
        attempt_id,
        activity_run_id,
        spark_attempt,
        client,
        files,
        save,
        collection_attempt=0,
    ):
        from healthcare_ingestion.diagnostics import collect_attempt

        operation = self.store.operation(operation_id)
        result = collect_attempt(
            self.store,
            client,
            spark_attempt,
            {
                "operation_id": operation_id,
                "attempt_id": attempt_id,
                "release_version": operation["release_version"],
                "activity_run_id": activity_run_id,
            },
            files,
            save,
            collection_attempt=collection_attempt,
        )
        if self.events and (
            result["metrics"]["failures"]
            or any(log["status"] == "UNAVAILABLE" for log in result["logs"])
        ):
            self.events.emit(
                "TelemetryGap",
                {
                    "operation_id": operation_id,
                    "attempt_id": attempt_id,
                    "release_version": operation["release_version"],
                },
            )
        return result

    def execute(self, operation_id, owner, dag_run_id):
        operation = self.store.operation(operation_id)
        snapshot = self.store.snapshot(operation["release_version"])
        if version("healthcare-ingestion") != snapshot.version:
            raise ValueError(
                "The installed package is not the operation's pinned framework release."
            )
        pinned = thaw(snapshot.artifacts.get("source_contracts", {}))
        if not pinned:
            raise ValueError("The deployed release must embed its approved source contracts.")
        pinned = bind_source_contracts(snapshot, pinned)
        task = snapshot.task(operation["task_id"])
        mapping = snapshot.physical(task.primary_output, operation["environment"])
        if "://" in mapping["path"]:
            namespace = mapping["schema"]
            if namespace not in {"clarity", "caboodle"}:
                raise ValueError("No additional output namespaces are authorized for this demo.")
            self.spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{namespace}`")
        with spark_settings(self.spark, snapshot.effective_settings(task.task_id).get("spark", {})):
            return run_operation(
                self.store,
                snapshot,
                operation_id,
                operation["task_id"],
                operation["environment"],
                owner,
                self.spark,
                self.artifacts,
                self.staging_root,
                self.source_factory,
                pinned,
                dag_run_id=dag_run_id,
                historical_capture=self.historical_capture or self.retained_capture,
                event_sink=self.events,
            )

    def execute_workflow(self, operation_ids, owner, dag_run_id):
        if not operation_ids:
            return {}
        operations = [self.store.operation(identity) for identity in operation_ids]
        releases = {operation["release_version"] for operation in operations}
        environments = {operation["environment"] for operation in operations}
        if len(releases) != 1 or len(environments) != 1:
            raise ValueError("A workflow run must keep one pinned release and environment.")
        snapshot = self.store.snapshot(operations[0]["release_version"])
        tasks = [snapshot.task(operation["task_id"]) for operation in operations]
        if len({task.workflow for task in tasks}) != 1:
            raise ValueError("Operations belong to different logical workflows.")
        from healthcare_ingestion.airflow_runtime import execution_signature

        if len({encoded(execution_signature(snapshot, task.task_id)) for task in tasks}) != 1:
            raise ValueError("A workflow invocation must keep one pinned execution profile.")
        contracts = bind_source_contracts(snapshot, thaw(snapshot.artifacts["source_contracts"]))
        selections = {}
        for task in tasks:
            dataset = snapshot.dataset(task.inputs[0].dataset_id)
            if dataset.layer == "source":
                mapping = snapshot.physical(dataset.dataset_id, operations[0]["environment"])
                selections.setdefault(mapping["connection_ref"], set()).add(mapping["table"])
        outcomes = {}
        with ExitStack() as stack:
            sources = {
                name: stack.enter_context(
                    WorkflowSource(
                        self.source_factory(name),
                        contracts[name],
                        tables,
                    )
                )
                for name, tables in selections.items()
            }
            scoped = Worker(
                self.store,
                self.artifacts,
                self.spark,
                self.staging_root,
                lambda name: sources[name],
                self.expected_source,
                self.historical_capture,
                self.events,
                self.dispatch,
            )
            expected = self.expected_source() if self.expected_source and selections else None

            def source_binding(operation, spec):
                if expected is None or expected.coverage is None:
                    return None
                dataset = snapshot.dataset(spec.dataset_id)
                mapping = snapshot.physical(dataset.dataset_id, operation["environment"])
                source = sources[mapping["connection_ref"]]
                source.assert_transaction()
                cursor = source.cursor()
                try:
                    head = source_checkpoint_evidence(
                        cursor, contracts[mapping["connection_ref"]]["source_system"]
                    )
                    committed = source_checkpoint_evidence(
                        cursor,
                        contracts[mapping["connection_ref"]]["source_system"],
                        expected.batch,
                    )
                finally:
                    cursor.close()
                if head != committed or not expected.matches(head):
                    return None
                proof = {
                    "batch": expected.batch,
                    "plan_digest": expected.plan_digest,
                    "head": head,
                    "dataset_id": dataset.dataset_id,
                }
                proof_digest = hashlib.sha256(encoded(proof)).hexdigest()
                key = f"source-checkpoints/{proof_digest}.json"
                self.artifacts.put(key, proof)

                def verify():
                    source.assert_transaction()
                    current = self.expected_source()
                    return (
                        current is not None
                        and current.batch == expected.batch
                        and current.plan_digest == expected.plan_digest
                        and current.matches(head)
                        and self.artifacts.get(key) == proof
                    )

                source_id = self.store.register_source_snapshot(
                    dataset.dataset_id,
                    operation["environment"],
                    expected.batch,
                    utc_coverage_time(expected.coverage["start"]),
                    utc_coverage_time(expected.coverage["end"]),
                    evidence_digest=proof_digest,
                    artifact_ref=key,
                    verify_snapshot=verify,
                    scope=snapshot.task(operation["task_id"]).scope,
                )
                return InputBinding(
                    dataset.dataset_id,
                    expected.batch,
                    operation["window_start"],
                    operation["window_end"],
                    source_snapshot_id=source_id,
                    source_coverage_start=utc_coverage_time(expected.coverage["start"]),
                    source_coverage_end=utc_coverage_time(expected.coverage["end"]),
                )

            for operation in operations:
                identity = operation["operation_id"]
                try:
                    if operation["status"] == "UNCERTAIN":
                        recovered = reconcile_operation(
                            self.store, identity, self.spark, self.artifacts
                        )
                        if recovered is not None:
                            outcomes[identity] = {"reconciled": recovered}
                            continue
                        outcomes[identity] = {"status": "UNCERTAIN_REQUIRES_OPERATOR"}
                        continue
                    if not resolve_waiting(self.store, identity, source_binding):
                        outcomes[identity] = {"status": "BLOCKED_BY_DEPENDENCY"}
                        continue
                    outcomes[identity] = {
                        "output_id": scoped.execute(identity, owner, dag_run_id),
                    }
                except Exception as error:
                    outcomes[identity] = {"error": type(error).__name__}
        if self.dispatch:
            try:
                self.dispatch()
            except Exception:
                try:
                    if self.events:
                        self.events.emit(
                            "TelemetryGap",
                            {
                                "release_version": snapshot.version,
                                "environment": operations[0]["environment"],
                                "reason_code": "EVENT_DISPATCH_UNAVAILABLE",
                            },
                        )
                except Exception:
                    pass
        return outcomes


def bootstrap(config, spark, identities=None):
    """No interactive CLI, personal token or undocumented NotebookUtils SQL fallback."""
    from azure.storage.blob import BlobServiceClient, ContainerClient

    from healthcare_ingestion.generator_blob import BlobStateStore
    from healthcare_ingestion.source_status import read_expected

    identities = (
        identities
        if identities is not None
        else {name: ConfiguredCredential(value) for name, value in config["identities"].items()}
    )
    connections = config["connections"]
    factories = {
        name: sql_factory(endpoint, identities[endpoint["identity_ref"]])
        for name, endpoint in connections.items()
    }
    storage = config["recovery_storage"]
    if not re.fullmatch(
        r"https://[a-z0-9]{3,24}\.blob\.core\.windows\.net/?", storage["account_url"]
    ):
        raise ValueError("Recovery credentials require the approved Azure Blob origin.")
    container = ContainerClient(
        storage["account_url"],
        storage["container"],
        credential=identities[storage["identity_ref"]],
    )
    expected = None
    if "generator_storage" in config:
        generator = config["generator_storage"]
        if not re.fullmatch(
            r"https://[a-z0-9]{3,24}\.blob\.core\.windows\.net/?", generator["account_url"]
        ):
            raise ValueError("Generator credentials require the approved Azure Blob origin.")
        state = BlobStateStore(
            BlobServiceClient(
                generator["account_url"],
                credential=identities[generator["identity_ref"]],
            ),
            state_container=generator["state_container"],
            export_container=generator["export_container"],
            manifest_container=generator["manifest_container"],
        )

        def expected():
            return read_expected(state)

    from healthcare_ingestion.events import EventSink

    artifacts = BlobArtifactStore(container, storage["prefix"])
    deliver = None
    if "log_ingestion" in config:
        from azure.monitor.ingestion import LogsIngestionClient

        logs = config["log_ingestion"]
        if not re.fullmatch(
            r"https://[a-zA-Z0-9.-]+\.ingest\.monitor\.azure\.com/?", logs["endpoint"]
        ):
            raise ValueError("Log credentials require the approved Azure Monitor origin.")
        client = LogsIngestionClient(
            logs["endpoint"], identities[logs["identity_ref"]], retry_total=2
        )

        def deliver(row):
            client.upload(rule_id=logs["rule_id"], stream_name=logs["stream"], logs=[row])

    store = SqlServerControlStore(factories["metadata-control"])
    dispatch = None
    if "release_notebooks" in config and "data_workspace_id" in config:

        def dispatch():
            from healthcare_ingestion.airflow_runtime import coordinate_pending
            from healthcare_ingestion.coordinator import dispatch_events

            return dispatch_events(store, lambda _: coordinate_pending(config))

    return Worker(
        store,
        artifacts,
        spark,
        config["staging_root"],
        lambda name: factories[name](),
        expected,
        events=EventSink(artifacts, deliver),
        dispatch=dispatch,
    )
