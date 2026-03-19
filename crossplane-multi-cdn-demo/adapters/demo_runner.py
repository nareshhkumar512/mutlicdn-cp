"""
Small runner that shows the same canonical intent rendered into
different provider-specific shapes.
"""

from __future__ import annotations

import json
from pathlib import Path

from akamai_adapter import from_claim_dict as akamai_from_claim
from akamai_adapter import build_akamai_property
from cloudflare_adapter import from_claim_dict as cloudflare_from_claim
from cloudflare_adapter import build_cloudflare_plan


def load_demo_claim() -> dict:
    return {
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


def main() -> None:
    claim = load_demo_claim()

    akamai = build_akamai_property(akamai_from_claim(claim))
    cloudflare = build_cloudflare_plan(cloudflare_from_claim(claim))

    out = {
        "canonicalIntent": claim["spec"],
        "akamaiPlan": akamai,
        "cloudflarePlan": cloudflare,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
