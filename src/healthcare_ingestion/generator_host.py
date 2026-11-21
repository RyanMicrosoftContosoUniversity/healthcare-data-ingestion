"""Consumption job host: Blob-authoritative plans, journals and serial source publication."""

import argparse
import json
import os
import signal
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from healthcare_ingestion.generator import (
    _inputs,
    read_fhir_directory,
    run_synthea,
    synthea_coverage_end,
)
from healthcare_ingestion.generator_blob import BlobStateStore, LeaseLost
from healthcare_ingestion.source_mapping import project_source, sql_timestamp
from healthcare_ingestion.sql_source import (
    PyodbcSourceAdapter,
    SqlSourceConnection,
    is_transient,
    load_source,
)
from healthcare_ingestion.sql_source_integrity import validate_source_rows
from healthcare_ingestion.synthetic_fhir import parse_bundles
from healthcare_ingestion.synthetic_population import (
    PopulationStore,
    change_population,
    digest,
    local_demo_population,
    source_delta,
)


@dataclass(frozen=True)
class HostConfig:
    account: str
    client_id: str | None
    state_container: str
    export_container: str
    manifest_container: str
    clarity_server: str
    clarity_database: str
    caboodle_server: str
    caboodle_database: str
    root: Path
    state_directory: Path
    timeout_seconds: int = 2700

    @classmethod
    def from_env(cls, root: Path, state_directory: Path):
        required = (
            "GENERATOR_STORAGE_ACCOUNT",
            "GENERATOR_STATE_CONTAINER",
            "GENERATOR_EXPORT_CONTAINER",
            "GENERATOR_MANIFEST_CONTAINER",
            "CLARITY_SQL_SERVER",
            "CLARITY_SQL_DATABASE",
            "CABOODLE_SQL_SERVER",
            "CABOODLE_SQL_DATABASE",
        )
        if any(not os.environ.get(name) for name in required):
            raise ValueError(
                "Approved storage containers and SQL endpoint/database bindings required."
            )
        timeout = int(os.environ.get("GENERATOR_TIMEOUT_SECONDS", "2700"))
        if not 1 <= timeout <= 2700:
            raise ValueError("Generator attempt cap cannot exceed 2700 seconds.")
        return cls(
            os.environ[required[0]],
            os.environ.get("AZURE_CLIENT_ID"),
            *[os.environ[name] for name in required[1:]],
            root,
            state_directory,
            timeout,
        )


def requested_plan(
    config, *, batch, profile, at=None, history_start=None, patients=1000, engine="synthea"
):
    PopulationStore._validate_batch(batch)
    if (
        profile not in {"normal", "zero", "spike"}
        or not 1 <= patients <= 1000
        or (engine not in {"synthea", "demo"})
    ):
        raise ValueError("A supported change profile and positive patient count are required.")
    at = sql_timestamp(at or datetime.now(UTC))
    moment = datetime.fromisoformat(at[:26])
    if history_start is None:
        if engine == "synthea":
            moment = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            history_start = moment.replace(year=moment.year - 1).isoformat()
        except ValueError:
            history_start = moment.replace(year=moment.year - 1, day=28).isoformat()
    pin = json.loads((config.root / "scripts" / "synthetic-data" / "synthea-pin.json").read_text())
    contracts = {}
    for source in ("Clarity", "Caboodle"):
        contract, mapping = _inputs(config.root, source)
        contracts[source] = {"contract": digest(contract), "mapping": digest(mapping)}
    return {
        "schema_version": 1,
        "batch": batch,
        "profile": profile,
        "at": at,
        "history_start": sql_timestamp(history_start),
        "patients": patients,
        "engine": engine,
        "synthea": pin,
        "contracts": contracts,
    }


