"""Copy the verified updater outside active components before requesting exit."""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from runtime.app_paths import app_cache_dir
from runtime.component_inventory import file_sha256
from runtime.distribution_manifest import DistributionManifest, ManifestError, read_json
from runtime.deployment_feedback import cleanup_deployment_task
from runtime.installed_resources import InstalledResources
from runtime.processes import hidden_subprocess_kwargs, independent_process_environment
from runtime.installation_layout import deployment_write_root
from update.deployment_transaction import atomic_json

logger = logging.getLogger(f'latexsnipper.{__name__}')


def retire_deployment(request: Path) -> None:
    """Wait for both helpers before releasing their private task and staging."""
    def clean():
        from update.updater_entry import wait_for_exit

        try:
            deadline = time.monotonic() + 330
            status = request.parent / 'deployment-result.json'
            while request.parent.exists() and time.monotonic() < deadline:
                if status.is_file():
                    result = read_json(status)
                    if result.get('state') in {'failed', 'rolled-back', 'committed'}:
                        if result.get('pid'):
                            wait_for_exit(result['pid'], timeout=30)
                        watcher = request.parent / 'watcher.json'
                        if watcher.is_file():
                            wait_for_exit(read_json(watcher)['pid'], timeout=30)
                        for _ in range(30):
                            if cleanup_deployment_task(request.parent):
                                return
                            time.sleep(0.2)
                        break
                time.sleep(0.1)
            if request.parent.exists():
                logger.warning('独立部署已取消，任务缓存尚未释放: %s', request.parent)
        except (OSError, ValueError, TimeoutError):
            logger.exception('清理独立部署任务失败')

    threading.Thread(target=clean, name='deployment-cleanup', daemon=True).start()

def _start_updater(executable: Path, request: Path, *, elevated: bool) -> subprocess.Popen | None:
    arguments = ['--request', str(request)]
    if elevated and os.name == 'nt':
        from ctypes import wintypes

        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
        shell.ShellExecuteW.restype = ctypes.c_void_p
        result = shell.ShellExecuteW(None, 'runas', str(executable), subprocess.list2cmdline(arguments), str(executable.parent), 0)
        if result is None or result <= 32:
            raise OSError('Administrator authorization was cancelled or unavailable')
    elif elevated and sys.platform == 'linux':
        return subprocess.Popen(['pkexec', str(executable), *arguments], env=independent_process_environment(), **hidden_subprocess_kwargs())
    elif elevated and sys.platform == 'darwin':
        import shlex

        command = shlex.join([str(executable), *arguments])
        # AppleScript treats this as one quoted string, not concatenated commands.
        escaped = command.replace('\\', '\\\\').replace('"', '\\"')
        return subprocess.Popen(['osascript', '-e', f'do shell script "{escaped}" with administrator privileges'], env=independent_process_environment(), **hidden_subprocess_kwargs())
    else:
        return subprocess.Popen([str(executable), *arguments], env=independent_process_environment(), **hidden_subprocess_kwargs())
    return None


def launch_deployment(resources: InstalledResources, staged: Path) -> Path:
    target = DistributionManifest.load(staged / 'distribution.json')
    relative = 'updater.exe' if target.platform == 'windows' else 'updater'
    component = target.component('application') if (staged / 'application').is_dir() else resources.manifest.component('application')
    source = staged / 'application' / relative if (staged / 'application').is_dir() else resources.resource('application', relative)
    record = next((item for item in component.files if item.path == relative and item.kind == 'file'), None)
    if record is None or source.is_symlink() or file_sha256(source) != record.sha256:
        raise ManifestError('The distribution does not contain a verified standalone updater')
    directory = Path(tempfile.mkdtemp(prefix='deployment-', dir=app_cache_dir()))
    try:
        executable = directory / relative
        shutil.copy2(source, executable)
        if file_sha256(executable) != record.sha256:
            raise ManifestError('The copied updater failed integrity verification')
        request = directory / 'request.json'
        atomic_json(request, {'schema': 1, 'root': str(resources.root), 'staged': str(staged),
                              'wait_pid': os.getpid(), 'recover': False})
        # Probe the actual ACL without changing an installed component.
        try:
            with tempfile.TemporaryFile(dir=deployment_write_root(resources.root, target.platform)):
                pass
            elevated = False
        except PermissionError:
            elevated = True
    except Exception:
        cleanup_deployment_task(directory)
        raise
    try:
        watcher = subprocess.Popen([str(executable), '--watch', str(request)], env=independent_process_environment(), **hidden_subprocess_kwargs())
        atomic_json(directory / 'watcher.json', {'pid': watcher.pid})
        process = _start_updater(executable, request, elevated=elevated)
        if process is not None:
            def monitor():
                code = process.wait()
                status = directory / 'deployment-result.json'
                if code and directory.exists():
                    try:
                        result = read_json(status) if status.is_file() else {}
                        if result.get('state') not in {'committed', 'rolled-back', 'failed'}:
                            atomic_json(status, {'state': 'failed', 'error': f'Independent updater exited with status {code}'})
                    except (OSError, ValueError):
                        logger.exception('记录独立更新进程退出失败')

            threading.Thread(target=monitor, name='deployment-monitor', daemon=True).start()
    except Exception as exc:
        (directory / 'cancel').touch()
        atomic_json(directory / 'deployment-result.json', {'state': 'failed', 'error': str(exc)})
        retire_deployment(request)
        raise
    return request
