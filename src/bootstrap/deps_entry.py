import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from bootstrap.deps_context import (
    CONFIG_FILE,
    PIP_INSTALL_SUPPRESS_ARGS,
    STATE_FILE,
    _config_dir_path,
    flags,
    pip_ready_event,
    psutil,
    set_last_ensure_deps_force_enter,
)
from bootstrap.deps_layer_specs import (
    LAYER_MAP,
    MATHCRAFT_RUNTIME_LAYERS,
    _filter_packages,
    _gpu_available,
    _normalize_chosen_layers,
    _sanitize_state_layers,
)
from bootstrap.deps_python_runtime import (
    find_existing_python as _find_existing_python,
    find_local_python311_installer as _find_local_python311_installer_impl,
    find_system_python3 as _find_system_python3,
    inject_private_python_paths as _inject_private_python_paths,
    is_usable_python as _is_usable_python,
    normalize_deps_base_dir as _normalize_deps_base_dir,
    site_packages_root as _site_packages_root,
)
from bootstrap.deps_qt_compat import QTimer
from bootstrap.deps_runtime_verify import _verify_installed_layers
from bootstrap.deps_state import save_json as _save_json
from bootstrap.deps_ui import (
    _build_layers_ui,
    _exec_close_only_message_box,
    _progress_dialog,
    _select_existing_directory_with_icon,
    custom_warning_dialog,
)
from bootstrap.deps_workers import InstallWorker, LayerVerifyWorker


