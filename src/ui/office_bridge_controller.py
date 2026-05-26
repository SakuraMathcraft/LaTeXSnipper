"""Office bridge lifecycle controller for the main window."""

from __future__ import annotations

import secrets
import threading

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from integration.office.bridge_auth import OfficeBridgeAuth
from integration.office.bridge_server import OfficeBridgeServer


OFFICE_BRIDGE_ENABLED_KEY = "office_bridge_enabled"
OFFICE_BRIDGE_PORT_KEY = "office_bridge_port"
OFFICE_BRIDGE_TOKEN_KEY = "office_bridge_token"
DEFAULT_OFFICE_BRIDGE_PORT = 8765


class _OfficeOcrRequest:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.result = ""
        self.error = ""
        self.state = "waiting"
        self._lock = threading.Lock()

    def set_state(self, state: str) -> None:
        with self._lock:
            self.state = state

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return {"state": self.state}


class _OfficeScreenshotRecognitionService:
    def __init__(self, window) -> None:
        self._window = window

    def recognize_screenshot(self, payload: dict) -> dict:
        try:
            timeout = float(payload.get("timeout", 120))
        except Exception:
            timeout = 120.0
        text = self._window.request_office_screenshot_ocr(timeout=max(10.0, min(timeout, 300.0)))
        return {"latex": text}

    def recognition_status(self) -> dict:
        return self._window.office_screenshot_ocr_status()


class _OfficeBridgeToggleWorker(QThread):
    completed = pyqtSignal(bool, str, object)

    def __init__(
        self,
        *,
        action: str,
        port: int,
        token: str,
        server: OfficeBridgeServer | None = None,
        recognition_service: object | None = None,
    ) -> None:
        super().__init__()
        self._action = action
        self._port = port
        self._token = token
        self._server = server
        self._recognition_service = recognition_service

    def run(self) -> None:
        try:
            if self._action == "start":
                server = OfficeBridgeServer(
                    port=self._port,
                    auth=OfficeBridgeAuth(self._token),
                    recognition_service=self._recognition_service,
                )
                server.start()
                self.completed.emit(True, f"Office bridge: {server.base_url}", server)
                return
            if self._server is not None:
                self._server.stop()
            self.completed.emit(True, "Office bridge: disabled", None)
        except Exception as exc:
            self.completed.emit(False, str(exc), None)


class _OfficeBridgeResultReceiver(QObject):
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


