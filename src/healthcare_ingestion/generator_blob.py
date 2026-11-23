"""Lease-fenced Azure Blob generator state; never creates accounts or containers."""

import hashlib
import json
import re
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from healthcare_ingestion.synthetic_population import atomic_json


class LeaseLost(RuntimeError):
    pass


class BlobStateStore:
    """All mutable authority lives in the leased control blob.

    Other writes are immutable/content-addressed. A stale worker may leave an orphan,
    but cannot advance a plan, checkpoint, attempt or retention decision after lease loss.
    """

    CONTROL = "generator/control-v1.json"

    def __init__(self, service, *, state_container, export_container, manifest_container):
        self.service = service
        self.containers = {
            "state": state_container,
            "exports": export_container,
            "manifests": manifest_container,
        }
        if len(set(self.containers.values())) != 3 or any(
            name == "terraform-state"
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", name)
            or "--" in name
            for name in self.containers.values()
        ):
            raise ValueError("Three separately approved generator containers are required.")
        self.lease = None
        self.failed = threading.Event()
        self.stop = threading.Event()
        self.control = None
        self.etag = None
        self.mutex = threading.RLock()

    @classmethod
    def from_account(cls, account, client_id, **containers):
        import re

        if not re.fullmatch(r"[a-z0-9]{3,24}", account):
            raise ValueError("Invalid approved storage account.")
        from azure.identity import ManagedIdentityCredential
        from azure.storage.blob import BlobServiceClient

        credential = ManagedIdentityCredential(client_id=client_id)
        service = BlobServiceClient(
            f"https://{account}.blob.core.windows.net",
            credential=credential,
            retry_total=0,
            connection_timeout=10,
            read_timeout=20,
        )
        instance = cls(service, **containers)
        instance.credential = credential
        return instance

    def client(self, area, key):
        path = PurePosixPath(key)
        if path.is_absolute() or ".." in path.parts or "\\" in key:
            raise ValueError("Unsafe generator blob key.")
        return self.service.get_blob_client(self.containers[area], key)

    @contextmanager
    def exclusive(self, *, heartbeat_seconds=20):
        if self.lease is not None:
            raise RuntimeError("Generator lease is already held.")
        for name in self.containers.values():
            self.service.get_container_client(name).get_container_properties()
        client = self.client("state", self.CONTROL)
        initial = {
            "schema_version": 1,
            "files": {},
            "batches": {},
            "expected": None,
            "last_good": {},
            "acks": {},
            "holds": {},
            "retired": {},
        }
        try:
            client.upload_blob(json.dumps(initial).encode(), overwrite=False, timeout=20)
        except Exception as error:
            if getattr(error, "status_code", None) != 409:
                raise
        self.lease = client.acquire_lease(lease_duration=60, timeout=20)
        self.failed.clear()
        self.stop.clear()
        thread = None
        try:
            with self.mutex:
                payload = client.download_blob(lease=self.lease, timeout=20)
                self.control = json.loads(payload.readall())
                if not isinstance(self.control, dict) or self.control.get("schema_version") != 1:
                    raise ValueError("Unsupported generator control schema.")
                for field in ("files", "batches", "last_good", "acks", "holds", "retired"):
                    if not isinstance(self.control.get(field), dict):
                        raise ValueError("Incomplete generator control schema.")
                if "expected" not in self.control or (
                    self.control["expected"] is not None
                    and not isinstance(self.control["expected"], dict)
                ):
                    raise ValueError("Incomplete generator expected-batch journal.")
                self.etag = client.get_blob_properties(lease=self.lease).etag
            thread = threading.Thread(
                target=self._heartbeat,
                args=(heartbeat_seconds,),
                daemon=True,
            )
            thread.start()
            yield self
        finally:
            self.stop.set()
            if thread is not None:
                thread.join(timeout=25)
            lease, self.lease = self.lease, None
            try:
                lease.release(timeout=20)
            except Exception:
                pass

    def _heartbeat(self, interval):
        while not self.stop.wait(interval):
            try:
                self.guard()
                with self.mutex:
                    self.lease.renew(timeout=20)
            except Exception:
                self.failed.set()
                return

    def guard(self):
        if self.lease is None or self.failed.is_set():
            raise LeaseLost("Generator lease authority is unavailable.")

    def save_control(self):
        from azure.core import MatchConditions

        self.guard()
        with self.mutex:
            try:
                response = self.client("state", self.CONTROL).upload_blob(
                    json.dumps(self.control, sort_keys=True).encode(),
                    overwrite=True,
                    lease=self.lease,
                    etag=self.etag,
                    match_condition=MatchConditions.IfNotModified,
                    timeout=20,
                )
                self.etag = response["etag"]
            except Exception:
                self.failed.set()
                raise

    def put_bytes(self, area, key, data):
        self.guard()
        fingerprint = hashlib.sha256(data).hexdigest()
        client = self.client(area, key)
        try:
            client.upload_blob(
                data,
                overwrite=False,
                metadata={"sha256": fingerprint},
                max_concurrency=1,
                timeout=20,
            )
        except Exception as error:
            if getattr(error, "status_code", None) != 409:
                raise
            existing = client.download_blob(timeout=20).readall()
            if hashlib.sha256(existing).hexdigest() != fingerprint:
                raise ValueError(
                    "Immutable generator blob conflicts with existing content."
                ) from None
        return {"area": area, "key": key, "sha256": fingerprint, "size": len(data)}

    def read_ref(self, reference):
        payload = (
            self.client(reference["area"], reference["key"])
            .download_blob(
                max_concurrency=1,
                timeout=20,
            )
            .readall()
        )
        if len(payload) != reference["size"] or (
            hashlib.sha256(payload).hexdigest() != reference["sha256"]
        ):
            raise ValueError("Generator blob checksum mismatch.")
        return payload

    def put_json(self, area, key, document):
        return self.put_bytes(area, key, json.dumps(document, sort_keys=True).encode())

    def restore(self, directory: Path):
        """Reconstruct the authoritative filesystem view, not an uncommitted local cache."""
        self.guard()
        directory.mkdir(parents=True, exist_ok=True)
        allowed = set(self.control["files"])
        for path in directory.rglob("*.json"):
            relative = path.relative_to(directory).as_posix()
            if relative.startswith("attempt-exports/"):
                continue
            if relative not in allowed:
                raise ValueError("Local generator cache has uncommitted authoritative state.")
        for relative, reference in self.control["files"].items():
            parts = PurePosixPath(relative).parts
            if (
                ".." in parts
                or PurePosixPath(relative).is_absolute()
                or ("\\" in relative or ":" in relative)
            ):
                raise ValueError("Unsafe state manifest path.")
            path = directory.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = self.read_ref(reference)
            if path.suffix == ".json":
                atomic_json(path, json.loads(data))
            else:
                path.write_bytes(data)

    def sync(self, directory: Path):
        """Checkpoint files before updating the single lease-fenced root."""
        self.guard()
        for path in sorted(directory.rglob("*.json")):
            relative = path.relative_to(directory).as_posix()
            if relative.startswith("attempt-exports/"):
                continue
            data = path.read_bytes()
            self.control["files"][relative] = self.put_bytes(
                "state",
                "objects/" + hashlib.sha256(data).hexdigest(),
                data,
            )
        self.save_control()

    def export_files(self, batch, directory: Path):
        references = []
        if directory.exists():
            for path in sorted(directory.rglob("*.json")):
                relative = path.relative_to(directory).as_posix()
                data = path.read_bytes()
                fingerprint = hashlib.sha256(data).hexdigest()
                references.append(
                    self.put_bytes(
                        "exports",
                        f"exports/{batch}/{fingerprint}/{relative}",
                        data,
                    )
                )
        return references

    def acknowledge_batch(self, batch, *, plan_digest, source_digests, tables):
        """Fabric callers must acquire exclusive() before publishing an acknowledgement."""
        self.guard()
        summary = self.control["batches"][batch]
        if batch in self.control["retired"] or summary["status"] != "SUCCEEDED":
            raise ValueError("Only active successful batches can receive Fabric acknowledgements.")
        expected = summary["source_digests"]
        if (
            plan_digest != summary["plan_digest"]
            or source_digests != expected
            or (tables != summary["tables"])
        ):
            raise ValueError("Fabric acknowledgement does not cover the exact source batch/models.")
        self.control["acks"][batch] = {
            "plan_digest": plan_digest,
            "source_digests": source_digests,
            "tables": tables,
            "at": datetime.now(UTC).isoformat(),
        }
        self.save_control()

    def set_hold(self, batch, hold_id, *, active=True):
        self.guard()
        if batch in self.control["retired"]:
            raise ValueError("Retired export artifacts cannot acquire new recovery references.")
        holds = set(self.control["holds"].get(batch, []))
        holds.add(hold_id) if active else holds.discard(hold_id)
        self.control["holds"][batch] = sorted(holds)
        self.save_control()

    def cleanup(self, *, now=None):
        """Five-day export/manifest GC with a fenced retirement point before deletion.

        State/populations/identities/checkpoints and plans are never age-purged here.
        Retirement rejects new holds, so even a delayed stale DELETE cannot erase an
        artifact for which a new recovery reference was subsequently accepted.
        """
        from azure.core import MatchConditions

        self.guard()
        now = now or datetime.now(UTC)
        protected = {v["batch"] for v in self.control["last_good"].values()}
        if self.control["expected"]:
            protected.add(self.control["expected"]["batch"])
        for batch, summary in self.control["batches"].items():
            if batch in protected or summary["status"] != "SUCCEEDED":
                continue
            if batch in self.control["retired"]:
                continue
            if datetime.fromisoformat(summary["completed_at"]) + timedelta(days=5) > now:
                continue
            if batch not in self.control["acks"] or self.control["holds"].get(batch):
                continue
            self.control["retired"][batch] = {
                "at": now.isoformat(),
                "references": summary.get("artifacts", []),
            }
            self.save_control()
        deleted = []
        for retirement in self.control["retired"].values():
            for ref in retirement["references"]:
                if not (
                    ref["area"] == "exports"
                    and ref["key"].startswith("exports/")
                    or ref["area"] == "manifests"
                    and ref["key"].startswith("export-manifests/")
                ):
                    raise ValueError("Retention cannot delete protected generator state.")
                self.guard()
                client = self.client(ref["area"], ref["key"])
                try:
                    # Read/verify immutable content before the terminal garbage deletion.
                    etag = client.get_blob_properties(timeout=20).etag
                    self.read_ref(ref)
                    client.delete_blob(
                        etag=etag,
                        match_condition=MatchConditions.IfNotModified,
                        timeout=20,
                    )
                    deleted.append(ref["key"])
                except Exception as error:
                    if getattr(error, "status_code", None) != 404:
                        raise
        return deleted

    def close(self):
        self.service.close()
        if hasattr(self, "credential"):
            self.credential.close()
