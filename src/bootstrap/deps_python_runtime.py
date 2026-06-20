"""Python runtime discovery and path isolation for dependency installs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from shutil import which


SUPPORTED_SYSTEM_PYTHON_MIN = (3, 10)
SUPPORTED_SYSTEM_PYTHON_MAX_EXCLUSIVE = (3, 13)
PREFERRED_SYSTEM_PYTHON_VERSIONS = ((3, 11), (3, 12), (3, 10))


def _version_label(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def supported_system_python_range_label() -> str:
    min_label = _version_label(SUPPORTED_SYSTEM_PYTHON_MIN)
    max_major, max_minor = SUPPORTED_SYSTEM_PYTHON_MAX_EXCLUSIVE
    return f">={min_label},<{max_major}.{max_minor}"


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _linux_site_packages(pyexe: Path) -> Path | None:
    """Search for lib/pythonX.Y/site-packages typical of Linux/macOS venvs."""
    py_dir = pyexe.parent  # e.g. .venv/bin/
    # Also check one level up in case python is at prefix/bin/ inside prefix/
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


def _system_python3_score(pyexe: Path) -> int:
    """Return a suitability score for a system Python used to create a venv."""
    try:
        path_text = str(pyexe).lower()
        if os.name == "nt" and ("microsoft\\windowsapps" in path_text or "\\windowsapps\\python" in path_text):
            return 0
        if not pyexe.exists() or not pyexe.is_file():
            return 0
        base_check = (
            "import sys, venv; "
            f"v=sys.version_info[:2]; "
            f"raise SystemExit(0 if {SUPPORTED_SYSTEM_PYTHON_MIN!r} <= v < {SUPPORTED_SYSTEM_PYTHON_MAX_EXCLUSIVE!r} else 1)"
        )
        proc = subprocess.run(
            [str(pyexe), "-c", base_check],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **_hidden_subprocess_kwargs(),
        )
        if proc.returncode != 0:
            return 0

        ensurepip_proc = subprocess.run(
            [str(pyexe), "-c", "import ensurepip"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **_hidden_subprocess_kwargs(),
        )
        return 2 if ensurepip_proc.returncode == 0 else 1
    except Exception:
        return 0


def find_system_python3() -> Path | None:
    """Find a usable system Python 3 interpreter for creating dependency venvs."""
    versioned_names = [f"python{major}.{minor}" for major, minor in PREFERRED_SYSTEM_PYTHON_VERSIONS]
    path_python = which("python3")
    path_versioned = [which(name) for name in versioned_names]
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
        windows_install_roots = []
        if local_appdata:
            windows_install_roots.extend([
                Path(local_appdata) / "Programs" / "Python" / "Python311" / "python.exe",
                Path(local_appdata) / "Programs" / "Python" / "Python312" / "python.exe",
                Path(local_appdata) / "Programs" / "Python" / "Python310" / "python.exe",
            ])
        for root in (program_files, program_files_x86):
            if not root:
                continue
            windows_install_roots.extend([
                Path(root) / "Python311" / "python.exe",
                Path(root) / "Python312" / "python.exe",
                Path(root) / "Python310" / "python.exe",
            ])
        candidates = [
            which("python3.11"),
            which("python3.11.exe"),
            which("python3.12"),
            which("python3.12.exe"),
            which("python3.10"),
            which("python3.10.exe"),
            which("python"),
            which("python.exe"),
            which("python3"),
            which("python3.exe"),
            *path_versioned,
            path_python,
            *windows_install_roots,
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
            "/opt/homebrew/bin/python3.11",
            "/usr/local/bin/python3.11",
            *path_versioned,
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
            "/opt/homebrew/bin/python3.12",
            "/usr/local/bin/python3.12",
            "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3",
            "/opt/homebrew/bin/python3.10",
            "/usr/local/bin/python3.10",
            path_python,
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]
    else:
        candidates = [
            "/usr/bin/python3.11",
            "/usr/local/bin/python3.11",
            "/opt/homebrew/bin/python3.11",
            "/home/linuxbrew/.linuxbrew/bin/python3.11",
            *path_versioned,
            "/usr/bin/python3.12",
            "/usr/local/bin/python3.12",
            "/opt/homebrew/bin/python3.12",
            "/home/linuxbrew/.linuxbrew/bin/python3.12",
            "/usr/bin/python3.10",
            "/usr/local/bin/python3.10",
            "/opt/homebrew/bin/python3.10",
            "/home/linuxbrew/.linuxbrew/bin/python3.10",
            "/usr/bin/python3",
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
            "/home/linuxbrew/.linuxbrew/bin/python3",
            path_python,
        ]

    seen: set[str] = set()
    fallback: Path | None = None
    for candidate in candidates:
        if not candidate:
            continue
        p = Path(candidate)
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)

        score = _system_python3_score(p)
        if score >= 2:
            return p
        if score == 1 and fallback is None:
            fallback = p
    if fallback is not None:
        return fallback
    return None


def is_usable_python(pyexe: Path) -> bool:
    """Return whether a Python executable can start with its own standard library."""
    try:
        if not pyexe.exists() or not pyexe.is_file():
            return False
        proc = subprocess.run(
            [str(pyexe), "-c", "import encodings, sys; print(sys.version_info[:2])"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **_hidden_subprocess_kwargs(),
        )
        return proc.returncode == 0
    except Exception:
        return False


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
            if candidate.exists() and is_usable_python(candidate):
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
