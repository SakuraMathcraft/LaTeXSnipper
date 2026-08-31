"""Automation API lifecycle controller."""

from __future__ import annotations

from localization.manager import translate as tr
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from integration.automation import (
    AutomationApiAuth,
    AutomationApiServer,
    AutomationApiSettings,
)


AUTOMATION_API_ENABLED_KEY = "automation_api_enabled"
AUTOMATION_API_PORT_KEY = "automation_api_port"
AUTOMATION_API_ACCESS_SCOPE_KEY = "automation_api_access_scope"
AUTOMATION_API_BIND_ADDRESS_KEY = "automation_api_bind_address"
AUTOMATION_API_REMOTE_SECURITY_KEY = "automation_api_remote_security"
AUTOMATION_API_REMOTE_KEY = "automation_api_remote_key"
AUTOMATION_API_TLS_CERT_PATH_KEY = "automation_api_tls_cert_path"
AUTOMATION_API_TLS_KEY_PATH_KEY = "automation_api_tls_key_path"
AUTOMATION_API_ALLOWED_ORIGINS_KEY = "automation_api_allowed_origins"
AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY = "automation_api_remote_external_enabled"
AUTOMATION_API_REMOTE_WARNING_ACKNOWLEDGED_KEY = (
    "automation_api_remote_warning_acknowledged"
)
DEFAULT_AUTOMATION_API_PORT = 28765


def automation_api_operation_error_message(action: str) -> str:
    if action == "stop":
        return tr("Automation API 停止失败，请重试或退出应用。")
    return tr("Automation API 启动失败，请检查端口、监听地址和证书配置。")


class _AutomationApiToggleWorker(QThread):
    completed = pyqtSignal(bool, str, object)

    def __init__(
        self,
        *,
        action: str,
        server: AutomationApiServer | None = None,
        create_server=None,
    ) -> None:
        super().__init__()
        self._action = action
        self._server = server
        self._create_server = create_server
        self._result_server = None

    def run(self) -> None:
        try:
            if self._action == "start":
                server = self._create_server()
                server.start()
                self._result_server = server
                self.completed.emit(
                    True,
                    tr("Automation API 已运行：{url}").format(url=server.base_url),
                    server,
                )
                return
            if self._server is not None:
                self._server.stop()
            self.completed.emit(True, tr("Automation API 已关闭"), None)
        except Exception:
            self._result_server = None
            self.completed.emit(
                False, automation_api_operation_error_message(self._action), None
            )


class _AutomationApiResultReceiver(QObject):
    def __init__(self, on_done, cleanup) -> None:
        super().__init__()
        self._on_done = on_done
        self._cleanup = cleanup

    @pyqtSlot(bool, str, object)
    def handle_completed(self, ok: bool, message: str, server: object) -> None:
        try:
            self._on_done(ok, message, server)
        finally:
            self._cleanup()


