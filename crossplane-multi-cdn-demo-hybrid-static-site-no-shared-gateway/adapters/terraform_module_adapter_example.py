from dataclasses import dataclass
from typing import Dict, Any
import json

@dataclass
class DeliveryIntent:
    service_name: str
    hostname: str
    primary_origin: str
    secondary_origin: str
    path_prefix: str
    cache_ttl_seconds: int
    owner_team: str
    owner_lob: str

def build_terraform_module_request(intent: DeliveryIntent) -> Dict[str, Any]:
    return {
        "provider": "akamai",
        "adapterType": "terraform-module",
        "moduleSource": "./terraform/akamai_static_assets_module",
        "variables": {
            "service_name": intent.service_name,
            "hostname": intent.hostname,
            "primary_origin": intent.primary_origin,
            "secondary_origin": intent.secondary_origin,
            "path_prefix": intent.path_prefix,
            "cache_ttl_seconds": intent.cache_ttl_seconds,
            "owner_team": intent.owner_team,
            "owner_lob": intent.owner_lob
        },
        "workspaceNotes": "Crossplane would reconcile a Terraform/OpenTofu Workspace using these inputs."
    }

if __name__ == "__main__":
    demo = DeliveryIntent(
        "static-assets",
        "assets.bank.example",
        "assets-use1.s3-website-us-east-1.amazonaws.com",
        "assets-usw2.s3-website-us-west-2.amazonaws.com",
        "/static",
        3600,
        "digital-assets-platform",
        "shared-services"
    )
    print(json.dumps(build_terraform_module_request(demo), indent=2))
