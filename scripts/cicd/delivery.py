"""Byte-verified Azure DevOps delivery; no release activation or fabricated evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from uuid import UUID


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle_file(root: Path, name: str) -> Path:
    parts = PurePosixPath(name)
    if "\\" in name or parts.is_absolute() or ".." in parts.parts:
        raise ValueError("Bundle path escapes the immutable release")
    path = root.joinpath(*parts.parts)
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Bundle file is missing or outside the release")
    return path


def verify(root: Path, commit: str | None = None) -> dict:
    bundle = root / "bundle"
    manifest = json.loads((bundle / "manifest.json").read_text())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("Release manifest is empty")
    for name, expected in manifest.items():
        if sha256(bundle_file(bundle, name)) != expected:
            raise ValueError(f"Release artifact digest mismatch: {name}")
    evidence = json.loads((root / "ci-evidence.json").read_text())
    if evidence["manifest_sha256"] != sha256(bundle / "manifest.json"):
        raise ValueError("CI manifest evidence does not match this bundle")
    if commit and evidence["commit"] != commit:
        raise ValueError("CI artifact belongs to another source commit")
    return evidence


def seal(root: Path) -> None:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if os.environ.get("BUILD_SOURCEVERSION", commit) != commit:
        raise ValueError("Checkout does not match the CI source commit")
    evidence = {
        "commit": commit,
        "ci_run_id": os.environ.get("BUILD_BUILDID"),
        "manifest_sha256": sha256(root / "bundle" / "manifest.json"),
    }
    (root / "ci-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    verify(root, commit)


def validate_plan(plan: dict, layer: str | None = None) -> None:
    for change in plan.get("resource_changes", []):
        if "delete" in change["change"]["actions"]:
            raise ValueError(
                f"Destruction/replacement requires separate approval: {change['address']}"
            )
        if layer and change.get("mode", "managed") == "managed":
            resource_type = change["type"]
            allowed = (
                resource_type.startswith(("azurerm_", "azapi_"))
                if layer in {"azure", "bootstrap"}
                else resource_type
                in {
                    "fabric_workspace",
                    "fabric_workspace_role_assignment",
                    "fabric_sql_database",
                    "fabric_lakehouse",
                }
            )
            if not allowed:
                raise ValueError(f"{resource_type} is outside the {layer} infrastructure boundary")


def trusted_fabric_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.fabric.microsoft.com"
        or not parsed.path.startswith("/v1/")
    ):
        raise ValueError("Fabric operation returned an untrusted polling URL")
    return url


class FabricClient:
    def request(self, method: str, url: str, **kwargs):
        import requests

        wait = kwargs.pop("_wait", True)
        token = subprocess.check_output(
            [
                shutil.which("az") or "az",
                "account",
                "get-access-token",
                "--resource",
                "https://api.fabric.microsoft.com",
                "--query",
                "accessToken",
                "-o",
                "tsv",
            ],
            text=True,
        ).strip()
        response = requests.request(
            method,
            trusted_fabric_url(url),
            headers={"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})},
            timeout=120,
            allow_redirects=False,
            **kwargs,
        )
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("Unexpected Fabric redirect")
        if response.status_code == 202 and wait:
            poll = trusted_fabric_url(response.headers["Location"])
            deadline = time.monotonic() + 1800
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Fabric operation did not complete within 30 minutes")
                time.sleep(min(max(int(response.headers.get("Retry-After", "10")), 1), 60))
                response = self.request("GET", poll, _wait=False)
                status = response.json()["status"]
                if status == "Succeeded":
                    break
                if status in {"Failed", "Cancelled"}:
                    raise RuntimeError(f"Fabric operation terminated: {status}")
            response.headers["X-Hc-Operation-Location"] = poll
        return response

    def items(self, workspace: str) -> list:
        result = []
        url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace}/items"
        while url:
            page = self.request("GET", url).json()
            result.extend(page["value"])
            url = page.get("continuationUri")
        return result

    def ensure_item(self, workspace: str, name: str, kind: str, definition=None) -> str:
        existing = [item for item in self.items(workspace) if item["displayName"] == name]
        if len(existing) > 1 or (existing and existing[0]["type"] != kind):
            raise ValueError(
                "Artifact display name is ambiguous or already belongs to another type"
            )
        url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace}"
        if not existing:
            body = {"displayName": name, "type": kind}
            if definition:
                body["definition"] = definition
            self.request("POST", url + "/items", json=body)
            existing = [item for item in self.items(workspace) if item["displayName"] == name]
            if len(existing) != 1 or existing[0]["type"] != kind:
                raise ValueError("Created Fabric artifact could not be resolved unambiguously")
        identity = str(UUID(existing[0]["id"]))
        if definition:
            response = self.request(
                "POST",
                url + f"/items/{identity}/getDefinition",
                params={"format": definition["format"]} if definition.get("format") else {},
            )
            # getDefinition is an LRO for some item types; retrieve its actual result.
            actual = response.json()
            if "definition" not in actual:
                operation = response.headers.get("X-Hc-Operation-Location")
                if not operation:
                    raise ValueError("Fabric definition operation returned no result location")
                actual = self.request(
                    "GET", trusted_fabric_url(operation).rstrip("/") + "/result"
                ).json()
            if not definitions_equal(actual["definition"], definition):
                raise ValueError(
                    "Versioned Fabric artifact definition differs; publish a new release version"
                )
        return identity


def definitions_equal(actual: dict, expected: dict) -> bool:
    def parts(definition):
        result = {}
        for part in definition["parts"]:
            decoded = base64.b64decode(part["payload"], validate=True)
            try:
                decoded = json.loads(decoded)
            except (ValueError, UnicodeDecodeError):
                pass
            result[part["path"]] = decoded
        return result

    actual_parts, expected_parts = parts(actual), parts(expected)
    return all(actual_parts.get(key) == value for key, value in expected_parts.items())


def artifact_definition(item: dict, bundle: Path, bindings: dict) -> dict:
    text = bundle_file(bundle, item["definition_file"]).read_text(encoding="utf-8")
    for token, value in bindings.items():
        text = text.replace("{{ ." + token + " }}", str(value))
    if "{{ ." in text:
        raise ValueError("Artifact has unresolved deployment bindings")
    if item["type"] == "Notebook":
        json.loads(text)
        return {
            "format": "ipynb",
            "parts": [
                {
                    "path": item["definition_path"],
                    "payload": base64.b64encode(text.encode()).decode(),
                    "payloadType": "InlineBase64",
                }
            ],
        }
    if item["type"] == "DataPipeline":
        return json.loads(text)
    raise ValueError("Only Notebook and DataPipeline definitions belong in this artifact manifest")


def publish(
    root: Path, outputs_file: Path, receipt_file: Path, infrastructure_run: str, *, client=None
) -> None:
    evidence = verify(root, os.environ["BUILD_SOURCEVERSION"])
    provenance = json.loads(outputs_file.with_name("deployment-evidence.json").read_text())
    if provenance["module"] != "fabric" or str(provenance["run_id"]) != infrastructure_run:
        raise ValueError(
            "Artifact bindings must come from the selected Fabric infrastructure apply"
        )
    outputs = json.loads(outputs_file.read_text())
    workspaces = {
        alias: str(UUID(outputs[f"fabric_{alias}_workspace_id"]["value"]))
        for alias in ("data", "metadata")
    }
    bundle = root / "bundle"
    hashes = json.loads((bundle / "manifest.json").read_text())
    for name in ("fabric-items.json", "deployment-requests.json"):
        if name not in hashes:
            raise ValueError(f"Deployment input is not in the verified manifest: {name}")
    manifest = json.loads(bundle_file(bundle, "fabric-items.json").read_text())
    deployment = json.loads(bundle_file(bundle, "deployment-requests.json").read_text())
    referenced = [item["definition_file"] for item in manifest["items"]]
    referenced.extend(
        operation["body_file"] for operation in deployment["requests"] if operation.get("body_file")
    )
    for name in referenced:
        if name not in hashes:
            raise ValueError(f"Deployment input is not in the verified manifest: {name}")
    client = client or FabricClient()
    receipt = {
        "state": "IN_PROGRESS",
        "ci": evidence,
        "infrastructure": provenance,
        "bindings": {},
        "items": {},
        "requests": [],
    }
    receipt_file.parent.mkdir(parents=True, exist_ok=True)

    def persist() -> None:
        receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")

    try:
        persist()
        workspace = workspaces["data"]
        environment = client.ensure_item(
            workspace, manifest["environment"]["display_name"], "Environment"
        )
        airflow = client.ensure_item(
            workspace, manifest["airflow"]["display_name"], "ApacheAirflowJob"
        )
        bindings = {"workspaceId": workspace, "environmentId": environment, "airflowId": airflow}
        receipt["bindings"] = bindings
        persist()
        client.request(
            "PATCH",
            f"https://api.fabric.microsoft.com/v1/workspaces/{workspace}/environments/"
            f"{environment}/staging/sparkcompute?beta=false",
            json={
                "runtimeVersion": manifest["environment"]["runtime_version"],
                "sparkProperties": [{"key": "spark.sql.session.timeZone", "value": "UTC"}],
            },
        )
        for item in manifest["items"]:
            target_workspace = workspaces[item["workspace"]]
            notebook_bindings = {
                "WorkspaceId": workspace,
                "EnvironmentId": environment,
            }
            if item.get("lakehouse"):
                layer = item["lakehouse"]
                notebook_bindings.update(
                    LakehouseId=str(UUID(outputs["lakehouses"]["value"][layer])),
                    LakehouseName=f"healthcare_data_ingestion_{layer}",
                )
            definition = artifact_definition(item, bundle, notebook_bindings)
            receipt["items"][item["key"]] = client.ensure_item(
                target_workspace, item["display_name"], item["type"], definition
            )
            persist()
        for operation in deployment["requests"]:
            route = operation["route"].format(**bindings)
            url = "https://api.fabric.microsoft.com/v1/" + route
            body = operation.get("body_file")
            response = client.request(
                operation["method"],
                url,
                data=bundle_file(bundle, body).read_bytes() if body else None,
                headers={"Content-Type": operation.get("content_type", "application/json")},
            )
            item = {
                "route": route,
                "status": response.status_code,
                "request_id": response.headers.get("request-id"),
            }
            if body:
                # Airflow PUT is not proof until GET returns the same actual bytes.
                if operation["method"] == "PUT":
                    actual = client.request("GET", url).content
                    if hashlib.sha256(actual).hexdigest() != sha256(bundle_file(bundle, body)):
                        raise ValueError("Airflow uploaded-file readback mismatch")
                item["sha256"] = sha256(bundle_file(bundle, body))
            receipt["requests"].append(item)
            persist()
        receipt["state"] = "ASSETS_PUBLISHED_NOT_ACTIVATED"
    except BaseException:
        receipt["state"] = "FAILED_OR_INCOMPLETE_NOT_ACTIVATED"
        persist()
        raise
    persist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("verify", "seal", "plan-check", "publish"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--outputs", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--layer", choices=("bootstrap", "azure", "fabric"))
    parser.add_argument("--infrastructure-run")
    args = parser.parse_args()
    if args.action == "verify":
        verify(args.path, args.commit)
    elif args.action == "seal":
        seal(args.path)
    elif args.action == "plan-check":
        validate_plan(json.loads(args.path.read_text()), args.layer)
    else:
        publish(args.path, args.outputs, args.receipt, args.infrastructure_run)


if __name__ == "__main__":
    main()
