"""Standalone updater entry point; never imports or owns a Qt application."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import shutil
import sys
import time
import subprocess
import tempfile

from runtime.distribution_manifest import DistributionManifest, ManifestError, read_json
from runtime.runtime_logging import init_app_logging
from runtime.processes import hidden_subprocess_kwargs, independent_process_environment
from update.component_release import fetch_component_release
from update.deployment_transaction import atomic_json
from update.platform_deployment import deployment_transaction
from runtime.installation_layout import deployment_directory, installation_manifest
from runtime.installed_resources import current_target
from update.deployment_validation import validate_installed_worker

logger = logging.getLogger(f'latexsnipper.{__name__}')


def wait_for_exit(pid: int, timeout: float = 120, cancel: Path | None = None) -> None:
    if type(pid) is not int or pid < 1 or pid == os.getpid():
        raise ManifestError('Invalid application process identity')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if cancel is not None and cancel.exists():
                    raise RuntimeError('Deployment cancelled before application exit')
                if kernel.WaitForSingleObject(handle, 100) == 0:
                    return
            raise TimeoutError('Application did not exit; installation was preserved')
        finally:
            kernel.CloseHandle(handle)
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel is not None and cancel.exists():
            raise RuntimeError('Deployment cancelled before application exit')
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    raise TimeoutError('Application did not exit; installation was preserved')


def run_request(request_path: Path) -> None:
    status = request_path.parent / 'deployment-result.json'
    def report(state: str, **fields) -> None:
        atomic_json(status, {'state': state, 'pid': os.getpid(), **fields})

    try:
        report('starting')
        request = read_json(request_path)
        fields = {'schema', 'root', 'staged', 'wait_pid', 'recover'}
        if set(request) != fields or type(request['schema']) is not int or request['schema'] != 1 or type(request['recover']) is not bool:
            raise ManifestError('Unsupported deployment request')
        if type(request['wait_pid']) is not int or request['wait_pid'] < 1 or request['wait_pid'] == os.getpid():
            raise ManifestError('Invalid application process identity')
        root = Path(request['root']).resolve(strict=True)
        transaction = deployment_transaction(root)
        if request['recover']:
            report('ready')
            wait_for_exit(request['wait_pid'])
            outcome = transaction.recover(timeout=600) or 'rolled-back'
        else:
            staged = Path(request['staged']).resolve(strict=True)
            target = DistributionManifest.load(staged / 'distribution.json')
            # Privileged deployment independently authenticates the requested
            # target; caller-supplied inventories are not a release authority.
            # Elevated helpers own and clean their download cache themselves;
            # root-owned cache directories must not be left in the user's task.
            with tempfile.TemporaryDirectory(prefix='latexsnipper-release-') as cache:
                release = fetch_component_release(Path(cache), tag=target.release_tag)
            if release.catalog.select(*target.target) != target:
                raise ManifestError('Prepared target is not the authoritative release')

            def checkpoint(state: str) -> None:
                if state == 'prepared':
                    helper = transaction.directory / ('updater.exe' if os.name == 'nt' else 'updater')
                    if getattr(sys, 'frozen', False):
                        shutil.copy2(sys.executable, helper)
                    report('ready')
                    wait_for_exit(request['wait_pid'], cancel=request_path.parent / 'cancel')
                else:
                    report(state)

            transaction.apply(staged, validate=validate_installed_worker, checkpoint=checkpoint)
            outcome = 'committed'
        report(outcome)
    except Exception as exc:
        logger.exception('独立更新进程失败')
        report('failed', error=str(exc))
        raise


def watch_request(request_path: Path) -> None:
    request = read_json(request_path)
    status = request_path.parent / 'deployment-result.json'
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        if status.is_file():
            result = read_json(status)
            stopped = False
            if result.get('pid'):
                try:
                    wait_for_exit(result['pid'], timeout=0.01)
                    stopped = True
                except TimeoutError:
                    pass
            if result.get('state') in {'committed', 'rolled-back', 'failed'} or stopped:
                # A failed handoff can leave the original UI open. Do not open
                # another instance, and never restart the UI with elevated rights.
                try:
                    wait_for_exit(request['wait_pid'], timeout=0.5)
                except TimeoutError:
                    return
                root = Path(request['root'])
                journal = deployment_directory(root, current_target()[0]) / 'journal.json'
                if result.get('state') == 'failed' and journal.is_file() and read_json(journal).get('status') not in {'rolled-back', 'committed'}:
                    logger.error('部署恢复未完成，保留事务供显式恢复，不循环启动应用')
                    return
                launcher = root / ('LaTeXSnipper.exe' if os.name == 'nt' else 'LaTeXSnipper')
                if launcher.is_file():
                    env = independent_process_environment()
                    env['LATEXSNIPPER_DEPLOYMENT_RESULT'] = str(status)
                    subprocess.Popen([str(launcher)], env=env, **hidden_subprocess_kwargs())
                return
        time.sleep(0.2)
    raise TimeoutError('Independent updater did not finish')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--request', type=Path)
    mode.add_argument('--watch', type=Path)
    mode.add_argument('--validate-root', type=Path)
    mode.add_argument('--install-from', type=Path)
    mode.add_argument('--recover-root', type=Path)
    parser.add_argument('--root', type=Path)
    arguments = parser.parse_args()
    init_app_logging()
    try:
        if arguments.recover_root is not None:
            from launcher_main import launch_installed

            launch_installed(arguments.recover_root.resolve(strict=True))
        elif arguments.install_from is not None:
            if arguments.root is None or current_target()[0] == 'macos':
                raise ManifestError('Offline installation requires a Windows or Linux installation root')
            root = arguments.root.resolve()
            root.mkdir(parents=True, exist_ok=True)
            target = DistributionManifest.load(arguments.install_from / 'distribution.json')
            if target.target[:2] != current_target():
                raise ManifestError('Offline installer does not match this platform and architecture')
            transaction = deployment_transaction(root)

            def installer_checkpoint(state: str) -> None:
                if state == 'prepared' and getattr(sys, 'frozen', False):
                    shutil.copy2(sys.executable, transaction.directory / ('updater.exe' if os.name == 'nt' else 'updater'))

            transaction.apply(arguments.install_from, validate=validate_installed_worker, complete=True, checkpoint=installer_checkpoint)
        elif arguments.validate_root is not None:
            root = arguments.validate_root.resolve(strict=True)
            manifest = DistributionManifest.load(installation_manifest(root, current_target()[0]))
            from update.deployment_transaction import verify_distribution

            verify_distribution(root, manifest)
            validate_installed_worker(root, manifest)
            if manifest.platform == 'macos':
                from update.macos_transaction import verify_bundle
                from runtime.installation_layout import macos_bundle

                verify_bundle(macos_bundle(root))
        elif arguments.watch is not None:
            watch_request(arguments.watch.resolve(strict=True))
        else:
            run_request(arguments.request.resolve(strict=True))
        return 0
    except Exception:
        logger.exception('独立部署命令失败')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