class OfficeBridgeControllerMixin:
    def _office_bridge_enabled_pref(self) -> bool:
        try:
            return bool(self.cfg.get(OFFICE_BRIDGE_ENABLED_KEY, False))
        except Exception:
            return False

    def _office_bridge_port_pref(self) -> int:
        try:
            value = int(self.cfg.get(OFFICE_BRIDGE_PORT_KEY, DEFAULT_OFFICE_BRIDGE_PORT))
        except Exception:
            value = DEFAULT_OFFICE_BRIDGE_PORT
        return min(max(value, 1024), 65535)

    def _office_bridge_token(self) -> str:
        token = ""
        try:
            token = str(self.cfg.get(OFFICE_BRIDGE_TOKEN_KEY, "") or "").strip()
        except Exception:
            token = ""
        if token:
            return token
        token = secrets.token_urlsafe(32)
        try:
            self.cfg.set(OFFICE_BRIDGE_TOKEN_KEY, token)
        except Exception:
            pass
        return token

    def office_bridge_is_running(self) -> bool:
        return bool(getattr(self, "_office_bridge_server", None))

    def office_bridge_status_text(self) -> str:
        server = getattr(self, "_office_bridge_server", None)
        if server:
            return f"Office bridge: {server.base_url}"
        if self._office_bridge_enabled_pref():
            return "Office bridge: enabled, not running"
        return "Office bridge: disabled"

    def apply_office_bridge_startup_preference(self) -> None:
        if self._office_bridge_enabled_pref():
            self._start_office_bridge_async()

    def set_office_bridge_enabled_async(self, enabled: bool, callback=None) -> None:
        try:
            self.cfg.set(OFFICE_BRIDGE_ENABLED_KEY, bool(enabled))
        except Exception:
            pass

        if enabled:
            self._start_office_bridge_async(callback)
        else:
            self._stop_office_bridge_async(callback)

    def _office_bridge_workers(self) -> list[tuple[_OfficeBridgeToggleWorker, _OfficeBridgeResultReceiver]]:
        workers = getattr(self, "_office_bridge_toggle_workers", None)
        if workers is None:
            workers = []
            self._office_bridge_toggle_workers = workers
        return workers

    def _run_office_bridge_worker(self, worker: _OfficeBridgeToggleWorker, on_done) -> None:
        workers = self._office_bridge_workers()

        def _cleanup() -> None:
            try:
                workers.remove((worker, receiver))
            except ValueError:
                pass
            worker.deleteLater()
            receiver.deleteLater()

        receiver = _OfficeBridgeResultReceiver(on_done, _cleanup)
        workers.append((worker, receiver))
        worker.completed.connect(receiver.handle_completed)
        worker.start()

    def _start_office_bridge_async(self, callback=None) -> None:
        if getattr(self, "_office_bridge_server", None):
            if callback:
                QTimer.singleShot(0, lambda: callback(True, self.office_bridge_status_text()))
            return

        worker = _OfficeBridgeToggleWorker(
            action="start",
            port=self._office_bridge_port_pref(),
            token=self._office_bridge_token(),
            recognition_service=_OfficeScreenshotRecognitionService(self),
        )

        def _done(ok: bool, message: str, server: object) -> None:
            if ok:
                self._office_bridge_server = server
                print(f"[INFO] Office bridge started: {server.base_url}")
            else:
                try:
                    self.cfg.set(OFFICE_BRIDGE_ENABLED_KEY, False)
                except Exception:
                    pass
            if callback:
                callback(ok, message)

        self._run_office_bridge_worker(worker, _done)

    def _stop_office_bridge_async(self, callback=None) -> None:
        server = getattr(self, "_office_bridge_server", None)
        self._office_bridge_server = None
        if server is None:
            if callback:
                QTimer.singleShot(0, lambda: callback(True, "Office bridge: disabled"))
            return

        worker = _OfficeBridgeToggleWorker(
            action="stop",
            port=self._office_bridge_port_pref(),
            token=self._office_bridge_token(),
            server=server,
        )

        def _done(ok: bool, message: str, _server: object) -> None:
            if ok:
                print("[INFO] Office bridge stopped")
            if callback:
                callback(ok, message)

        self._run_office_bridge_worker(worker, _done)

    def _start_office_bridge(self) -> None:
        if getattr(self, "_office_bridge_server", None):
            return
        server = OfficeBridgeServer(
            port=self._office_bridge_port_pref(),
            auth=OfficeBridgeAuth(self._office_bridge_token()),
            recognition_service=_OfficeScreenshotRecognitionService(self),
        )
        server.start()
        self._office_bridge_server = server
        print(f"[INFO] Office bridge started: {server.base_url}")

    def _stop_office_bridge(self) -> None:
        server = getattr(self, "_office_bridge_server", None)
        self._office_bridge_server = None
        if server:
            server.stop()
            print("[INFO] Office bridge stopped")

    def request_office_screenshot_ocr(self, *, timeout: float = 120.0) -> str:
        if getattr(self, "_office_ocr_request", None) is not None:
            raise RuntimeError("another Office screenshot OCR request is already running")
        request = _OfficeOcrRequest()
        self._office_ocr_request = request
        try:
            if not request.event.wait(timeout):
                self._office_ocr_request = None
                raise RuntimeError("screenshot OCR timed out")
            if request.error:
                raise RuntimeError(request.error)
            return request.result
        finally:
            if getattr(self, "_office_ocr_request", None) is request:
                self._office_ocr_request = None

    def office_screenshot_ocr_status(self) -> dict[str, str]:
        request = getattr(self, "_office_ocr_request", None)
        if request is None:
            return {"state": "idle"}
        return request.snapshot()

    def set_office_screenshot_ocr_state(self, state: str) -> None:
        request = getattr(self, "_office_ocr_request", None)
        if request is not None:
            request.set_state(state)

    def _complete_office_screenshot_ocr(self, *, result: str = "", error: str = "") -> bool:
        request = getattr(self, "_office_ocr_request", None)
        if request is None:
            return False
        request.set_state("completed" if not error else "failed")
        request.result = str(result or "").strip()
        request.error = str(error or "").strip()
        request.event.set()
        return True
