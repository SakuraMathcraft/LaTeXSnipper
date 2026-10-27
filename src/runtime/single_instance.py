"""Single-instance ownership and local window activation."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from hashlib import sha256

from PyQt6.QtCore import QObject
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from runtime.app_paths import app_state_dir

_single_instance_lock = None
_activation_server = None


def _activation_name() -> str:
    owner = os.path.normcase(str(app_state_dir().resolve())).encode("utf-8")
    return "latexsnipper-" + sha256(owner).hexdigest()[:24]


class _ActivationServer(QObject):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.handler: Callable[[], None] | None = None
        self.pending = False
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        name = _activation_name()
        QLocalServer.removeServer(name)
        if not self.server.listen(name):
            raise RuntimeError(self.server.errorString())
        self.server.newConnection.connect(self._accept)

    def _accept(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            assert socket is not None
            socket.disconnected.connect(socket.deleteLater)
            socket.readyRead.connect(lambda socket=socket: self._receive(socket))
            socket.write(f"{os.getpid()}\n".encode("utf-8"))  # noqa: UP012
            self._receive(socket)

    def _receive(self, socket: QLocalSocket) -> None:
        if socket.canReadLine() and socket.readLine().data() == b"activate\n":
            if self.handler is None:
                self.pending = True
            else:
                self.handler()
            socket.disconnectFromServer()


def start_instance_activation(app: QObject) -> None:
    global _activation_server
    _activation_server = _ActivationServer(app)


def set_instance_activation_handler(handler: Callable[[], None]) -> None:
    if _activation_server is None:
        return
    _activation_server.handler = handler
    if _activation_server.pending:
        _activation_server.pending = False
        handler()


def activate_running_instance() -> None:
    socket = QLocalSocket()
    deadline = time.monotonic() + 2
    while True:
        socket.connectToServer(_activation_name())
        if socket.waitForConnected(100):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(socket.errorString())
        socket.abort()
        time.sleep(0.05)
    if os.name == "nt":
        import ctypes

        if not socket.canReadLine() and not socket.waitForReadyRead(2000):
            raise RuntimeError(socket.errorString())
        pid = int(socket.readLine().data().decode("utf-8"))
        ctypes.windll.user32.AllowSetForegroundWindow(pid)
    socket.write(b"activate\n")
    if socket.bytesToWrite() and not socket.waitForBytesWritten(2000):
        raise RuntimeError(socket.errorString())
    socket.disconnectFromServer()


def release_single_instance_lock() -> None:
    """Release the single-instance file lock explicitly."""
    global _single_instance_lock, _activation_server
    if _activation_server is not None:
        _activation_server.server.close()
        _activation_server.deleteLater()
        _activation_server = None
    fh = _single_instance_lock
    _single_instance_lock = None
    if fh is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            try:
                fh.seek(0)
            except Exception:
                pass
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
    except Exception:
        pass
    try:
        fh.close()
    except Exception:
        pass


def ensure_single_instance() -> bool:
    """Prevent multiple GUI instances using a file lock."""
    global _single_instance_lock
    lock_dir = app_state_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / "instance.lock"
    restart_flag = os.environ.get("LATEXSNIPPER_RESTART") == "1"
    attempts = 150 if restart_flag else 1
    delay = 0.2

    if os.name == "nt":
        try:
            import msvcrt

            for _ in range(attempts):
                fh = open(lock_file, "a+", encoding="utf-8")
                try:
                    fh.seek(0)
                except Exception:
                    pass
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    fh.close()
                    if restart_flag:
                        time.sleep(delay)
                        continue
                    return False
                _single_instance_lock = fh
                return True
            return False
        except Exception:
            return True

    try:
        import fcntl

        for _ in range(attempts):
            fh = open(lock_file, "a+", encoding="utf-8")
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                fh.close()
                if restart_flag:
                    time.sleep(delay)
                    continue
                return False
            _single_instance_lock = fh
            return True
        return False
    except Exception:
        return True
