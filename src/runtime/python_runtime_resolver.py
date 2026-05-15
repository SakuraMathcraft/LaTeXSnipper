"""Python runtime and dependency-directory resolver."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from runtime.app_paths import app_config_path, app_state_dir, get_app_root, is_packaged_mode
from ui.theme_controller import apply_theme_mode, read_theme_mode_from_config
from ui.window_helpers import (
    apply_app_window_icon as _apply_app_window_icon,
    select_existing_directory_with_icon as _select_existing_directory_with_icon,
)

APP_DIR = get_app_root()


def _app_state_dir() -> Path:
    return app_state_dir()


def _get_app_root() -> Path:
    return APP_DIR


def _is_packaged_mode() -> bool:
    return is_packaged_mode()


def _project_root() -> Path:
    return APP_DIR.parent if APP_DIR.name.lower() == "src" else APP_DIR


def _developer_deps_dir() -> Path:
    return _project_root() / "tools" / "deps"


def _initial_deps_dir() -> Path:
    env_value = os.environ.get("LATEXSNIPPER_DEPS_DIR")
    if env_value:
        return Path(env_value)
    if _is_packaged_mode() and os.name != "nt":
        return _app_state_dir() / "deps"
    current_dev_base = _current_dev_install_base_dir()
    if current_dev_base is not None:
        return current_dev_base
    return _developer_deps_dir()


def _same_exe(a: str, b: str) -> bool:
    try:
        return os.path.abspath(a).lower() == os.path.abspath(b).lower()
    except Exception:
        return False


def _config_path() -> Path:
    return app_config_path()


def _looks_like_packaged_deps_dir(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        text = str(path.resolve()).lower()
    except Exception:
        text = str(path).lower()
    normalized = text.replace("\\", "/")
    return ("_internal" in normalized) and normalized.endswith("/deps")


def _default_python_exe_name() -> str:
    return "python.exe" if os.name == "nt" else "python3"


def _default_packaged_user_deps_dir() -> Path:
    return _app_state_dir() / "deps"


def _python_candidate_usable(pyexe: Path) -> bool:
    """Return whether a Python executable can start with its own standard library."""
    try:
        if not pyexe.exists() or not pyexe.is_file():
            return False
        proc = subprocess.run(
            [str(pyexe), "-c", "import encodings, sys; print(sys.version_info[:2])"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **_win_subprocess_kwargs(),
        )
        return proc.returncode == 0
    except Exception:
        return False


def _iter_install_base_python_candidates(base_dir: Path) -> list[Path]:
    """Return likely python.exe candidates inside a selected dependency base directory."""
    base_dir = Path(base_dir)
    # Common candidates for both Windows and Linux
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
    # Linux-specific candidates (python3, venv/bin/python3)
    if os.name != "nt":
        candidates.extend([
            base_dir / "python3",
            base_dir / "bin" / "python3",
            base_dir / "python311" / "bin" / "python3",
            base_dir / "venv" / "bin" / "python3",
            base_dir / ".venv" / "bin" / "python3",
        ])
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


def _find_install_base_python(base_dir: Path) -> Path | None:
    """Reuse any existing python.exe inside the dependency directory."""
    for candidate in _iter_install_base_python_candidates(base_dir):
        try:
            if candidate.exists() and _python_candidate_usable(candidate):
                return candidate
        except Exception:
            continue
    return None


def _normalize_install_base_dir(selected_dir: Path) -> Path:
    """
    Normalize the dependency base directory.

    The chosen path should be the base directory that contains a nested
    `python311`, not the leaf `python311` directory itself. If the user or a
    previous partial initialization points at an empty leaf like `.../python311`,
    fold it back to the parent to avoid `python311/python311`.
    """
    path = Path(selected_dir)
    try:
        name = path.name.lower()
    except Exception:
        return path

    looks_like_python_leaf = (
        name in {"venv", ".venv", "python_full"}
        or name.startswith("python")
    )
    if not looks_like_python_leaf:
        return path

    existing_py = _find_install_base_python(path)
    if existing_py is not None:
        return path

    parent = path.parent
    try:
        if parent and str(parent) != str(path):
            return parent
    except Exception:
        pass
    return path


def _current_dev_install_base_dir() -> Path | None:
    if _is_packaged_mode():
        return None
    try:
        exe_path = Path(sys.executable).resolve()
        exe_name = exe_path.name.lower()
        parent_name = exe_path.parent.name.lower()
        if exe_name == "python.exe":
            if parent_name == "deps":
                base = exe_path.parent
                if base.exists():
                    return base
            if exe_path.parent.parent.name.lower() == "deps" and (
                parent_name.startswith("python") or parent_name in {"venv", ".venv", "python_full", "scripts"}
            ):
                base = exe_path.parent.parent
                if base.exists():
                    return base
    except Exception:
        pass
    try:
        base = _developer_deps_dir().resolve()
        pyexe = _find_install_base_python(base)
        if pyexe is not None and _same_exe(str(pyexe), sys.executable):
            return base
    except Exception:
        pass
    return None


def _read_install_base_dir() -> Path | None:
    cfg = _config_path()
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text("utf-8"))
            p = _normalize_install_base_dir(Path(data.get("install_base_dir", "")).expanduser())
            if p and p.exists():
                if _looks_like_packaged_deps_dir(p):
                    return None
                if _is_packaged_mode() and os.name != "nt":
                    existing_py = _find_install_base_python(p)
                    if existing_py is None and str(p).startswith("/usr/"):
                        return None
                return p
        except Exception:
            pass
    return None


def _get_bundled_deps_dir_for_packaged() -> Path | None:
    """Return the bundled dependency directory for packaged builds."""
    if not _is_packaged_mode():
        return None
    candidates: list[Path] = []
    try:
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)
            candidates.append(meipass / "deps")
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "_internal" / "deps",
            exe_dir / "deps",
        ])
    except Exception:
        pass
    seen: set[str] = set()
    for base in candidates:
        try:
            key = str(base.resolve()).lower()
        except Exception:
            key = str(base).lower()
        if key in seen:
            continue
        seen.add(key)
        pyexe = _find_install_base_python(base)
        if pyexe is not None and pyexe.exists():
            return base
    return None


def _select_install_base_dir() -> Path:
    """Prompt for the dependency installation base directory."""
    from pathlib import Path
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFont
        app = QApplication.instance() or QApplication([])
        apply_theme_mode(read_theme_mode_from_config())
        _apply_app_window_icon(app)
        font = QFont("Microsoft YaHei UI", 9)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)
        d = _select_existing_directory_with_icon(None, "请选择依赖安装目录", os.path.expanduser("~"))
        if d:
            p = _normalize_install_base_dir(Path(d))
            p.mkdir(parents=True, exist_ok=True)
            return p
        else:

            raise RuntimeError("user canceled")
    except RuntimeError:
        raise
    except Exception as e:
        print(f"[ERROR] 目录选择失败: {e}")
        raise RuntimeError("user canceled")


def _save_install_base_dir(p: Path) -> None:
    """Save the dependency directory to the config file."""
    try:
        p = _normalize_install_base_dir(p)
        cfg = {}
        c = _config_path()
        if c.exists():
            cfg = json.loads(c.read_text("utf-8") or "{}")
        cfg["install_base_dir"] = str(p)
        c.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] 配置已保存: {p}")
    except Exception as e:
        print(f"[WARN] 保存配置失败: {e}")


def resolve_install_base_dir() -> Path:
    """Resolve the dependency installation base directory."""
    import time

    if not _is_packaged_mode():
        current_dev_base = _current_dev_install_base_dir()
        if current_dev_base is not None:
            return current_dev_base


    p = _read_install_base_dir()

    if not p and _is_packaged_mode() and os.name != "nt":
        p = _default_packaged_user_deps_dir()
        p.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Packaged Linux/macOS dependency directory: {p}")
        _save_install_base_dir(p)

    if not p and os.name == "nt":
        bundled = _get_bundled_deps_dir_for_packaged()
        if bundled:
            try:
                bundled.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            print(f"[INFO] 首次启动：自动使用内置依赖目录: {bundled}")
            _save_install_base_dir(bundled)
            p = bundled


    if not p:
        print("[INFO] 首次启动，请选择依赖安装目录...")
        try:
            p = _select_install_base_dir()
        except RuntimeError:
            print("[ERROR] 用户取消了目录选择，退出。")
            time.sleep(2)
            sys.exit(7)
    p = _normalize_install_base_dir(p)

    py_exe = _find_install_base_python(p)


    if py_exe is not None and py_exe.exists():
        print(f"[OK] ✓ 已复用目录内 Python: {py_exe}")
        _save_install_base_dir(p)
        return p

    print(f"[INFO] 选定目录未检测到可复用 Python，将由依赖向导按需初始化: {p / 'python311'}")
    _save_install_base_dir(p)
    return p


def _current_runtime_roots() -> list[str]:
    """Collect interpreter roots and standard-library paths that must survive cleanup."""
    bases: set[Path] = set()
    for b in (getattr(sys, "base_prefix", None),
              getattr(sys, "exec_prefix", None),
              getattr(sys, "prefix", None)):
        if b:
            try:
                bases.add(Path(b).resolve())
            except Exception:
                pass

    roots: set[str] = set()
    for base in bases:
        roots.update({
            str(base),
            str(base / "DLLs"),
            str(base / "Lib"),
            str(base / "Lib" / "site-packages"),
        })

    try:
        for p in list(sys.path):
            try:
                q = Path(p)
                if q.name.lower().startswith("python") and q.suffix.lower() == ".zip":
                    roots.add(str(q.resolve()))
            except Exception:
                continue
    except Exception:
        pass
    return list(roots)


def _sanitize_sys_path(pyexe: str | None, base_dir: Path):
    """Sanitize sys.path while preserving project, private interpreter, and runtime stdlib paths."""
    try:
        allowed = [Path(r).resolve() for r in _allowed_roots_for(pyexe, base_dir)]
        runtime_roots = [Path(r).resolve() for r in _current_runtime_roots()]

        def under_any(q: Path, bases: list[Path]) -> bool:
            ql = str(q).lower()
            for b in bases:
                bl = str(b).lower()
                if ql.startswith(bl):
                    return True
            return False

        def ok(item: str) -> bool:
            try:
                q = Path(item).resolve()
            except Exception:
                return False
            sl = str(q).lower()

            if "windowsapps\\python" in sl or "microsoft\\windowsapps" in sl:
                return False


            if under_any(q, allowed) or under_any(q, runtime_roots):
                return True


            try:
                import re
                if re.fullmatch(r"python\d+\.zip", q.name.lower()):
                    return True
            except Exception:
                pass
            return False
        newp = [p for p in list(sys.path) if ok(p)]


        try:
            src_dir = str(Path(__file__).resolve().parent)
            if src_dir not in newp:
                newp.insert(0, src_dir)
        except Exception:
            pass

        sys.path[:] = newp
    except Exception:
        pass


def _in_ide() -> bool:
    """Detect whether the app is running under an IDE or debugger console."""
    e = os.environ
    return any(k in e for k in ("PYCHARM_HOSTED", "PYCHARM_DISPLAY_PORT", "PYDEV_CONSOLE_ENCODING"))


def _python_base_from_exe(pyexe: str) -> Path:
    p = Path(pyexe)
    return p.parent.parent if p.parent.name.lower() in {"scripts", "bin"} else p.parent


def _stdlib_zip_versions(base: Path) -> list[tuple[int, int, str]]:
    """Return pythonXY.zip versions found under the base directory."""
    out: list[tuple[int, int, str]] = []
    try:
        for p in base.glob("python*.zip"):
            bn = p.name
            m = re.fullmatch(r"python(\d)(\d+)\.zip", bn, re.I)
            if m:
                out.append((int(m.group(1)), int(m.group(2)), str(p)))
    except Exception:
        pass
    return out


def _same_runtime_version_as_current(pyexe: str | None) -> bool:
    """Return whether the private interpreter stdlib zip matches the current major/minor version."""
    if not pyexe or not os.path.exists(pyexe):
        return False
    base = _python_base_from_exe(pyexe)
    cur = (sys.version_info.major, sys.version_info.minor)
    return any((maj, minr) == cur for maj, minr, _ in _stdlib_zip_versions(base))


def _scrub_path_inplace(env: dict | None = None):
    """Remove Windows Store Python aliases from PATH."""
    e = env if env is not None else os.environ
    paths = (e.get("PATH") or "").split(";")
    bad_tokens = ("\\WindowsApps\\Python", "Microsoft\\WindowsApps")
    keep = []
    for p in paths:
        q = (p or "").strip()
        if not q:
            continue
        low = q.lower()
        if any(tok.lower() in low for tok in bad_tokens):
            continue
        keep.append(q)
    e["PATH"] = ";".join(keep)


def _append_private_site_packages(pyexe: str | None):
    '''
    Append dependency-runtime Lib/site-packages in packaged mode.
    UI dependencies are bundled with the app and are not managed by dependency layers.
    '''
    if not pyexe or not os.path.exists(pyexe):
        return
    try:
        base = _python_base_from_exe(pyexe)
    except Exception:
        return

    for p in (base / "Lib", base / "Lib" / "site-packages"):
        try:
            if p.exists():
                pstr = str(p)
                if pstr not in sys.path:
                    sys.path.append(pstr)
        except Exception:
            pass
    print(f"[INFO] packaged: appended dependency runtime path: {base}")


def _allowed_roots_for(pyexe: str | None, base_dir: Path) -> list[str]:
    """Return path roots allowed for the target interpreter."""
    roots: set[str] = set()


    try:
        src_dir = Path(__file__).resolve().parent
        roots.add(str(src_dir))
        roots.add(str(src_dir.parent))
    except Exception:
        pass
    def add_private_base(b: Path, allow_core: bool):
        if not b.exists():
            return

        roots.update({
            str(b / "Lib"),
            str(b / "Lib" / "site-packages"),
        })

        if allow_core:
            roots.update({
                str(b),
                str(b / "DLLs"),
            })
            try:
                for maj, minr, z in _stdlib_zip_versions(b):
                    if (maj, minr) == (sys.version_info.major, sys.version_info.minor):
                        roots.add(z)
            except Exception:
                pass

    try:
        allow_core = _same_runtime_version_as_current(pyexe) if (pyexe and os.path.exists(pyexe)) else False
        if pyexe and os.path.exists(pyexe):
            base = _python_base_from_exe(pyexe)
            add_private_base(base, allow_core=allow_core)
    except Exception:
        pass


    for r in _current_runtime_roots():
        roots.add(r)
    return list(roots)


def _relaunch_with(pyexe: str):
    """Relaunch with the private interpreter while hiding background windows on Windows."""
    import subprocess
    if not pyexe or not os.path.exists(pyexe):
        print("[ERROR] 无法重启：未找到目标解释器。")
        sys.exit(5)
    env = os.environ.copy()
    env["LATEXSNIPPER_BOOTSTRAPPED"] = "1"
    env["PYTHONNOUSERSITE"] = "1" if os.name == "nt" else "0"
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    _scrub_path_inplace(env)
    if os.name == "nt":
        env.setdefault("QT_QPA_PLATFORM", "windows")
    elif sys.platform.startswith("linux"):
        env.setdefault("QT_QPA_PLATFORM", "xcb")
    argv = [pyexe, os.path.abspath(__file__), *sys.argv[1:]]
    print(f"[INFO] 使用私有解释器重启(子进程): {pyexe}")
    try:
        proc = subprocess.Popen(argv, env=env, **_win_subprocess_kwargs())
    except Exception as e:
        print(f"[ERROR] 启动子进程失败: {e}")
        sys.exit(6)
    print(f"[INFO] 私有解释器子进程已启动: pid={getattr(proc, 'pid', None)}")
    sys.exit(0)


def _norm_path(s: str | None) -> str | None:
    if not s:
        return None
    return s.strip().strip('"').strip("'").strip()


def _win_subprocess_flags() -> int:
    """Return Windows subprocess flags for background tasks."""
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _win_startupinfo():
    """Return hidden Windows startup info for console subprocesses."""
    if os.name != "nt":
        return None
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return startupinfo
    except Exception:
        return None


def _win_subprocess_kwargs() -> dict:
    """Return Windows subprocess options that suppress transient console windows."""
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": _win_subprocess_flags()}
    startupinfo = _win_startupinfo()
    if startupinfo is not None:
        kwargs["startupinfo"] = startupinfo
    return kwargs


def _clean_bad_env():
    """Remove or repair invalid LATEXSNIPPER_PYEXE values."""
    val = os.environ.get("LATEXSNIPPER_PYEXE")
    p = _norm_path(val)
    if not p or not os.path.exists(p):
        os.environ.pop("LATEXSNIPPER_PYEXE", None)


def _has_full_python_bootstrap_modules(pyexe: str) -> bool:
    """Check whether the interpreter has the full bootstrap standard-library modules."""
    try:
        import subprocess
        r = subprocess.run([pyexe, "-c", "import ensurepip, venv;print('ok')"],
                           capture_output=True, text=True, timeout=20, **_win_subprocess_kwargs())
        return r.returncode == 0
    except Exception:
        return False


def _find_full_python(base_dir: Path) -> str | None:
    """Reuse an existing Python from the install directory before installing python311."""
    candidate = _find_install_base_python(base_dir)
    if candidate is not None:
        try:
            if candidate.exists() and _has_full_python_bootstrap_modules(str(candidate)):
                return str(candidate)
        except Exception:
            pass
        print(f"[WARN] Ignoring Python without bootstrap modules: {candidate}")
    if getattr(sys, "frozen", False):
        installer = base_dir / "python-3.11.0-amd64.exe"
        if installer.exists():
            if _run_python_installer(installer, base_dir / "python311"):
                candidate = _find_install_base_python(base_dir)
                if candidate is not None and candidate.exists():
                    return str(candidate)
        return None
    for name in ("python3.11.exe", "python.exe", "python3.exe"):
        which = _norm_path(shutil.which(name))
        if which and os.path.exists(which) and _has_full_python_bootstrap_modules(which):
            return which
    return None


def _run_python_installer(installer: Path, target_dir: Path) -> bool:
    import subprocess
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        args = [str(installer), "/quiet", "InstallAllUsers=0",
                f"TargetDir={str(target_dir)}",
                "Include_pip=1", "PrependPath=0", "Include_test=0",
                "Include_doc=0", "Include_launcher=0", "SimpleInstall=1"]
        print(f"[INFO] 正在静默安装 Python 到: {target_dir}")
        r = subprocess.run(args, timeout=600, **_win_subprocess_kwargs())
        if r.returncode != 0:
            print(f"[WARN] 静默安装返回码: {r.returncode}")
            return False
        return True
    except Exception as e:
        print(f"[WARN] 启动安装器失败: {e}")
        return False


def ensure_full_python_or_prompt(base_dir: Path) -> str | None:
    if getattr(sys, "frozen", False):
        py = _find_full_python(base_dir)
        if py:

            py_norm = os.path.normcase(os.path.abspath(py))
            bundled_norm = os.path.normcase(os.path.abspath(str(base_dir)))
            if py_norm.startswith(bundled_norm):
                print(f"[INFO] (打包模式) 使用依赖目录内 Python: {py}")
            else:
                print(f"[INFO] (打包模式) 使用外部私有 Python: {py}")
            return py
        print("[INFO] (打包模式) 依赖目录内未检测到可用 Python，先使用内置运行时启动依赖向导。")
        return sys.executable

    py = _find_full_python(base_dir)
    if py:
        print(f"[INFO] 使用依赖目录 Python: {py}")
        return py


    installer: Path | None = None
    for root in (base_dir, Path(__file__).resolve().parent, Path(os.getcwd())):
        try:
            cands = list(Path(root).glob("python-3.11*.exe")) + list(Path(root).glob("python311*.exe"))
            if cands:
                installer = cands[0]
                break
        except Exception:
            pass

    if installer:
        target_dir = base_dir / "python311"
        if _run_python_installer(installer, target_dir):
            py = _find_full_python(base_dir)
            if py:
                print(f"[INFO] Python 3.11 已安装到: {py}")
                return py

    print("[ERROR] 未找到可用的 Python 3.11；请将安装器放入安装目录_internal下或手动安装后重试。")
    return None
