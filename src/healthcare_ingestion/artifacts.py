"""Immutable recovery proof storage; holds are owned by the authoritative control store."""

import hashlib
import json
import re
from itertools import islice
from pathlib import Path


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def checked_key(key):
    if not re.fullmatch(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*", key):
        raise ValueError("Artifact keys must be portable relative paths.")
    if any(part in {".", ".."} for part in key.split("/")):
        raise ValueError("Artifact traversal is forbidden.")
    return key


class LocalArtifactStore:
    """Durable reference adapter for local protocol/integration tests only."""

    def __init__(self, root, max_bytes=8 * 1024 * 1024):
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key, value):
        path = self.root.joinpath(*checked_key(key).split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = encoded(value)
        if len(data) > self.max_bytes:
            raise ValueError("Recovery artifact exceeds its size limit.")
        try:
            with path.open("xb") as output:
                output.write(data)
                output.flush()
                import os

                os.fsync(output.fileno())
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("Immutable artifact content conflicts with an existing key.")
        return hashlib.sha256(data).hexdigest()

    def get(self, key):
        path = self.root.joinpath(*checked_key(key).split("/"))
        if path.exists() and path.stat().st_size > self.max_bytes:
            raise ValueError("Recovery artifact exceeds its size limit.")
        return json.loads(path.read_bytes()) if path.exists() else None

    def pending_events(self, limit=1000):
        if type(limit) is not int or not 0 < limit <= 1000:
            raise ValueError("Bounded event replay is required.")
        root = self.root / "event-outbox"
        return tuple("event-outbox/" + path.name for path in islice(root.glob("*.json"), limit))

    def discard_event(self, key):
        checked_key(key)
        if not key.startswith("event-outbox/") or len(key.split("/")) != 2:
            raise ValueError("Only a named event outbox marker can be discarded.")
        self.root.joinpath(*key.split("/")).unlink(missing_ok=True)


class BlobArtifactStore:
    """OneLake/Azure Blob adapter; credentials are supplied by the verified machine caller."""

    def __init__(self, container_client, prefix, max_bytes=8 * 1024 * 1024):
        self.container = container_client
        self.prefix = checked_key(prefix).rstrip("/") + "/"
        self.max_bytes = max_bytes

    def _read(self, blob):
        size = blob.get_blob_properties().size
        if size > self.max_bytes:
            raise ValueError("Recovery artifact exceeds its size limit.")
        data = blob.download_blob(length=self.max_bytes + 1).readall()
        if len(data) > self.max_bytes:
            raise ValueError("Recovery artifact exceeds its size limit.")
        return data

    def put(self, key, value):
        from azure.core.exceptions import ResourceExistsError

        blob = self.container.get_blob_client(self.prefix + checked_key(key))
        data = encoded(value)
        if len(data) > self.max_bytes:
            raise ValueError("Recovery artifact exceeds its size limit.")
        try:
            blob.upload_blob(data, overwrite=False)
        except ResourceExistsError:
            if self._read(blob) != data:
                raise ValueError("Immutable artifact content conflicts with an existing key.")
        return hashlib.sha256(data).hexdigest()

    def get(self, key):
        from azure.core.exceptions import ResourceNotFoundError

        blob = self.container.get_blob_client(self.prefix + checked_key(key))
        try:
            return json.loads(self._read(blob))
        except ResourceNotFoundError:
            return None

    def pending_events(self, limit=1000):
        if type(limit) is not int or not 0 < limit <= 1000:
            raise ValueError("Bounded event replay is required.")
        result = []
        for blob in self.container.list_blobs(
            name_starts_with=self.prefix + "event-outbox/", results_per_page=limit
        ):
            result.append(blob.name[len(self.prefix) :])
            if len(result) >= limit:
                break
        return tuple(result)

    def discard_event(self, key):
        from azure.core.exceptions import ResourceNotFoundError

        checked_key(key)
        if not key.startswith("event-outbox/") or len(key.split("/")) != 2:
            raise ValueError("Only a named event outbox marker can be discarded.")
        try:
            self.container.get_blob_client(self.prefix + key).delete_blob()
        except ResourceNotFoundError:
            pass
