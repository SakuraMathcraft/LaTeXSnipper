"""Coordinate cooperative downloads and pip process suspension."""

import threading
import psutil


class DownloadControl:
    def __init__(self, pause_event):
        self.event = pause_event
        self.proc = None
        self._suspended = []
        self._lock = threading.RLock()

    def set_process(self, proc):
        with self._lock:
            self._resume()
            self.proc = proc
            if proc is not None and not self.event.is_set():
                self._suspend()

    def _suspend(self):
        if self.proc is None or self.proc.poll() is not None:
            return
        root = psutil.Process(self.proc.pid)
        root.suspend()
        self._suspended.append(root)
        for child in root.children(recursive=True):
            try:
                child.suspend()
                self._suspended.append(child)
            except psutil.NoSuchProcess:
                pass

    def _resume(self):
        for proc in reversed(self._suspended):
            try:
                proc.resume()
            except psutil.NoSuchProcess:
                pass
        self._suspended.clear()

    def set_paused(self, paused):
        with self._lock:
            if paused:
                self.event.clear()
                try:
                    self._suspend()
                except psutil.Error:
                    self.event.set()
                    self._resume()
                    raise
            else:
                self._resume()
                self.event.set()


def wait_for_download(pause_event, stop_event):
    while pause_event is not None and not pause_event.is_set():
        if stop_event is not None and stop_event.is_set():
            return False
        pause_event.wait(0.1)
    return stop_event is None or not stop_event.is_set()
