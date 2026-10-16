"""Copy the verified updater outside active components before requesting exit."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from runtime.app_paths import app_cache_dir
from runtime.component_inventory import file_sha256
from runtime.distribution_manifest import DistributionManifest, ManifestError
from runtime.installed_resources import InstalledResources
from runtime.processes import hidden_subprocess_kwargs, independent_process_environment
from runtime.installation_layout import deployment_write_root
from update.deployment_transaction import atomic_json


def _start_updater(executable: Path, request: Path, *, elevated: bool) -> None:
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
        subprocess.Popen(['pkexec', str(executable), *arguments], env=independent_process_environment(), **hidden_subprocess_kwargs())
    elif elevated and sys.platform == 'darwin':
        import shlex

        command = shlex.join([str(executable), *arguments])
        # AppleScript treats this as one quoted string, not concatenated commands.
        escaped = command.replace('\\', '\\\\').replace('"', '\\"')
        subprocess.Popen(['osascript', '-e', f'do shell script "{escaped}" with administrator privileges'], env=independent_process_environment(), **hidden_subprocess_kwargs())
    else:
        subprocess.Popen([str(executable), *arguments], env=independent_process_environment(), **hidden_subprocess_kwargs())


def launch_deployment(resources: InstalledResources, staged: Path) -> Path:
    target = DistributionManifest.load(staged / 'distribution.json')
    relative = 'updater.exe' if target.platform == 'windows' else 'updater'
    component = target.component('application') if (staged / 'application').is_dir() else resources.manifest.component('application')
    source = staged / 'application' / relative if (staged / 'application').is_dir() else resources.resource('application', relative)
    record = next((item for item in component.files if item.path == relative and item.kind == 'file'), None)
    if record is None or source.is_symlink() or file_sha256(source) != record.sha256:
        raise ManifestError('The distribution does not contain a verified standalone updater')
    directory = Path(tempfile.mkdtemp(prefix='deployment-', dir=app_cache_dir()))
    executable = directory / relative
    shutil.copy2(source, executable)
    if file_sha256(executable) != record.sha256:
        raise ManifestError('The copied updater failed integrity verification')
    request = directory / 'request.json'
    atomic_json(request, {'schema': 1, 'root': str(resources.root), 'staged': str(staged),
                          'wait_pid': os.getpid(), 'recover': False})
    # A real write probe is necessary on Windows, where os.access does not check
    # the full directory ACL. It never alters an installed component.
    try:
        with tempfile.TemporaryFile(dir=deployment_write_root(resources.root, target.platform)):
            pass
        elevated = False
    except PermissionError:
        elevated = True
    _start_updater(executable, request, elevated=elevated)
    subprocess.Popen([str(executable), '--watch', str(request)], env=independent_process_environment(), **hidden_subprocess_kwargs())
    return request
