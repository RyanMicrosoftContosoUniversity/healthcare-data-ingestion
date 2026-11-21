"""Checksum-validated expected generator slot; no fallback to an older successful run."""

import hashlib
import json
from dataclasses import dataclass

from healthcare_ingestion.discovery import timestamp7
from healthcare_ingestion.synthetic_population import digest


def utc_coverage_time(value):
    if value.endswith("Z"):
        value = value[:-1]
    elif value.endswith("+00:00"):
        value = value[:-6]
    return timestamp7(value)


@dataclass(frozen=True)
class ExpectedSource:
    batch: str
    plan_digest: str
    plan: dict
    population_digest: str | None
    coverage: dict | None
    status: str

    def matches(self, head):
        return bool(
            head
            and self.coverage
            and self.population_digest
            and head["batch"] == self.batch
            and head["population_digest"] == self.population_digest
            and utc_coverage_time(head["coverage_start"])
            == utc_coverage_time(self.coverage["start"])
            and utc_coverage_time(head["coverage_end"]) == utc_coverage_time(self.coverage["end"])
        )


def _bounded_read(client, limit):
    if client.get_blob_properties().size > limit:
        raise ValueError("Generator control document exceeds the bounded reader limit.")
    content = client.download_blob(length=limit + 1).readall()
    if len(content) > limit:
        raise ValueError("Generator document exceeds the bounded reader limit.")
    return content


def _read_reference(state, reference, limit):
    if type(reference["size"]) is not int or not 0 <= reference["size"] <= limit:
        raise ValueError("Generator reference exceeds the bounded reader limit.")
    content = _bounded_read(state.client(reference["area"], reference["key"]), limit)
    if (
        len(content) != reference["size"]
        or hashlib.sha256(content).hexdigest() != reference["sha256"]
    ):
        raise ValueError("Generator reference checksum or size differs.")
    return json.loads(content)


def read_expected(state, max_bytes=4 * 1024 * 1024, max_ref_bytes=128 * 1024 * 1024):
    if (
        type(max_bytes) is not int
        or type(max_ref_bytes) is not int
        or not 0 < max_bytes <= 8 * 1024 * 1024
        or not 0 < max_ref_bytes <= 256 * 1024 * 1024
    ):
        raise ValueError("Explicit bounded generator reader limits are required.")
    control = json.loads(
        _bounded_read(state.client("state", "generator/control-v1.json"), max_bytes)
    )
    expected = control.get("expected")
    if not expected:
        return None
    batch = expected["batch"]
    journal = control["batches"][batch]
    plan = _read_reference(state, journal["plan_ref"], max_ref_bytes)
    if digest(plan) != expected["plan_digest"] or plan["batch"] != batch:
        raise ValueError("Expected generator plan does not match its immutable journal.")
    reference = control["files"].get(f"batches/{batch}.json")
    document = _read_reference(state, reference, max_ref_bytes) if reference else None
    population = document["population"] if document else None
    if document and (document["batch"] != batch or document["digest"] != digest(population)):
        raise ValueError("Generator population does not match the expected batch.")
    coverage = population.get("coverage") if population else None
    if coverage is not None and (
        set(coverage) != {"start", "end"}
        or utc_coverage_time(coverage["start"]) >= utc_coverage_time(coverage["end"])
    ):
        raise ValueError("Generator coverage is malformed.")
    return ExpectedSource(
        batch,
        expected["plan_digest"],
        plan,
        digest(population) if population else None,
        coverage,
        expected["status"],
    )
