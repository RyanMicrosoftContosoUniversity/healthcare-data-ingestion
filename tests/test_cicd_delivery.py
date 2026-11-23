import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "delivery", Path(__file__).parents[1] / "scripts" / "cicd" / "delivery.py"
)
delivery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(delivery)


def release(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    content = b"reviewed immutable content"
    (bundle / "release.json").write_bytes(content)
    manifest = {"release.json": hashlib.sha256(content).hexdigest()}
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "ci-evidence.json").write_text(
        json.dumps(
            {"commit": "abc123", "manifest_sha256": delivery.sha256(bundle / "manifest.json")}
        )
    )
    return tmp_path


def test_delivery_rejects_changed_artifact_and_wrong_commit(tmp_path):
    root = release(tmp_path)
    assert delivery.verify(root, "abc123")["commit"] == "abc123"
    with pytest.raises(ValueError, match="another source commit"):
        delivery.verify(root, "def456")
    (root / "bundle" / "release.json").write_bytes(b"unreviewed replacement")
    with pytest.raises(ValueError, match="digest mismatch"):
        delivery.verify(root, "abc123")


@pytest.mark.parametrize("name", ["../secret", "/secret", r"..\secret"])
def test_bundle_paths_cannot_escape_release(tmp_path, name):
    with pytest.raises(ValueError, match="escapes"):
        delivery.bundle_file(tmp_path, name)


def test_infrastructure_rejects_replacement_and_delete_but_accepts_add_update():
    delivery.validate_plan(
        {"resource_changes": [{"address": "approved.resource", "change": {"actions": ["create"]}}]}
    )
    for actions in (["delete"], ["delete", "create"], ["create", "delete"]):
        with pytest.raises(ValueError, match="separate approval"):
            delivery.validate_plan(
                {
                    "resource_changes": [
                        {"address": "protected.resource", "change": {"actions": actions}}
                    ]
                }
            )


@pytest.mark.parametrize(
    "url",
    [
        "https://other.example/v1/operation",
        "http://api.fabric.microsoft.com/v1/operation",
        "https://api.fabric.microsoft.com@other.example/v1/operation",
    ],
)
def test_polling_never_forwards_credentials_to_other_hosts(url):
    with pytest.raises(ValueError, match="untrusted"):
        delivery.trusted_fabric_url(url)


@pytest.mark.parametrize(
    ("layer", "resource_type"),
    [
        ("azure", "fabric_workspace"),
        ("fabric", "azurerm_storage_account"),
        ("fabric", "fabric_notebook"),
        ("fabric", "fabric_environment"),
        ("bootstrap", "fabric_workspace_role_assignment"),
        ("bootstrap", "azuread_application"),
        ("fabric", "azuread_service_principal"),
        ("azure", "azuread_application_password"),
        ("azure", "tls_private_key"),
    ],
)
def test_terraform_plan_rejects_cross_boundary_resources(layer, resource_type):
    with pytest.raises(ValueError, match="outside"):
        delivery.validate_plan(
            {
                "resource_changes": [
                    {
                        "address": resource_type + ".test",
                        "type": resource_type,
                        "change": {"actions": ["create"]},
                    }
                ]
            },
            layer,
        )


@pytest.mark.parametrize(
    "resource_type",
    ["azuread_application", "azuread_service_principal", "azuread_application_certificate"],
)
def test_azure_plan_accepts_certificate_backed_runtime_identity_resources(resource_type):
    delivery.validate_plan(
        {
            "resource_changes": [
                {
                    "address": resource_type + ".runtime",
                    "type": resource_type,
                    "change": {"actions": ["create"]},
                }
            ]
        },
        "azure",
    )


def test_artifact_definitions_bind_notebook_without_mutating_bundle(tmp_path):
    notebook = {"metadata": {"environment": "{{ .EnvironmentId }}"}, "cells": []}
    path = tmp_path / "notebook.ipynb"
    path.write_text(json.dumps(notebook))
    spec = {
        "type": "Notebook",
        "definition_file": path.name,
        "definition_path": "notebook-content.ipynb",
    }
    bound = delivery.artifact_definition(spec, tmp_path, {"EnvironmentId": "actual-id"})
    assert json.loads(base64.b64decode(bound["parts"][0]["payload"]))["metadata"] == {
        "environment": "actual-id"
    }
    assert json.loads(path.read_text()) == notebook
    with pytest.raises(ValueError, match="unresolved"):
        delivery.artifact_definition(spec, tmp_path, {})


def test_data_pipeline_definition_and_versioned_content_comparison(tmp_path):
    pipeline = {
        "parts": [
            {
                "path": "pipeline-content.json",
                "payload": base64.b64encode(b'{"properties":{"activities":[]}}').decode(),
                "payloadType": "InlineBase64",
            }
        ]
    }
    (tmp_path / "pipeline.json").write_text(json.dumps(pipeline))
    spec = {"type": "DataPipeline", "definition_file": "pipeline.json"}
    actual = delivery.artifact_definition(spec, tmp_path, {})
    assert delivery.definitions_equal(actual, pipeline)
    changed = json.loads(json.dumps(actual))
    changed["parts"][0]["payload"] = base64.b64encode(b'{"different":true}').decode()
    assert not delivery.definitions_equal(changed, pipeline)


