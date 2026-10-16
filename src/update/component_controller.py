"""Own asynchronous update state, download control and deployment handoff."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import tempfile
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from runtime.app_paths import app_cache_dir
from runtime.component_inventory import verify_component
from runtime.distribution_manifest import read_json
from runtime.installed_resources import installed_resources
from update.component_download import DownloadCancelled, DownloadControl
from update.component_plan import plan_component_update
from update.component_release import fetch_component_release, fetch_release_info
from update.component_staging import prepare_components
from update.deployment_launch import launch_deployment

logger = logging.getLogger(f'latexsnipper.{__name__}')


class ComponentUpdateController(QObject):
    changed = pyqtSignal(str, object)

    def __init__(self, parent=None, *, repair: bool = False):
        super().__init__(parent)
        self.repair = repair
        self.busy = False
        self.paused = False
        self.resources = None
        self.release = None
        self.plan = None
        self.staged: Path | None = None
        self._directory: Path | None = None
        self._request: Path | None = None
        self._closed = False
        self._control = DownloadControl()

    def _emit(self, state: str, data=None) -> None:
        if not self._closed:
            try:
                self.changed.emit(state, data or {})
            except RuntimeError:
                pass

    def _run(self, state: str, action) -> None:
        if self.busy or self._closed:
            return
        self.busy = True
        self._control = DownloadControl()
        self.paused = False
        self._emit(state)

        def run():
            try:
                result = action()
            except DownloadCancelled:
                result = 'cancelled', {}
            except Exception as exc:
                logger.exception('组件更新任务失败')
                result = 'failed', {'error': str(exc)}
            finally:
                self.busy = False
                if self._closed and self._request is None:
                    self._cleanup()
            self._emit(*result)

        threading.Thread(target=run, name='component-update', daemon=True).start()

    def check(self) -> None:
        def check():
            self.resources = installed_resources()
            if self.resources is None:
                self._emit('release', {'release': fetch_release_info()})
                return 'source', {}
            tag = self.resources.manifest.release_tag if self.repair and self.resources else None
            self.release = fetch_component_release(app_cache_dir() / 'components', control=self._control, tag=tag,
                                                   on_release=lambda info: self._emit('release', {'release': info}))
            self._control.checkpoint()
            self.plan = None
            if self.resources is not None:
                installed = self.resources.manifest
                target = self.release.catalog.select(*installed.target)
                damaged = [item.name for item in installed.components if verify_component(self.resources.root / item.name, item)]
                damaged_bundle = False
                if installed.platform == 'macos':
                    from update.macos_transaction import bundle_is_damaged

                    damaged_bundle = bundle_is_damaged(self.resources.root)
                self.plan = plan_component_update(installed, target, damaged_components=damaged, damaged_bundle=damaged_bundle)
            return 'available', {'release': self.release, 'plan': self.plan, 'resources': self.resources}

        self._run('checking', check)

    def prepare(self) -> None:
        if self.resources is None or self.plan is None:
            return

        def prepare():
            self._cleanup()
            cache = app_cache_dir().resolve()
            self._directory = Path(tempfile.mkdtemp(prefix='component-update-', dir=cache))
            self.staged = self._directory / 'staged'
            done = {}

            def progress(name: str, count: int, total: int) -> None:
                done[name] = count
                self._emit('progress', {'done': sum(done.values()), 'total': self.plan.download_bytes})

            prepare_components(
                self.resources.root, self.plan.target, self.staged, cache / 'components',
                control=self._control, progress=progress,
                status=lambda state, name: self._emit(state, {'component': name}),
            )
            return 'ready', {'staged': self.staged}

        self._run('downloading', prepare)

    def pause(self) -> None:
        self.paused = not self.paused
        self._control.pause(self.paused)
        self._emit('paused' if self.paused else 'downloading')

    def deploy(self) -> None:
        if self.resources is None or self.staged is None:
            return

        def handoff():
            self._request = launch_deployment(self.resources, self.staged)
            status = self._request.parent / 'deployment-result.json'
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if self._closed:
                    (self._request.parent / 'cancel').touch()
                    raise DownloadCancelled()
                if status.is_file():
                    result = read_json(status)
                    if result.get('state') == 'ready':
                        return 'handoff-ready', {}
                    if result.get('state') == 'failed':
                        raise RuntimeError(result.get('error', 'Independent updater failed'))
                time.sleep(0.1)
            (self._request.parent / 'cancel').touch()
            raise TimeoutError('Independent updater did not become ready')

        self._run('handoff', handoff)

    def _cleanup(self) -> None:
        if self._directory is not None and self._directory.exists():
            if self._directory.is_symlink() or self._directory.parent != app_cache_dir().resolve():
                logger.error('拒绝清理应用缓存之外的更新暂存目录')
            else:
                try:
                    shutil.rmtree(self._directory)
                except OSError:
                    logger.exception('清理更新暂存目录失败')
        self._directory = None
        self.staged = None

    def close(self) -> None:
        self._closed = True
        self._control.cancel()
        if self._request is not None:
            try:
                (self._request.parent / 'cancel').touch()
            except OSError:
                logger.exception('写入部署取消标记失败')
        elif not self.busy:
            self._cleanup()
