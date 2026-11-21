import hashlib
import importlib.util
import json
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