@pytest.mark.parametrize("unhashed", [None, "fabric-items.json", "pipeline.json"])
def test_artifact_publication_uses_fabric_outputs_and_both_workspaces(
    tmp_path, monkeypatch, unhashed
):
    from types import SimpleNamespace

    root = release(tmp_path)
    bundle = root / "bundle"
    identifiers = {
        "data": "11111111-1111-4111-8111-111111111111",
        "metadata": "22222222-2222-4222-8222-222222222222",
        "environment": "33333333-3333-4333-8333-333333333333",
        "airflow": "44444444-4444-4444-8444-444444444444",
    }
    pipeline = {
        "parts": [
            {
                "path": "pipeline-content.json",
                "payload": base64.b64encode(b"{}").decode(),
                "payloadType": "InlineBase64",
            }
        ]
    }
    files = {
        "pipeline.json": pipeline,
        "fabric-items.json": {
            "environment": {"display_name": "environment-0.1.0", "runtime_version": "2.0"},
            "airflow": {"display_name": "airflow"},
            "items": [
                {
                    "key": "pipeline",
                    "type": "DataPipeline",
                    "workspace": "metadata",
                    "display_name": "pipeline-0.1.0",
                    "definition_file": "pipeline.json",
                }
            ],
        },
        "deployment-requests.json": {"requests": []},
    }
    for name, value in files.items():
        (bundle / name).write_text(json.dumps(value))
    manifest = {p.name: delivery.sha256(p) for p in bundle.iterdir() if p.name != "manifest.json"}
    if unhashed:
        del manifest[unhashed]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    (root / "ci-evidence.json").write_text(
        json.dumps(
            {
                "commit": "abc123",
                "manifest_sha256": delivery.sha256(bundle / "manifest.json"),
            }
        )
    )
    outputs = root / "outputs.json"
    outputs.write_text(
        json.dumps(
            {
                f"fabric_{alias}_workspace_id": {"value": identifiers[alias]}
                for alias in ("data", "metadata")
            }
        )
    )
    (root / "deployment-evidence.json").write_text(json.dumps({"module": "fabric", "run_id": "42"}))
    calls = []

    class Client:
        def ensure_item(self, workspace, name, kind, definition=None):
            calls.append((workspace, name, kind))
            return identifiers.get(kind.lower(), identifiers["airflow"])

        def request(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, headers={})

    monkeypatch.setenv("BUILD_SOURCEVERSION", "abc123")
    receipt = root / "receipt.json"
    if unhashed:
        with pytest.raises(ValueError, match="not in the verified manifest"):
            delivery.publish(root, outputs, receipt, "42", client=Client())
        assert calls == []
        return
    delivery.publish(root, outputs, receipt, "42", client=Client())
    assert calls[-1] == (identifiers["metadata"], "pipeline-0.1.0", "DataPipeline")
    assert json.loads(receipt.read_text())["state"] == "ASSETS_PUBLISHED_NOT_ACTIVATED"
    with pytest.raises(ValueError, match="selected Fabric"):
        delivery.publish(root, outputs, receipt, "999", client=Client())


def test_item_publication_rejects_existing_version_with_different_definition():
    from types import SimpleNamespace

    class Client(delivery.FabricClient):
        def items(self, workspace):
            return [
                {
                    "displayName": "patient-0.1.0",
                    "type": "Notebook",
                    "id": "11111111-1111-4111-8111-111111111111",
                }
            ]

        def request(self, *args, **kwargs):
            return SimpleNamespace(
                json=lambda: {
                    "definition": {
                        "parts": [
                            {
                                "path": "notebook-content.ipynb",
                                "payload": base64.b64encode(b'{"changed":true}').decode(),
                            }
                        ]
                    }
                }
            )

    expected = {
        "parts": [
            {
                "path": "notebook-content.ipynb",
                "payload": base64.b64encode(b"{}").decode(),
            }
        ]
    }
    with pytest.raises(ValueError, match="new release version"):
        Client().ensure_item("workspace", "patient-0.1.0", "Notebook", expected)


@pytest.mark.parametrize("poll_status", [200, 202])
def test_fabric_client_retains_lro_result_location(monkeypatch, poll_status):
    from types import SimpleNamespace

    responses = iter(
        [
            SimpleNamespace(
                status_code=202,
                is_redirect=False,
                headers={
                    "Location": "https://api.fabric.microsoft.com/v1/operations/actual",
                    "Retry-After": "1",
                },
                raise_for_status=lambda: None,
            ),
            SimpleNamespace(
                status_code=poll_status,
                is_redirect=False,
                headers={},
                json=lambda: {"status": "Running"},
                raise_for_status=lambda: None,
            ),
            SimpleNamespace(
                status_code=200,
                is_redirect=False,
                headers={},
                json=lambda: {"status": "Succeeded"},
                raise_for_status=lambda: None,
            ),
        ]
    )
    monkeypatch.setattr(delivery.subprocess, "check_output", lambda *a, **k: "token")
    monkeypatch.setattr(delivery.time, "sleep", lambda _: None)
    monkeypatch.setitem(
        sys.modules, "requests", SimpleNamespace(request=lambda *a, **k: next(responses))
    )
    response = delivery.FabricClient().request(
        "POST", "https://api.fabric.microsoft.com/v1/workspaces/id/items/id/getDefinition"
    )
    assert response.headers["X-Hc-Operation-Location"].endswith("/operations/actual")
