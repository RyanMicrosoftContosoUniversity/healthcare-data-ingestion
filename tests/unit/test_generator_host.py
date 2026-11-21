import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from healthcare_ingestion.generator_blob import BlobStateStore, LeaseLost
from healthcare_ingestion.generator_host import HostConfig, requested_plan, run_job

ROOT = Path(__file__).resolve().parents[2]


class BlobError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code


class MemoryBlobs:
    """Service double with server-side lease and ETag enforcement, not just local locks."""

    def __init__(self):
        self.objects, self.leases, self.deleted = {}, {}, []

    def get_container_client(self, name):
        assert name in {"state", "exports", "manifests"}
        return SimpleNamespace(get_container_properties=lambda: {})

    def get_blob_client(self, container, key):
        return MemoryBlob(self, (container, key))

    def close(self):
        pass


class MemoryBlob:
    def __init__(self, service, key):
        self.service, self.key = service, key

    def upload_blob(self, data, overwrite=False, lease=None, etag=None, **kwargs):
        objects = self.service.objects
        if lease is not None and self.service.leases.get(self.key) != lease.id:
            raise BlobError(412)
        if etag is not None and objects[self.key][1] != etag:
            raise BlobError(412)
        if self.key in objects and not overwrite:
            raise BlobError(409)
        version = str(int(objects.get(self.key, (None, "0"))[1]) + 1)
        objects[self.key] = (bytes(data), version)
        return {"etag": version}

    def download_blob(self, **kwargs):
        if self.key not in self.service.objects:
            raise BlobError(404)
        return SimpleNamespace(readall=lambda: self.service.objects[self.key][0])

    def get_blob_properties(self, **kwargs):
        return SimpleNamespace(etag=self.service.objects[self.key][1])

    def acquire_lease(self, **kwargs):
        if self.key in self.service.leases:
            raise BlobError(409)
        lease = SimpleNamespace(id=str(uuid4()))
        self.service.leases[self.key] = lease.id

        def renew(**kwargs):
            if self.service.leases.get(self.key) != lease.id:
                raise BlobError(412)

        def release(**kwargs):
            renew()
            del self.service.leases[self.key]

        lease.renew, lease.release = renew, release
        return lease

    def delete_blob(self, **kwargs):
        if self.key not in self.service.objects:
            raise BlobError(404)
        if kwargs.get("etag") is not None and self.service.objects[self.key][1] != kwargs["etag"]:
            raise BlobError(412)
        del self.service.objects[self.key]
        self.service.deleted.append(self.key)


def store(service):
    return BlobStateStore(
        service,
        state_container="state",
        export_container="exports",
        manifest_container="manifests",
    )


class SourceAdapter:
    def __init__(self, failure=False):
        self.committed, self.ledger, self.rows = None, {}, {}
        self.begins, self.writes, self.failure = 0, 0, failure

    def begin(self, *args):
        self.begins += 1
        self.pending = copy.deepcopy(self.rows)

    def checkpoint(self, source):
        return copy.deepcopy(self.committed)

    def batch_commit(self, source, batch):
        return copy.deepcopy(self.ledger.get(batch))

    def assert_empty_source(self, contract):
        assert not self.rows

    def write(self, table, rows, schema):
        self.writes += len(rows)
        if self.failure:
            self.failure = False
            raise RuntimeError("08S01", "simulated transport failure")
        self.pending[table["name"]] = rows

    def commit_checkpoint(self, source, evidence):
        self.committed = {**evidence, "committed_at": "2026-11-01T23:59:59.1234567"}
        self.ledger[evidence["batch"]] = copy.deepcopy(self.committed)
        self.rows = self.pending
        return copy.deepcopy(self.committed)

    def rollback(self):
        self.pending = None

    def close(self):
        pass


