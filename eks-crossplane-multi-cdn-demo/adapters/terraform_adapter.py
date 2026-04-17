#!/usr/bin/env python3
import ast
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from akamai.edgegrid import EdgeGridAuth

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

TERRAFORM_VERSION = os.getenv('TERRAFORM_VERSION', '1.7.8')
TERRAFORM_BINARY = os.getenv('TERRAFORM_BINARY', 'terraform')


class TerraformModuleAdapter:
    def __init__(self, module_root: Optional[Path] = None):
        self.module_root = Path(module_root or '/app').resolve()
        self.workspace_base = Path(os.getenv('TERRAFORM_WORKSPACE_BASE', '/tmp/terraform-adapter')).resolve()
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    def execute_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        operation = str(payload.get('operation', 'apply')).strip().lower()
        tfvars_text = payload.get('tfvars') or payload.get('tfvars.json')
        if not tfvars_text:
            raise ValueError('Terraform adapter requires tfvars data')

        tfvars = self._normalize_tfvars(self._parse_tfvars(tfvars_text))
        raw_allowed_paths = payload.get('allowedPaths') or payload.get('allowed_paths')
        if raw_allowed_paths:
            parsed_paths = self._parse_allowed_paths(raw_allowed_paths)
            for key in ('allowedPath3', 'allowedPath4', 'allowedPath5'):
                extra = payload.get(key)
                if not extra:
                    continue
                p = str(extra).strip()
                if not p:
                    continue
                if not p.startswith('/'):
                    p = f'/{p}'
                if p not in parsed_paths:
                    parsed_paths.append(p)
            tfvars['allowed_paths'] = parsed_paths
        module_path = payload.get('modulePath') or payload.get('module_path') or './terraform/akamai_static_assets_module'
        module_source = self._resolve_module_source(module_path)

        service_name = tfvars.get('service_name') or tfvars.get('serviceName')
        if not service_name:
            raise ValueError('tfvars must contain service_name for workspace naming')

        workspace = self.workspace_base / _normalize_name(service_name)
        workspace.mkdir(parents=True, exist_ok=True)

        self._prepare_workspace(workspace, module_source, tfvars)
        self._install_terraform_if_needed()

        if operation in {'delete', 'destroy', 'decommission'}:
            execution_result = self._run_terraform_destroy(workspace)
        else:
            execution_result = self._run_terraform(workspace)
            activation = self._maybe_submit_async_akamai_activation(tfvars)
            if activation:
                execution_result['activation'] = activation

        return {
            'provider': 'akamai',
            'operation': operation,
            'status': execution_result.get('status', 'unknown'),
            'workspace': str(workspace),
            'outputs': execution_result.get('outputs', {}),
            'plan': execution_result.get('plan', ''),
            'activation': execution_result.get('activation', {}),
        }

    def _parse_tfvars(self, tfvars_text: str) -> Dict[str, Any]:
        try:
            return json.loads(tfvars_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Unable to parse tfvars JSON: {exc}')

    def _normalize_tfvars(self, tfvars: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(tfvars)
        # Stamp every run for Akamai property comment traceability.
        normalized['run_timestamp'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        for key in ('primary_origin', 'secondary_origin'):
            value = normalized.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                trimmed = value.strip()
                if not trimmed:
                    raise ValueError(f'{key} is required for Akamai Terraform execution')
                if not re.match(r'^https?://', trimmed):
                    normalized[key] = f'http://{trimmed}'
                elif trimmed.startswith('https://'):
                    normalized[key] = f"http://{trimmed[len('https://'):]}"
        raw_paths = normalized.get('allowed_paths')
        if raw_paths:
            normalized['allowed_paths'] = self._parse_allowed_paths(raw_paths)
        return normalized

    def _parse_allowed_paths(self, raw_allowed_paths: Any) -> list[str]:
        paths: list[str] = []
        if isinstance(raw_allowed_paths, list):
            paths = [str(p).strip() for p in raw_allowed_paths if str(p).strip()]
        elif isinstance(raw_allowed_paths, str):
            text = raw_allowed_paths.strip()
            if text:
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
                            paths = [p.strip() for p in text.split(',') if p.strip()]
                    except (ValueError, SyntaxError):
                        paths = [p.strip() for p in text.split(',') if p.strip()]
        elif raw_allowed_paths is not None:
            paths = [str(raw_allowed_paths).strip()]

        normalized: list[str] = []
        for path in paths:
            normalized.append(path if path.startswith('/') else f'/{path}')
        return normalized or ['/healthz', '/static/mdemo.html']

    def _resolve_module_source(self, module_path: str) -> Path:
        candidate = Path(module_path)
        if not candidate.is_absolute():
            candidate = self.module_root / module_path.lstrip('./')
        if not candidate.exists():
            raise FileNotFoundError(f'Module source not found: {candidate}')
        return candidate.resolve()

    def _prepare_workspace(self, workspace: Path, module_source: Path, tfvars: Dict[str, Any]) -> None:
        module_dest = workspace / module_source.name
        if module_dest.exists():
            shutil.rmtree(module_dest)
        shutil.copytree(module_source, module_dest)
        self._write_tfvars(workspace, tfvars)
        self._write_root_module(workspace, module_source.name, tfvars)

    def _write_tfvars(self, workspace: Path, tfvars: Dict[str, Any]) -> None:
        tfvars_path = workspace / 'terraform.tfvars.json'
        tfvars_path.write_text(json.dumps(tfvars, indent=2))
        logger.info('Wrote Terraform variable file: %s', tfvars_path)

    def _write_root_module(self, workspace: Path, module_name: str, tfvars: Dict[str, Any]) -> None:
        variable_declarations = []
        for key in sorted(tfvars.keys()):
            var_type = self._infer_variable_type(tfvars[key])
            variable_declarations.append(
                f"variable \"{key}\" {{\n  type = {var_type}\n}}\n"
            )

        main_tf = [
            'terraform {',
            '  required_version = ">= 1.3.0"',
            '}',
            '',
            '\n'.join(variable_declarations),
            '',
            'module "akamai_static_assets_module" {',
            f'  source = "./{module_name}"',
        ]

        for key in sorted(tfvars.keys()):
            main_tf.append(f'  {key} = var.{key}')

        main_tf.append('}')
        main_path = workspace / 'main.tf'
        main_path.write_text('\n'.join(main_tf).strip() + '\n')
        logger.info('Wrote Terraform root module: %s', main_path)

    def _infer_variable_type(self, value: Any) -> str:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int) and not isinstance(value, bool):
            return "number"
        if isinstance(value, float):
            return "number"
        if isinstance(value, list):
            element_type = "string"
            if value and any(not isinstance(item, str) for item in value):
                element_type = "any"
            return f"list({element_type})"
        if isinstance(value, dict):
            return "map(any)"
        return "string"

    def _install_terraform_if_needed(self) -> None:
        if shutil.which(TERRAFORM_BINARY):
            logger.info('Terraform binary already installed: %s', TERRAFORM_BINARY)
            return

        download_url = f'https://releases.hashicorp.com/terraform/{TERRAFORM_VERSION}/terraform_{TERRAFORM_VERSION}_linux_amd64.zip'
        destination = Path(tempfile.mkdtemp()) / 'terraform.zip'
        logger.info('Downloading Terraform from %s', download_url)
        import urllib.request

        urllib.request.urlretrieve(download_url, str(destination))
        extract_dir = destination.parent
        shutil.unpack_archive(str(destination), str(extract_dir))
        terraform_bin = extract_dir / 'terraform'
        target = Path('/usr/local/bin/terraform')
        shutil.move(str(terraform_bin), str(target))
        target.chmod(0o755)
        logger.info('Installed Terraform to %s', target)

    def _run_terraform(self, workspace: Path) -> Dict[str, Any]:
        env = os.environ.copy()
        env['TF_IN_AUTOMATION'] = '1'
        results = {'status': 'pending', 'outputs': {}, 'plan': ''}
        retried_with_import = False

        # Best-effort cleanup for prior failed runs that tainted resources.
        self._run_best_effort(
            workspace,
            env,
            ['untaint', 'module.akamai_static_assets_module.akamai_property.cdn'],
        )

        for command in [
            ['init', '-upgrade'],
            ['validate'],
            ['plan', '-out=tfplan', '-input=false'],
            ['apply', '-auto-approve', '-input=false'],
        ]:
            logger.info('Running terraform %s', ' '.join(command))
            result = subprocess.run(
                [TERRAFORM_BINARY] + command,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            if result.returncode != 0:
                if (
                    command[0] == 'apply'
                    and not retried_with_import
                    and self._is_akamai_property_name_in_use(result.stderr)
                ):
                    logger.warning('Akamai property already exists; attempting import-and-retry flow')
                    imported = self._import_existing_akamai_property(workspace, env)
                    if imported:
                        retried_with_import = True
                        retry = subprocess.run(
                            [TERRAFORM_BINARY, 'apply', '-auto-approve', '-input=false'],
                            cwd=workspace,
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=900,
                        )
                        if retry.returncode == 0:
                            continue
                        result = retry
                raise RuntimeError(
                    'Terraform command failed: %s\nSTDOUT:%s\nSTDERR:%s' % (
                        ' '.join(command), result.stdout, result.stderr
                    )
                )
            if command[0] == 'plan':
                results['plan'] = result.stdout

        outputs = subprocess.run(
            [TERRAFORM_BINARY, 'output', '-json'],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if outputs.returncode == 0:
            try:
                results['outputs'] = json.loads(outputs.stdout)
            except json.JSONDecodeError:
                results['outputs'] = {'raw_output': outputs.stdout}

        results['status'] = 'completed'
        return results

    def _is_akamai_property_name_in_use(self, stderr: str) -> bool:
        lowered = (stderr or '').lower()
        return 'property name already in use' in lowered or 'property/name-in-use' in lowered

    def _import_existing_akamai_property(self, workspace: Path, env: Dict[str, str]) -> bool:
        tfvars_path = workspace / 'terraform.tfvars.json'
        if not tfvars_path.exists():
            logger.warning('terraform.tfvars.json not found; cannot import existing Akamai property')
            return False

        tfvars = json.loads(tfvars_path.read_text())
        contract_id = str(tfvars.get('contract_id') or '').strip()
        group_id = str(tfvars.get('group_id') or '').strip()
        hostname = str(tfvars.get('hostname') or '').strip().lower()
        if not contract_id or not group_id or not hostname:
            logger.warning('Missing contract_id/group_id/hostname in tfvars; cannot import existing Akamai property')
            return False

        property_name = self._derive_property_name(hostname)
        property_id = self._lookup_akamai_property_id(contract_id, group_id, property_name)
        if not property_id:
            logger.warning('Could not resolve Akamai property id for %s', property_name)
            return False

        resource_addr = 'module.akamai_static_assets_module.akamai_property.cdn'
        candidates = [
            property_id,
            f'{property_id},{contract_id},{group_id}',
            f'{property_id}:{contract_id}:{group_id}',
            f'{contract_id}:{group_id}:{property_id}',
        ]
        for import_id in candidates:
            logger.info('Trying terraform import %s %s', resource_addr, import_id)
            proc = subprocess.run(
                [TERRAFORM_BINARY, 'import', resource_addr, import_id],
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode == 0:
                logger.info('Imported existing Akamai property %s as %s', property_id, resource_addr)
                return True
            logger.info('Import attempt failed for id %s: %s', import_id, proc.stderr.strip())

        logger.warning('All import attempts failed for existing Akamai property %s', property_id)
        return False

    def _derive_property_name(self, hostname: str) -> str:
        safe = hostname.replace('.', '-').replace('*', 'wildcard')
        return f'{safe}_pm'

    def _lookup_akamai_property_id(self, contract_id: str, group_id: str, property_name: str) -> Optional[str]:
        host = os.getenv('AKAMAI_HOST', '').strip()
        client_token = os.getenv('AKAMAI_CLIENT_TOKEN', '').strip()
        client_secret = os.getenv('AKAMAI_CLIENT_SECRET', '').strip()
        access_token = os.getenv('AKAMAI_ACCESS_TOKEN', '').strip()
        if not host or not client_token or not client_secret or not access_token:
            logger.warning('Missing Akamai API credentials for property lookup')
            return None

        base_url = f'https://{host}' if not host.startswith('http') else host
        endpoint = f'{base_url}/papi/v1/properties'
        session = requests.Session()
        session.auth = EdgeGridAuth(
            client_token=client_token,
            client_secret=client_secret,
            access_token=access_token,
        )
        params = {
            'contractId': contract_id,
            'groupId': group_id,
            'propertyName': property_name,
        }
        response = session.get(endpoint, params=params, timeout=30)
        if response.status_code >= 300:
            logger.warning('Akamai property lookup failed: %s %s', response.status_code, response.text)
            return None
        payload = response.json()
        items = (
            payload.get('properties', {}).get('items')
            or payload.get('properties', {}).get('property')
            or []
        )
        for item in items:
            name = str(item.get('propertyName') or item.get('name') or '').strip()
            if name == property_name:
                pid = str(item.get('propertyId') or item.get('id') or '').strip()
                if pid:
                    logger.info('Resolved existing Akamai property %s to id %s', property_name, pid)
                    return pid
        logger.warning('Akamai property %s not found in lookup response', property_name)
        return None

    def _run_best_effort(self, workspace: Path, env: Dict[str, str], command: list[str]) -> None:
        result = subprocess.run(
            [TERRAFORM_BINARY] + command,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.info('Ignoring non-fatal terraform %s: %s', ' '.join(command), result.stderr.strip())

    def _cleanup_workspace(self, workspace: Path) -> None:
        if not workspace.exists():
            return
        try:
            shutil.rmtree(workspace)
            logger.info('Removed Terraform workspace: %s', workspace)
        except Exception as exc:
            logger.warning('Failed to remove Terraform workspace %s: %s', workspace, exc)

    def _resolve_akamai_network(self, tfvars: Dict[str, Any]) -> str:
        """Return the claim-provided Akamai network with safe fallback."""
        requested = str(tfvars.get('network') or 'STAGING').strip().upper()
        if requested not in {'STAGING', 'PRODUCTION'}:
            logger.warning(
                'Invalid Akamai network %s in request; defaulting to STAGING',
                requested or '<empty>',
            )
            return 'STAGING'
        return requested

    def _api_based_akamai_cleanup(self, workspace: Path) -> Dict[str, Any]:
        """Fallback cleanup via Akamai PAPI when Terraform state is missing.

        Looks up the property by derived name, deactivates it on requested network,
        waits for deactivation, then deletes the property. CP codes and edge
        hostnames are left in place (Akamai does not allow deleting shared
        edge hostnames and cp codes may be referenced elsewhere).
        """
        result: Dict[str, Any] = {'status': 'no-state'}
        tfvars_path = workspace / 'terraform.tfvars.json'
        if not tfvars_path.exists():
            logger.info('No terraform.tfvars.json for API cleanup; nothing to clean')
            return result

        try:
            tfvars = json.loads(tfvars_path.read_text())
        except json.JSONDecodeError:
            logger.warning('Cannot parse terraform.tfvars.json for API cleanup')
            return result

        contract_id = str(tfvars.get('contract_id') or '').strip()
        group_id = str(tfvars.get('group_id') or '').strip()
        hostname = str(tfvars.get('hostname') or '').strip().lower()
        owner_team = str(tfvars.get('owner_team') or 'platform').strip().lower()
        if not contract_id or not group_id or not hostname:
            logger.info('Missing contract/group/hostname for API cleanup')
            return result

        property_name = self._derive_property_name(hostname)
        property_id = self._lookup_akamai_property_id(contract_id, group_id, property_name)
        if not property_id:
            logger.info('Akamai property %s not found; nothing to clean via API', property_name)
            result['status'] = 'not-found'
            return result

        try:
            session, base_url = self._akamai_api_session()
        except ValueError as exc:
            logger.warning('Akamai API unavailable for cleanup: %s', exc)
            result['status'] = 'api-unavailable'
            result['error'] = str(exc)
            return result

        # Deactivate on claim-requested network.
        network = self._resolve_akamai_network(tfvars)
        for network in [network]:
            activation = self._lookup_latest_or_pending_activation(
                session, base_url, property_id, contract_id, group_id, network
            )
            if not activation:
                continue
            version = activation.get('property_version')
            if isinstance(version, str) and version.isdigit():
                version = int(version)
            if not isinstance(version, int):
                continue
            deact = self._submit_akamai_deactivation(
                session=session, base_url=base_url, property_id=property_id,
                contract_id=contract_id, group_id=group_id, network=network,
                property_version=version, owner_team=owner_team,
            )
            logger.info('API cleanup deactivation %s/%s: %s', property_id, network, deact)

        self._wait_for_akamai_property_inactive(
            session=session, base_url=base_url, property_id=property_id,
            contract_id=contract_id, group_id=group_id,
            timeout_seconds=720, poll_interval_seconds=20,
            networks=[network],
        )

        # Delete the property via PAPI
        delete_url = f'{base_url}/papi/v1/properties/{property_id}'
        try:
            resp = session.delete(
                delete_url,
                params={'contractId': contract_id, 'groupId': group_id},
                timeout=30,
            )
            if resp.status_code < 300:
                logger.info('Deleted Akamai property %s via API', property_id)
                result['status'] = 'api-destroyed'
                result['property_id'] = property_id
            elif 'cant-delete-active' in (resp.text or '').lower():
                logger.warning('Property %s still active after deactivation wait; API delete blocked', property_id)
                result['status'] = 'still-active'
                result['error'] = resp.text
            else:
                logger.warning('Akamai property delete failed: %s %s', resp.status_code, resp.text)
                result['status'] = 'api-delete-failed'
                result['error'] = resp.text
        except Exception as exc:
            logger.exception('Akamai property delete request failed: %s', exc)
            result['status'] = 'api-delete-error'
            result['error'] = str(exc)

        return result

    def _run_terraform_destroy(self, workspace: Path) -> Dict[str, Any]:
        env = os.environ.copy()
        env['TF_IN_AUTOMATION'] = '1'
        results = {'status': 'pending', 'outputs': {}, 'plan': ''}

        # No local state means nothing to destroy from this runtime instance.
        # Fall back to API-based cleanup so resources are not orphaned.
        if not (workspace / 'terraform.tfstate').exists():
            logger.info('No terraform.tfstate found in workspace %s; attempting API-based cleanup', workspace)
            api_result = self._api_based_akamai_cleanup(workspace)
            results['status'] = api_result.get('status', 'no-state')
            results['api_cleanup'] = api_result
            self._cleanup_workspace(workspace)
            return results

        # Akamai refuses property deletion while active. Best effort:
        # submit deactivation on claim-requested network and wait before destroy.
        self._pre_destroy_deactivate_akamai_property(workspace)

        for command in [
            ['init', '-upgrade'],
            ['destroy', '-auto-approve', '-input=false'],
        ]:
            logger.info('Running terraform %s', ' '.join(command))
            result = subprocess.run(
                [TERRAFORM_BINARY] + command,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            if result.returncode != 0:
                if command[0] == 'destroy' and self._is_akamai_property_active_delete_error(result.stderr):
                    raise RuntimeError(
                        'Terraform destroy blocked by active Akamai property. '
                        'Deactivation was requested but is still ACTIVE/PENDING in Akamai. '
                        'Wait for deactivation to complete, then retry.\n'
                        'Terraform command failed: %s\nSTDOUT:%s\nSTDERR:%s' % (
                            ' '.join(command), result.stdout, result.stderr
                        )
                    )
                raise RuntimeError(
                    'Terraform command failed: %s\nSTDOUT:%s\nSTDERR:%s' % (
                        ' '.join(command), result.stdout, result.stderr
                    )
                )
            if command[0] == 'destroy':
                results['plan'] = result.stdout

        results['status'] = 'destroyed'
        self._cleanup_workspace(workspace)
        return results

    def _is_akamai_property_active_delete_error(self, stderr: str) -> bool:
        lowered = (stderr or '').lower()
        return 'cant-delete-active' in lowered or 'cannot delete active property' in lowered

    def _pre_destroy_deactivate_akamai_property(self, workspace: Path) -> None:
        tfvars_path = workspace / 'terraform.tfvars.json'
        if not tfvars_path.exists():
            logger.info('No terraform.tfvars.json in %s; skipping Akamai pre-destroy deactivation', workspace)
            return

        try:
            tfvars = json.loads(tfvars_path.read_text())
        except json.JSONDecodeError:
            logger.warning('Unable to parse terraform.tfvars.json for pre-destroy deactivation; continuing')
            return

        contract_id = str(tfvars.get('contract_id') or '').strip()
        group_id = str(tfvars.get('group_id') or '').strip()
        hostname = str(tfvars.get('hostname') or '').strip().lower()
        owner_team = str(tfvars.get('owner_team') or 'platform').strip().lower()
        if not contract_id or not group_id or not hostname:
            logger.info('Missing contract/group/hostname for pre-destroy deactivation; continuing')
            return

        property_name = self._derive_property_name(hostname)
        property_id = self._lookup_akamai_property_id(contract_id, group_id, property_name)
        if not property_id:
            logger.info('Akamai property not found for %s during pre-destroy deactivation; continuing', property_name)
            return

        try:
            session, base_url = self._akamai_api_session()
        except ValueError as exc:
            logger.warning('Akamai API session unavailable for pre-destroy deactivation: %s', exc)
            return

        network = self._resolve_akamai_network(tfvars)
        for network in [network]:
            activation = self._lookup_latest_or_pending_activation(
                session, base_url, property_id, contract_id, group_id, network
            )
            if not activation:
                continue
            version = activation.get('property_version')
            if isinstance(version, str) and version.isdigit():
                version = int(version)
            if not isinstance(version, int):
                logger.warning('Cannot determine active property version for %s on %s', property_id, network)
                continue

            deactivate_result = self._submit_akamai_deactivation(
                session=session,
                base_url=base_url,
                property_id=property_id,
                contract_id=contract_id,
                group_id=group_id,
                network=network,
                property_version=version,
                owner_team=owner_team,
            )
            logger.info('Akamai pre-destroy deactivation for %s/%s: %s', property_id, network, deactivate_result)

        self._wait_for_akamai_property_inactive(
            session=session,
            base_url=base_url,
            property_id=property_id,
            contract_id=contract_id,
            group_id=group_id,
            timeout_seconds=720,
            poll_interval_seconds=20,
            networks=[network],
        )

    def _submit_akamai_deactivation(
        self,
        session: requests.Session,
        base_url: str,
        property_id: str,
        contract_id: str,
        group_id: str,
        network: str,
        property_version: int,
        owner_team: str,
    ) -> Dict[str, Any]:
        endpoint = f'{base_url}/papi/v1/properties/{property_id}/activations'
        payload = {
            'propertyVersion': property_version,
            'network': network,
            'notifyEmails': [f'{owner_team}@bank.example'],
            'note': f'Crossplane pre-destroy deactivate {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}',
            'acknowledgeAllWarnings': True,
        }

        # Try explicit deactivate intent via query param first.
        response = session.post(
            endpoint,
            params={'contractId': contract_id, 'groupId': group_id, 'activationType': 'DEACTIVATE'},
            json=payload,
            timeout=30,
        )
        if response.status_code < 300:
            return {'status': 'submitted', 'mode': 'query-param', 'response': response.json()}

        # Fallback: include deactivate intent in payload for compatibility.
        payload_with_type = dict(payload)
        payload_with_type['activationType'] = 'DEACTIVATE'
        response2 = session.post(
            endpoint,
            params={'contractId': contract_id, 'groupId': group_id},
            json=payload_with_type,
            timeout=30,
        )
        if response2.status_code < 300:
            return {'status': 'submitted', 'mode': 'payload-field', 'response': response2.json()}

        # If Akamai reports already in progress, treat as non-fatal.
        body = response2.text or response.text
        lowered = body.lower()
        if 'still pending' in lowered or 'already' in lowered:
            return {'status': 'already-in-progress', 'error': body}
        return {
            'status': 'failed',
            'http_status': response2.status_code,
            'error': body,
        }

    def _wait_for_akamai_property_inactive(
        self,
        session: requests.Session,
        base_url: str,
        property_id: str,
        contract_id: str,
        group_id: str,
        timeout_seconds: int,
        poll_interval_seconds: int,
        networks: Optional[list[str]] = None,
    ) -> None:
        deadline = time.time() + timeout_seconds
        networks = networks or ['STAGING']
        while time.time() < deadline:
            active_networks = []
            for network in networks:
                activation = self._lookup_latest_or_pending_activation(
                    session, base_url, property_id, contract_id, group_id, network
                )
                if activation:
                    active_networks.append(f'{network}:{activation.get("status")}')
            if not active_networks:
                logger.info('Akamai property %s is inactive on %s', property_id, ','.join(networks))
                return
            logger.info(
                'Waiting for Akamai property %s deactivation (%s)',
                property_id,
                ','.join(active_networks),
            )
            time.sleep(poll_interval_seconds)

        logger.warning(
            'Timed out waiting for Akamai property %s to become inactive; destroy may still fail',
            property_id,
        )

    def _maybe_submit_async_akamai_activation(self, tfvars: Dict[str, Any]) -> Dict[str, Any]:
        activate = tfvars.get('activate_property', False)
        if isinstance(activate, str):
            activate = activate.strip().lower() in {'1', 'true', 'yes', 'on'}
        if not activate:
            return {'status': 'skipped', 'reason': 'activate_property=false'}

        networks = [self._resolve_akamai_network(tfvars)]

        contract_id = str(tfvars.get('contract_id') or '').strip()
        group_id = str(tfvars.get('group_id') or '').strip()
        hostname = str(tfvars.get('hostname') or '').strip().lower()
        owner_team = str(tfvars.get('owner_team') or 'platform').strip().lower()
        if not contract_id or not group_id or not hostname:
            return {'status': 'skipped', 'reason': 'missing contract_id/group_id/hostname'}

        property_name = self._derive_property_name(hostname)
        property_id = self._lookup_akamai_property_id(contract_id, group_id, property_name)
        if not property_id:
            return {'status': 'failed', 'reason': f'property not found for {property_name}'}

        session, base_url = self._akamai_api_session()
        version = self._lookup_latest_property_version(
            session, base_url, property_id, contract_id, group_id
        )
        if not version:
            return {'status': 'failed', 'reason': f'latest version not found for {property_id}'}

        endpoint = f'{base_url}/papi/v1/properties/{property_id}/activations'
        per_network: Dict[str, Any] = {}
        submitted = 0
        in_progress = 0
        failed = 0
        for network in networks:
            active = self._lookup_latest_or_pending_activation(
                session, base_url, property_id, contract_id, group_id, network
            )
            active_version = None
            if active:
                raw_active_version = active.get('property_version')
                if isinstance(raw_active_version, int):
                    active_version = raw_active_version
                elif isinstance(raw_active_version, str) and raw_active_version.isdigit():
                    active_version = int(raw_active_version)
            if active:
                # Only skip when the currently active/pending activation is already for the latest version.
                # If Akamai is ACTIVE on an older version, submit activation for the new version.
                if active_version == version:
                    in_progress += 1
                    per_network[network] = {
                        'status': 'already-in-progress',
                        'activation': active,
                    }
                    continue

            payload = {
                'propertyVersion': version,
                'network': network,
                'notifyEmails': [f'{owner_team}@bank.example'],
                'note': f'Crossplane async activation {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}',
                'acknowledgeAllWarnings': True,
            }
            response = session.post(
                endpoint,
                params={'contractId': contract_id, 'groupId': group_id},
                json=payload,
                timeout=30,
            )
            if response.status_code >= 300:
                failed += 1
                per_network[network] = {
                    'status': 'failed',
                    'http_status': response.status_code,
                    'error': response.text,
                }
                continue

            submitted += 1
            per_network[network] = {
                'status': 'submitted-async',
                'response': response.json(),
            }

        overall_status = 'submitted-async'
        if submitted == 0 and in_progress > 0 and failed == 0:
            overall_status = 'already-in-progress'
        elif submitted == 0 and failed > 0:
            overall_status = 'failed'
        elif failed > 0:
            overall_status = 'partial'

        return {
            'status': overall_status,
            'requested_networks': networks,
            'property_id': property_id,
            'property_version': version,
            'fast_activation': 'requires Akamai account feature enabled',
            'networks': per_network,
        }

    def _akamai_api_session(self) -> tuple[requests.Session, str]:
        host = os.getenv('AKAMAI_HOST', '').strip()
        client_token = os.getenv('AKAMAI_CLIENT_TOKEN', '').strip()
        client_secret = os.getenv('AKAMAI_CLIENT_SECRET', '').strip()
        access_token = os.getenv('AKAMAI_ACCESS_TOKEN', '').strip()
        if not host or not client_token or not client_secret or not access_token:
            raise ValueError('Missing Akamai API credentials for activation submission')

        base_url = f'https://{host}' if not host.startswith('http') else host
        session = requests.Session()
        session.auth = EdgeGridAuth(
            client_token=client_token,
            client_secret=client_secret,
            access_token=access_token,
        )
        return session, base_url.rstrip('/')

    def _lookup_latest_property_version(
        self,
        session: requests.Session,
        base_url: str,
        property_id: str,
        contract_id: str,
        group_id: str,
    ) -> Optional[int]:
        endpoint = f'{base_url}/papi/v1/properties/{property_id}'
        response = session.get(
            endpoint,
            params={'contractId': contract_id, 'groupId': group_id},
            timeout=30,
        )
        if response.status_code >= 300:
            logger.warning('Akamai property details lookup failed: %s %s', response.status_code, response.text)
            return None
        payload = response.json()
        items = (
            payload.get('properties', {}).get('items')
            or payload.get('properties', {}).get('property')
            or []
        )
        versions: list[int] = []
        for item in items:
            for key in ('latestVersion', 'productionVersion', 'stagingVersion'):
                value = item.get(key)
                if isinstance(value, int):
                    versions.append(value)
            for v in (item.get('versions', {}).get('items') or []):
                pv = v.get('propertyVersion')
                if isinstance(pv, int):
                    versions.append(pv)
        return max(versions) if versions else None

    def _lookup_latest_or_pending_activation(
        self,
        session: requests.Session,
        base_url: str,
        property_id: str,
        contract_id: str,
        group_id: str,
        network: str,
    ) -> Optional[Dict[str, Any]]:
        endpoint = f'{base_url}/papi/v1/properties/{property_id}/activations'
        response = session.get(
            endpoint,
            params={'contractId': contract_id, 'groupId': group_id, 'network': network},
            timeout=30,
        )
        if response.status_code >= 300:
            return None
        payload = response.json()
        items = (
            payload.get('activations', {}).get('items')
            or payload.get('activations', {}).get('activation')
            or []
        )
        for item in items:
            status = str(item.get('status') or '').upper()
            if status in {'PENDING', 'ACTIVE', 'ZONE_1', 'ZONE_2', 'ZONE_3'}:
                return {
                    'activation_id': item.get('activationId') or item.get('id'),
                    'status': status,
                    'property_version': item.get('propertyVersion'),
                }
        return None


def _normalize_name(name: str) -> str:
    return re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-')