def _ensure_pip(main_python: Path) -> bool:
    """Ensure pip is available for the target interpreter."""
    import subprocess
    import urllib.request

    if not main_python.exists():
        raise RuntimeError(f"[ERR] 主 Python 不存在: {main_python}")

    # Verify this looks like a real python executable before bootstrap
    try:
        name = main_python.name.lower()
        is_python_exe = (
            (os.name == "nt" and name.startswith("python") and name.endswith(".exe"))
            or (os.name != "nt" and (name.startswith("python") or "python" in name))
        )
        if not is_python_exe:
            print(f"[WARN] pip bootstrap skipped for non-python executable: {main_python}")
            return False
    except Exception:
        pass



    try:
        pth_candidates = list(main_python.parent.glob("python*.pth")) + list(main_python.parent.glob("python*._pth"))
        for pth_file in pth_candidates:
            content = pth_file.read_text(encoding="utf-8")
            if "#import site" in content:
                from pathlib import Path
                Path(pth_file).write_text(content.replace("#import site", "import site"), encoding="utf-8")
    except Exception:
        pass


    def _pip_version_tuple(raw: str) -> tuple[int, ...]:
        parts: list[int] = []
        current = ""
        for ch in raw:
            if ch.isdigit():
                current += ch
            elif current:
                parts.append(int(current))
                current = ""
                if len(parts) >= 3:
                    break
        if current and len(parts) < 3:
            parts.append(int(current))
        return tuple(parts)

    def _query_pip_version() -> tuple[int, ...] | None:
        code = "import pip; print(pip.__version__)"
        proc = subprocess.run(
            [str(main_python), "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        if proc.returncode != 0:
            return None
        return _pip_version_tuple(proc.stdout.strip())

    def _has_packaging_toolchain() -> bool:
        proc = subprocess.run(
            [str(main_python), "-c", "import setuptools, wheel"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return proc.returncode == 0

    def _upgrade_packaging_toolchain() -> bool:
        cmd = [
            str(main_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
            "--no-cache-dir",
            *PIP_INSTALL_SUPPRESS_ARGS,
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        if res.returncode != 0:
            print(f"[WARN] pip toolchain upgrade failed: {res.stdout[-1000:]}")
            return False
        return True

    pip_version = _query_pip_version()
    if pip_version is None:
        try:
            subprocess.check_call(
                [str(main_python), "-m", "ensurepip", "--upgrade"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            pip_version = _query_pip_version()
        except Exception:
            pip_version = None

    if pip_version is None:
        gp_url = "https://bootstrap.pypa.io/get-pip.py"
        gp_path = main_python.parent / "get-pip.py"
        urllib.request.urlretrieve(gp_url, gp_path)
        subprocess.check_call([str(main_python), str(gp_path)], timeout=180, creationflags=flags)
        pip_version = _query_pip_version()

    needs_upgrade = pip_version is None or pip_version < (23, 0) or not _has_packaging_toolchain()
    ok = True
    if needs_upgrade:
        ok = _upgrade_packaging_toolchain()
    if ok:
        pip_ready_event.set()
    return ok


def clear_deps_state():
    """Clear the dependency state file."""
    import json
    import os
    from pathlib import Path

    try:

        home_config = _load_config_path()
        print(f"[DEBUG] 清理状态文件：{home_config}")

        if not home_config.exists():
            print("[WARN] 配置文件不存在，无需清理。")
            return

        with open(home_config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        deps_dir = cfg.get("install_base_dir")

        if not deps_dir or not os.path.exists(deps_dir):
            print(f"[ERR] 无法找到依赖目录：{deps_dir}")
            return


        state_path = Path(deps_dir) / ".deps_state.json"
        if state_path.exists():
            state_path.unlink()
            print(f"[OK] 已删除状态文件：{state_path}")


        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"installed_layers": []}, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已重新生成空状态文件：{state_path}")

    except Exception as e:
        print(f"[ERR] 清除依赖状态文件失败: {e}")


def _load_config_path():
    return _config_dir_path() / CONFIG_FILE


def _read_config_install_dir(cfg_path: Path) -> str | None:
    if cfg_path.exists():
        try:
            import json
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            v = data.get("install_base_dir")
            if isinstance(v, str) and v.strip():
                return v
        except Exception:
            pass
    return None


def _write_config_install_dir(cfg_path: Path, deps_dir: str) -> None:
    try:
        import json
        data = {}
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        data["install_base_dir"] = deps_dir
        Path(cfg_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _find_local_python311_installer(deps_dir: Path) -> Path | None:
    return _find_local_python311_installer_impl(deps_dir, __file__)


def _system_python_install_hint(reason: str) -> str:
    """Return platform-specific instructions for creating the dependency venv."""
    lines = [
        reason,
        "",
        "请安装带 venv/pip 支持的 Python 3.10+ 后重试。",
    ]
    if sys.platform == "darwin":
        lines.extend([
            "  Homebrew：brew install python",
            "  python.org：安装最新版 macOS Python 3 安装包",
            "  安装后请重新打开 LaTeXSnipper。",
        ])
    else:
        lines.extend([
            "  Debian/Ubuntu：sudo apt install python3 python3-venv",
            "  Fedora：        sudo dnf install python3",
            "  Arch：          sudo pacman -S python",
        ])
    return "\n".join(lines)


def _setup_python_venv_from_system(target_dir: Path, timeout: int = 300) -> bool:
    """Create a Python venv at target_dir using the system python3 interpreter.

    Only meaningful on Linux/macOS.  On Windows this always returns False.
    """
    import time

    if os.name == "nt":
        return False

    system_python = _find_system_python3()
    if system_python is None:
        print("[WARN] 未找到系统 Python 3，无法创建 venv")
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 使用系统 Python 创建 venv: {system_python} -> {target_dir}")
    try:
        commands = [
            [str(system_python), "-m", "venv", "--copies", str(target_dir)],
            [str(system_python), "-m", "venv", "--copies", "--without-pip", str(target_dir)],
        ]
        last_output = ""
        for cmd in commands:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            deadline = time.monotonic() + timeout
            while True:
                ret = proc.poll()
                if ret is not None:
                    break
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                time.sleep(0.2)
            if ret == 0:
                print(f"[OK] venv 创建成功: {target_dir}")
                return True
            last_output = proc.stdout.read() if proc.stdout else ""
        print(f"[WARN] venv 创建失败: {last_output[-500:]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"[WARN] venv 创建超时（{timeout} 秒）")
        try:
            proc.kill()
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"[WARN] venv 创建异常: {e}")
        return False


def _run_local_python311_installer(installer: Path, target_dir: Path, timeout: int = 900,
                                   before_launch=None) -> bool:
    """
    Launch the local Python installer and wait for it to finish.
    The installer UI is shown to the user; no network download is attempted here.

    Windows-only: the .exe installer only exists on Windows.
    """
    if os.name != "nt":
        return False
    import time

    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 正在启动本地 Python 安装器: {installer}")
    print(f"[INFO] 期望安装目录: {target_dir}")
    try:
        if callable(before_launch):
            try:
                before_launch()
            except Exception as e:
                print(f"[WARN] installer pre-launch callback failed: {e}")
        try:
            from PyQt6.QtWidgets import QApplication as _QApplication
            app = _QApplication.instance()
        except Exception:
            app = None
        proc = subprocess.Popen([str(installer)])
        deadline = time.monotonic() + timeout
        ret = None
        while True:
            ret = proc.poll()
            if ret is not None:
                break
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired([str(installer)], timeout)
            if app is not None:
                try:
                    app.processEvents()
                except Exception:
                    pass
            time.sleep(0.2)
        print(f"[INFO] Python 安装器已退出（返回码: {ret}）")
        time.sleep(1)
    except subprocess.TimeoutExpired:
        print(f"[WARN] Python 安装器超时（{timeout} 秒）")
        try:
            proc.kill()
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"[WARN] 启动本地 Python 安装器失败: {e}")
        return False
    _default_pyexe_name = "python.exe" if os.name == "nt" else "python3"
    return (target_dir / _default_pyexe_name).exists()


def ensure_deps(prompt_ui=True, require_layers=("BASIC", "CORE"), force_enter=False, always_show_ui=False,
                deps_dir=None, from_settings=False, before_show_ui=None,
                after_force_enter=None):
    set_last_ensure_deps_force_enter(False)
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])

    def _notify_before_show_ui():
        if not callable(before_show_ui):
            return
        try:
            before_show_ui()
        except Exception as e:
            print(f"[WARN] before_show_ui callback failed: {e}")

    def _notify_after_force_enter():
        if not callable(after_force_enter):
            return
        try:
            after_force_enter()
            try:
                app.processEvents()
            except Exception:
                pass
        except Exception as e:
            print(f"[WARN] after_force_enter callback failed: {e}")

    current_pyexe = Path(sys.executable)
    current_site = _site_packages_root(current_pyexe)


    cfg_path = _load_config_path()
    if not deps_dir:
        deps_dir = _read_config_install_dir(cfg_path)

    if not deps_dir:
        parent = app.activeWindow()
        _notify_before_show_ui()
        chosen = _select_existing_directory_with_icon(parent, "选择依赖安装/加载目录", str(Path.home()))
        if not chosen:

            return False
        deps_dir = str(_normalize_deps_base_dir(Path(chosen)))
        _write_config_install_dir(cfg_path, deps_dir)

    deps_path = _normalize_deps_base_dir(Path(deps_dir))
    deps_dir = str(deps_path)
    deps_path.mkdir(parents=True, exist_ok=True)


    from PyQt6.QtWidgets import QMessageBox, QDialog
    need_install = False
    if force_enter:
        if not _find_existing_python(Path(deps_dir)):
            try:
                custom_warning_dialog("不可进入", "当前依赖目录尚未检测到可复用的 Python 环境，请先初始化依赖环境。")
            except Exception:
                print("[WARN] 缺少可复用 Python 环境，不能跳过安装直接进入。")
            return False
        set_last_ensure_deps_force_enter(True)
        _notify_after_force_enter()
        try:
            custom_warning_dialog("警告", "缺失依赖，程序将跳过安装并进入，部分功能可能不可用。")
        except Exception:
            print("[WARN] 缺失依赖，程序将跳过安装并进入，部分功能可能不可用。")
        print("[Deps] 用户选择跳过依赖安装并进入主程序")
        return True

    is_frozen = getattr(sys, 'frozen', False)
    _DEFAULT_PYEXE_NAME = "python.exe" if os.name == "nt" else "python3"
    if is_frozen:
        # Packaged: runtime stays bundled, but dependency wizard should only treat
        # a python inside deps_dir as reusable. Missing deps python must remain
        # visible to the UI so the user can initialize it from the wizard.
        py_root = Path(deps_dir) / "python311"
        existing_pyexe = _find_existing_python(Path(deps_dir))
        pyexe = existing_pyexe or (py_root / _DEFAULT_PYEXE_NAME)
        if existing_pyexe and existing_pyexe.exists():
            print(f"[INFO] packaged: use deps python for pip: {pyexe}")
            use_bundled_python = False
        else:
            print(f"[INFO] packaged: no reusable deps python yet, wizard will initialize: {pyexe}")
            use_bundled_python = True
    else:

        py_root = Path(deps_dir) / "python311"
        existing_pyexe = _find_existing_python(Path(deps_dir))
        pyexe = existing_pyexe or (py_root / _DEFAULT_PYEXE_NAME)
        deps_dir_resolved = str(Path(deps_dir).resolve())
        mismatch_reason = ""


        is_packaged = hasattr(sys, '_MEIPASS') or '_internal' in str(Path(__file__).parent)
        mode_str = "打包模式" if is_packaged else "开发模式"

        def _path_is_under(child: str | None, parent: str) -> bool:
            if not child:
                return False
            try:
                child_norm = os.path.normcase(os.path.abspath(child))
                parent_norm = os.path.normcase(os.path.abspath(parent))
                return os.path.commonpath([child_norm, parent_norm]) == parent_norm
            except Exception:
                return str(child).lower().startswith(str(parent).lower())

        current_site_in_deps = _path_is_under(current_site, deps_dir_resolved)

        if current_site_in_deps:
            print(f"[INFO] {mode_str}：当前 Python 环境与依赖目录一致: {current_pyexe}")
            print(f"[DIAG] 当前 site-packages 路径: {current_site}")
            print(f"[DIAG] 依赖目录路径: {deps_dir_resolved}")
            pyexe = current_pyexe
            use_bundled_python = False
        else:
            if existing_pyexe and existing_pyexe.exists():
                use_bundled_python = False
                pyexe = existing_pyexe
                print(f"[INFO] {mode_str}：当前 Python 与依赖目录不一致，将复用目录内已有 Python: {pyexe}")
            else:
                use_bundled_python = True
                print(f"[INFO] {mode_str}：当前 Python 与依赖目录不一致，将使用独立 Python: {pyexe}")
            print(f"[DIAG] 当前 Python 解释器: {current_pyexe}")
            print(f"[DIAG] 当前 site-packages 路径: {current_site if current_site else '(未找到)'}")
            print(f"[DIAG] 依赖目录路径: {deps_dir_resolved}")
            if not current_site:
                mismatch_reason = "未能定位当前 Python 的 site-packages 路径。"
            elif not current_site_in_deps:
                mismatch_reason = "当前 Python 的 site-packages 不在依赖目录下。"
            else:
                mismatch_reason = "未知原因导致环境不一致。"
            print(f"[DIAG] 环境不一致原因: {mismatch_reason}")

        if use_bundled_python and not _is_usable_python(pyexe):
            if from_settings:
                print("[INFO] 设置入口：目标依赖目录未检测到可复用 Python，先打开依赖向导，待用户确认后再初始化。")
            else:
                try:
                    if os.name != "nt":
                        # Linux / macOS: use system python3 to create a venv
                        ok = _setup_python_venv_from_system(py_root)
                        if not ok:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "未找到 Python 3",
                                _system_python_install_hint(
                                    "未检测到可复用的 Python 环境，且系统中未找到可用的 python3。"
                                ),
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            return False
                        pyexe = py_root / "bin" / "python3"
                        print(f"[OK] 已通过系统 Python 创建 venv: {pyexe}")
                    else:
                        installer = _find_local_python311_installer(Path(deps_dir))
                        if installer is None:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装器未找到",
                                "未检测到可复用 Python，且未找到本地 Python 3.11.0 安装器。\n\n"
                                "请将 `python-3.11.0-amd64.exe` 放到依赖目录、程序目录下的 `_internal`，或项目根目录后重试。",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            return False
                        print(f"[INFO] 未找到私有 Python，将调用本地安装器: {installer}")
                        _notify_before_show_ui()
                        ok = _run_local_python311_installer(installer, py_root, before_launch=_notify_before_show_ui)
                        if not ok or not _is_usable_python(pyexe):
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装失败",
                                "Python 3.11.0 安装失败。\n\n"
                                f"请确认已通过本地安装器安装到以下目录：\n{py_root}",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            return False
                        print(f"[OK] 已安装私有 Python: {pyexe}")
                except Exception as e:
                    print(f"[ERR] 自动安装 Python 失败: {e}")
                    _notify_before_show_ui()
                    _exec_close_only_message_box(
                        None,
                        "安装失败",
                        f"调用本地 Python 安装器失败：{e}",
                        icon=QMessageBox.Icon.Critical,
                        buttons=QMessageBox.StandardButton.Ok,
                    )
                    return False


    try:
        _ensure_pip(pyexe)
        state_path = Path(deps_dir) / STATE_FILE
        if not state_path.exists():
            _save_json(state_path, {"installed_layers": []})
        pip_ready_event.set()
    except Exception as e:
        print(f"[Deps] 预初始化 pip 失败: {e}")
        pip_ready_event.set()

    import platform
    print("【依赖目录选择后环境信息】")
    print("主进程解释器:", current_pyexe)
    print("主进程平台:", platform.platform())
    print("主进程 sys.path:", sys.path)
    print("目标依赖解释器:", pyexe)
    print("目标依赖目录:", deps_dir)

    def _apply_runtime_context(active_pyexe: Path) -> None:
        sp_local = _site_packages_root(active_pyexe)

        if (
            os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") != "1"
            and active_pyexe is not None
            and active_pyexe.exists()
        ):
            _inject_private_python_paths(active_pyexe)
        os.environ["LATEX_SNIPPER_SITE"] = str(sp_local or "")
        if active_pyexe is not None and active_pyexe.exists():
            os.environ["LATEXSNIPPER_PYEXE"] = str(active_pyexe)
        os.environ["LATEXSNIPPER_INSTALL_BASE_DIR"] = str(deps_path)
        os.environ["LATEXSNIPPER_DEPS_DIR"] = str(deps_path)

    _apply_runtime_context(pyexe)

    state_path = deps_path / STATE_FILE
    state = _sanitize_state_layers(state_path)
    installed = {"layers": state.get("installed_layers", [])}

    state_path = deps_path / STATE_FILE

    needed = {required_layer for required_layer in require_layers if required_layer in LAYER_MAP}

    def _missing_required_layers(layer_list: list[str]) -> list[str]:
        missing = [layer for layer in needed if layer not in layer_list]
        if not any(layer in layer_list for layer in MATHCRAFT_RUNTIME_LAYERS):
            missing.append("MATHCRAFT_CPU")
        return missing

    def _deps_ready(layer_list: list[str]) -> bool:
        return not _missing_required_layers(layer_list)

    missing_layers = _missing_required_layers(installed["layers"])
    skip_next_ui_runtime_verify = False

    def _default_selected_layers(installed_layers_list: list[str], failed_layers_list: list[str] | None = None) -> list[str]:
        defaults = ["BASIC", "CORE"]
        installed_set = {str(x) for x in (installed_layers_list or [])}
        failed_set = {str(x) for x in (failed_layers_list or [])}
        runtime_present = any(x in set(MATHCRAFT_RUNTIME_LAYERS) for x in (installed_set | failed_set))
        if not runtime_present:
            defaults.append("MATHCRAFT_CPU")
        return defaults

    def _reverify_installed_layers_if_needed(reason: str = "") -> bool:
        """Reverify installed layers when needed before entering the app."""
        nonlocal state, installed, missing_layers
        if not from_settings:
            return _deps_ready(installed["layers"])
        if not pyexe or not os.path.exists(pyexe):
            return _deps_ready(installed["layers"])

        claimed = [layer for layer in installed.get("layers", []) if layer in LAYER_MAP]
        if not claimed:
            missing_layers = _missing_required_layers(installed["layers"])
            return _deps_ready(installed["layers"])

        if reason:
            print(f"[INFO] 触发已安装层复验: {reason}")
        print("[INFO] 从设置入口复验已安装功能层...")
        verified = _verify_installed_layers(
            str(pyexe),
            claimed,
            log_fn=lambda m: print(m),
        )
        failed = [layer for layer in claimed if layer not in verified]
        payload = {"installed_layers": verified}
        if failed:
            payload["failed_layers"] = failed
        _save_json(state_path, payload)

        state = payload
        installed["layers"] = verified
        missing_layers = _missing_required_layers(installed["layers"])
        if failed:
            print(f"[WARN] 复验失败层: {', '.join(failed)}")
        return _deps_ready(installed["layers"])

    def _switch_deps_context(target_deps_dir: str) -> tuple[list[str], bool]:
        nonlocal deps_dir, deps_path, state_path, state, installed, missing_layers, pyexe
        deps_dir = str(_normalize_deps_base_dir(Path(target_deps_dir or deps_dir)))
        deps_path = Path(deps_dir)
        py_root = deps_path / "python311"
        existing_pyexe = _find_existing_python(deps_path)
        if is_frozen:
            pyexe = existing_pyexe or (py_root / _DEFAULT_PYEXE_NAME)
            use_bundled = not (existing_pyexe and existing_pyexe.exists())
        else:
            deps_dir_resolved = str(deps_path.resolve())
            if current_site and str(current_site).startswith(deps_dir_resolved):
                pyexe = current_pyexe
                use_bundled = False
            elif existing_pyexe and existing_pyexe.exists():
                pyexe = existing_pyexe
                use_bundled = False
            else:
                pyexe = py_root / _DEFAULT_PYEXE_NAME
                use_bundled = True
        _apply_runtime_context(pyexe)
        state_path = deps_path / STATE_FILE
        state = _sanitize_state_layers(state_path)
        installed["layers"] = state.get("installed_layers", [])
        missing_layers = _missing_required_layers(installed["layers"])
        return missing_layers, use_bundled

    while True:
        if (missing_layers and prompt_ui) or always_show_ui:
            stop_event = threading.Event()

            default_select = _default_selected_layers(
                installed.get("layers", []),
                state.get("failed_layers", []),
            )

            chosen = []
            dlg, chosen = _build_layers_ui(
                pyexe,
                deps_dir,
                installed,
                default_select,
                chosen,
                state_path,
                from_settings=from_settings,
                skip_runtime_verify_once=skip_next_ui_runtime_verify
            )
            skip_next_ui_runtime_verify = False
            _notify_before_show_ui()
            result = dlg.exec()
            if result != dlg.DialogCode.Accepted:

                return False

            chosen_layers = _normalize_chosen_layers(chosen.get("layers", []))
            mirror_source = str(chosen.get("mirror_source", "")).strip().lower()
            if mirror_source in ("off", "tuna"):
                use_mirror = (mirror_source == "tuna")
            else:
                use_mirror = bool(chosen.get("mirror", False))
                mirror_source = "tuna" if use_mirror else "off"
            missing_layers, use_bundled_python = _switch_deps_context(chosen.get("deps_path", deps_dir))


            if chosen.get("force_enter", False):
                set_last_ensure_deps_force_enter(True)
                _notify_after_force_enter()
                print("[INFO] 用户选择跳过依赖安装并进入主程序")
                return True
            if chosen.get("action") == "enter":
                print("[INFO] 用户选择直接进入主程序。")
                return True
            if chosen["layers"]:
                failed_claims = {
                    str(x) for x in (state.get("failed_layers", []) if isinstance(state, dict) else [])
                }
                already_have = all(
                    layer in state.get("installed_layers", []) for layer in chosen["layers"]
                )
                has_failed_choice = any(layer in failed_claims for layer in chosen["layers"])
                if already_have and not has_failed_choice:
                    if not chosen.get("verified_in_ui", False) and not _reverify_installed_layers_if_needed("skip_download_already_have"):
                        print("[WARN] 复验后关键层不完整，返回向导。")
                        continue
                    print("[INFO] 所选层已存在，跳过下载。")
                    return True

            print(f"[INFO] 依赖下载源: {'清华镜像' if use_mirror else '官方 PyPI'} ({mirror_source})")
            py_root = deps_path / "python311"
            need_install = bool(chosen_layers) and bool(missing_layers)
            need_install = bool(chosen_layers)

        if need_install:
            if chosen_layers:
                if use_bundled_python and not _is_usable_python(Path(pyexe)):
                    if os.name != "nt":
                        # Linux / macOS: use system python3 to create a venv
                        ok = _setup_python_venv_from_system(py_root)
                        if not ok:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "未找到 Python 3",
                                _system_python_install_hint(
                                    "系统中未找到可用的 python3，无法初始化依赖环境。"
                                ),
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            always_show_ui = True
                            continue
                        pyexe = py_root / "bin" / "python3"
                        print(f"[OK] 已通过系统 Python 创建 venv: {pyexe}")
                    else:
                        installer = _find_local_python311_installer(deps_path)
                        if installer is None:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装器未找到",
                                "目标依赖目录未检测到可复用 Python，且未找到本地安装器。\n\n"
                                "请将 `python-3.11.0-amd64.exe` 放到依赖目录、程序目录下的 `_internal`，或项目根目录后重试。",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            always_show_ui = True
                            continue

                        _notify_before_show_ui()
                        confirm = _exec_close_only_message_box(
                            None,
                            "初始化依赖环境",
                            "目标依赖目录未检测到可复用 Python 环境。\n\n"
                            f"是否现在初始化以下目录后继续安装依赖？\n{py_root}",
                            icon=QMessageBox.Icon.Question,
                            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            default_button=QMessageBox.StandardButton.Yes,
                        )
                        if confirm != QMessageBox.StandardButton.Yes:
                            always_show_ui = True
                            continue

                        _notify_before_show_ui()
                        ok = _run_local_python311_installer(installer, py_root, before_launch=_notify_before_show_ui)
                        if not ok or not _is_usable_python(Path(pyexe)):
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装失败",
                                "Python 3.11.0 安装失败。\n\n"
                                f"请确认已通过本地安装器安装到以下目录：\n{py_root}",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            always_show_ui = True
                            continue
                    try:
                        _ensure_pip(pyexe)
                    except Exception as e:
                        print(f"[Deps] 初始化目标 Python 后确保 pip 失败: {e}")

                RESULT_BACK_TO_WIZARD = 1001
                if "MATHCRAFT_GPU" in chosen_layers and not _gpu_available():
                    r = _exec_close_only_message_box(
                        None,
                        "GPU 未检测",
                        "未检测到 NVIDIA GPU，继续安装 onnxruntime-gpu 可能无法启用 CUDAExecutionProvider，是否继续？",
                        icon=QMessageBox.Icon.Question,
                        buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        default_button=QMessageBox.StandardButton.No,
                    )
                    if r != QMessageBox.StandardButton.Yes:
                        chosen_layers = [c for c in chosen_layers if c != "MATHCRAFT_GPU"]

                if "CORE" in chosen_layers and not any(layer in chosen_layers for layer in MATHCRAFT_RUNTIME_LAYERS):
                    chosen_layers = list(chosen_layers) + ["MATHCRAFT_CPU"]
                    print("[INFO] CORE 未指定 MathCraft 后端，已自动补充 MATHCRAFT_CPU")

                pkgs = []
                for layer in chosen_layers:
                    pkgs.extend(LAYER_MAP[layer])

                if "MATHCRAFT_GPU" in chosen_layers:
                    pkgs = [p for p in pkgs if not (p.lower().startswith("onnxruntime") and "gpu" not in p.lower())]
                elif "MATHCRAFT_CPU" in chosen_layers:
                    pkgs = [p for p in pkgs if not p.lower().startswith("onnxruntime-gpu")]

                pkgs = _filter_packages(pkgs)
                log_q = queue.Queue()
                stop_event = threading.Event()
                pause_event = threading.Event()
                state_lock = threading.Lock()

                dlg, info, logw, btn_cancel, btn_pause, progress = _progress_dialog()
                from PyQt6 import sip
                ui_closed = {"value": False}
                timer_holder = {"log": None, "speed": None}
                verify_worker_holder = {"obj": None}
                post_install_verify_passed = {"value": False}
                paused = False
                net_speed_state = {
                    "busy": False,
                    "base_text": "",
                    "last_sample": None,
                    "down_bps": None,
                    "pip_speed_text": "",
                    "pip_eta_text": "",
                    "pip_progress_text": "",
                }

                def _is_alive(obj):
                    try:
                        return obj is not None and not sip.isdeleted(obj)
                    except Exception:
                        return False

                def _append_log(text: str):
                    if _is_alive(logw):
                        try:
                            logw.append(text)
                        except RuntimeError:
                            pass

                def _set_progress(val: int):
                    if _is_alive(progress):
                        try:
                            progress.setValue(int(val))
                        except RuntimeError:
                            pass

                def _format_speed(bytes_per_sec):
                    try:
                        speed = float(bytes_per_sec)
                    except Exception:
                        return ""
                    if speed < 1024:
                        return f"{speed:.0f} B/s"
                    if speed < 1024 * 1024:
                        return f"{speed / 1024:.1f} KB/s"
                    if speed < 1024 * 1024 * 1024:
                        return f"{speed / (1024 * 1024):.1f} MB/s"
                    return f"{speed / (1024 * 1024 * 1024):.2f} GB/s"

                def _render_info_text():
                    text = net_speed_state.get("base_text", "") or ""
                    if net_speed_state.get("busy", False):
                        pip_speed = (net_speed_state.get("pip_speed_text") or "").strip()
                        pip_eta = (net_speed_state.get("pip_eta_text") or "").strip()
                        pip_progress = (net_speed_state.get("pip_progress_text") or "").strip()
                        if pip_speed:
                            text = f"{text}  下载速度：{pip_speed}"
                            if pip_eta:
                                text = f"{text}  剩余：{pip_eta}"
                            if pip_progress:
                                text = f"{text}  {pip_progress}"
                        else:
                            speed = net_speed_state.get("down_bps")
                            if speed is not None:
                                text = f"{text}  下载速度：{_format_speed(speed)}"
                            else:
                                text = f"{text}  下载速度：计算中..."
                    if _is_alive(info):
                        try:
                            info.setText(text)
                        except RuntimeError:
                            pass

                def _parse_pip_transfer_status(line: str):
                    if not line:
                        return None
                    text = line.strip().replace("\r", " ")
                    if not text:
                        return None
                    speed_match = re.search(r"(\d+(?:\.\d+)?)\s*([kmg]?i?B/s)", text, re.IGNORECASE)
                    if not speed_match:
                        return None
                    speed_text = f"{speed_match.group(1)} {speed_match.group(2)}"
                    eta_match = re.search(r"(\d+:\d{2}:\d{2}|\d+:\d{2})", text)
                    progress_match = re.search(
                        r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([kmg]?i?B)",
                        text,
                        re.IGNORECASE,
                    )
                    progress_text = ""
                    if progress_match:
                        progress_text = (
                            f"{progress_match.group(1)}/{progress_match.group(2)} {progress_match.group(3)}"
                        )
                    return {
                        "speed_text": speed_text,
                        "eta_text": eta_match.group(1) if eta_match else "",
                        "progress_text": progress_text,
                    }

                def _sample_network_speed():
                    if psutil is None or not net_speed_state.get("busy", False):
                        return
                    try:
                        counters = psutil.net_io_counters()
                    except Exception:
                        return
                    if counters is None:
                        return
                    now = time.monotonic()
                    current = (now, int(getattr(counters, "bytes_recv", 0)))
                    last = net_speed_state.get("last_sample")
                    net_speed_state["last_sample"] = current
                    if last is None:
                        net_speed_state["down_bps"] = None
                        _render_info_text()
                        return
                    elapsed = max(0.001, current[0] - last[0])
                    delta = max(0, current[1] - last[1])
                    net_speed_state["down_bps"] = delta / elapsed
                    _render_info_text()

                def _set_info_text(text: str):
                    net_speed_state["base_text"] = text or ""
                    _render_info_text()

                def _set_network_speed_busy(is_busy: bool):
                    net_speed_state["busy"] = bool(is_busy)
                    net_speed_state["last_sample"] = None
                    net_speed_state["down_bps"] = None
                    net_speed_state["pip_speed_text"] = ""
                    net_speed_state["pip_eta_text"] = ""
                    net_speed_state["pip_progress_text"] = ""
                    _render_info_text()

                def toggle_pause():
                    nonlocal paused
                    paused = not paused
                    if paused:
                        pause_event.clear()
                        btn_pause.setText("继续下载")
                    else:
                        pause_event.set()
                        btn_pause.setText("暂停下载")

                btn_pause.clicked.connect(toggle_pause)
                pause_event.set()


                worker = InstallWorker(
                    pyexe, pkgs, stop_event, pause_event, state_lock, state, state_path,
                    chosen_layers, log_q, mirror=use_mirror,
                    force_reinstall=False, no_cache=False
                )

                def request_cancel():
                    ui_closed["value"] = True
                    stop_event.set()
                    for t in timer_holder.values():
                        if t is not None:
                            try:
                                t.stop()
                            except Exception:
                                pass
                    try:
                        if worker.isRunning():
                            worker.stop()
                    except Exception:
                        pass
                    if _is_alive(dlg):
                        try:
                            dlg.reject()
                        except RuntimeError:
                            pass

                btn_cancel.clicked.connect(request_cancel)

                worker.log_updated.connect(_append_log)
                worker.progress_updated.connect(_set_progress)
                worker.status_updated.connect(_set_info_text)
                worker.busy_state_changed.connect(_set_network_speed_busy)

                def _finalize_done_ui():
                    _set_network_speed_busy(False)
                    if _is_alive(progress):
                        _set_progress(progress.maximum())
                    if _is_alive(btn_cancel):
                        btn_cancel.setText("完成")
                    if _is_alive(btn_pause):
                        btn_pause.setEnabled(False)
                    if _is_alive(btn_cancel):
                        try:
                            btn_cancel.clicked.disconnect()
                        except Exception:
                            pass
                        btn_cancel.clicked.connect(
                            lambda: dlg.done(RESULT_BACK_TO_WIZARD) if _is_alive(dlg) else None
                        )
                    try:
                        if hasattr(dlg, "refresh_ui"):
                            dlg.refresh_ui()
                    except Exception as e:
                        print(f"[WARN] refresh ui failed: {e}")

                def on_install_done(success: bool):
                    if ui_closed["value"] or stop_event.is_set() or (not _is_alive(dlg)):
                        return

                    if not success:
                        _append_log("\n[ERR] Install has failures, check logs ❌")
                        if _is_alive(dlg):
                            _exec_close_only_message_box(
                                dlg,
                                "Install Incomplete",
                                "Some dependencies failed to install. Please check logs and retry.",
                                icon=QMessageBox.Icon.Warning,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                        _finalize_done_ui()
                        return

                    _append_log("\n[INFO] 正在后台验证已安装功能层...")
                    _set_info_text("依赖下载完成，正在后台验证功能层...")

                    verify_worker = LayerVerifyWorker(pyexe, chosen_layers, state_path)
                    verify_worker_holder["obj"] = verify_worker
                    verify_worker.log_updated.connect(_append_log)

                    def on_verify_done(_ok_layers: list, fail_layers: list):
                        if ui_closed["value"] or (not _is_alive(dlg)):
                            return
                        post_install_verify_passed["value"] = not bool(fail_layers)
                        if fail_layers:
                            _append_log(f"\n[WARN] Layers installed but verify failed: {', '.join(fail_layers)}")
                            _exec_close_only_message_box(
                                dlg,
                                "部分验证失败",
                                f"以下功能层安装但无法正常工作:\n{', '.join(fail_layers)}\n\n请查看日志或使用【打开环境终端】手动修复。",
                                icon=QMessageBox.Icon.Warning,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                        else:
                            _exec_close_only_message_box(
                                dlg,
                                "安装完成",
                                "所有依赖已安装并验证通过！点击完成返回依赖向导。",
                                icon=QMessageBox.Icon.Information,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                        _finalize_done_ui()

                    verify_worker.done.connect(on_verify_done)
                    verify_worker.start()

                worker.done.connect(on_install_done)


                timer = QTimer(dlg)
                timer_holder["log"] = timer
                timer.setInterval(50)

                def drain_log_queue():
                    drained = 0
                    lines_to_emit = []
                    while drained < 50:
                        try:
                            line = log_q.get_nowait()
                        except queue.Empty:
                            break
                        else:
                            lines_to_emit.append(line)
                            drained += 1
                    if lines_to_emit:
                        for line in lines_to_emit:
                            parsed_transfer = _parse_pip_transfer_status(line)
                            if parsed_transfer:
                                net_speed_state["pip_speed_text"] = parsed_transfer["speed_text"]
                                net_speed_state["pip_eta_text"] = parsed_transfer["eta_text"]
                                net_speed_state["pip_progress_text"] = parsed_transfer["progress_text"]
                                _render_info_text()
                        _append_log("\n".join(lines_to_emit))

                timer.timeout.connect(drain_log_queue)
                timer.start()

                speed_timer = QTimer(dlg)
                timer_holder["speed"] = speed_timer
                speed_timer.setInterval(1000)
                speed_timer.timeout.connect(_sample_network_speed)
                speed_timer.start()

                def on_close_event(event):
                    ui_closed["value"] = True
                    try:
                        for t in timer_holder.values():
                            if t is not None:
                                t.stop()
                        try:
                            worker.log_updated.disconnect(_append_log)
                        except Exception:
                            pass
                        try:
                            worker.progress_updated.disconnect(_set_progress)
                        except Exception:
                            pass
                        try:
                            worker.done.disconnect(on_install_done)
                        except Exception:
                            pass
                        vw = verify_worker_holder.get("obj")
                        if vw is not None:
                            try:
                                vw.log_updated.disconnect(_append_log)
                            except Exception:
                                pass
                            try:
                                vw.done.disconnect()
                            except Exception:
                                pass
                            try:
                                if vw.isRunning():
                                    vw.wait(3000)
                            except Exception:
                                pass
                        worker.stop()
                        worker.wait(5000)
                    except Exception as e:
                        print(f"[WARN] 关闭事件清理异常: {e}")
                    finally:
                        event.accept()

                dlg.closeEvent = on_close_event

                worker.start()
                result = dlg.exec()
                if worker.isRunning():
                    worker.stop()
                    worker.wait(3000)
                vw = verify_worker_holder.get("obj")
                if vw is not None and vw.isRunning():
                    vw.wait(3000)

                install_verified_in_progress_ui = bool(post_install_verify_passed.get("value", False))
                if result == RESULT_BACK_TO_WIZARD:
                    try:
                        state = _sanitize_state_layers(state_path)
                        installed["layers"] = state.get("installed_layers", [])
                        missing_layers = _missing_required_layers(installed["layers"])
                    except Exception:
                        pass
                    skip_next_ui_runtime_verify = install_verified_in_progress_ui
                    always_show_ui = True
                    continue
                if result != QDialog.DialogCode.Accepted:

                    skip_next_ui_runtime_verify = install_verified_in_progress_ui
                    continue
        break
    return True
