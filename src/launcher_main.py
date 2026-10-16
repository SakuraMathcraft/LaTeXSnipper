"""Stable desktop entry point that recovers deployment before importing the UI."""

from __future__ import annotations

import logging
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if not getattr(sys, 'frozen', False):
    project = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(project), str(project / 'src')]

from runtime.app_paths import app_cache_dir
from runtime.component_inventory import file_sha256
from runtime.distribution_manifest import DistributionManifest, ManifestError
from runtime.installed_resources import current_target
from runtime.installation_layout import deployment_directory, deployment_write_root, installation_manifest
from runtime.processes import hidden_subprocess_kwargs, independent_process_environment
from runtime.runtime_logging import init_app_logging
from update.deployment_launch import _start_updater
from update.deployment_transaction import atomic_json, needs_recovery

logger = logging.getLogger(f'latexsnipper.{__name__}')


def launch_installed(root: Path) -> None:
    executable = 'LaTeXSnipper.exe' if os.name == 'nt' else 'LaTeXSnipper'
    system, _ = current_target()
    transaction = deployment_directory(root, system)
    if needs_recovery(transaction):
        helper_name = 'updater.exe' if os.name == 'nt' else 'updater'
        helper = transaction / helper_name
        if not helper.is_file():
            helper = root / 'application' / helper_name
            manifest = DistributionManifest.load(installation_manifest(root, system))
            record = next((item for item in manifest.component('application').files if item.path == helper_name), None)
            if record is None or file_sha256(helper) != record.sha256:
                raise ManifestError('No verified recovery helper is available')
        directory = Path(tempfile.mkdtemp(prefix='recovery-', dir=app_cache_dir()))
        copy = directory / helper_name
        if helper.is_symlink():
            raise ManifestError('Recovery executable cannot be a symbolic link')
        shutil.copy2(helper, copy)
        request = directory / 'request.json'
        atomic_json(request, {'schema': 1, 'root': str(root), 'staged': '', 'wait_pid': os.getpid(), 'recover': True})
        try:
            with tempfile.TemporaryFile(dir=deployment_write_root(root, system)):
                pass
            elevated = False
        except PermissionError:
            elevated = True
        _start_updater(copy, request, elevated=elevated)
        subprocess.Popen([str(copy), '--watch', str(request)], env=independent_process_environment(), **hidden_subprocess_kwargs())
        return
    manifest = DistributionManifest.load(installation_manifest(root, system))
    relative = executable
    record = next((item for item in manifest.component('application').files if item.path == relative), None)
    target = root / 'application' / relative
    if record is None or target.is_symlink() or file_sha256(target) != record.sha256:
        raise ManifestError('Application executable is missing or corrupt; reinstall its application component')
    subprocess.Popen([str(target), *sys.argv[1:]], cwd=root / 'application', env=independent_process_environment(), **hidden_subprocess_kwargs())


def main() -> int:
    init_app_logging()
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--installation-root', type=Path)
        arguments, remaining = parser.parse_known_args()
        sys.argv[1:] = remaining
        root = arguments.installation_root or Path(sys.executable).resolve().parent
        launch_installed(root.resolve(strict=True))
        return 0
    except Exception:
        logger.exception('发行启动或恢复失败')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
