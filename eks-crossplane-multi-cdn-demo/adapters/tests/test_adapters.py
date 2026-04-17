import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudflare_adapter import CloudflareNativeAdapter
from terraform_adapter import TerraformModuleAdapter


def test_terraform_workspace_generation(tmp_path):
    adapter = TerraformModuleAdapter(module_root=tmp_path)
    module_dir = tmp_path / "terraform" / "akamai_static_assets_module"
    module_dir.mkdir(parents=True)
    (module_dir / "main.tf").write_text("# placeholder")

    payload = {
        "tfvars": json.dumps({
            "service_name": "static-assets",
            "hostname": "assets.bank.example",
            "primary_origin": "https://origin1.example.com",
            "secondary_origin": "https://origin2.example.com",
            "path_prefix": "/static",
            "cache_ttl_seconds": 3600,
            "owner_team": "platform",
            "owner_lob": "banking",
        }),
        "modulePath": "./terraform/akamai_static_assets_module",
    }

    workspace = adapter.workspace_base / "static-assets"
    if workspace.exists():
        for child in workspace.iterdir():
            if child.is_file():
                child.unlink()
            else:
                for nested in child.rglob("*"):
                    if nested.is_file():
                        nested.unlink()
                child.rmdir()
        workspace.rmdir()

    adapter._parse_tfvars(payload["tfvars"])
    module_source = adapter._resolve_module_source(payload["modulePath"])
    adapter._prepare_workspace(workspace, module_source, json.loads(payload["tfvars"]))

    assert (workspace / "terraform.tfvars.json").exists()
    assert (workspace / "main.tf").exists()
    assert (workspace / module_source.name / "main.tf").exists()


def test_cloudflare_zone_resolution(monkeypatch):
    class DummyResponse:
        def __init__(self, ok, result):
            self.ok = ok
            self._result = result
            self.text = json.dumps({"result": result})

        def json(self):
            return {"result": self._result}

    def dummy_get(url, headers=None, params=None, timeout=None):
        zone_name = params.get("name") if params else "example.com"
        return DummyResponse(True, [{"id": "abcdef1234567890abcdef1234567890", "name": zone_name}])

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "dummy")
    monkeypatch.setattr(requests, "get", dummy_get)

    adapter = CloudflareNativeAdapter()
    zone_id = adapter._resolve_zone_id("example.com")
    assert zone_id == "abcdef1234567890abcdef1234567890"
