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

def build_cloudflare_native_request(intent: DeliveryIntent) -> Dict[str, Any]:
    route = intent.path_prefix.rstrip("/") + "/*" if intent.path_prefix != "/" else "/*"
    return {
        "provider": "cloudflare",
        "adapterType": "native-api",
        "zone": intent.hostname,
        "loadBalancer": {
            "name": intent.hostname,
            "default_pools": [f"{intent.service_name}-pool"],
            "fallback_pool": f"{intent.service_name}-pool"
        },
        "pool": {
            "name": f"{intent.service_name}-pool",
            "origins": [
                {"name": "aws-use1-origin", "address": intent.primary_origin, "enabled": True},
                {"name": "aws-usw2-origin", "address": intent.secondary_origin, "enabled": True}
            ],
            "minimum_origins": 1
        },
        "ruleset": {
            "phase": "http_request_cache_settings",
            "rules": [{
                "description": "Cache static assets",
                "expression": f'(http.host eq "{intent.hostname}" and http.request.uri.path matches "{route}")',
                "action": "set_cache_settings",
                "action_parameters": {
                    "edge_ttl": {"mode": "override_origin", "default": intent.cache_ttl_seconds}
                }
            }]
        },
        "ownership": {"team": intent.owner_team, "lob": intent.owner_lob}
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
    print(json.dumps(build_cloudflare_native_request(demo), indent=2))