@pytest.fixture
def workspace():
    path = ROOT / (".source-test-state-" + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def configuration(workspace):
    return HostConfig(
        "approved",
        "managed-client",
        "state",
        "exports",
        "manifests",
        "clarity.database.windows.net",
        "clarity",
        "caboodle.database.windows.net",
        "caboodle",
        ROOT,
        workspace,
    )


def plan(config, batch="baseline", profile="normal", at="2026-11-01T23:59:59Z"):
    return requested_plan(
        config,
        batch=batch,
        profile=profile,
        at=at,
        history_start="2025-11-01T00:00:00Z",
        patients=2,
        engine="demo",
    )


def test_blob_global_lease_prevents_overlap_and_stale_control_publication():
    service = MemoryBlobs()
    first, second = store(service), store(service)
    with first.exclusive():
        with pytest.raises(BlobError):
            with second.exclusive():
                pytest.fail("overlapping worker")
        original = service.objects[("state", first.CONTROL)][0]
        service.leases[("state", first.CONTROL)] = "new-owner"
        first.control["expected"] = {"batch": "stale"}
        with pytest.raises(BlobError):
            first.save_control()
        assert service.objects[("state", first.CONTROL)][0] == original
        with pytest.raises(LeaseLost):
            first.guard()


def test_blob_checksum_restore_and_immutable_collision(workspace):
    service, blobs = MemoryBlobs(), None
    blobs = store(service)
    with blobs.exclusive():
        ref = blobs.put_bytes("state", "objects/test", b"valid")
        with pytest.raises(ValueError, match="conflicts"):
            blobs.put_bytes("state", "objects/test", b"changed")
        blobs.control["files"]["identities.json"] = blobs.put_json(
            "state", "objects/identities", {"Patient|fixture": 1}
        )
        blobs.save_control()
        blobs.restore(workspace)
        assert json.loads((workspace / "identities.json").read_text()) == {"Patient|fixture": 1}
        service.objects[("state", ref["key"])] = (b"tampered", "2")
        with pytest.raises(ValueError, match="checksum"):
            blobs.read_ref(ref)


def test_host_failure_keeps_independent_good_checkpoint_and_resumes_exact_plan(workspace):
    service, config = MemoryBlobs(), configuration(workspace)
    adapters = {"Clarity": SourceAdapter(), "Caboodle": SourceAdapter(failure=True)}
    factory = adapters.__getitem__
    with pytest.raises(RuntimeError):
        run_job(config, store(service), plan(config), adapter_factory=factory, allow_demo=True)
    assert adapters["Clarity"].committed is not None
    assert adapters["Caboodle"].committed is None
    first_writes = adapters["Clarity"].writes
    durable = json.loads(service.objects[("state", BlobStateStore.CONTROL)][0])
    assert durable["expected"]["status"] == "FAILED"
    assert durable["batches"]["baseline"]["attempts"][0]["retryable"]
    assert set(durable["last_good"]) == {"Clarity"}
    assert durable["last_good"]["Clarity"]["coverage_end"] == "2026-11-01T23:59:59.0000000"
    assert (
        durable["batches"]["baseline"]["source_checkpoints"]["Clarity"]
        == (durable["last_good"]["Clarity"])
    )
    # Fresh ephemeral filesystem simulates a new Container Apps replica.
    restarted = workspace / "replica-two"
    resumed_config = configuration(restarted)
    resumed = run_job(
        resumed_config,
        store(service),
        plan(resumed_config, at="2026-11-02T23:59:59Z"),
        adapter_factory=factory,
        allow_demo=True,
    )
    assert resumed["status"] == "SUCCEEDED"
    assert adapters["Clarity"].writes == first_writes
    assert adapters["Caboodle"].begins == 2  # No nested SQL retry in either host attempt.
    assert len(resumed["attempts"]) == 2
    committed = json.loads((restarted / "batches" / "baseline.json").read_text())
    assert committed["population"]["publication"]["at"].startswith("2026-11-01")
    assert (
        run_job(
            resumed_config,
            store(service),
            plan(resumed_config),
            adapter_factory=factory,
            allow_demo=True,
        )["status"]
        == "SUCCEEDED"
    )
    assert adapters["Caboodle"].begins == 2


def test_retention_requires_exact_fabric_ack_no_holds_and_excludes_current_state():
    from datetime import UTC, datetime

    service, blobs = MemoryBlobs(), None
    blobs = store(service)
    with blobs.exclusive():
        ref = blobs.put_bytes("exports", "exports/old/file", b"clinical-fixture")
        protected = blobs.put_bytes("state", "objects/current-population", b"protected")
        blobs.control["files"]["batches/current.json"] = protected
        blobs.control["expected"] = {"batch": "current"}
        blobs.control["last_good"] = {"Clarity": {"batch": "current"}}
        blobs.control["batches"]["old"] = {
            "status": "SUCCEEDED",
            "completed_at": "2026-11-01T00:00:00+00:00",
            "artifacts": [ref],
            "plan_digest": "plan",
            "source_digests": {"Clarity": "p"},
            "tables": {"Clarity": ["Patient"]},
        }
        now = datetime(2026, 11, 20, tzinfo=UTC)
        assert blobs.cleanup(now=now) == []  # Unacknowledged exports are protected.
        with pytest.raises(ValueError):
            blobs.acknowledge_batch(
                "old",
                plan_digest="wrong",
                source_digests={"Clarity": "p"},
                tables={"Clarity": ["Patient"]},
            )
        blobs.acknowledge_batch(
            "old",
            plan_digest="plan",
            source_digests={"Clarity": "p"},
            tables={"Clarity": ["Patient"]},
        )
        blobs.set_hold("old", "recovery")
        assert blobs.cleanup(now=now) == []
        blobs.set_hold("old", "recovery", active=False)
        assert blobs.cleanup(now=now) == [ref["key"]]
        assert ("state", protected["key"]) in service.objects
        with pytest.raises(ValueError, match="Retired"):
            blobs.set_hold("old", "late-recovery")


def test_environment_bindings_require_approved_containers_and_enforce_attempt_cap(
    workspace, monkeypatch
):
    for name, value in {
        "AZURE_CLIENT_ID": "approved-client",
        "GENERATOR_STORAGE_ACCOUNT": "approved",
        "GENERATOR_STATE_CONTAINER": "state",
        "GENERATOR_EXPORT_CONTAINER": "exports",
        "GENERATOR_MANIFEST_CONTAINER": "manifests",
        "CLARITY_SQL_SERVER": "clarity.database.windows.net",
        "CLARITY_SQL_DATABASE": "clarity",
        "CABOODLE_SQL_SERVER": "caboodle.database.windows.net",
        "CABOODLE_SQL_DATABASE": "caboodle",
        "GENERATOR_TIMEOUT_SECONDS": "2700",
    }.items():
        monkeypatch.setenv(name, value)
    config = HostConfig.from_env(ROOT, workspace)
    assert config.client_id == "approved-client" and config.timeout_seconds == 2700
    with pytest.raises(ValueError):
        requested_plan(config, batch="invalid-size", profile="normal", patients=1001)
    monkeypatch.setenv("GENERATOR_TIMEOUT_SECONDS", "2701")
    with pytest.raises(ValueError, match="2700"):
        HostConfig.from_env(ROOT, workspace)


def test_invalid_control_releases_lease_and_unpublished_local_batches_are_rejected(workspace):
    service, blobs = MemoryBlobs(), None
    service.objects[("state", BlobStateStore.CONTROL)] = (b"{}", "1")
    blobs = store(service)
    with pytest.raises(ValueError, match="schema"):
        with blobs.exclusive():
            pytest.fail("invalid authority accepted")
    assert not service.leases and blobs.lease is None
    del service.objects[("state", BlobStateStore.CONTROL)]
    (workspace / "batches").mkdir()
    (workspace / "batches" / "unpublished.json").write_text("{}")
    with blobs.exclusive():
        with pytest.raises(ValueError, match="uncommitted"):
            blobs.restore(workspace)


def test_nontransient_failure_and_retry_exhaustion_do_not_start_another_sql_attempt(workspace):
    class AlwaysFail(SourceAdapter):
        error = ValueError("synthetic validation failure")

        def write(self, *args):
            raise self.error

    config, service, bad = configuration(workspace), MemoryBlobs(), AlwaysFail()

    def factory(source):
        return bad

    with pytest.raises(ValueError):
        run_job(config, store(service), plan(config), adapter_factory=factory, allow_demo=True)
    with pytest.raises(RuntimeError, match="Nontransient"):
        run_job(config, store(service), plan(config), adapter_factory=factory, allow_demo=True)
    assert bad.begins == 1
    other = workspace / "retry-replica"
    config, service, bad = configuration(other), MemoryBlobs(), AlwaysFail()
    bad.error = RuntimeError("08S01", "synthetic transport failure")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            run_job(config, store(service), plan(config), adapter_factory=factory, allow_demo=True)
    with pytest.raises(RuntimeError, match="exhausted"):
        run_job(config, store(service), plan(config), adapter_factory=factory, allow_demo=True)
    assert bad.begins == 2


def test_abandoned_running_attempt_resumes_same_batch_with_one_recovery(workspace):
    config, service = configuration(workspace), MemoryBlobs()
    adapters = {"Clarity": SourceAdapter(failure=True), "Caboodle": SourceAdapter()}
    with pytest.raises(RuntimeError):
        run_job(
            config,
            store(service),
            plan(config),
            adapter_factory=adapters.__getitem__,
            allow_demo=True,
        )
    blobs = store(service)
    with blobs.exclusive():
        summary = blobs.control["batches"]["baseline"]
        summary["status"] = summary["attempts"][-1]["status"] = "RUNNING"
        blobs.control["expected"]["status"] = "RUNNING"
        blobs.save_control()
    result = run_job(
        config, store(service), plan(config), adapter_factory=adapters.__getitem__, allow_demo=True
    )
    assert result["status"] == "SUCCEEDED"
    assert result["attempts"][0]["error_code"] == "ABANDONED_ATTEMPT"
    assert len(result["attempts"]) == 2


def test_lease_renewal_loss_is_checked_after_checkpoint_sql_before_commit():
    import time

    from healthcare_ingestion.generator_host import FencedSqlAdapter

    service, blobs = MemoryBlobs(), None
    blobs = store(service)
    with blobs.exclusive():
        events = []

        class Cursor:
            def close(self):
                pass

            def execute(self, sql, *args):
                if "INSERT dbo.SyntheticSourceBatchCommit" in sql:
                    service.leases[("state", blobs.CONTROL)] = "different-owner"
                    blobs._heartbeat(0)

        adapter = FencedSqlAdapter(None, blobs, time.monotonic() + 2700)
        adapter.cursor = Cursor()
        adapter.deadline = time.monotonic() + 2700
        adapter.connection = SimpleNamespace(
            commit=lambda: events.append("commit"),
            rollback=lambda: events.append("rollback"),
            cursor=Cursor,
        )
        with pytest.raises(LeaseLost):
            adapter.commit_checkpoint(
                "Clarity",
                {
                    "batch": "baseline",
                    "population_digest": "p",
                    "mapping_digest": "m",
                    "contract_digest": "c",
                    "row_count": 1,
                    "coverage_start": "2025-11-01T00:00:00.0000000",
                    "coverage_end": "2026-11-01T23:59:59.0000000",
                },
            )
        adapter.rollback()
        assert events == ["rollback"]


def test_windows_manifest_paths_cannot_escape_the_owned_state_directory(workspace):
    service, blobs = MemoryBlobs(), None
    blobs = store(service)
    with blobs.exclusive():
        blobs.control["files"]["C:\\outside.json"] = blobs.put_json("state", "objects/test", {})
        with pytest.raises(ValueError, match="Unsafe state"):
            blobs.restore(workspace)


def test_invalid_fhir_keeps_durable_raw_export_for_failed_batch_review(workspace, monkeypatch):
    import healthcare_ingestion.generator_host as module

    def exported(**kwargs):
        path = kwargs["output"] / "fhir"
        path.mkdir(parents=True)
        (path / "fixture.json").write_text(
            json.dumps(
                {
                    "resourceType": "Bundle",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "UnapprovedClinical",
                                "id": "fixture",
                            }
                        }
                    ],
                }
            )
        )
        return {"inputs": {"simulation_end_date": "20261120", "simulation_timezone": "UTC"}}

    monkeypatch.setattr(module, "run_synthea", exported)
    config, service = configuration(workspace), MemoryBlobs()
    requested = requested_plan(
        config,
        batch="seed-review",
        profile="normal",
        patients=2,
        at="2026-11-20T23:59:59Z",
    )
    with pytest.raises(ValueError, match="Unsupported FHIR"):
        run_job(config, store(service), requested)
    durable = json.loads(service.objects[("state", BlobStateStore.CONTROL)][0])
    summary = durable["batches"]["seed-review"]
    assert summary["status"] == "FAILED" and durable["last_good"] == {}
    assert summary["artifacts"]
    assert all(("exports", ref["key"]) in service.objects for ref in summary["artifacts"])
    blobs = store(service)
    with blobs.exclusive():
        assert blobs.cleanup() == []  # Failed/unacknowledged recovery artifacts are protected.
