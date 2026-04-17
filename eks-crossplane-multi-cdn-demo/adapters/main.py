#!/usr/bin/env python3
import json
import logging
import os
import time
from pathlib import Path

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

from cloudflare_adapter import CloudflareNativeAdapter
from terraform_adapter import TerraformModuleAdapter
from akamai_adapter import AkamaiAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WATCH_NAMESPACE = os.getenv("ADAPTER_WATCH_NAMESPACE", "crossplane-system")
LABEL_SELECTOR = os.getenv("ADAPTER_LABEL_SELECTOR", "milionmonkee.win/adapter=true")
STATUS_SUFFIX = os.getenv("ADAPTER_STATUS_SUFFIX", "-status")
MODULE_ROOT = Path(os.getenv("ADAPTER_MODULE_ROOT", "/app"))


class AdapterController:
    def __init__(self):
        self.processed = set()
        self.kube_client = self._create_kube_client()
        self.core_api = client.CoreV1Api(self.kube_client)

    def _create_kube_client(self):
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except Exception:
            config.load_kube_config()
            logger.info("Loaded local kubeconfig")
        return client.ApiClient()

    def run(self):
        logger.info("Starting adapter controller")
        self._process_existing_requests()
        watcher = watch.Watch()
        while True:
            try:
                for event in watcher.stream(
                    self.core_api.list_namespaced_config_map,
                    namespace=WATCH_NAMESPACE,
                    label_selector=LABEL_SELECTOR,
                    timeout_seconds=0,
                ):
                    self._handle_event(event)
            except Exception as exc:
                logger.exception("Watch stream failed, retrying in 10 seconds: %s", exc)
                time.sleep(10)

    def _process_existing_requests(self):
        configmaps = self.core_api.list_namespaced_config_map(
            namespace=WATCH_NAMESPACE,
            label_selector=LABEL_SELECTOR,
        ).items
        for cm in configmaps:
            self._process_request(cm)

    def _handle_event(self, event):
        event_type = event.get("type")
        cm = event.get("object")
        if not cm or event_type == "DELETED":
            return
        self._process_request(cm)

    def _process_request(self, cm):
        request_uid = cm.metadata.uid
        request_version = cm.metadata.resource_version
        key = f"{request_uid}:{request_version}"
        if key in self.processed:
            return

        logger.info("Processing adapter request: %s", cm.metadata.name)
        try:
            payload = self._sanitize_optional_path_keys(cm)
            result = self._execute_adapter(payload)
            self._publish_status(cm, "completed", result)
            logger.info("Adapter request completed: %s", cm.metadata.name)
        except Exception as exc:
            logger.exception("Adapter request failed: %s", cm.metadata.name)
            self._publish_status(cm, "failed", {"error": str(exc)})
        finally:
            self.processed.add(key)

    def _execute_adapter(self, data):
        provider = (data.get("provider") or "").strip().lower()
        adapter_type = (data.get("adapterType") or "").strip().lower()

        if adapter_type == "native-api" and provider == "cloudflare":
            adapter = CloudflareNativeAdapter()
            return adapter.execute_request(data)

        if adapter_type == "native-api" and provider == "akamai":
            adapter = AkamaiAdapter()
            return adapter.execute_request(data)

        if adapter_type == "terraform-module":
            adapter = TerraformModuleAdapter(module_root=MODULE_ROOT)
            return adapter.execute_request(data)

        raise ValueError(f"Unsupported adapter type/provider: {adapter_type}/{provider}")

    def _sanitize_optional_path_keys(self, cm):
        data = dict(cm.data or {})
        annotations = cm.metadata.annotations or {}
        last_applied = annotations.get("kubectl.kubernetes.io/last-applied-configuration")
        if not last_applied:
            return data

        try:
            applied_obj = json.loads(last_applied)
            applied_data = applied_obj.get("data", {}) or {}
        except Exception:
            return data

        for key in ("allowedPath3", "allowedPath4", "allowedPath5"):
            if key in data and key not in applied_data:
                logger.info("Dropping stale key %s from request %s", key, cm.metadata.name)
                data.pop(key, None)
        return data

    def _publish_status(self, cm, status, result):
        status_name = f"{cm.metadata.name}{STATUS_SUFFIX}"
        status_configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name=status_name,
                namespace=cm.metadata.namespace,
                labels={"milionmonkee.win/adapter-status": "true"},
            ),
            data={
                "request_name": cm.metadata.name,
                "status": status,
                "result": json.dumps(result, indent=2),
            },
        )

        try:
            existing = self.core_api.read_namespaced_config_map(name=status_name, namespace=cm.metadata.namespace)
            self.core_api.replace_namespaced_config_map(name=status_name, namespace=cm.metadata.namespace, body=status_configmap)
            logger.info("Updated status ConfigMap: %s", status_name)
        except ApiException as exc:
            if exc.status == 404:
                self.core_api.create_namespaced_config_map(namespace=cm.metadata.namespace, body=status_configmap)
                logger.info("Created status ConfigMap: %s", status_name)
            else:
                raise


if __name__ == "__main__":
    controller = AdapterController()
    controller.run()
