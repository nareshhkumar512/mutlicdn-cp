"""
Example Akamai adapter for the Crossplane multi-CDN demo.

Purpose:
- Read the canonical XDeliveryService intent
- Convert it into a demo Akamai Property Manager-style payload
- Stay deterministic and easy to explain in a leadership demo

This is NOT production code.
It is a demo translator only.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


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


def build_akamai_property(intent: DeliveryIntent) -> Dict[str, Any]:
    """
    Render a simplified Akamai-like property payload.

    Real Akamai configs are far more detailed.
    This keeps the structure recognizable for a demo:
    - property metadata
    - hostname
    - default rule tree
    - origin behavior
    - cache behavior
    """
    return {
        "productId": "prd_Fresca",
        "propertyName": f"{intent.serviceName}-property",
        "contractScope": {
            "lob": intent.lob,
            "team": intent.team,
            "sharedGateway": intent.sharedGateway,
        },
        "hostnames": [
            {
                "cnameFrom": intent.hostname,
                "certProvisioningType": "DEFAULT",
            }
        ],
        "rules": {
            "name": "default",
            "criteria": [],
            "behaviors": [
                {
                    "name": "origin",
                    "options": {
                        "hostname": intent.originHost,
                        "originType": "CUSTOMER",
                        "forwardHostHeader": "ORIGIN_HOSTNAME",
                    },
                },
                {
                    "name": "caching",
                    "options": {
                        "behavior": "MAX_AGE",
                        "ttlSeconds": intent.cacheTtlSeconds,
                    },
                },
                {
                    "name": "cpCode",
                    "options": {
                        "value": {"id": 123456}
                    },
                },
            ],
            "children": [
                {
                    "name": "path-routing",
                    "criteria": [
                        {
                            "name": "path",
                            "options": {
                                "matchOperator": "MATCHES_ONE_OF",
                                "values": [f"{intent.pathPrefix}*"],
                            },
                        }
                    ],
                    "behaviors": [
                        {
                            "name": "origin",
                            "options": {
                                "hostname": intent.originHost,
                                "originType": "CUSTOMER",
                            },
                        }
                    ],
                }
            ],
        },
        "governance": {
            "ownerTeam": intent.team,
            "ownerLob": intent.lob,
            "sharedObjectReference": intent.sharedGateway,
            "changeClass": "standard",
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
    payload = build_akamai_property(intent)

    import json
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    demo()