class FencedSqlAdapter(PyodbcSourceAdapter):
    def __init__(self, configuration, blobs, deadline):
        super().__init__(configuration)
        self.blobs, self.host_deadline = blobs, deadline

    def begin(self, source, batch_id, timeout_seconds):
        self.blobs.guard()
        remaining = int(self.host_deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Generator attempt budget exhausted.")
        super().begin(source, batch_id, min(timeout_seconds, remaining))

    def _budget(self):
        self.blobs.guard()
        if time.monotonic() >= self.host_deadline:
            raise TimeoutError("Generator attempt budget exhausted.")
        super()._budget()


def retryable(error):
    return (
        isinstance(error, LeaseLost)
        or is_transient(error)
        or (getattr(error, "status_code", None) in {408, 429, 500, 502, 503, 504})
    )


def run_job(config, blobs, plan, *, adapter_factory=None, allow_demo=False):
    """One persisted attempt per invocation; at most one transient recovery attempt.

    No nested SQL retries: the host owns retry lineage across job invocations. A global
    deadline covers generation, uploads and both serial SQL loads. Previous good source
    checkpoints remain unchanged on failure; SQL commit uncertainty is recovered by its
    immutable ledger on the next permitted invocation.
    """
    if plan["engine"] == "demo" and not allow_demo:
        raise ValueError("Hosted clinical generation requires verified Synthea.")
    deadline = time.monotonic() + config.timeout_seconds

    def budget():
        blobs.guard()
        if time.monotonic() >= deadline:
            raise TimeoutError("Generator attempt budget exhausted.")

    batch = plan["batch"]
    with blobs.exclusive():
        control = blobs.control
        expected = control["expected"]
        if expected and expected["batch"] != batch and expected["status"] != "SUCCEEDED":
            raise ValueError("Recover the previous expected batch before advancing the population.")
        summary = control["batches"].get(batch)
        if summary:
            stored = json.loads(blobs.read_ref(summary["plan_ref"]))
            if digest(stored) != summary["plan_digest"]:
                raise ValueError("Stored generator plan digest does not match its journal.")
            # Timestamps/default parameters come from the immutable stored plan on restart.
            for field in ("profile", "engine", "patients", "contracts", "synthea"):
                if plan[field] != stored[field]:
                    raise ValueError("Same-batch restart conflicts with its immutable plan.")
            plan = stored
            if summary["status"] == "SUCCEEDED":
                return summary
            previous_attempt = summary["attempts"][-1]
            if previous_attempt["status"] == "FAILED" and not previous_attempt["retryable"]:
                raise RuntimeError(
                    "Nontransient source failure requires explicit operator recovery."
                )
            if len(summary["attempts"]) >= 2:
                raise RuntimeError("Single transient source retry has been exhausted.")
            if previous_attempt["status"] == "RUNNING":
                previous_attempt.update(
                    status="FAILED",
                    retryable=True,
                    error_code="ABANDONED_ATTEMPT",
                    ended_at=datetime.now(UTC).isoformat(),
                )
        else:
            fingerprint = digest(plan)
            reference = blobs.put_json(
                "manifests",
                f"plans/{batch}/{fingerprint}.json",
                plan,
            )
            summary = {
                "plan_digest": fingerprint,
                "plan_ref": reference,
                "status": "RUNNING",
                "attempts": [],
                "artifacts": [],
                "source_digests": {},
                "tables": {},
            }
            control["batches"][batch] = summary
        attempt = {
            "attempt_id": str(uuid4()),
            "status": "RUNNING",
            "retryable": False,
            "started_at": datetime.now(UTC).isoformat(),
        }
        summary["attempts"].append(attempt)
        summary["status"] = "RUNNING"
        control["expected"] = {
            "batch": batch,
            "plan_digest": summary["plan_digest"],
            "status": "RUNNING",
            "attempt_id": attempt["attempt_id"],
        }
        blobs.save_control()
        active_adapters = []
        try:
            budget()
            blobs.restore(config.state_directory)
            store = PopulationStore(config.state_directory)
            path = config.state_directory / "batches" / f"{batch}.json"
            if path.exists():
                document = store.read_batch(batch)
            else:
                predecessor = store.head()
                if predecessor is not None:
                    population = change_population(
                        store.read_batch(predecessor)["population"],
                        batch=batch,
                        at=plan["at"],
                        profile=plan["profile"],
                    )
                elif plan["engine"] == "demo":
                    population = local_demo_population(
                        patients=plan["patients"],
                        history_start=plan["history_start"],
                        publication_at=plan["at"],
                    )
                else:
                    output = config.state_directory / "attempt-exports" / attempt["attempt_id"]
                    pin = plan["synthea"]
                    execution = run_synthea(
                        version=pin["version"],
                        jar=config.root / pin["jar_path"],
                        expected_sha256=pin["sha256"],
                        output=output,
                        patients=plan["patients"],
                        seed=pin["seed"],
                        reference_date=plan["at"][:10].replace("-", ""),
                    )
                    summary["artifacts"] = blobs.export_files(batch, output)
                    blobs.save_control()
                    population = parse_bundles(
                        read_fhir_directory(output / "fhir"),
                        history_start=plan["history_start"],
                        publication_at=plan["at"],
                        coverage_end=synthea_coverage_end(execution),
                    )
                combined = 0
                for source in ("Clarity", "Caboodle"):
                    contract, mapping = _inputs(config.root, source)
                    current = project_source(population, contract, mapping)
                    validate_source_rows(current, contract)
                    if predecessor is not None:
                        previous = project_source(
                            store.read_batch(predecessor)["population"],
                            contract,
                            mapping,
                        )
                        combined += sum(
                            map(len, source_delta(current, previous, contract).values())
                        )
                if predecessor is not None:
                    lower, upper = {"zero": (0, 0), "normal": (500, 1000), "spike": (4500, 5500)}[
                        plan["profile"]
                    ]
                    if not lower <= combined <= upper:
                        raise ValueError("Generated changes exceed the approved pilot profile.")
                    summary["combined_changes"] = combined
                budget()
                document = store.publish(batch, population, predecessor)
                # Never SQL-publish a population plan that exists only in ephemeral storage.
                blobs.sync(config.state_directory)
            for source in ("Clarity", "Caboodle"):
                budget()
                contract, mapping = _inputs(config.root, source)
                server = config.clarity_server if source == "Clarity" else config.caboodle_server
                database = (
                    config.clarity_database if source == "Clarity" else config.caboodle_database
                )
                adapter = (
                    adapter_factory(source)
                    if adapter_factory
                    else FencedSqlAdapter(
                        SqlSourceConnection(server, database, config.client_id),
                        blobs,
                        deadline,
                    )
                )
                active_adapters.append(adapter)
                # load_source's retry owner is bypassed: this wrapper classifies/rethrows
                # SQL errors as nontransient inside that helper, then classifies original.
                wrapped = SingleAttemptAdapter(adapter)
                evidence = load_source(
                    store=store,
                    batch=batch,
                    contract=contract,
                    mapping=mapping,
                    adapter=wrapped,
                    checkpoint_directory=config.state_directory / "source-checkpoints",
                    retry_delay_seconds=0,
                )
                evidence = {k: v for k, v in evidence.items() if k != "recovered"}
                control["last_good"][source] = evidence
                summary["source_digests"][source] = evidence["population_digest"]
                summary.setdefault("source_checkpoints", {})[source] = evidence
                summary["tables"][source] = sorted(t["name"] for t in contract["tables"])
                blobs.sync(config.state_directory)
            budget()
            manifest = {
                "schema_version": 1,
                "batch": batch,
                "plan_digest": summary["plan_digest"],
                "population_digest": document["digest"],
                "sources": control["last_good"],
                "tables": summary["tables"],
            }
            summary["artifacts"].append(
                blobs.put_json(
                    "manifests",
                    f"export-manifests/{batch}/{digest(manifest)}.json",
                    manifest,
                )
            )
            summary["status"] = attempt["status"] = "SUCCEEDED"
            summary["completed_at"] = attempt["ended_at"] = datetime.now(UTC).isoformat()
            control["expected"]["status"] = "SUCCEEDED"
            blobs.save_control()
            return summary
        except BaseException as error:
            original = error.original if isinstance(error, SingleAttemptFailure) else error
            attempt.update(
                status="FAILED",
                retryable=retryable(original),
                error_code=type(original).__name__,
                ended_at=datetime.now(UTC).isoformat(),
            )
            summary["status"] = control["expected"]["status"] = "FAILED"
            try:
                blobs.save_control()
            except Exception:
                # Persisted RUNNING is recovered as abandoned; never overwrite authority
                # with a stale lease, and never replace a previous good checkpoint.
                pass
            raise original
        finally:
            for adapter in active_adapters:
                try:
                    adapter.rollback()
                    adapter.close()
                except Exception:
                    pass


class SingleAttemptFailure(RuntimeError):
    def __init__(self, original):
        super().__init__("Source attempt failed; original payload suppressed.")
        self.original = original


class SingleAttemptAdapter:
    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        value = getattr(self.inner, name)
        if not callable(value):
            return value

        def call(*args, **kwargs):
            try:
                return value(*args, **kwargs)
            except Exception as error:
                raise SingleAttemptFailure(error) from None

        return call


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--state", type=Path, default=Path("generator-host-state"))
    parser.add_argument("--batch", default=os.environ.get("GENERATOR_BATCH"))
    parser.add_argument("--profile", choices=("normal", "zero", "spike"), default="normal")
    parser.add_argument("--at", default=os.environ.get("GENERATOR_PUBLICATION_AT"))
    parser.add_argument("--history-start", default=os.environ.get("GENERATOR_HISTORY_START"))
    parser.add_argument("--patients", type=int, default=1000)
    args = parser.parse_args(argv)
    blobs = None
    try:
        config = HostConfig.from_env(args.root, args.state)
        # Container Apps supplies a hard replica timeout too. The local process timer
        # reserves final journal/lease cleanup within, never beyond, the attempt cap.
        if os.name != "nt":
            grace = min(60, config.timeout_seconds / 10)
            expired_once = False

            def expired(signum, frame):
                nonlocal expired_once
                if expired_once:
                    os._exit(1)
                expired_once = True
                signal.setitimer(signal.ITIMER_REAL, grace)
                raise TimeoutError("Generator attempt deadline exceeded.")

            signal.signal(signal.SIGALRM, expired)
            signal.setitimer(signal.ITIMER_REAL, config.timeout_seconds - grace)
        blobs = BlobStateStore.from_account(
            config.account,
            config.client_id,
            state_container=config.state_container,
            export_container=config.export_container,
            manifest_container=config.manifest_container,
        )
        if args.batch is None:
            with blobs.exclusive():
                expected = blobs.control["expected"]
                if expected and expected["status"] != "SUCCEEDED":
                    args.batch = expected["batch"]
                else:
                    prefix = "daily-" if blobs.control["last_good"] else "seed-"
                    args.batch = prefix + datetime.now(UTC).strftime("%Y%m%d")
        plan = requested_plan(
            config,
            batch=args.batch,
            profile=args.profile,
            at=args.at,
            history_start=args.history_start,
            patients=args.patients,
        )
        result = run_job(config, blobs, plan)
        with blobs.exclusive():
            blobs.cleanup()
        print(json.dumps({"batch": args.batch, "status": result["status"]}))
        return 0
    except BaseException as error:
        print(json.dumps({"status": "FAILED", "error_code": type(error).__name__}))
        return 1
    finally:
        if os.name != "nt":
            signal.setitimer(signal.ITIMER_REAL, 0)
        if blobs is not None:
            blobs.close()


if __name__ == "__main__":
    raise SystemExit(main())
