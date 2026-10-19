"""Own asynchronous update state, download control and deployment handoff."""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from runtime.app_paths import app_cache_dir
from runtime.distribution_manifest import read_json
from runtime.installed_resources import installed_resources
from update.component_download import DownloadCancelled, DownloadControl
from update.component_plan import plan_component_update
from update.component_release import fetch_component_release, fetch_release_info
from update.component_staging import prepare_components
from update.deployment_launch import launch_deployment, retire_deployment

logger = logging.getLogger(f"latexsnipper.{__name__}")


class ComponentUpdateController(QObject):
    changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
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
            result: tuple[str, dict] = "cancelled", {}
            try:
                result = action()
            except DownloadCancelled:
                result = "cancelled", {}
            except Exception as exc:
                logger.exception("应用更新任务失败")
                result = "failed", {"error": str(exc)}
            finally:
                if self._request is not None and (
                    self._closed or result[0] in {"failed", "cancelled"}
                ):
                    self._retire_request()
                if self._closed and self._request is None:
                    self._cleanup()
                self.busy = False
            self._emit(result[0], result[1])

        threading.Thread(target=run, name="component-update", daemon=True).start()

    def check(self) -> None:
        def check():
            self.resources = installed_resources()
            if self.resources is None:
                self._emit("release", {"release": fetch_release_info()})
                return "source", {}
            self.release = fetch_component_release(
                app_cache_dir() / "components",
                control=self._control,
                on_release=lambda info: self._emit("release", {"release": info}),
            )
            self._control.checkpoint()
            installed = self.resources.manifest
            target = self.release.catalog.select(*installed.target)
            self.plan = plan_component_update(installed, target)
            return "available", {
                "release": self.release,
                "plan": self.plan,
                "resources": self.resources,
            }

        self._run("checking", check)

    def prepare(self) -> None:
        resources, plan = self.resources, self.plan
        if resources is None or plan is None:
            return

        def prepare():
            self._cleanup()
            cache = app_cache_dir().resolve()
            self._directory = Path(
                tempfile.mkdtemp(prefix="component-update-", dir=cache)
            )
            self.staged = self._directory / "staged"
            done = {}

            def progress(name: str, count: int, total: int) -> None:
                done[name] = count
                self._emit(
                    "progress",
                    {"done": sum(done.values()), "total": plan.download_bytes},
                )

            prepare_components(
                resources.root,
                plan.target,
                self.staged,
                cache / "components",
                control=self._control,
                progress=progress,
                status=lambda state, name: self._emit(state, {"component": name}),
            )
            return "ready", {"staged": self.staged}

        self._run("downloading", prepare)

    def pause(self) -> None:
        self.paused = not self.paused
        self._control.pause(self.paused)
        self._emit("paused" if self.paused else "downloading")

    def deploy(self) -> None:
        resources, staged = self.resources, self.staged
        if resources is None or staged is None:
            return

        def handoff():
            self._request = launch_deployment(resources, staged)
            status = self._request.parent / "deployment-result.json"
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if self._closed:
                    (self._request.parent / "cancel").touch()
                    raise DownloadCancelled()
                if status.is_file():
                    result = read_json(status)
                    if result.get("state") == "ready":
                        return "handoff-ready", {}
                    if result.get("state") == "failed":
                        raise RuntimeError(
                            result.get("error", "Independent updater failed")
                        )
                time.sleep(0.1)
            (self._request.parent / "cancel").touch()
            raise TimeoutError("Independent updater did not become ready")

        self._run("handoff", handoff)

    def _cleanup(self) -> None:
        if self._directory is not None and self._directory.exists():
            if (
                self._directory.is_symlink()
                or self._directory.parent != app_cache_dir().resolve()
            ):
                logger.error("拒绝清理应用缓存之外的更新暂存目录")
            else:
                try:
                    shutil.rmtree(self._directory)
                except OSError:
                    logger.exception("清理更新暂存目录失败")
        self._directory = None
        self.staged = None

    def close(self) -> None:
        self._closed = True
        self._control.cancel()
        if self._request is not None:
            try:
                (self._request.parent / "cancel").touch()
            except OSError:
                logger.exception("写入部署取消标记失败")
            if not self.busy:
                self._retire_request()
        elif not self.busy:
            self._cleanup()

    def _retire_request(self) -> None:
        if self._request is not None:
            request, self._request = self._request, None
            # The helper still owns these files until it has stopped.
            self._directory = None
            self.staged = None
            retire_deployment(request)
