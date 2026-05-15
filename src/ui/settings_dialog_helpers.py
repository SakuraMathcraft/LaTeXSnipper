import os
import subprocess
import sys
from pathlib import Path


def _resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def _apply_app_window_icon(win) -> None:
    try:
        from PyQt6.QtGui import QIcon
        icon_path = _resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass


def _select_open_file_with_icon(parent, title: str, initial_path: str, filter_: str):
    from PyQt6.QtWidgets import QFileDialog
    dlg = QFileDialog(parent, title, initial_path, filter_)
    dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    _apply_app_window_icon(dlg)
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return "", ""
    selected = dlg.selectedFiles()
    chosen_filter = dlg.selectedNameFilter()
    return (selected[0] if selected else ""), chosen_filter


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": _subprocess_creationflags()}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _existing_non_launcher_pyexe_from_env() -> str:
    pyexe = (os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
    if not pyexe or not os.path.exists(pyexe):
        return ""
    if getattr(sys, "frozen", False):
        try:
            if os.path.normcase(os.path.abspath(pyexe)) == os.path.normcase(os.path.abspath(sys.executable)):
                return ""
        except Exception:
            return ""
    return pyexe


def _mathcraft_code_roots() -> list[str]:
    roots: list[Path] = []

    def add(path: str | Path | None) -> None:
        if not path:
            return
        try:
            p = Path(path).resolve()
        except Exception:
            return
        if p.exists() and p not in roots:
            roots.append(p)

    current = Path(__file__).resolve()
    add(current.parent)
    for parent in current.parents:
        add(parent)
        add(parent / "_internal")
        if (parent / "mathcraft_ocr").is_dir() or (parent / "_internal" / "mathcraft_ocr").is_dir():
            break
    meipass = getattr(sys, "_MEIPASS", None)
    add(meipass)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        add(exe_dir)
        add(exe_dir / "_internal")
    return [str(path) for path in roots]
