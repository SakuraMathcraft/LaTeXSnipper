"""Python runtime discovery and path isolation for dependency installs."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _linux_site_packages(pyexe: Path) -> Path | None:
    """Search for lib/pythonX.Y/site-packages typical of Linux/macOS venvs."""
    py_dir = pyexe.parent  # e.g. .venv/bin/
    # Check for site-packages relative to the python executable location
    for p in (py_dir.parent, py_dir.parent.parent, py_dir):
        try:
            lib = p / "lib"
            if lib.is_dir():
                for child in sorted(lib.iterdir(), reverse=True):
                    if child.is_dir() and child.name.startswith("python"):
                        sp = child / "site-packages"
                        if sp.exists():
                            return sp
        except Exception:
            continue
    return None


def site_packages_root(pyexe: Path):
    """Return the best matching site-packages directory for a python executable."""
    pyexe = Path(pyexe)
    py_dir = pyexe.parent

    # Windows-style paths
    win_candidates = [
        py_dir / "Lib" / "site-packages",
        py_dir.parent / "Lib" / "site-packages",
        py_dir.parent.parent / "Lib" / "site-packages",
    ]
    for site_packages in win_candidates:
        if site_packages.exists():
            return site_packages

    # Linux/macOS-style paths (lib/pythonX.Y/site-packages)
    linux_sp = _linux_site_packages(pyexe)
    if linux_sp is not None:
        return linux_sp

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
    """Locate the bundled/local Python 3.11 installer without downloading anything.

    Windows-only: the .exe installer only exists on Windows.
    """
    if os.name != "nt":
        return None
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


def find_system_python3() -> Path | None:
    """Find a usable system Python 3 interpreter on Linux/macOS.

    On Windows this always returns None — the .exe installer path is used instead.
    """
    if os.name == "nt":
        return None
    # Common system paths in order of preference
    candidates = [
        "/usr/bin/python3",
        "/usr/local/bin/python3",
        "/opt/homebrew/bin/python3",
        "/home/linuxbrew/.linuxbrew/bin/python3",
    ]
    for candidate in candidates:
        p = Path(candidate)
        if p.exists() and p.is_file():
            return p
    # Fallback: search PATH
    import shutil as _shutil
    which = _shutil.which("python3")
    if which:
        return Path(which)
    return None


def iter_python_candidates(base_dir: Path) -> list[Path]:
    """Return likely python executable candidates inside the selected dependency directory."""
    base_dir = Path(base_dir)
    # Executable names: platform-dependent
    if os.name == "nt":
        exe_names = ("python.exe",)
        scripts_dir = "Scripts"
    else:
        exe_names = ("python3", "python")
        scripts_dir = "bin"

    candidates: list[Path] = []
    for exe_name in exe_names:
        candidates.extend([
            base_dir / exe_name,
            base_dir / scripts_dir / exe_name,
            base_dir / "python311" / exe_name,
            base_dir / "python311" / scripts_dir / exe_name,
            base_dir / "Python311" / exe_name,
            base_dir / "Python311" / scripts_dir / exe_name,
            base_dir / "python_full" / exe_name,
            base_dir / "venv" / scripts_dir / exe_name,
            base_dir / ".venv" / scripts_dir / exe_name,
        ])
    try:
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if name in {"venv", ".venv", "python_full"} or name.startswith("python"):
                for exe_name in exe_names:
                    candidates.extend([
                        child / exe_name,
                        child / scripts_dir / exe_name,
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
