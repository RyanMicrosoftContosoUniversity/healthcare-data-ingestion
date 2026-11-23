"""Byte-verified Azure DevOps delivery; no release activation or fabricated evidence."""

from __future__ import annotations

import argparse
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


def validate_plan(plan: dict) -> None:
    for change in plan.get("resource_changes", []):
        if "delete" in change["change"]["actions"]:
            raise ValueError(
                f"Destruction/replacement requires separate approval: {change['address']}"
            )


def trusted_fabric_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.fabric.microsoft.com"
        or not parsed.path.startswith("/v1/")
    ):
        raise ValueError("Fabric operation returned an untrusted polling URL")
    return url


def publish(root: Path, outputs_file: Path, receipt_file: Path) -> None:
    import requests

    evidence = verify(root, os.environ["BUILD_SOURCEVERSION"])
    outputs = json.loads(outputs_file.read_text())
    bindings = {
        "workspaceId": str(UUID(outputs["fabric_data_workspace_id"]["value"])),
        "environmentId": str(UUID(outputs["release_environment_id"]["value"])),
        "airflowId": str(UUID(outputs["airflow_item_id"]["value"])),
    }
    bundle = root / "bundle"
    deployment = json.loads((bundle / "deployment-requests.json").read_text())
    receipts = []
    # A partial failure must leave truthful evidence, not mutate the immutable bundle.
    receipt = {"state": "IN_PROGRESS", "ci": evidence, "bindings": bindings, "requests": receipts}
    receipt_file.parent.mkdir(parents=True, exist_ok=True)

    def persist() -> None:
        receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")

    def request(method: str, url: str, **kwargs):
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
        return response

    persist()
    try:
        for operation in deployment["requests"]:
            route = operation["route"].format(**bindings)
            url = "https://api.fabric.microsoft.com/v1/" + route
            body = operation.get("body_file")
            response = request(
                operation["method"],
                url,
                data=bundle_file(bundle, body).read_bytes() if body else None,
                headers={"Content-Type": operation.get("content_type", "application/json")},
            )
            if response.status_code == 202:
                poll = trusted_fabric_url(response.headers["Location"])
                deadline = time.monotonic() + 1800
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Fabric publication did not complete within 30 minutes")
                    time.sleep(min(max(int(response.headers.get("Retry-After", "10")), 1), 60))
                    response = request("GET", poll)
                    status = response.json()["status"]
                    if status == "Succeeded":
                        break
                    if status in {"Failed", "Cancelled"}:
                        raise RuntimeError(f"Fabric publication terminated: {status}")
            item = {
                "route": route,
                "status": response.status_code,
                "request_id": response.headers.get("request-id"),
            }
            if body:
                # Airflow PUT is not proof until GET returns the same actual bytes.
                if operation["method"] == "PUT":
                    actual = request("GET", url).content
                    if hashlib.sha256(actual).hexdigest() != sha256(bundle_file(bundle, body)):
                        raise ValueError("Airflow uploaded-file readback mismatch")
                item["sha256"] = sha256(bundle_file(bundle, body))
            receipts.append(item)
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
    args = parser.parse_args()
    if args.action == "verify":
        verify(args.path, args.commit)
    elif args.action == "seal":
        seal(args.path)
    elif args.action == "plan-check":
        validate_plan(json.loads(args.path.read_text()))
    else:
        publish(args.path, args.outputs, args.receipt)


if __name__ == "__main__":
    main()