class AutomationApiController(QObject):
    _AUTOMATION_SETTING_KEYS = (
        AUTOMATION_API_PORT_KEY,
        AUTOMATION_API_ACCESS_SCOPE_KEY,
        AUTOMATION_API_BIND_ADDRESS_KEY,
        AUTOMATION_API_REMOTE_SECURITY_KEY,
        AUTOMATION_API_REMOTE_KEY,
        AUTOMATION_API_TLS_CERT_PATH_KEY,
        AUTOMATION_API_TLS_KEY_PATH_KEY,
        AUTOMATION_API_ALLOWED_ORIGINS_KEY,
        AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY,
        AUTOMATION_API_REMOTE_WARNING_ACKNOWLEDGED_KEY,
    )

    def __init__(
        self, cfg, recognition_coordinator, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.recognition_coordinator = recognition_coordinator
        self._automation_api_server: AutomationApiServer | None = None
        self._automation_api_toggle_workers: list[
            tuple[_AutomationApiToggleWorker, _AutomationApiResultReceiver]
        ] = []
        self._automation_api_pending_operations: list[tuple[str, object]] = []
        self._automation_api_operation_active = False
        self._automation_api_shutting_down = False

    def _automation_api_enabled_pref(self) -> bool:
        try:
            return bool(self.cfg.get(AUTOMATION_API_ENABLED_KEY, False))
        except Exception:
            return False

    def _automation_api_settings(
        self, overrides: dict[str, object] | None = None
    ) -> AutomationApiSettings:
        values = overrides or {}

        def read(key: str, default):
            return values[key] if key in values else self.cfg.get(key, default)

        scope = str(read(AUTOMATION_API_ACCESS_SCOPE_KEY, "local") or "local")
        default_bind = "127.0.0.1"
        bind = str(
            read(AUTOMATION_API_BIND_ADDRESS_KEY, default_bind) or default_bind
        ).strip()
        try:
            port = int(read(AUTOMATION_API_PORT_KEY, DEFAULT_AUTOMATION_API_PORT))
        except (TypeError, ValueError):
            port = DEFAULT_AUTOMATION_API_PORT
        origins_value = read(AUTOMATION_API_ALLOWED_ORIGINS_KEY, [])
        if isinstance(origins_value, str):
            origins = tuple(
                value.strip() for value in origins_value.splitlines() if value.strip()
            )
        elif isinstance(origins_value, (list, tuple)):
            origins = tuple(
                str(value).strip() for value in origins_value if str(value).strip()
            )
        else:
            origins = ()
        return AutomationApiSettings(
            host=bind,
            port=port,
            access_scope=scope,
            remote_security=str(
                read(AUTOMATION_API_REMOTE_SECURITY_KEY, "tunnel") or "tunnel"
            ),
            remote_key=str(read(AUTOMATION_API_REMOTE_KEY, "") or ""),
            tls_cert_path=str(read(AUTOMATION_API_TLS_CERT_PATH_KEY, "") or ""),
            tls_key_path=str(read(AUTOMATION_API_TLS_KEY_PATH_KEY, "") or ""),
            allowed_origins=origins,
            remote_external_enabled=bool(
                read(AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY, False)
            ),
        )

    def automation_api_status_text(self) -> str:
        server = getattr(self, "_automation_api_server", None)
        if server:
            return tr("Automation API 已运行：{url}").format(url=server.base_url)
        if self._automation_api_enabled_pref():
            return tr("Automation API 已启用，但当前未运行")
        return tr("Automation API 已关闭")

    def automation_api_is_running(self) -> bool:
        return getattr(self, "_automation_api_server", None) is not None

    def apply_automation_api_startup_preference(self) -> None:
        if self._automation_api_enabled_pref():
            self._start_automation_api_async()

    def set_automation_api_enabled_async(self, enabled: bool, callback=None) -> None:
        self.cfg.set(AUTOMATION_API_ENABLED_KEY, bool(enabled))
        if enabled:
            self._start_automation_api_async(callback)
        else:
            self._stop_automation_api_async(callback)

    def _set_automation_api_config(self, values: dict[str, object]) -> None:
        set_many = getattr(self.cfg, "set_many", None)
        if callable(set_many):
            set_many(values)
            return
        for key, value in values.items():
            self.cfg.set(key, value)

    def update_automation_api_settings_async(
        self, values: dict[str, object], callback=None
    ) -> None:
        old_values = {
            key: self.cfg.get(key, None) for key in self._AUTOMATION_SETTING_KEYS
        }
        was_running = self.automation_api_is_running()
        new_values = {
            key: values[key] for key in self._AUTOMATION_SETTING_KEYS if key in values
        }
        old_settings = self._automation_api_settings()
        new_settings = self._automation_api_settings(new_values)
        new_settings.validate()
        self._set_automation_api_config(new_values)
        if not was_running:
            if callback:
                QTimer.singleShot(
                    0, lambda: callback(True, tr("Automation API 配置已保存"))
                )
            return
        if new_settings == old_settings:
            if callback:
                QTimer.singleShot(
                    0, lambda: callback(True, tr("Automation API 配置未更改"))
                )
            return

        def after_stop(ok: bool, message: str) -> None:
            if not ok:
                if callback:
                    callback(False, message)
                return

            def after_start(started: bool, start_message: str) -> None:
                if started:
                    if callback:
                        callback(True, start_message)
                    return
                self._set_automation_api_config(
                    {**old_values, AUTOMATION_API_ENABLED_KEY: True}
                )
                self._start_automation_api_async(
                    lambda _restored, _restore_message: (
                        callback and callback(False, start_message)
                    )
                )

            self.cfg.set(AUTOMATION_API_ENABLED_KEY, True)
            self._start_automation_api_async(after_start)

        self._stop_automation_api_async(after_stop)

    def _create_automation_api_server(self) -> AutomationApiServer:
        settings = self._automation_api_settings()
        return AutomationApiServer(
            self.recognition_coordinator,
            settings=settings,
            auth=AutomationApiAuth(
                remote_key=settings.remote_key,
                remote_external_enabled=settings.remote_external_enabled,
            ),
        )

    def _automation_api_workers(self):
        workers = getattr(self, "_automation_api_toggle_workers", None)
        if workers is None:
            workers = []
            self._automation_api_toggle_workers = workers
        return workers

    def _run_automation_api_worker(
        self, worker: _AutomationApiToggleWorker, on_done
    ) -> None:
        workers = self._automation_api_workers()

        def cleanup() -> None:
            try:
                workers.remove((worker, receiver))
            except ValueError:
                pass
            worker.deleteLater()
            receiver.deleteLater()

        receiver = _AutomationApiResultReceiver(on_done, cleanup)
        workers.append((worker, receiver))
        worker.completed.connect(receiver.handle_completed)
        worker.start()

    def _automation_api_operation_queue(self):
        operations = getattr(self, "_automation_api_pending_operations", None)
        if operations is None:
            operations = []
            self._automation_api_pending_operations = operations
        return operations

    def _enqueue_automation_api_operation(self, action: str, callback=None) -> None:
        if bool(getattr(self, "_automation_api_shutting_down", False)):
            return
        self._automation_api_operation_queue().append((action, callback))
        self._run_next_automation_api_operation()

    def _run_next_automation_api_operation(self) -> None:
        if bool(getattr(self, "_automation_api_shutting_down", False)):
            return
        if bool(getattr(self, "_automation_api_operation_active", False)):
            return
        operations = self._automation_api_operation_queue()
        if not operations:
            return
        action, callback = operations.pop(0)
        self._automation_api_operation_active = True

        def finish(ok: bool, message: str) -> None:
            self._automation_api_operation_active = False
            if callback:
                callback(ok, message)
            self._run_next_automation_api_operation()

        server = getattr(self, "_automation_api_server", None)
        if action == "start" and server is not None:
            QTimer.singleShot(
                0, lambda: finish(True, self.automation_api_status_text())
            )
            return
        if action == "stop" and server is None:
            QTimer.singleShot(0, lambda: finish(True, tr("Automation API 已关闭")))
            return

        worker = _AutomationApiToggleWorker(
            action=action,
            server=server if action == "stop" else None,
            create_server=self._create_automation_api_server
            if action == "start"
            else None,
        )

        def done(ok: bool, message: str, result_server: object) -> None:
            if bool(getattr(self, "_automation_api_shutting_down", False)):
                if result_server is not None:
                    result_server.stop()
                self._automation_api_operation_active = False
                return
            if action == "start":
                if ok:
                    self._automation_api_server = result_server
                else:
                    self.cfg.set(AUTOMATION_API_ENABLED_KEY, False)
            elif ok:
                if self._automation_api_server is server:
                    self._automation_api_server = None
            else:
                self._automation_api_server = server
                self.cfg.set(AUTOMATION_API_ENABLED_KEY, True)
            finish(ok, message)

        self._run_automation_api_worker(worker, done)

    def _start_automation_api_async(self, callback=None) -> None:
        self._enqueue_automation_api_operation("start", callback)

    def _stop_automation_api_async(self, callback=None) -> None:
        self._enqueue_automation_api_operation("stop", callback)

    def _stop_automation_api(self) -> None:
        self._automation_api_shutting_down = True
        pending = getattr(self, "_automation_api_pending_operations", None)
        if pending is not None:
            pending.clear()
        server = getattr(self, "_automation_api_server", None)
        self._automation_api_server = None
        if server is not None:
            server.stop()

    def _cleanup_automation_api_workers(self, timeout_ms: int = 3000) -> None:
        workers = getattr(self, "_automation_api_toggle_workers", []) or []
        remaining = []
        for worker, receiver in list(workers):
            if worker.isRunning():
                worker.quit()
                worker.wait(timeout_ms)
            if worker.isRunning():
                remaining.append((worker, receiver))
                continue
            try:
                worker.completed.disconnect(receiver.handle_completed)
            except Exception:
                pass
            result_server = getattr(worker, "_result_server", None)
            if result_server is not None and result_server is not getattr(
                self, "_automation_api_server", None
            ):
                result_server.stop()
            worker.deleteLater()
            receiver.deleteLater()
        workers[:] = remaining
        self._automation_api_toggle_workers = workers

    def shutdown(self) -> None:
        self._stop_automation_api()
        self._cleanup_automation_api_workers()
