"""Python runtime discovery and path isolation for dependency installs."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def site_packages_root(pyexe: Path):
    """Return the best matching site-packages directory for a private python.exe."""
    pyexe = Path(pyexe)
    py_dir = pyexe.parent
    candidates = [
        py_dir / "Lib" / "site-packages",
        py_dir.parent / "Lib" / "site-packages",
        py_dir.parent.parent / "Lib" / "site-packages",
    ]
    for site_packages in candidates:
        if site_packages.exists():
            return site_packages
    return None


def inject_private_python_paths(pyexe: Path) -> None:
    """Inject private site-packages in source mode without polluting packaged mode."""
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        print("[INFO] 打包模式：跳过路径注入，AI 模型将在子进程中使用独立 Python")
        return

    site_packages = site_packages_root(Path(pyexe))
    if not site_packages:
        return

    bad_markers = [
        os.sep + ".venv" + os.sep,
        os.sep + "env" + os.sep,
        os.sep + "venv" + os.sep,
    ]
    sys.path[:] = [p for p in sys.path if not any(marker in p for marker in bad_markers)]
    if str(site_packages) not in sys.path:
        sys.path.insert(0, str(site_packages))

    if os.name == "nt":
        try:
            dlls_dir = Path(pyexe).parent / "DLLs"
            if dlls_dir.exists():
                os.add_dll_directory(str(dlls_dir))
        except Exception:
            pass


def find_local_python311_installer(deps_dir: Path, module_file: str) -> Path | None:
    """Locate the bundled/local Python 3.11 installer without downloading anything."""
    deps_dir = Path(deps_dir)
    candidates: list[Path] = []
    try:
        candidates.append(deps_dir / "python-3.11.0-amd64.exe")
    except Exception:
        pass
    try:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "python-3.11.0-amd64.exe")
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "python-3.11.0-amd64.exe")
        candidates.append(exe_dir / "python-3.11.0-amd64.exe")
    except Exception:
        pass
    candidates.extend([
        Path(module_file).resolve().parent.parent / "python-3.11.0-amd64.exe",
        Path.cwd() / "python-3.11.0-amd64.exe",
    ])
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def iter_python_candidates(base_dir: Path) -> list[Path]:
    """Return likely python.exe candidates inside the selected dependency directory."""
    base_dir = Path(base_dir)
    candidates = [
        base_dir / "python.exe",
        base_dir / "Scripts" / "python.exe",
        base_dir / "python311" / "python.exe",
        base_dir / "python311" / "Scripts" / "python.exe",
        base_dir / "Python311" / "python.exe",
        base_dir / "Python311" / "Scripts" / "python.exe",
        base_dir / "python_full" / "python.exe",
        base_dir / "venv" / "Scripts" / "python.exe",
        base_dir / ".venv" / "Scripts" / "python.exe",
    ]
    try:
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if name in {"venv", ".venv", "python_full"} or name.startswith("python"):
                candidates.extend([
                    child / "python.exe",
                    child / "Scripts" / "python.exe",
                ])
    except Exception:
        pass

    seen: set[str] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def find_existing_python(base_dir: Path) -> Path | None:
    """Reuse any existing python.exe inside the selected dependency directory."""
    for candidate in iter_python_candidates(base_dir):
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def normalize_deps_base_dir(selected_dir: Path) -> Path:
    """Normalize user-selected dependency base directories."""
    path = Path(selected_dir)
    try:
        name = path.name.lower()
    except Exception:
        return path

    looks_like_python_leaf = name in {"venv", ".venv", "python_full"} or name.startswith("python")
    if not looks_like_python_leaf:
        return path

    existing_py = find_existing_python(path)
    if existing_py is not None:
        return path

    parent = path.parent
    try:
        if parent and str(parent) != str(path):
            return parent
    except Exception:
        pass
    return path
