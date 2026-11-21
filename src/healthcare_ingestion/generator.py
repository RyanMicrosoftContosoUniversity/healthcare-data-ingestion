"""Executable Synthea, population/change planning and independent SQL source commands."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from healthcare_ingestion.source_mapping import (
    load_mapping,
    mapping_document,
    project_source,
)
from healthcare_ingestion.sql_source import (
    ATTEMPT_SECONDS,
    PyodbcSourceAdapter,
    SqlSourceConnection,
    load_source,
)
from healthcare_ingestion.sql_source_integrity import validate_source_rows
from healthcare_ingestion.sql_source_migrations import render_source_migration
from healthcare_ingestion.synthetic_fhir import parse_bundles
from healthcare_ingestion.synthetic_population import (
    PopulationStore,
    atomic_json,
    change_population,
    file_lock,
    local_demo_population,
    source_delta,
)


def synthea_command(
    *,
    jar: Path,
    expected_sha256: str,
    output: Path,
    patients: int,
    seed: int,
    reference_date: str,
) -> list[str]:
    """Verify the supplied versioned binary; do not download/execute an unpinned jar."""
    import re

    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("Reviewed Synthea jar SHA256 is required.")
    if not 1 <= patients <= 1000:
        raise ValueError("Synthea pilot population is bounded at 1000.")
    from datetime import datetime

    datetime.strptime(reference_date, "%Y%m%d")
    with jar.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected_sha256.lower():
        raise ValueError("Synthea binary fingerprint mismatch; execution rejected.")
    return [
        "java",
        "-XX:ActiveProcessorCount=2",
        "-Xmx2g",
        "-Duser.timezone=UTC",
        "-jar",
        str(jar.resolve()),
        "-s",
        str(seed),
        "-cs",
        str(seed),
        "-p",
        str(patients),
        "-r",
        reference_date,
        "-e",
        reference_date,
        "-o",
        "false",
        "--generate.thread_pool_size=2",
        "--generate.log_patients.detail=none",
        "--exporter.years_of_history=1",
        "--exporter.fhir.export=true",
        "--exporter.fhir.bulk_data=false",
        "--exporter.fhir_stu3.export=false",
        "--exporter.fhir_dstu2.export=false",
        "--exporter.ccda.export=false",
        "--exporter.hospital.fhir.export=true",
        "--exporter.practitioner.fhir.export=true",
        f"--exporter.baseDirectory={output.resolve()}",
    ]


def run_synthea(*, version: str, **kwargs) -> dict:
    if not version or version.lower() in {"latest", "master", "main"}:
        raise ValueError("An immutable reviewed Synthea release/commit label is required.")
    output = kwargs["output"]
    output.mkdir(parents=True, exist_ok=True)
    with file_lock(output / "synthea.lock"):
        evidence_path = output / "synthea-execution.json"
        command = synthea_command(**kwargs)
        inputs = {
            "version": version,
            "jar_sha256": kwargs["expected_sha256"].lower(),
            "patients": kwargs["patients"],
            "seed": kwargs["seed"],
            "reference_date": kwargs["reference_date"],
            "simulation_end_date": kwargs["reference_date"],
            "simulation_timezone": "UTC",
        }
        if evidence_path.exists():
            evidence = json.loads(evidence_path.read_text())
            if evidence["inputs"] != inputs:
                raise ValueError("Synthea output directory belongs to another immutable run.")
            for name, fingerprint in evidence["files"].items():
                path = output / name
                if not path.resolve().is_relative_to(output.resolve()) or (
                    hashlib.sha256(path.read_bytes()).hexdigest() != fingerprint
                ):
                    raise ValueError("Previously committed Synthea file evidence changed.")
            return evidence
        if (output / "fhir").exists():
            raise ValueError(
                "Uncommitted Synthea output exists; review/recover in a fresh run directory."
            )
        # Captured clinical output is never persisted or printed in application logs.
        # Synthea runtime failures are not assumed transient and do not get blind retries.
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=ATTEMPT_SECONDS,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(f"Synthea execution failed with exit code {completed.returncode}.")
        files = sorted((output / "fhir").rglob("*.json"))
        if not files:
            raise RuntimeError("Synthea did not publish FHIR bundle files.")
        evidence = {
            "inputs": inputs,
            "files": {
                str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in files
            },
            "runtime_measured": False,
        }
        atomic_json(evidence_path, evidence)
        return evidence


def synthea_coverage_end(execution: dict) -> str:
    """The pinned simulation ends at midnight UTC, not at loader/publication completion."""
    from datetime import datetime

    from healthcare_ingestion.source_mapping import sql_timestamp

    inputs = execution["inputs"]
    if inputs["simulation_timezone"] != "UTC":
        raise ValueError("Verified UTC Synthea simulation horizon required.")
    return sql_timestamp(datetime.strptime(inputs["simulation_end_date"], "%Y%m%d"))


def read_fhir_directory(directory: Path) -> list[dict]:
    # Decimal strings are retained from JSON parsing; never round through binary floats.
    from decimal import Decimal

    files = sorted(directory.rglob("*.json"))
    if not files:
        raise ValueError("FHIR input directory contains no JSON bundle files.")
    return [json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal) for path in files]


def export_artifacts(root: Path):
    contracts = [
        json.loads((root / "database" / "schema-contracts" / f"{name}.json").read_text())
        for name in ("clarity", "caboodle")
    ]
    atomic_json(
        root / "metadata" / "source-mappings" / "synthea-r4-v1.json",
        mapping_document(contracts),
        indent=2,
    )
    for contract in contracts:
        path = root / "database" / contract["source_system"].lower() / "migrations"
        path.mkdir(parents=True, exist_ok=True)
        (path / "002-synthetic-integrity-and-write-path.sql").write_text(
            render_source_migration(contract), encoding="utf-8"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export-artifacts")
    for command in ("demo", "import-fhir", "synthea", "change", "validate", "load"):
        p = sub.add_parser(command)
        p.add_argument("--state", type=Path, required=True)
        p.add_argument("--batch", required=True)
        if command in {"demo", "import-fhir", "synthea", "change"}:
            p.add_argument("--at", required=True, help="Explicit UTC publication/window timestamp")
        if command in {"demo", "import-fhir", "synthea"}:
            p.add_argument("--history-start", required=True)
        if command in {"demo", "synthea"}:
            p.add_argument("--patients", type=int, default=1000)
        if command == "import-fhir":
            p.add_argument("--fhir-directory", type=Path, required=True)
        if command == "synthea":
            p.add_argument("--jar", type=Path, required=True)
            p.add_argument("--jar-sha256", required=True)
            p.add_argument("--synthea-version", required=True)
            p.add_argument("--seed", type=int, default=20261120)
            p.add_argument("--reference-date", required=True)
        if command == "change":
            p.add_argument("--profile", choices=("normal", "zero", "spike"), default="normal")
        if command == "load":
            p.add_argument("--source", choices=("Clarity", "Caboodle"), required=True)
            p.add_argument("--server", required=True)
            p.add_argument("--database", required=True)
            p.add_argument("--managed-identity-client-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "export-artifacts":
            export_artifacts(args.root)
            print("Exported 28-model mapping and source-only SQL upgrade scripts; not applied.")
            return 0
        store = PopulationStore(args.state)
        if args.command in {"demo", "import-fhir", "synthea"}:
            if args.command == "demo":
                population = local_demo_population(
                    patients=args.patients, history_start=args.history_start, publication_at=args.at
                )
            else:
                if args.command == "synthea":
                    output = args.state / "synthea" / args.batch
                    PopulationStore._validate_batch(args.batch)
                    execution = run_synthea(
                        version=args.synthea_version,
                        jar=args.jar,
                        expected_sha256=args.jar_sha256,
                        output=output,
                        patients=args.patients,
                        seed=args.seed,
                        reference_date=args.reference_date,
                    )
                    directory = output / "fhir"
                else:
                    directory = args.fhir_directory
                    execution = {"engine": "imported-fhir", "runtime_measured": False}
                population = parse_bundles(
                    read_fhir_directory(directory),
                    history_start=args.history_start,
                    publication_at=args.at,
                    coverage_end=(
                        synthea_coverage_end(execution) if args.command == "synthea" else args.at
                    ),
                )
                population["generator"] = execution
            # Verify both independent source projections before publishing an immutable
            # population. Unsupported rows cannot become accepted generation checkpoints.
            for source in ("Clarity", "Caboodle"):
                contract, mapping = _inputs(args.root, source)
                rows = project_source(population, contract, mapping)
                validate_source_rows(rows, contract)
            store.publish(args.batch, population)
            print("Published validated synthetic population and shared identity manifest.")
        elif args.command == "change":
            # Reuse the stored predecessor on rerun rather than treating the current head
            # as a new generation input. Immutable batch publish checks configuration.
            batch_path = args.state / "batches" / f"{args.batch}.json"
            PopulationStore._validate_batch(args.batch)
            predecessor = (
                store.read_batch(args.batch)["predecessor"] if batch_path.exists() else store.head()
            )
            if predecessor is None:
                raise ValueError("A baseline population is required before change scenarios.")
            previous = store.read_batch(predecessor)["population"]
            population = change_population(
                previous, batch=args.batch, at=args.at, profile=args.profile
            )
            counts = {}
            for source in ("Clarity", "Caboodle"):
                contract, mapping = _inputs(args.root, source)
                current = project_source(population, contract, mapping)
                validate_source_rows(current, contract)
                old = project_source(previous, contract, mapping)
                counts[source] = sum(map(len, source_delta(current, old, contract).values()))
            combined = sum(counts.values())
            if args.profile == "zero" and combined != 0:
                raise ValueError("Zero-change profile produced changed source rows.")
            if args.profile == "normal" and not 500 <= combined <= 1000:
                raise ValueError("Normal profile outside approved combined row-change range.")
            if args.profile == "spike" and not 4500 <= combined <= 5500:
                raise ValueError("Spike profile outside approved approximate 5000-row range.")
            store.publish(args.batch, population, predecessor)
            print(json.dumps({"profile": args.profile, "changed_rows": counts}))
        elif args.command == "validate":
            population = store.read_batch(args.batch)["population"]
            counts = {}
            for source in ("Clarity", "Caboodle"):
                contract, mapping = _inputs(args.root, source)
                rows = project_source(population, contract, mapping)
                validate_source_rows(rows, contract)
                counts[source] = {name: len(values) for name, values in rows.items()}
            print(json.dumps({"source_row_counts": counts}, sort_keys=True))
        else:
            contract, mapping = _inputs(args.root, args.source)
            evidence = load_source(
                store=store,
                batch=args.batch,
                contract=contract,
                mapping=mapping,
                checkpoint_directory=args.state / "source-checkpoints",
                adapter=PyodbcSourceAdapter(
                    SqlSourceConnection(args.server, args.database, args.managed_identity_client_id)
                ),
            )
            print(
                json.dumps(
                    {
                        "source": args.source,
                        "batch": evidence["batch"],
                        "committed_at": evidence["committed_at"],
                        "changed_rows": evidence["row_count"],
                        "recovered": evidence["recovered"],
                    }
                )
            )
        return 0
    except Exception as error:
        # Deliberately suppress original exception payload, FHIR values and ODBC SQL text.
        print(
            f"Source generator operation failed ({type(error).__name__}); no checkpoint asserted."
        )
        return 1


def _inputs(root: Path, source: str):
    contract = json.loads(
        (root / "database" / "schema-contracts" / f"{source.lower()}.json").read_text()
    )
    mapping = load_mapping(root / "metadata" / "source-mappings" / "synthea-r4-v1.json", contract)
    return contract, mapping


if __name__ == "__main__":
    raise SystemExit(main())
