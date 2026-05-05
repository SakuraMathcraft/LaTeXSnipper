"""Qt symbols used by dependency bootstrap with non-GUI fallbacks for tests."""

from __future__ import annotations

import threading

__all__ = ["QIcon", "QThread", "QTimer", "pyqtSignal"]

try:
    from PyQt6.QtCore import QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import QIcon
except Exception:

    class _Signal:
        def __init__(self):
            self._handlers = []

        def connect(self, fn):
            if callable(fn) and fn not in self._handlers:
                self._handlers.append(fn)

        def disconnect(self, fn):
            try:
                self._handlers.remove(fn)
            except ValueError:
                pass

        def emit(self, *args, **kwargs):
            for fn in list(self._handlers):
                try:
                    fn(*args, **kwargs)
                except Exception:
                    pass

    class _SignalDescriptor:
        def __set_name__(self, _owner, name):
            self._name = f"__sig_{name}"

        def __get__(self, instance, _owner):
            if instance is None:
                return self
            sig = instance.__dict__.get(self._name)
            if sig is None:
                sig = _Signal()
                instance.__dict__[self._name] = sig
            return sig

    def pyqtSignal(*_args, **_kwargs):
        return _SignalDescriptor()

    class QThread:
        def __init__(self, *args, **kwargs):
            super().__init__()
            self._thread = None
            self._running = False

        def start(self):
            if self._thread and self._thread.is_alive():
                return

            def _runner():
                try:
                    self._running = True
                    self.run()
                finally:
                    self._running = False

            self._thread = threading.Thread(target=_runner, daemon=True)
            self._thread.start()

        def run(self):
            pass

        def isRunning(self):
            return bool(self._thread and self._thread.is_alive())

        def wait(self, timeout_ms=None):
            if not self._thread:
                return True
            timeout_s = None
            if timeout_ms is not None:
                try:
                    timeout_s = max(0.0, float(timeout_ms) / 1000.0)
                except Exception:
                    timeout_s = None
            self._thread.join(timeout=timeout_s)
            return not self._thread.is_alive()

    class QTimer:
        def __init__(self, *_args, **_kwargs):
            self.timeout = _Signal()

        def start(self, *_args, **_kwargs):
            return

        def stop(self):
            return

        @staticmethod
        def singleShot(_ms, fn):
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass

    class QIcon:
        def __init__(self, *_args, **_kwargs):
            pass
