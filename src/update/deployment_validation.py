"""Validate the installed worker protocol in its own interpreter before commit."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from mathcraft_ocr.protocol import validate_response
from runtime.distribution_manifest import DistributionManifest, ManifestError, read_json
from runtime.installed_resources import InstalledResources, worker_command, worker_environment
from runtime.processes import hidden_subprocess_kwargs


def validate_installed_worker(root: Path, manifest: DistributionManifest) -> None:
    resources = InstalledResources(root, manifest)
    command = worker_command(resources)
    request = {'protocol': manifest.component('application').worker_protocol, 'id': 'deployment', 'action': 'hello'}
    result = subprocess.run(
        command, input=json.dumps(request) + '\n', capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=90, env=worker_environment(resources),
        **hidden_subprocess_kwargs(),
    )
    if result.returncode:
        raise ManifestError(f'Updated worker failed ({result.returncode}): {result.stderr[-4000:]}')
    try:
        response = validate_response(json.loads(result.stdout), 'deployment')
    except (ValueError, TypeError) as exc:
        raise ManifestError('Updated worker returned an invalid handshake') from exc
    if not response['ok']:
        raise ManifestError(f'Updated worker rejected its handshake: {response["error"]}')
    info = response['result']
    runtime = read_json(resources.resource('inference', 'runtime.json'))
    if info.get('model_format') != manifest.component('models').model_format or info.get('worker_protocol') != request['protocol'] or any(
        info.get(key) != runtime.get(key) for key in ('python_version', 'ort_version')
    ):
        raise ManifestError('Updated worker versions do not match the inference component')
