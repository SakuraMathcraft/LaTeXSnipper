"""Subprocess path and bundled-resource helpers for the MathCraft worker."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from runtime.dependency_python import clean_path_value, python_env_root

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _worker_code_roots() -> list[Path]:
    candidates: list[Path] = []

    def add(path: str | Path | None) -> None:
        if not path:
            return
        try:
            p = Path(path).resolve()
        except Exception:
            return
        if p not in candidates:
            candidates.append(p)

    add(_repo_root())
    add(_repo_root() / "_internal")
    try:
        add(getattr(sys, "_MEIPASS", None))
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        add(exe_dir)
        add(exe_dir / "_internal")
    except Exception:
        pass
    try:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "mathcraft_ocr").is_dir() or (parent / "_internal" / "mathcraft_ocr").is_dir():
                add(parent)
                add(parent / "_internal")
    except Exception:
        pass
    return [root for root in candidates if root.is_dir()]


def _path_key(path: str | Path | None) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(str(path)))
    except Exception:
        return os.path.normcase(str(path))


def _path_entries(value: str | None) -> list[str]:
    entries: list[str] = []
    seen: set[str] = set()
    for raw in str(value or "").split(os.pathsep):
        text = clean_path_value(raw)
        if not text:
            continue
        key = _path_key(text)
        if key and key not in seen:
            entries.append(text)
            seen.add(key)
    return entries


def _dependency_python_path_prefix(pyexe: str | Path) -> list[str]:
    try:
        root = python_env_root(pyexe).resolve()
    except Exception:
        return []
    candidates = [
        root,
        root / "DLLs",
        root / "Library" / "bin",
        root / "Scripts",
    ]
    return [str(path) for path in candidates if path.exists()]


def _packaged_runtime_path_roots() -> set[str]:
    roots: set[str] = set()

    def add(path: str | Path | None) -> None:
        key = _path_key(path)
        if key:
            roots.add(key)

    try:
        add(getattr(sys, "_MEIPASS", None))
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        add(exe_dir)
        add(exe_dir / "_internal")
    except Exception:
        pass
    try:
        add(_repo_root() / "_internal")
    except Exception:
        pass
    return roots


def _worker_path_value(pyexe: str | Path, inherited_path: str | None) -> str:
    prefix = _dependency_python_path_prefix(pyexe)
    blocked = _packaged_runtime_path_roots()
    entries = [entry for entry in _path_entries(inherited_path) if _path_key(entry) not in blocked]
    merged: list[str] = []
    seen: set[str] = set()
    for entry in [*prefix, *entries]:
        key = _path_key(entry)
        if key and key not in seen:
            merged.append(entry)
            seen.add(key)
    return os.pathsep.join(merged)


def _failed_warmup_component_details(result: dict[str, Any]) -> list[str]:
    statuses = result.get("component_statuses", [])
    if not isinstance(statuses, list):
        return []
    details: list[str] = []
    for status in statuses:
        if not isinstance(status, dict) or bool(status.get("ready")):
            continue
        model_id = str(status.get("model_id") or "").strip()
        detail = str(status.get("detail") or "").strip()
        if model_id and detail:
            details.append(f"{model_id}: {detail}")
        elif detail:
            details.append(detail)
        elif model_id:
            details.append(f"{model_id}: not ready")
    return details


def _bundled_mathcraft_models_dir() -> Path | None:
    candidates: list[Path] = []
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "MathCraft" / "models")
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "MathCraft" / "models")
        candidates.append(exe_dir / "MathCraft" / "models")
    except Exception:
        pass
    try:
        for root in _worker_code_roots():
            candidates.append(root / "MathCraft" / "models")
    except Exception:
        pass
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate.resolve()
        except Exception:
            continue
    return None


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


def _same_path(left: str | Path | None, right: str | Path | None) -> bool:
    if not left or not right:
        return False
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))
    except Exception:
        return str(left) == str(right)
