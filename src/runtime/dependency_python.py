from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable


def clean_path_value(value: str | Path | None) -> str:
    text = str(value or "").strip()
    while text and text[0] in {"'", '"'}:
        text = text[1:].strip()
    while text and text[-1] in {"'", '"'}:
        text = text[:-1].strip()
    return os.path.expandvars(text)


def normalize_path(path: str | Path | None) -> Path | None:
    text = clean_path_value(path)
    if not text:
        return None
    try:
        return Path(text).expanduser()
    except Exception:
        return None


def python_env_root(pyexe: str | Path) -> Path:
    path = Path(pyexe)
    return path.parent.parent if path.parent.name.lower() in {"scripts", "bin"} else path.parent


def normalize_deps_base_dir(path: str | Path | None) -> Path | None:
    raw = normalize_path(path)
    if raw is None:
        return None
    try:
        from bootstrap.deps_python_runtime import normalize_deps_base_dir as normalize_base

        return normalize_base(raw)
    except Exception:
        name = raw.name.lower()
        if name in {"venv", ".venv", "python_full"} or name.startswith("python"):
            return raw.parent if raw.parent != raw else raw
        return raw


def find_dependency_python(base_dir: str | Path | None) -> Path | None:
    base = normalize_deps_base_dir(base_dir)
    if base is None:
        return None
    try:
        from bootstrap.deps_python_runtime import find_existing_python

        return find_existing_python(base)
    except Exception:
        return None


def _existing_file(path: str | Path | None) -> str:
    candidate = normalize_path(path)
    if candidate is None:
        return ""
    try:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    except Exception:
        return ""
    return ""


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_dependency_python(
    configured_base_dirs: Iterable[str | Path | None] = (),
    *,
    fallback_to_current: bool = True,
) -> str:
    env_py = _existing_file(os.environ.get("LATEXSNIPPER_PYEXE"))
    if env_py:
        return env_py

    bases: list[str | Path | None] = []
    bases.extend(configured_base_dirs)
    bases.extend((
        os.environ.get("LATEXSNIPPER_INSTALL_BASE_DIR"),
        os.environ.get("LATEXSNIPPER_DEPS_DIR"),
        _project_root() / "tools" / "deps",
    ))
    for base in bases:
        pyexe = find_dependency_python(base)
        if pyexe is not None:
            return str(pyexe)

    current = _existing_file(sys.executable)
    if fallback_to_current and current:
        return current
    return ""
