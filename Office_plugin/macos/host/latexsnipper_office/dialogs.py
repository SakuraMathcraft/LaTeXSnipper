"""Native JSON open/save panels for preset import and export.

Server requests run on worker threads, but AppKit panels must run on the main
thread, which the host's run loop owns. Requests are therefore handed to the
main thread and the worker waits for the answer.
"""

from __future__ import annotations

import threading
from pathlib import Path


class NativeFileChooser:
    def open_json(self, title: str) -> Path | None:
        return self._on_main_thread(lambda: _open_panel(title))

    def save_json(self, title: str, suggested_name: str) -> Path | None:
        return self._on_main_thread(lambda: _save_panel(title, suggested_name))

    @staticmethod
    def _on_main_thread(show) -> Path | None:
        from Foundation import NSThread
        from PyObjCTools import AppHelper

        if NSThread.isMainThread():
            return show()
        result: dict[str, Path | None] = {}
        done = threading.Event()

        def run() -> None:
            try:
                result["path"] = show()
            finally:
                done.set()

        AppHelper.callAfter(run)
        done.wait()
        return result.get("path")


def _bring_to_front() -> None:
    from AppKit import NSApplication

    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def _documents() -> str:
    return str(Path.home() / "Documents")


def _open_panel(title: str) -> Path | None:
    from AppKit import NSModalResponseOK, NSOpenPanel
    from Foundation import NSURL

    _bring_to_front()
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setMessage_(title)
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(False)
    panel.setAllowedFileTypes_(["json"])
    panel.setDirectoryURL_(NSURL.fileURLWithPath_(_documents()))
    if panel.runModal() != NSModalResponseOK:
        return None
    return Path(str(panel.URLs()[0].path()))


def _save_panel(title: str, suggested_name: str) -> Path | None:
    from AppKit import NSModalResponseOK, NSSavePanel
    from Foundation import NSURL

    _bring_to_front()
    panel = NSSavePanel.savePanel()
    panel.setTitle_(title)
    panel.setMessage_(title)
    panel.setAllowedFileTypes_(["json"])
    panel.setNameFieldStringValue_(suggested_name)
    panel.setDirectoryURL_(NSURL.fileURLWithPath_(_documents()))
    if panel.runModal() != NSModalResponseOK:
        return None
    path = Path(str(panel.URL().path()))
    return path if path.suffix.lower() == ".json" else path.with_suffix(".json")
