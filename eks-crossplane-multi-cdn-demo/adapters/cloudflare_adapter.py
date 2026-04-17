#!/usr/bin/env python3
import ast
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-_")


class CloudflareNativeAdapter:
    def __init__(self, api_token: Optional[str] = None, zone_name: Optional[str] = None, account_id: Optional[str] = None):
        self.api_token = api_token
        self.default_zone = zone_name
        self.default_account = account_id
        self.headers: Optional[Dict[str, str]] = None
        self._config_loaded = False

    def _ensure_configured(self):
        if self._config_loaded:
            return
        if self.api_token and self.default_zone is not None:
            self.headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
            self._config_loaded = True
            return
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.default_zone = os.getenv("CLOUDFLARE_ZONE_ID")
        self.default_account = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        if not self.api_token:
            raise ValueError("Missing required environment variable: CLOUDFLARE_API_TOKEN")
        if not self.default_zone:
            raise ValueError("Missing required environment variable: CLOUDFLARE_ZONE_ID")
        self._config_loaded = True
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _ensure_dns_record(self, zone_id: str, hostname: str, target: str, record_type: str = "CNAME") -> Dict[str, Any]:
        """
        Ensure a DNS record exists for the hostname, pointing to the target (LB or origin).
        """
        response = requests.get(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records",
            headers=self.headers,
            params={"name": hostname},
            timeout=30,
        )
        data = response.json()
        if response.ok and data.get("result"):
            logger.info("Using existing DNS record for %s", hostname)
            return data["result"][0]
        body = {
            "type": record_type,
            "name": hostname,
            "content": target,
            "proxied": True
        }
        response, result = self._request_json_with_rate_limit(
            "post",
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records",
            data=json.dumps(body),
            timeout=30,
            max_attempts=5,
        )
        if not response.ok or not result.get("success"):
            if self._is_dns_already_exists_error(result):
                logger.info("Cloudflare DNS record already exists for %s; treating as success", hostname)
                return {
                    "id": "existing-record",
                    "name": hostname,
                    "status": "exists",
                    "warning": str(result),
                }
            if self._is_auth_error(result):
                logger.warning("Cloudflare token lacks DNS write permissions; skipping DNS record create")
                return {
                    "id": "skipped-auth",
                    "name": hostname,
                    "status": "skipped-auth",
                    "warning": str(result),
                }
            raise RuntimeError(f"Cloudflare DNS record create failed: {result}")
        return result["result"]
        

    def execute_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_configured()
        operation = str(payload.get("operation", "apply")).strip().lower()
        zone_hint = payload.get("zone") or payload.get("hostname")
        zone_id = self._resolve_zone_id(zone_hint)
        zone_name = self._resolve_zone_name(zone_id)
        service_name = payload.get("service_name") or payload.get("serviceName") or self._derive_service_label(zone_hint, zone_name)
        hostname = payload.get("hostname") or zone_hint or service_name
        if hostname is None:
            raise ValueError("Cloudflare adapter requires hostname")
        hostname = str(hostname)
        lb_hostname = self._hostname_for_zone(hostname, service_name, zone_name)
        if operation in {"delete", "destroy", "decommission"}:
            return self._decommission_request(zone_id, service_name, lb_hostname)

        primary_origin = payload.get("primaryOrigin") or payload.get("primary_origin")
        secondary_origin = payload.get("secondaryOrigin") or payload.get("secondary_origin")
        cache_ttl_seconds = int(payload.get("cacheTtlSeconds") or payload.get("cache_ttl_seconds") or 3600)
        path_prefix = payload.get("pathPrefix") or payload.get("path_prefix") or "/"
        html_cache_policy = payload.get("htmlCachePolicy") or payload.get("html_cache_policy") or "inherit"
        raw_allowed_paths = payload.get("allowedPaths") or payload.get("allowed_paths")
        allowed_paths = self._parse_allowed_paths(raw_allowed_paths, path_prefix)
        extra_allowed_paths = [
            payload.get("allowedPath3"),
            payload.get("allowedPath4"),
            payload.get("allowedPath5"),
        ]
        for extra in extra_allowed_paths:
            if extra:
                p = str(extra).strip()
                if p:
                    if not p.startswith("/"):
                        p = f"/{p}"
                    if p not in allowed_paths:
                        allowed_paths.append(p)

        if not primary_origin:
            raise ValueError("Cloudflare adapter requires primaryOrigin")

        secondary_origin_value = str(secondary_origin or "").strip()
        use_load_balancer = bool(secondary_origin_value) and secondary_origin_value != str(primary_origin).strip()

        # Optional LB mode: enabled only when a distinct secondary origin hostname is provided.
        if use_load_balancer:
            try:
                account_id = self._resolve_account_id(zone_id)
                pool = self._ensure_origin_pool(account_id, service_name, primary_origin, secondary_origin_value)
                lb = self._ensure_load_balancer(zone_id, service_name, lb_hostname, pool["id"])
                ruleset = self._ensure_ruleset(
                    zone_id,
                    service_name,
                    lb_hostname,
                    path_prefix,
                    cache_ttl_seconds,
                    pool["id"],
                    primary_origin,
                    html_cache_policy,
                )
                firewall_ruleset = self._ensure_allowlist_firewall_ruleset(
                    zone_id,
                    service_name,
                    lb_hostname,
                    allowed_paths,
                )
                # For Cloudflare Load Balancer, DNS record is managed by LB name itself.
                return {
                    "provider": "cloudflare",
                    "operation": operation,
                    "status": "completed",
                    "zone_id": zone_id,
                    "service_name": service_name,
                    "primary_origin": primary_origin,
                    "secondary_origin": secondary_origin_value,
                    "hostname": lb_hostname,
                    "pool_id": pool.get("id"),
                    "load_balancer_id": lb.get("id"),
                    "ruleset_id": ruleset.get("id"),
                    "firewall_ruleset_id": firewall_ruleset.get("id"),
                    "dns_record_id": "managed-by-lb",
                    "mode": "load-balancer",
                }
            except Exception as exc:
                logger.warning(
                    "Cloudflare LB setup failed, falling back to primary-origin-only mode for %s: %s",
                    service_name,
                    exc,
                )
                ruleset = self._ensure_ruleset(
                    zone_id,
                    service_name,
                    lb_hostname,
                    path_prefix,
                    cache_ttl_seconds,
                    None,
                    primary_origin,
                    html_cache_policy,
                )
                firewall_ruleset = self._ensure_allowlist_firewall_ruleset(
                    zone_id,
                    service_name,
                    lb_hostname,
                    allowed_paths,
                )
                import ipaddress
                try:
                    ipaddress.ip_address(primary_origin)
                    record_type = "A"
                except ValueError:
                    record_type = "CNAME"
                dns_record = self._ensure_dns_record(zone_id, lb_hostname, primary_origin, record_type=record_type)
                return {
                    "provider": "cloudflare",
                    "operation": operation,
                    "status": "completed",
                    "mode": "fallback-primary-origin",
                    "zone_id": zone_id,
                    "service_name": service_name,
                    "primary_origin": primary_origin,
                    "secondary_origin": secondary_origin_value,
                    "hostname": lb_hostname,
                    "ruleset_id": ruleset.get("id"),
                    "firewall_ruleset_id": firewall_ruleset.get("id"),
                    "dns_record_id": dns_record.get("id"),
                    "warning": str(exc),
                }
        else:
            ruleset = self._ensure_ruleset(
                zone_id,
                service_name,
                lb_hostname,
                path_prefix,
                cache_ttl_seconds,
                None,
                primary_origin,
                html_cache_policy,
            )
            firewall_ruleset = self._ensure_allowlist_firewall_ruleset(
                zone_id,
                service_name,
                lb_hostname,
                allowed_paths,
            )
            # Create DNS record for hostname pointing to primary origin (A or CNAME)
            # If primary_origin is an IP, use A; else, use CNAME
            import ipaddress
            try:
                ipaddress.ip_address(primary_origin)
                record_type = "A"
            except ValueError:
                record_type = "CNAME"
            dns_record = self._ensure_dns_record(zone_id, lb_hostname, primary_origin, record_type=record_type)
            return {
                "provider": "cloudflare",
                "operation": operation,
                "status": "completed",
                "zone_id": zone_id,
                "service_name": service_name,
                "primary_origin": primary_origin,
                "hostname": lb_hostname,
                "ruleset_id": ruleset.get("id"),
                "firewall_ruleset_id": firewall_ruleset.get("id"),
                "dns_record_id": dns_record.get("id"),
                "mode": "single-origin",
            }

    def _decommission_request(self, zone_id: str, service_name: str, hostname: str) -> Dict[str, Any]:
        account_id = self._resolve_account_id(zone_id)
        zone_name = self._resolve_zone_name(zone_id)
        derived_service_name = self._derive_service_label(hostname, zone_name)

        service_candidates: List[str] = []
        for candidate in [service_name, derived_service_name]:
            normalized = _normalize_name(str(candidate))
            if normalized and normalized not in service_candidates:
                service_candidates.append(normalized)

        # 1. Remove rules from entrypoint rulesets (match by service aliases and hostname).
        ruleset_result = self._remove_service_rules_from_entrypoint(
            zone_id,
            service_candidates,
            hostname=hostname,
        )
        firewall_ruleset_result = self._remove_service_rules_from_entrypoint(
            zone_id,
            service_candidates,
            phase="http_request_firewall_custom",
            hostname=hostname,
        )

        # 2. Delete load balancer (uses hostname as name, not service_name-load-balancer).
        #    Must be deleted before pool deletion.
        load_balancer_result = self._delete_named_resource(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/load_balancers",
            hostname,
        )

        # 3. Delete origin pool and 4. health monitor for all known name variants.
        pool_results: List[Dict[str, Any]] = []
        monitor_results: List[Dict[str, Any]] = []
        for candidate in service_candidates:
            pool_results.append(
                self._delete_named_resource(
                    f"{CLOUDFLARE_API_BASE}/accounts/{account_id}/load_balancers/pools",
                    f"{candidate}-origin-pool",
                )
            )
            monitor_results.append(self._delete_health_monitor(account_id, candidate))

        # 5. Delete DNS records for hostname.
        deleted_dns_ids = self._delete_dns_records(zone_id, hostname)

        return {
            "provider": "cloudflare",
            "operation": "delete",
            "status": "completed",
            "zone_id": zone_id,
            "service_name": service_name,
            "hostname": hostname,
            "service_candidates": service_candidates,
            "deleted": {
                "ruleset": ruleset_result,
                "firewall_ruleset": firewall_ruleset_result,
                "load_balancer": load_balancer_result,
                "origin_pools": pool_results,
                "health_monitors": monitor_results,
                "dns_record_ids": deleted_dns_ids,
            },
        }

    def _remove_service_rules_from_entrypoint(
        self,
        zone_id: str,
        service_names: List[str],
        phase: str = "http_request_cache_settings",
        hostname: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Remove rules belonging to service aliases from the zone entrypoint ruleset."""
        entrypoint_url = f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets/phases/{phase}/entrypoint"
        response = requests.get(entrypoint_url, headers=self.headers, timeout=30)
        if not response.ok:
            logger.warning("Could not fetch entrypoint ruleset for cleanup: %s", response.text)
            return {"status": "not-found", "phase": phase}
        data = response.json()
        if not data.get("success") or not data.get("result"):
            return {"status": "not-found", "phase": phase}

        aliases = [_normalize_name(str(s)).lower() for s in service_names if str(s).strip()]
        host = str(hostname or "").strip().lower()
        entrypoint = data["result"]
        ruleset_id = entrypoint["id"]
        existing_rules = entrypoint.get("rules", [])
        kept_rules: List[Dict[str, Any]] = []
        removed_count = 0
        for rule in existing_rules:
            description = str(rule.get("description") or "").lower()
            expression = str(rule.get("expression") or "").lower()
            matched_alias = any(alias and alias in description for alias in aliases)
            matched_host = bool(host) and (host in description or host in expression)
            if matched_alias or matched_host:
                removed_count += 1
                continue
            kept_rules.append(rule)

        if removed_count == 0:
            logger.info("No rules found for %s in entrypoint ruleset", ",".join(aliases) or "unknown-service")
            return {"status": "no-matching-rules", "phase": phase, "service_aliases": aliases}

        response = requests.put(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets/{ruleset_id}",
            headers=self.headers,
            data=json.dumps({"rules": kept_rules}),
            timeout=30,
        )
        result = response.json()
        if not response.ok or not result.get("success"):
            logger.warning("Failed to remove rules from entrypoint ruleset: %s", result)
            return {"status": "failed", "error": str(result), "phase": phase, "service_aliases": aliases}

        logger.info(
            "Removed %d rules for aliases %s from entrypoint ruleset %s",
            removed_count,
            ",".join(aliases) or "unknown-service",
            ruleset_id,
        )
        return {
            "status": "deleted",
            "removed_rules": removed_count,
            "ruleset_id": ruleset_id,
            "phase": phase,
            "service_aliases": aliases,
        }

    def _resolve_zone_id(self, hint: Optional[str]) -> str:
        if not hint and not self.default_zone:
            raise ValueError("Cloudflare zone identifier is required via payload zone or CLOUDFLARE_ZONE_ID")

        # If caller provided an explicit zone ID, trust it.
        if hint and self._looks_like_zone_id(hint):
            return hint

        # If caller provided a zone name/hostname, resolve that first.
        if hint and not self._looks_like_zone_id(hint):
            # Try exact first, then hostname suffixes (e.g. assets.a.b.com -> a.b.com -> b.com).
            candidates = self._zone_name_candidates(hint)
            for candidate in candidates:
                response = requests.get(
                    f"{CLOUDFLARE_API_BASE}/zones",
                    headers=self.headers,
                    params={"name": candidate, "status": "active"},
                    timeout=30,
                )
                data = response.json()
                if response.ok and data.get("result"):
                    zone_id = data["result"][0]["id"]
                    logger.info("Resolved Cloudflare zone %s to %s (candidate=%s)", hint, zone_id, candidate)
                    return zone_id

        # Fallback to configured default zone ID.
        if self.default_zone and self._looks_like_zone_id(self.default_zone):
            return self.default_zone

        zone_name = hint or self.default_zone
        if not zone_name:
            raise ValueError("Cloudflare zone name or ID must be provided")

        response = requests.get(
            f"{CLOUDFLARE_API_BASE}/zones",
            headers=self.headers,
            params={"name": zone_name, "status": "active"},
            timeout=30,
        )
        data = response.json()
        if not response.ok or not data.get("result"):
            raise RuntimeError(f"Unable to resolve Cloudflare zone: {zone_name} {data}")

        zone_id = data["result"][0]["id"]
        logger.info("Resolved Cloudflare zone %s to %s", zone_name, zone_id)
        return zone_id

    def _looks_like_zone_id(self, value: str) -> bool:
        return bool(re.match(r"^[0-9a-fA-F-]{32,36}$", value))

    def _zone_name_candidates(self, hint: str) -> List[str]:
        cleaned = hint.strip().strip(".").lower()
        parts = [p for p in cleaned.split(".") if p]
        if len(parts) < 2:
            return [cleaned]
        candidates: List[str] = [cleaned]
        for i in range(1, len(parts) - 1):
            candidates.append(".".join(parts[i:]))
        # Deduplicate while preserving order.
        seen: set[str] = set()
        ordered: List[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                ordered.append(c)
        return ordered

    def _resolve_account_id(self, zone_id: str) -> str:
        if self.default_account:
            return self.default_account
        response = requests.get(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}",
            headers=self.headers,
            timeout=30,
        )
        payload = response.json()
        if not response.ok or not payload.get("success"):
            raise RuntimeError(f"Unable to resolve Cloudflare account from zone {zone_id}: {payload}")
        account = (payload.get("result") or {}).get("account") or {}
        account_id = account.get("id")
        if not account_id:
            raise RuntimeError(f"Cloudflare account id missing for zone {zone_id}")
        return account_id

    def _resolve_zone_name(self, zone_id: str) -> str:
        response = requests.get(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}",
            headers=self.headers,
            timeout=30,
        )
        payload = response.json()
        if not response.ok or not payload.get("success"):
            raise RuntimeError(f"Unable to resolve Cloudflare zone name from zone {zone_id}: {payload}")
        name = (payload.get("result") or {}).get("name")
        if not name:
            raise RuntimeError(f"Cloudflare zone name missing for zone {zone_id}")
        return str(name).strip().lower()

    def _hostname_for_zone(self, hostname: str, service_name: str, zone_name: str) -> str:
        h = hostname.strip().strip(".").lower()
        z = zone_name.strip().strip(".").lower()
        if h == z or h.endswith(f".{z}"):
            return h
        label = _normalize_name(service_name).lower()
        return f"{label}.{z}"

    def _derive_service_label(self, hostname: Optional[str], zone_name: str) -> str:
        """Extract the subdomain label from hostname as the service name.

        Example: assets129.millionmonkee.win with zone millionmonkee.win -> assets129
        """
        if not hostname:
            return _normalize_name("cloudflare")
        h = hostname.strip().strip(".").lower()
        z = zone_name.strip().strip(".").lower()
        # Strip zone suffix to get subdomain label
        if h.endswith(f".{z}"):
            label = h[: -(len(z) + 1)]
        elif "." in h:
            # Fallback: take first label (before first dot)
            label = h.split(".")[0]
        else:
            label = h
        return _normalize_name(label) if label else _normalize_name(h)

    def _ensure_origin_pool(self, account_id: str, service_name: str, primary_origin: str, secondary_origin: str) -> Dict[str, Any]:
        pool_name = f"{service_name}-origin-pool"
        endpoint = f"{CLOUDFLARE_API_BASE}/accounts/{account_id}/load_balancers/pools"
        existing = self._find_resource(endpoint, pool_name)
        if existing:
            logger.info("Using existing Cloudflare origin pool %s", pool_name)
            # Ensure health monitor is attached even if pool already exists
            if not existing.get("monitor"):
                monitor_id = self._ensure_health_monitor(account_id, service_name)
                if monitor_id:
                    pool_id = existing["id"]
                    patch_resp = requests.patch(
                        f"{endpoint}/{pool_id}",
                        headers=self.headers,
                        data=json.dumps({"monitor": monitor_id}),
                        timeout=30,
                    )
                    if patch_resp.ok:
                        logger.info("Attached health monitor %s to existing pool %s", monitor_id, pool_name)
                    else:
                        logger.warning("Failed to attach health monitor to pool: %s", patch_resp.text)
            return existing

        # Create health monitor first
        monitor_id = self._ensure_health_monitor(account_id, service_name)

        body = {
            "name": pool_name,
            "description": f"Origin pool for {service_name}",
            "check_regions": ["WNAM", "ENAM"],
            "origins": [
                {
                    "name": f"{service_name}-primary",
                    "address": primary_origin,
                    "enabled": True,
                    "weight": 1.0,
                },
                {
                    "name": f"{service_name}-secondary",
                    "address": secondary_origin,
                    "enabled": True,
                    "weight": 0.5,
                },
            ],
            "minimum_origins": 1,
            "enabled": True,
        }
        if monitor_id:
            body["monitor"] = monitor_id

        response = requests.post(
            endpoint,
            headers=self.headers,
            data=json.dumps(body),
            timeout=30,
        )
        result = response.json()
        if not response.ok or not result.get("success"):
            raise RuntimeError(f"Cloudflare origin pool create failed: {result}")
        return result["result"]

    def _ensure_health_monitor(self, account_id: str, service_name: str) -> Optional[str]:
        """Create or reuse an HTTP health monitor that checks /healthz."""
        monitor_name = f"{service_name}-health-monitor"
        endpoint = f"{CLOUDFLARE_API_BASE}/accounts/{account_id}/load_balancers/monitors"
        desired_body = {
            "type": "http",
            "description": monitor_name,
            "method": "GET",
            "path": "/healthz",
            "expected_codes": "200",
            "timeout": 5,
            "interval": 60,
            "retries": 2,
            "follow_redirects": True,
            "allow_insecure": True,
        }

        # Check for existing monitor
        response = requests.get(endpoint, headers=self.headers, timeout=30)
        if response.ok:
            for item in (response.json().get("result") or []):
                if item.get("description") == monitor_name:
                    logger.info("Using existing Cloudflare health monitor %s", monitor_name)
                    monitor_id = item["id"]
                    # Keep existing monitors aligned with desired health-check config.
                    update_resp = requests.put(
                        f"{endpoint}/{monitor_id}",
                        headers=self.headers,
                        data=json.dumps(desired_body),
                        timeout=30,
                    )
                    if not update_resp.ok:
                        logger.warning(
                            "Cloudflare health monitor update failed for %s (non-fatal): %s",
                            monitor_name,
                            update_resp.text,
                        )
                    return item["id"]

        response = requests.post(
            endpoint,
            headers=self.headers,
            data=json.dumps(desired_body),
            timeout=30,
        )
        result = response.json()
        if not response.ok or not result.get("success"):
            logger.warning("Cloudflare health monitor create failed (non-fatal): %s", result)
            return None
        monitor_id = result["result"]["id"]
        logger.info("Created Cloudflare health monitor %s (id=%s)", monitor_name, monitor_id)
        return monitor_id

    def _ensure_load_balancer(self, zone_id: str, service_name: str, hostname: str, pool_id: str) -> Dict[str, Any]:
        lb_name = hostname
        existing = self._find_resource(f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/load_balancers", lb_name)
        if existing:
            logger.info("Using existing Cloudflare load balancer %s", lb_name)
            return existing

        body = {
            "name": lb_name,
            "description": f"Load balancer for {service_name}",
            "fallback_pool": pool_id,
            "default_pools": [pool_id],
            "proxied": True,
            "ttl": 30,
            "enabled": True,
            "region_pools": {},
            "pop_pools": {},
            "country_pools": {},
            "steering_policy": "dynamic_latency",
            "session_affinity": "none",
            "session_affinity_ttl": 120,
        }

        response = requests.post(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/load_balancers",
            headers=self.headers,
            data=json.dumps(body),
            timeout=30,
        )
        result = response.json()
        if not response.ok or not result.get("success"):
            raise RuntimeError(f"Cloudflare load balancer create failed: {result}")
        return result["result"]

    def _ensure_ruleset(
        self,
        zone_id: str,
        service_name: str,
        hostname: str,
        path_prefix: str,
        cache_ttl_seconds: int,
        pool_id: Any,
        primary_origin: str,
        html_cache_policy: str = "inherit",
    ) -> Dict[str, Any]:
        ruleset_name = f"{service_name}-cache-ruleset"
        existing = self._find_resource(f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets", ruleset_name)
        if existing:
            logger.info("Using existing Cloudflare ruleset %s", ruleset_name)
            return existing

        # Determine path expression
        if path_prefix == "/":
            expression = f'(http.host eq "{hostname}")'
        else:
            normalized_prefix = "/" + path_prefix.strip("/")
            expression = f'(http.host eq "{hostname}" and starts_with(http.request.uri.path, "{normalized_prefix}"))'

        # Build rules for cache-settings only (route action is not valid in this phase).
        rules = []

        # Cache settings rule
        rules.append({
            "description": f"Static asset caching for {service_name}",
            "enabled": True,
            "expression": expression,
            "action": "set_cache_settings",
            "action_parameters": {
                "cache": True,
                "edge_ttl": {
                    "mode": "override_origin",
                    "default": cache_ttl_seconds
                },
                "browser_ttl": {
                    "mode": "override_origin",
                    "default": cache_ttl_seconds // 2
                },
            },
        })

        # Optional override to demonstrate policy variants in the same claim model.
        if str(html_cache_policy).lower() == "no-store":
            rules.append({
                "description": f"Disable HTML cache for {service_name}",
                "enabled": True,
                "expression": f'(http.host eq "{hostname}" and ends_with(lower(http.request.uri.path), ".html"))',
                "action": "set_cache_settings",
                "action_parameters": {
                    "cache": False,
                },
            })

        body = {
            "name": ruleset_name,
            "description": f"Cache and origin rules for {service_name}",
            "kind": "zone",
            "phase": "http_request_cache_settings",
            "rules": rules,
        }

        response = requests.post(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets",
            headers=self.headers,
            data=json.dumps(body),
            timeout=30,
        )
        result = response.json()
        if not response.ok or not result.get("success"):
            if self._is_ruleset_limit_error(result):
                logger.info("Zone phase limit reached; updating existing entrypoint ruleset instead")
                return self._update_entrypoint_ruleset(zone_id, service_name, rules)
            if self._is_auth_error(result):
                logger.warning("Cloudflare token lacks ruleset permissions; skipping ruleset create")
                return {
                    "id": "skipped-auth",
                    "name": ruleset_name,
                    "status": "skipped-auth",
                    "warning": str(result),
                }
            raise RuntimeError(f"Cloudflare ruleset create failed: {result}")
        return result["result"]

    def _ensure_allowlist_firewall_ruleset(
        self,
        zone_id: str,
        service_name: str,
        hostname: str,
        allowed_paths: List[str],
    ) -> Dict[str, Any]:
        ruleset_name = f"{service_name}-allowlist-firewall"
        existing = self._find_resource(f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets", ruleset_name)
        if existing:
            logger.info("Using existing Cloudflare firewall ruleset %s", ruleset_name)
            return existing

        allow_checks = [f'http.request.uri.path eq "{path}"' for path in allowed_paths]
        allow_expr = f"({' or '.join(allow_checks)})"
        block_expr = f'(http.host eq "{hostname}" and not {allow_expr})'
        rules = [
            {
                "description": f"Block non-allowlisted paths for {service_name}",
                "enabled": True,
                "expression": block_expr,
                "action": "block",
            }
        ]

        body = {
            "name": ruleset_name,
            "description": f"Firewall allowlist rules for {service_name}",
            "kind": "zone",
            "phase": "http_request_firewall_custom",
            "rules": rules,
        }

        response = requests.post(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets",
            headers=self.headers,
            data=json.dumps(body),
            timeout=30,
        )
        result = response.json()
        if not response.ok or not result.get("success"):
            if self._is_ruleset_limit_error(result):
                logger.info("Firewall phase limit reached; updating existing entrypoint firewall ruleset instead")
                return self._update_entrypoint_ruleset(
                    zone_id,
                    service_name,
                    rules,
                    phase="http_request_firewall_custom",
                )
            if self._is_auth_error(result):
                logger.warning("Cloudflare token lacks firewall ruleset permissions; skipping firewall ruleset create")
                return {
                    "id": "skipped-auth",
                    "name": ruleset_name,
                    "status": "skipped-auth",
                    "warning": str(result),
                }
            raise RuntimeError(f"Cloudflare firewall ruleset create failed: {result}")
        return result["result"]

    def _parse_allowed_paths(self, raw_allowed_paths: Any, path_prefix: str) -> List[str]:
        default_paths = ["/healthz", f"/{str(path_prefix or '/').strip('/')}/mdemo.html".replace("//", "/")]
        if not raw_allowed_paths:
            return default_paths

        paths: List[str] = []
        if isinstance(raw_allowed_paths, list):
            paths = [str(p).strip() for p in raw_allowed_paths if str(p).strip()]
        elif isinstance(raw_allowed_paths, str):
            text = raw_allowed_paths.strip()
            if not text:
                return default_paths
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    paths = [str(p).strip() for p in parsed if str(p).strip()]
                else:
                    paths = [text]
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, list):
                        paths = [str(p).strip() for p in parsed if str(p).strip()]
                    else:
                        paths = [p.strip() for p in text.split(",") if p.strip()]
                except (ValueError, SyntaxError):
                    paths = [p.strip() for p in text.split(",") if p.strip()]
        else:
            paths = [str(raw_allowed_paths).strip()]

        normalized = []
        for path in paths:
            p = path if path.startswith("/") else f"/{path}"
            normalized.append(p)
        return normalized or default_paths

    def _update_entrypoint_ruleset(
        self,
        zone_id: str,
        service_name: str,
        new_rules: List[Dict[str, Any]],
        phase: str = "http_request_cache_settings",
    ) -> Dict[str, Any]:
        """Update the existing zone entrypoint ruleset for a given phase
        by appending our rules (identified by service_name in description) to avoid duplicates."""
        entrypoint_url = f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets/phases/{phase}/entrypoint"

        response = requests.get(entrypoint_url, headers=self.headers, timeout=30)
        if not response.ok:
            raise RuntimeError(
                f"Cloudflare entrypoint ruleset fetch failed for phase {phase}: {response.text}"
            )
        data = response.json()
        if not data.get("success"):
            raise RuntimeError(f"Cloudflare entrypoint ruleset fetch error: {data}")

        entrypoint = data["result"]
        ruleset_id = entrypoint["id"]
        existing_rules: List[Dict[str, Any]] = entrypoint.get("rules", [])

        # Remove any previous rules for this service_name (matched by description containing service_name)
        kept_rules = [
            r for r in existing_rules
            if service_name not in (r.get("description") or "")
        ]

        # Append our new rules
        merged_rules = kept_rules + new_rules

        update_body = {
            "rules": merged_rules,
        }

        response = requests.put(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/rulesets/{ruleset_id}",
            headers=self.headers,
            data=json.dumps(update_body),
            timeout=30,
        )
        result = response.json()
        if not response.ok or not result.get("success"):
            if self._is_auth_error(result):
                logger.warning("Cloudflare token lacks ruleset update permissions; skipping")
                return {
                    "id": "skipped-auth",
                    "name": f"{service_name}-cache-ruleset",
                    "status": "skipped-auth",
                    "warning": str(result),
                }
            raise RuntimeError(f"Cloudflare entrypoint ruleset update failed: {result}")

        logger.info(
            "Updated entrypoint ruleset %s with %d rules for %s",
            ruleset_id,
            len(new_rules),
            service_name,
        )
        return result["result"]

    def _is_auth_error(self, payload: Dict[str, Any]) -> bool:
        for err in payload.get("errors", []):
            code = str(err.get("code", ""))
            if code in {"10000", "9109"}:
                return True
        return False

    def _is_ruleset_limit_error(self, payload: Dict[str, Any]) -> bool:
        for err in payload.get("errors", []):
            if str(err.get("code", "")) == "20217":
                return True
        return False

    def _is_dns_already_exists_error(self, payload: Dict[str, Any]) -> bool:
        for err in payload.get("errors", []):
            if str(err.get("code", "")) == "81053":
                return True
        return False

    def _request_json_with_rate_limit(
        self,
        method: str,
        url: str,
        *,
        max_attempts: int = 4,
        **kwargs: Any,
    ) -> tuple[requests.Response, Dict[str, Any]]:
        attempt = 0
        while True:
            attempt += 1
            response = requests.request(method, url, headers=self.headers, **kwargs)
            payload: Dict[str, Any]
            try:
                payload = response.json()
            except ValueError:
                payload = {"success": False, "errors": [{"code": "non_json", "message": response.text}]}

            if not self._is_rate_limited(response, payload) or attempt >= max_attempts:
                return response, payload

            wait_seconds = self._retry_after_seconds(response, attempt)
            logger.warning(
                "Cloudflare rate limited on %s %s (attempt %s/%s). Retrying in %ss",
                method.upper(),
                url,
                attempt,
                max_attempts,
                wait_seconds,
            )
            time.sleep(wait_seconds)

    def _is_rate_limited(self, response: requests.Response, payload: Dict[str, Any]) -> bool:
        if response.status_code == 429:
            return True
        for err in payload.get("errors", []):
            if str(err.get("code", "")) == "10429":
                return True
        return False

    def _retry_after_seconds(self, response: requests.Response, attempt: int) -> int:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                pass
        # Simple backoff if header is missing.
        return min(30, 2 ** (attempt - 1))

    def _find_resource(self, endpoint: str, name: str) -> Optional[Dict[str, Any]]:
        response = requests.get(endpoint, headers=self.headers, timeout=30)
        if not response.ok:
            logger.warning("Cloudflare search failed for %s: %s", endpoint, response.text)
            return None
        payload = response.json()
        for item in payload.get("result", []):
            if item.get("name") == name:
                return item
        return None

    def _delete_named_resource(self, endpoint: str, name: str) -> Dict[str, Any]:
        existing = self._find_resource(endpoint, name)
        if not existing:
            return {"name": name, "status": "not-found"}

        resource_id = existing.get("id")
        if not resource_id:
            return {"name": name, "status": "missing-id"}

        response = requests.delete(f"{endpoint}/{resource_id}", headers=self.headers, timeout=30)
        payload = response.json() if response.content else {}
        if response.ok and payload.get("success", True):
            return {"name": name, "id": resource_id, "status": "deleted"}
        raise RuntimeError(f"Cloudflare delete failed for {name}: {payload}")

    def _delete_health_monitor(self, account_id: str, service_name: str) -> Dict[str, Any]:
        """Delete the health monitor associated with this service."""
        monitor_name = f"{service_name}-health-monitor"
        endpoint = f"{CLOUDFLARE_API_BASE}/accounts/{account_id}/load_balancers/monitors"
        response = requests.get(endpoint, headers=self.headers, timeout=30)
        if not response.ok:
            return {"name": monitor_name, "status": "list-failed"}
        for item in (response.json().get("result") or []):
            if item.get("description") == monitor_name:
                del_resp = requests.delete(f"{endpoint}/{item['id']}", headers=self.headers, timeout=30)
                if del_resp.ok:
                    return {"name": monitor_name, "id": item["id"], "status": "deleted"}
                return {"name": monitor_name, "status": "delete-failed"}
        return {"name": monitor_name, "status": "not-found"}

    def _delete_dns_records(self, zone_id: str, hostname: str) -> List[str]:
        response = requests.get(
            f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records",
            headers=self.headers,
            params={"name": hostname},
            timeout=30,
        )
        payload = response.json()
        if not response.ok or not payload.get("success", False):
            raise RuntimeError(f"Cloudflare DNS record list failed: {payload}")

        deleted_ids: List[str] = []
        for record in payload.get("result", []):
            record_id = record.get("id")
            if not record_id:
                continue
            delete_resp = requests.delete(
                f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records/{record_id}",
                headers=self.headers,
                timeout=30,
            )
            delete_payload = delete_resp.json() if delete_resp.content else {}
            if not delete_resp.ok or not delete_payload.get("success", True):
                raise RuntimeError(f"Cloudflare DNS delete failed for {record_id}: {delete_payload}")
            deleted_ids.append(record_id)
        return deleted_ids
