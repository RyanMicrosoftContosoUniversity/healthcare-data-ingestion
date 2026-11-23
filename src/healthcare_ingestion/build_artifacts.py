"""Deterministic notebook/DAG specifications and hashed local release preparation."""

import ast
import hashlib
import json
import re
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from healthcare_ingestion.artifacts import checked_key, encoded
from healthcare_ingestion.configuration import ReleaseSnapshot, thaw
from healthcare_ingestion.function_contracts import FUNCTION_SCHEMAS
from healthcare_ingestion.source_contracts import bind_source_contracts, validate_source_contract


def notebook_definition(stage):
    if stage not in {"bronze", "silver1"}:
        raise ValueError("Only the approved Bronze and Patient Silver notebook stages exist.")
    cells = [
        (
            [
                "runtime_config_json = ''",
                "operation_id = ''",
                "operation_ids_json = ''",
                "owner = ''",
                "dag_run_id = ''",
            ],
            {"tags": ["parameters"]},
        ),
        (
            [
                "import json",
                "from healthcare_ingestion.runtime import bootstrap",
                "if not all((runtime_config_json, owner, dag_run_id)):",
                "    raise ValueError('Explicit pinned run parameters are required.')",
                "operation_ids = json.loads(operation_ids_json) if operation_ids_json else []",
                "operation_ids = operation_ids or [operation_id]",
                "if not all(operation_ids):",
                "    raise ValueError('Explicit operation identities are required.')",
                "worker = bootstrap(json.loads(runtime_config_json), spark)",
                "operation = worker.store.operation(operation_ids[0])",
                "snapshot = worker.store.snapshot(operation['release_version'])",
                "task = snapshot.task(operation['task_id'])",
                f"if snapshot.dataset(task.primary_output).layer != '{stage}':",
                "    raise ValueError('Operation targets another notebook stage.')",
                "outcomes = worker.execute_workflow(operation_ids, owner, dag_run_id)",
                "if any('error' in outcome for outcome in outcomes.values()):",
                "    raise RuntimeError('Operation failure; consult control evidence.')",
            ],
            {},
        ),
    ]
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Synapse PySpark",
                "language": "python",
                "name": "synapse_pyspark",
            },
            "language_info": {"name": "python"},
            "dependencies": {
                "environment": {
                    "environmentId": "{{ .EnvironmentId }}",
                    "workspaceId": "{{ .WorkspaceId }}",
                },
                "lakehouse": {
                    "default_lakehouse": "{{ .LakehouseId }}",
                    "default_lakehouse_name": "{{ .LakehouseName }}",
                    "default_lakehouse_workspace_id": "{{ .WorkspaceId }}",
                },
            },
        },
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": metadata,
                "outputs": [],
                "source": [line + "\n" for line in lines],
            }
            for lines, metadata in cells
        ],
    }


def dag_specifications(snapshot):
    parents = snapshot.graph()
    workflows = sorted({task.workflow for task in snapshot.tasks if not task.retired})
    return {
        workflow: {
            "workflow": workflow,
            "framework_version": snapshot.version,
            "timezone": "America/New_York",
            "schedule": "0 10 * * *",
            "required_availability": "11:00",
            "deadline_cancels_work": False,
            "reconciliation_seconds": 300,
            "catchup": False,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "parents": list(parents[task.task_id]),
                    "output": task.primary_output,
                    "settings": thaw(snapshot.effective_settings(task.task_id)),
                }
                for task in snapshot.tasks
                if task.workflow == workflow and not task.retired
            ],
        }
        for workflow in workflows
    }


