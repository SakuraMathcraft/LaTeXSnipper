import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from typing import Any

from backend.daemon_protocol import DEFAULT_HOST, find_free_port, recv_line, send_line
from backend.model import get_deps_python
from backend.rpc_contract import (
    METHOD_HEALTH,
    METHOD_SHUTDOWN,
    METHOD_TASK_CANCEL,
    METHOD_TASK_STATUS,
    METHOD_TASK_SUBMIT,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_ERROR,
    TASK_STATUS_SUCCESS,
)


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


class LocalDaemonClient:
    def __init__(
        self,
        model_name: str = "pix2text",
        host: str = DEFAULT_HOST,
        port: int | None = None,
        log_cb=None,
    ):
        self.model_name = model_name
        self.host = host
        self.port = int(port) if port else int(find_free_port(host))
        self.token = secrets.token_hex(16)
        self.proc: subprocess.Popen[str] | None = None
        self._log_cb = log_cb
        self._stdout_thread: threading.Thread | None = None
        self._stdout_stop = threading.Event()
        self.last_error: dict[str, Any] | None = None

    def _log(self, msg: str) -> None:
        line = str(msg or "").strip()
        if not line:
            return
        if callable(self._log_cb):
            try:
                self._log_cb(line)
                return
            except Exception:
                pass
        try:
            print(line, flush=True)
        except Exception:
            pass

    def _is_alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def _start_stdout_pump(self) -> None:
        proc = self.proc
        if not proc or not proc.stdout:
            return
        if self._stdout_thread and self._stdout_thread.is_alive():
            return
        self._stdout_stop.clear()

        def _pump() -> None:
            try:
                while not self._stdout_stop.is_set():
                    line = proc.stdout.readline()
                    if not line:
                        break
                    self._log(f"[daemon/stdout] {line.rstrip()}")
            except Exception as e:
                self._log(f"[WARN] daemon stdout pump error: {e}")

        self._stdout_thread = threading.Thread(target=_pump, daemon=True)
        self._stdout_thread.start()

    def start(self, timeout_sec: float = 15.0) -> bool:
        if self._is_alive():
            return True
        pyexe = get_deps_python() or sys.executable
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        argv = [
            pyexe,
            "-m",
            "backend.daemon_server",
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--token",
            self.token,
            "--model",
            self.model_name,
        ]
        try:
            self.proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=_subprocess_creationflags(),
            )
        except Exception:
            self.proc = None
            self.last_error = {"error": "spawn failed", "error_type": "SpawnError"}
            return False

        self._start_stdout_pump()
        self._log(
            f"[INFO] daemon spawn ok (pid={getattr(self.proc, 'pid', None)}, host={self.host}, port={self.port})"
        )
        start = time.time()
        while (time.time() - start) < timeout_sec:
            if not self._is_alive():
                break
            try:
                out = self.request(METHOD_HEALTH, {}, timeout_sec=1.0, autostart=False)
                if out.get("ok"):
                    self.last_error = None
                    self._log("[INFO] daemon health check passed")
                    return True
            except Exception:
                time.sleep(0.15)
        self.last_error = {"error": "health check timeout", "error_type": "TimeoutError"}
        self._log("[WARN] daemon health check timeout")
        return False

    def stop(self, force: bool = False) -> None:
        p = self.proc
        if not p:
            return
        self._log(f"[INFO] daemon stop requested (pid={getattr(p, 'pid', None)})")
        if p.poll() is None:
            try:
                self.request(METHOD_SHUTDOWN, {}, timeout_sec=1.0, autostart=False)
            except Exception:
                pass
            if force and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        self._stdout_stop.set()
        try:
            if self._stdout_thread and self._stdout_thread.is_alive():
                self._stdout_thread.join(timeout=0.8)
        except Exception:
            pass
        self._stdout_thread = None
        self.proc = None
        self._log("[INFO] daemon stopped")

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_sec: float = 30.0,
        autostart: bool = True,
    ) -> dict[str, Any]:
        if autostart and not self._is_alive():
            if not self.start():
                detail = self.last_error or {"error": "daemon start failed", "error_type": "StartError"}
                raise RuntimeError(f"daemon start failed: {detail.get('error')}")

        req = {"token": self.token, "method": method, "params": params or {}}
        with socket.create_connection((self.host, self.port), timeout=timeout_sec) as sock:
            sock.settimeout(timeout_sec)
            send_line(sock, req)
            resp = recv_line(sock)
        if not isinstance(resp, dict):
            raise RuntimeError("invalid daemon response")
        if not resp.get("ok", False):
            self.last_error = {
                "method": method,
                "error": str(resp.get("error", "unknown")),
                "error_type": str(resp.get("error_type", "RemoteError")),
            }
        return resp

    def submit_task(
        self,
        kind: str,
        params: dict[str, Any] | None = None,
        timeout_sec: float = 15.0,
    ) -> str:
        resp = self.request(
            METHOD_TASK_SUBMIT,
            {"kind": str(kind or ""), "params": params or {}},
            timeout_sec=timeout_sec,
            autostart=True,
        )
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error", "task submit failed")))
        task_id = str(resp.get("task_id", "") or "")
        if not task_id:
            raise RuntimeError("task submit failed: empty task_id")
        return task_id

    def get_task_status(self, task_id: str, timeout_sec: float = 10.0) -> dict[str, Any]:
        resp = self.request(
            METHOD_TASK_STATUS,
            {"task_id": str(task_id or "")},
            timeout_sec=timeout_sec,
            autostart=True,
        )
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error", "task status failed")))
        task = resp.get("task")
        if not isinstance(task, dict):
            raise RuntimeError("task status invalid")
        return task

    def cancel_task(self, task_id: str, timeout_sec: float = 5.0) -> bool:
        resp = self.request(
            METHOD_TASK_CANCEL,
            {"task_id": str(task_id or "")},
            timeout_sec=timeout_sec,
            autostart=True,
        )
        return bool(resp.get("ok"))

    def wait_task(
        self,
        task_id: str,
        timeout_sec: float = 300.0,
        poll_interval_sec: float = 0.2,
        progress_cb=None,
        cancel_cb=None,
    ) -> dict[str, Any]:
        start = time.time()
        last_progress = (-1, -1)
        while True:
            if callable(cancel_cb):
                try:
                    if bool(cancel_cb()):
                        try:
                            self.cancel_task(task_id, timeout_sec=2.0)
                        except Exception:
                            pass
                        raise RuntimeError("已取消")
                except RuntimeError:
                    raise
                except Exception:
                    pass

            task = self.get_task_status(task_id, timeout_sec=10.0)
            status = str(task.get("status", "") or "")
            current = int(task.get("progress_current", 0) or 0)
            total = int(task.get("progress_total", 0) or 0)
            if callable(progress_cb) and (current, total) != last_progress:
                try:
                    progress_cb(current, total, task)
                except Exception:
                    pass
                last_progress = (current, total)

            if status == TASK_STATUS_SUCCESS:
                return task
            if status == TASK_STATUS_CANCELLED:
                raise RuntimeError("已取消")
            if status == TASK_STATUS_ERROR:
                err = str(task.get("error", "task failed") or "task failed")
                raise RuntimeError(err)

            if (time.time() - start) > timeout_sec:
                raise RuntimeError(f"task timeout ({timeout_sec:.0f}s)")
            time.sleep(max(float(poll_interval_sec), 0.05))
