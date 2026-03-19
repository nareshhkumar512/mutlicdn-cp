"""
Example Cloudflare adapter for the Crossplane multi-CDN demo.

Purpose:
- Read the canonical XDeliveryService intent
- Convert it into a demo Cloudflare-style payload
- Show why the provider-specific model is different from Akamai

This is NOT production code.
It is a demo translator only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class DeliveryIntent:
    serviceName: str
    team: str
    lob: str
    hostname: str
    sharedGateway: str
    originHost: str
    pathPrefix: str = "/"
    cacheTtlSeconds: int = 60
    tlsMinVersion: str = "TLS1.2"


def build_cloudflare_plan(intent: DeliveryIntent) -> Dict[str, Any]:
    """
    Render a simplified Cloudflare-like plan.

    Demo shape:
    - load balancer pool
    - monitor
    - load balancer
    - ruleset using ordered phase logic
    """
    expression_path = intent.pathPrefix.rstrip("/") + "/*" if intent.pathPrefix != "/" else "/*"

    return {
        "zone": intent.hostname,
        "ownership": {
            "lob": intent.lob,
            "team": intent.team,
            "sharedGateway": intent.sharedGateway,
        },
        "monitor": {
            "type": "https",
            "path": "/health",
            "method": "GET",
            "timeout": 5,
            "interval": 60,
        },
        "pool": {
            "name": f"{intent.serviceName}-pool",
            "origins": [
                {
                    "name": f"{intent.serviceName}-origin-1",
                    "address": intent.originHost,
                    "enabled": True,
                }
            ],
            "minimum_origins": 1,
        },
        "loadBalancer": {
            "name": intent.hostname,
            "default_pools": [f"{intent.serviceName}-pool"],
            "fallback_pool": f"{intent.serviceName}-pool",
            "proxied": True,
        },
        "ruleset": {
            "phase": "http_request_origin",
            "rules": [
                {
                    "description": "Route canonical app intent",
                    "expression": f'(http.host eq "{intent.hostname}" and http.request.uri.path matches "{expression_path}")',
                    "action": "route",
                    "action_parameters": {
                        "origin": {
                            "host": intent.originHost
                        }
                    },
                },
                {
                    "description": "Apply edge cache behavior",
                    "expression": f'http.host eq "{intent.hostname}"',
                    "action": "set_cache_settings",
                    "action_parameters": {
                        "edge_ttl": {
                            "mode": "override_origin",
                            "default": intent.cacheTtlSeconds,
                        }
                    },
                },
            ],
        },
        "governance": {
            "changeClass": "standard",
            "provider": "cloudflare",
        },
    }


def from_claim_dict(claim: Dict[str, Any]) -> DeliveryIntent:
    spec = claim.get("spec", claim)
    return DeliveryIntent(
        serviceName=spec["serviceName"],
        team=spec["team"],
        lob=spec["lob"],
        hostname=spec["hostname"],
        sharedGateway=spec["sharedGateway"],
        originHost=spec["originHost"],
        pathPrefix=spec.get("pathPrefix", "/"),
        cacheTtlSeconds=int(spec.get("cacheTtlSeconds", 60)),
        tlsMinVersion=spec.get("tlsMinVersion", "TLS1.2"),
    )


def demo() -> None:
    claim = {
        "spec": {
            "serviceName": "retail-login",
            "team": "retail-platform",
            "lob": "retail-banking",
            "hostname": "login.bank.example",
            "sharedGateway": "customer-login-gw",
            "originHost": "login-origin.internal.bank.example",
            "pathPrefix": "/login",
            "cacheTtlSeconds": 60,
            "tlsMinVersion": "TLS1.2",
        }
    }
    intent = from_claim_dict(claim)
    payload = build_cloudflare_plan(intent)

    import json
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    demo()