def prepare_release(snapshot, source_contracts, wheel, dependency_lock, output):
    snapshot.validate(FUNCTION_SCHEMAS)
    for contract in source_contracts.values():
        validate_source_contract(contract)
    if {c["source_system"] for c in source_contracts.values()} != {"Clarity", "Caboodle"}:
        raise ValueError("The initial demo requires both approved independent sources.")
    if Path(wheel).stat().st_size > 100 * 1024 * 1024:
        raise ValueError("The package exceeds the supported environment library size.")
    with ZipFile(wheel) as archive:
        if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError("Expanded package content exceeds the bounded release size.")
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("The release requires one valid package wheel.")
        package = BytesParser().parsebytes(archive.read(names[0]))
        if package["Name"] != "healthcare-ingestion" or package["Version"] != snapshot.version:
            raise ValueError("Package wheel version differs from the pinned framework release.")
        plugins = {
            "plugins/" + checked_key(name): archive.read(name)
            for name in archive.namelist()
            if name.startswith("healthcare_ingestion/") and name.endswith(".py")
        }
        required = {
            "__init__.py",
            "airflow_runtime.py",
            "runtime.py",
            "configuration.py",
            "control_store.py",
            "execution.py",
        }
        if not {f"plugins/healthcare_ingestion/{name}" for name in required} <= plugins.keys():
            raise ValueError("The package is missing required executable runtime modules.")
        for name, body in plugins.items():
            if len(body) > 2 * 1024 * 1024:
                raise ValueError("An Airflow plugin exceeds the supported file upload size.")
            ast.parse(body.decode("utf-8"), filename=name)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "bronze.ipynb": encoded(notebook_definition("bronze")),
        "patient-silver.ipynb": encoded(notebook_definition("silver1")),
        "fabric-items.json": encoded(
            {
                "environment": {
                    "display_name": f"hc-ingestion-environment-{snapshot.version}",
                    "runtime_version": "2.0",
                },
                "airflow": {"display_name": "hc-ingestion-orchestration"},
                "items": [
                    {
                        "key": workflow,
                        "workspace": "data",
                        "display_name": f"hc-{workflow}-{snapshot.version}",
                        "type": "Notebook",
                        "format": "ipynb",
                        "definition_file": source,
                        "definition_path": "notebook-content.ipynb",
                        "lakehouse": layer,
                    }
                    for workflow, source, layer in (
                        ("clarity_bronze", "bronze.ipynb", "bronze"),
                        ("caboodle_bronze", "bronze.ipynb", "bronze"),
                        ("patient_silver", "patient-silver.ipynb", "silver"),
                    )
                ],
            }
        ),
        "dag-specifications.json": encoded(dag_specifications(snapshot)),
        "dependency.lock": Path(dependency_lock).read_bytes(),
        Path(wheel).name: Path(wheel).read_bytes(),
        "environment.json": encoded(
            {
                "runtime_version": "2.0",
                "spark": "4.1",
                "delta": "4.2",
                "python": "3.13",
                "odbc_driver": "ODBC Driver 18 for SQL Server",
                "wheel": Path(wheel).name,
                "publication_verified": False,
                "cloud_dependencies": [
                    "azure-identity==1.27.0",
                    "azure-storage-blob==12.31.1",
                    "azure-monitor-ingestion==1.1.0",
                    "pyodbc==5.5.0",
                ],
            }
        ),
    }
    for workflow in dag_specifications(snapshot):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", workflow):
            raise ValueError("Workflow names must be safe Airflow identifiers.")
        payloads[f"{workflow}.py"] = dag_source(workflow).encode()
        payloads.update(plugins)
        requirements = [
            "azure-identity==1.27.0",
            "azure-storage-blob==12.31.1",
            "azure-monitor-ingestion==1.1.0",
            "pyodbc==5.5.0",
        ]
        payloads["environment.yml"] = (
            "dependencies:\n  - pip:\n" + "".join(f"      - {name}\n" for name in requirements)
        ).encode()
        payloads["airflow-profile.json"] = encoded(
            {
                "airflow_version": "2.10.5",
                "python_version": "3.12",
                "package_provider_path": "plugins",
                "requirements": requirements,
                "live_profile_verified": False,
            }
        )
        environment_route = "workspaces/{workspaceId}/environments/{environmentId}/staging/"
        airflow_route = "workspaces/{workspaceId}/apacheAirflowJobs/{airflowId}/"
        requests = [
            {
                "method": "POST",
                "route": environment_route + "libraries/" + Path(wheel).name,
                "content_type": "application/octet-stream",
                "body_file": Path(wheel).name,
            },
            {
                "method": "POST",
                "route": environment_route + "libraries/importExternalLibraries",
                "content_type": "application/octet-stream",
                "body_file": "environment.yml",
            },
            {"method": "POST", "route": environment_route + "publish?beta=false"},
        ]
        for name in payloads:
            if name.startswith("plugins/") or name.endswith(".py"):
                destination = name if name.startswith("plugins/") else "dags/" + name
                requests.append(
                    {
                        "method": "PUT",
                        "route": airflow_route + "files/" + destination + "?beta=true",
                        "content_type": "application/octet-stream",
                        "body_file": name,
                    }
                )
        payloads["deployment-requests.json"] = encoded(
            {
                "state": "UNEXECUTED",
                "infrastructure_review_required": True,
                "framework_version": snapshot.version,
                "requests": requests,
            }
        )
    payloads["reconciliation.py"] = (
        b"from airflow import DAG\n"
        b"from airflow.operators.python import PythonOperator\n"
        b"import pendulum\n"
        b"from healthcare_ingestion.airflow_runtime import coordinate_pending\n\n"
        b"with DAG(dag_id='hc_reconciliation', schedule='*/5 * * * *',\n"
        b"         start_date=pendulum.datetime(2026, 1, 1, tz='America/New_York'),\n"
        b"         catchup=False, max_active_runs=1) as dag:\n"
        b"    PythonOperator(task_id='reconcile', python_callable=coordinate_pending,\n"
        b"                   retries=0)\n"
    )
    requests.append(
        {
            "method": "PUT",
            "route": airflow_route + "files/dags/reconciliation.py?beta=true",
            "content_type": "application/octet-stream",
            "body_file": "reconciliation.py",
        }
    )
    payloads["deployment-requests.json"] = encoded(
        {
            "state": "UNEXECUTED",
            "infrastructure_review_required": True,
            "framework_version": snapshot.version,
            "requests": requests,
        }
    )
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    release = snapshot.to_dict()
    release["artifacts"]["source_contracts"] = bind_source_contracts(snapshot, source_contracts)
    release["artifacts"]["local_manifest"] = digests
    # Local preparation is not environment publication or Airflow recognition.
    release["artifacts"]["preparation_state"] = "LOCAL_VALIDATED"
    release["artifacts"]["package"] = {
        "sha256": digests[Path(wheel).name],
        "path": Path(wheel).name,
    }
    release["artifacts"]["dependencies"] = {
        "sha256": digests["dependency.lock"],
        "path": "dependency.lock",
    }
    for key in ("notebooks", "environments", "dags"):
        release["artifacts"][key] = {
            "state": "UNPUBLISHED",
            "approved_digest_required": True,
            "prepared_manifest": digests,
        }
    prepared = ReleaseSnapshot.from_dict(release)
    payloads["release.json"] = encoded(prepared.to_dict())
    payloads["manifest.json"] = encoded(
        {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    )
    for name, data in payloads.items():
        path = output / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError("A prepared immutable release directory cannot be overwritten.")
    for name, data in payloads.items():
        path = output / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as file:
                file.write(data)
    return prepared


def dag_source(workflow):
    return (
        "from airflow import DAG\n"
        "from airflow.operators.python import PythonOperator\n"
        "import pendulum\n"
        "from healthcare_ingestion.airflow_runtime import run_workflow\n\n"
        "with DAG(\n"
        f"    dag_id={workflow!r},\n"
        "    schedule='0 10 * * *',\n"
        "    start_date=pendulum.datetime(2026, 1, 1, tz='America/New_York'),\n"
        "    catchup=False, max_active_runs=1,\n"
        ") as dag:\n"
        "    PythonOperator(\n"
        "        task_id='coordinate', python_callable=run_workflow,\n"
        f"        op_kwargs={{'workflow': {workflow!r}}}, retries=0,\n"
        "    )\n"
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Prepare an immutable local Fabric release.")
    for name in ("release", "contracts", "wheel", "lock", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    contracts = {
        name: json.loads((Path(args.contracts) / f"{name}.json").read_text())
        for name in ("clarity", "caboodle")
    }
    prepare_release(
        ReleaseSnapshot.from_dict(json.loads(Path(args.release).read_text())),
        contracts,
        args.wheel,
        args.lock,
        args.output,
    )


if __name__ == "__main__":
    main()
