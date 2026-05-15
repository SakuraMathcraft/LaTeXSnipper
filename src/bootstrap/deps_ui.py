import json
import os
import sys
from pathlib import Path

from runtime.app_paths import resource_path
from bootstrap.deps_context import STATE_FILE
from bootstrap.deps_layer_specs import (
    LAYER_MAP,
    MATHCRAFT_RUNTIME_LAYERS,
    _cuda_toolkit_available,
    _gpu_available,
    _normalize_chosen_layers,
    _sanitize_state_layers,
)
from bootstrap.deps_python_runtime import (
    find_existing_python as _find_existing_python,
    normalize_deps_base_dir as _normalize_deps_base_dir,
)
from bootstrap.deps_qt_compat import QIcon
from bootstrap.deps_runtime_verify import _verify_layer_runtime
from bootstrap.deps_state import load_json as _load_json, save_json as _save_json
from bootstrap.deps_workers import UninstallLayerWorker


def _load_config_path():
    from bootstrap.deps_entry import _load_config_path as _entry_load_config_path

    return _entry_load_config_path()


def _build_layers_ui(pyexe, deps_dir, installed_layers, default_select, chosen, state_path,
                     from_settings=False, skip_runtime_verify_once=False):

    from PyQt6.QtGui import QColor, QPalette
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QLabel,
                                 QHBoxLayout, QLineEdit, QMessageBox, QApplication, QToolButton)
    from qfluentwidgets import PushButton, FluentIcon, ComboBox

    def _is_dark_ui() -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        c = app.palette().window().color()
        return ((c.red() + c.green() + c.blue()) / 3.0) < 128


    _sync_deps_fluent_theme()

    theme = {
        "dialog_bg": "#1b1f27" if _is_dark_ui() else "#ffffff",
        "text": "#e7ebf0" if _is_dark_ui() else "#222222",
        "muted": "#a9b3bf" if _is_dark_ui() else "#555555",
        "input_bg": "#232934" if _is_dark_ui() else "#ffffff",
        "border": "#465162" if _is_dark_ui() else "#d0d7de",
        "warn": "#ff8a80" if _is_dark_ui() else "#c62828",
        "ok": "#7bd88f" if _is_dark_ui() else "#2e7d32",
        "hint": "#d9b36c" if _is_dark_ui() else "#856404",
        "accent": "#8ec5ff" if _is_dark_ui() else "#1976d2",
        "accent_hover": "#63b3ff" if _is_dark_ui() else "#0f62c9",
        "btn_bg": "#2b3440" if _is_dark_ui() else "#f8fbff",
        "btn_hover": "#344151" if _is_dark_ui() else "#eef6ff",
    }

    def _style_layer_checkbox(cb, warn_text=False):
        text_color = theme["warn"] if warn_text else (theme["text"] if cb.isEnabled() else theme["muted"])
        disabled_color = theme["muted"]
        pal = cb.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.WindowText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.Text, QColor(text_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(disabled_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(disabled_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(disabled_color))
        cb.setPalette(pal)
        cb.setStyleSheet(
            f"QCheckBox {{ color: {text_color}; spacing: 3px; padding-left: 3px; }}"
            f"QCheckBox:disabled {{ color: {disabled_color}; }}"
        )
        cb.style().unpolish(cb)
        cb.style().polish(cb)
        cb.update()

    def _style_installed_layer_label(cb):
        _style_layer_checkbox(cb)
        fill = "#3a4350" if _is_dark_ui() else "#d8dee6"
        border = "#556170" if _is_dark_ui() else "#c0c7d0"
        cb.setStyleSheet(
            f"QCheckBox {{ color: {theme['muted']}; spacing: 3px; padding-left: 3px; }}"
            "QCheckBox:disabled { color: " + theme["muted"] + "; }"
            "QCheckBox::indicator {"
            " width: 14px;"
            " height: 14px;"
            " margin: 0px;"
            " padding: 0px;"
            f" border: 1px solid {border};"
            " border-radius: 4px;"
            f" background: {fill};"
            " image: none;"
            "}"
            "QCheckBox::indicator:disabled,"
            "QCheckBox::indicator:unchecked:disabled,"
            "QCheckBox::indicator:checked:disabled {"
            f" border: 1px solid {border};"
            " border-radius: 4px;"
            f" background: {fill};"
            " image: none;"
            "}"
        )
        cb.style().unpolish(cb)
        cb.style().polish(cb)
        cb.update()

    def _style_layer_delete_button(btn):
        btn.setFixedSize(30, 30)
        btn.setIcon(FluentIcon.DELETE.icon())
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip("删除该依赖层")
        btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: {theme['muted']};
                padding: 0px;
                margin: 0px;
            }}
            QToolButton:hover {{
                background: {theme['btn_hover']};
                color: {theme['warn']};
                border: 1px solid {theme['warn']};
            }}
            QToolButton:pressed {{
                background: {theme['input_bg']};
                color: {theme['warn']};
                border: 1px solid {theme['warn']};
            }}
        """)

    dlg = QDialog()
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))
    dlg.setWindowTitle("依赖管理向导")
    lay = QVBoxLayout(dlg)
    lay.setSpacing(8)
    lay.setContentsMargins(16, 16, 16, 12)

    def _force_quit():

        try:
            global stop_event
            if 'stop_event' in globals():
                stop_event.set()
        except Exception:
            pass

        QTimer.singleShot(0, lambda: QApplication.instance().quit())
        QTimer.singleShot(20, lambda: sys.exit(0))

    def _on_close(evt):
        evt.accept()
        _force_quit()


    state_path = Path(state_path)
    state_file = str(state_path)
    claimed_layers = []
    failed_layer_names = []
    if os.path.exists(state_file):
        try:
            state = _load_json(Path(state_file), {"installed_layers": []})
            state = _sanitize_state_layers(Path(state_file), state)
            claimed_layers = state.get("installed_layers", [])
            failed_layer_names = state.get("failed_layers", [])
        except Exception:
            pass




    failed_layers = []
    verified_layers = []
    verified_in_ui = False
    skip_verify = bool(skip_runtime_verify_once) or (
        not from_settings and "BASIC" in claimed_layers and "CORE" in claimed_layers
    )
    if skip_verify:
        installed_layers["layers"] = claimed_layers
        verified_in_ui = bool(skip_runtime_verify_once)
    else:
        verified_layers = []
        failed_layers = []
        if claimed_layers and pyexe and os.path.exists(pyexe):
            verified_in_ui = True
            print("[INFO] 正在验证已安装的功能层...")
            for layer in claimed_layers:
                ok, err = _verify_layer_runtime(pyexe, layer, timeout=30)
                if ok:
                    verified_layers.append(layer)
                    print(f"  [OK] {layer} 验证通过")
                else:
                    failed_layers.append((layer, err))
                    print(f"  [FAIL] {layer} 验证失败: {err[:100]}")
            installed_layers["layers"] = verified_layers
            if failed_layers:
                failed_layer_names = [layer for layer, _ in failed_layers]
            try:
                payload = {"installed_layers": verified_layers}
                if failed_layers:
                    payload["failed_layers"] = [layer for layer, _ in failed_layers]
                _save_json(state_file, payload)
                if failed_layers:
                    print(f"[INFO] 已更新状态文件，移除失败的层: {[layer for layer, _ in failed_layers]}")
            except Exception as e:
                print(f"[WARN] 更新状态文件失败: {e}")
        else:
            installed_layers["layers"] = claimed_layers


    py_ready = bool(pyexe and os.path.exists(str(pyexe)))


    missing_layers = []
    if "BASIC" not in installed_layers["layers"]:
        missing_layers.append("BASIC")
    if "CORE" not in installed_layers["layers"]:
        missing_layers.append("CORE")
    if not any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS):
        missing_layers.append("MATHCRAFT_CPU")

    def _build_status_text(current_deps_dir: str, current_py_ready: bool,
                           current_installed_layers: list[str], current_failed_layers: list[str]) -> tuple[str, str]:
        if not current_py_ready:
            return (
                f"当前依赖环境： {current_deps_dir}\n"
                "⚠️ 该目录尚未检测到可复用的 Python 环境。\n"
                "如需在此目录安装依赖，请先点击【下载】并按提示初始化。",
                theme["hint"],
            )
        if current_failed_layers:
            return (
                f"当前依赖环境： {current_deps_dir}\n"
                f"⚠️ 以下功能层安装但无法使用: {', '.join(current_failed_layers)}\n"
                f"可用功能层： {', '.join(current_installed_layers) if current_installed_layers else '(无)'}",
                theme["warn"],
            )
        if current_installed_layers:
            if any(required_layer not in current_installed_layers for required_layer in ("BASIC", "CORE")) or not any(layer in current_installed_layers for layer in MATHCRAFT_RUNTIME_LAYERS):
                return (
                    f"检测到当前环境 {current_deps_dir} 的功能层不完整\n"
                    f"已完整安装的功能层：{', '.join(current_installed_layers)}",
                    theme["muted"],
                )
            return (
                f"当前依赖环境： {current_deps_dir}\n"
                f"已完整安装的功能层：{', '.join(current_installed_layers)}",
                theme["ok"],
            )
        return (
            f"当前依赖环境： {current_deps_dir}\n已安装层：(无)",
            theme["warn"],
        )

    status_text, status_color = _build_status_text(
        deps_dir,
        py_ready,
        installed_layers["layers"],
        failed_layer_names,
    )

    env_info = QLabel(status_text)
    env_info.setStyleSheet(f"color:{status_color};font-size:12px;margin-bottom:4px;")
    lay.addWidget(env_info)
    lay.addWidget(QLabel("选择需要安装的功能层:"))


    failed_layer_names = list(dict.fromkeys(failed_layer_names))

    checks = {}
    delete_buttons = {}

    def _effective_default_select() -> set[str]:
        defaults = {"BASIC", "CORE"}
        active_runtime = {
            str(x) for x in (installed_layers.get("layers", []) or [])
            if str(x) in MATHCRAFT_RUNTIME_LAYERS
        }
        active_runtime.update(
            str(x) for x in (failed_layer_names or [])
            if str(x) in MATHCRAFT_RUNTIME_LAYERS
        )
        if not active_runtime:
            defaults.add("MATHCRAFT_CPU")
        return defaults

    def _sync_layer_checkbox(layer: str, cb, del_btn, effective_defaults: set[str]) -> None:
        if layer in failed_layer_names:
            cb.setChecked(True)
            cb.setEnabled(True)
            cb.setText(f"{layer}（需要修复）")
            _style_layer_checkbox(cb, warn_text=True)
            del_btn.setVisible(True)
            del_btn.setEnabled(True)
        elif layer in installed_layers["layers"]:
            cb.setChecked(False)
            cb.setEnabled(False)
            cb.setText(f"{layer}（已安装）")
            _style_installed_layer_label(cb)
            del_btn.setVisible(True)
            del_btn.setEnabled(True)
        else:
            cb.setEnabled(True)
            cb.setChecked(layer in effective_defaults)
            cb.setText(layer)
            _style_layer_checkbox(cb)
            del_btn.setVisible(False)
            del_btn.setEnabled(False)

    def make_del_func(layer_name):
        def _del():
            reply = _exec_close_only_message_box(
                dlg,
                "删除确认",
                f"确定要删除层 [{layer_name}] 及其所有依赖包吗？\n\n确认后将打开卸载进度窗口，并在当前程序内执行卸载。",
                icon=QMessageBox.Icon.Warning,
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                pkgs = list(LAYER_MAP.get(layer_name, []))
                pkg_names = []
                for pkg in pkgs:
                    pkg_name = pkg.split('~')[0].split('=')[0].split('>')[0].split('<')[0].strip()
                    if pkg_name and pkg_name not in pkg_names:
                        pkg_names.append(pkg_name)
                pdlg, info2, logw2, btn_cancel2, btn_pause2, progress2 = _progress_dialog()
                pdlg.setWindowTitle("卸载进度")
                info2.setText(f"正在卸载层 {layer_name}，请不要关闭此窗口...")
                btn_pause2.hide()
                btn_cancel2.setText("关闭")
                btn_cancel2.setEnabled(False)

                worker = UninstallLayerWorker(str(pyexe), state_file, layer_name, pkg_names)
                worker.log_updated.connect(logw2.append)
                worker.progress_updated.connect(progress2.setValue)

                def _on_done(success: bool, removed_layer: str):
                    btn_cancel2.setEnabled(True)
                    btn_cancel2.setText("完成")
                    try:
                        btn_cancel2.clicked.disconnect()
                    except Exception:
                        pass
                    btn_cancel2.clicked.connect(lambda: pdlg.accept())
                    if success:
                        info2.setText(f"层 {removed_layer} 已卸载完成。点击完成返回依赖向导。")
                        try:
                            if removed_layer in installed_layers["layers"]:
                                installed_layers["layers"].remove(removed_layer)
                        except Exception:
                            pass
                        try:
                            dlg.refresh_ui()
                        except Exception:
                            pass
                    else:
                        info2.setText(f"层 {removed_layer} 卸载过程中存在问题，请查看日志。")
                    progress2.setValue(100)

                worker.done.connect(_on_done)
                worker.start()
                pdlg.exec()
        return _del


    effective_default_select = _effective_default_select()
    for layer in LAYER_MAP.keys():
        row = QHBoxLayout()
        cb = QCheckBox(layer)
        del_btn = QToolButton()
        _style_layer_delete_button(del_btn)
        del_btn.clicked.connect(make_del_func(layer))
        _sync_layer_checkbox(layer, cb, del_btn, effective_default_select)
        checks[layer] = cb
        delete_buttons[layer] = del_btn
        row.addWidget(cb)
        row.addWidget(del_btn)
        lay.addLayout(row)


    def on_mathcraft_cpu_changed(state):
        if state and checks.get("MATHCRAFT_GPU") and checks["MATHCRAFT_GPU"].isEnabled():
            checks["MATHCRAFT_GPU"].setChecked(False)

    def on_mathcraft_gpu_changed(state):
        if state and checks.get("MATHCRAFT_CPU") and checks["MATHCRAFT_CPU"].isEnabled():
            checks["MATHCRAFT_CPU"].setChecked(False)

    if "MATHCRAFT_CPU" in checks:
        checks["MATHCRAFT_CPU"].stateChanged.connect(on_mathcraft_cpu_changed)
    if "MATHCRAFT_GPU" in checks:
        checks["MATHCRAFT_GPU"].stateChanged.connect(on_mathcraft_gpu_changed)


    gpu_info_label = QLabel()

    def _refresh_gpu_info_label() -> None:
        current_installed_layers = {
            str(layer) for layer in (installed_layers.get("layers", []) or [])
        }
        current_failed_layers = {str(layer) for layer in (failed_layer_names or [])}
        if "MATHCRAFT_GPU" in current_installed_layers:
            text = "✅ MATHCRAFT_GPU 已安装，GPU 加速可用"
            color = theme["ok"]
        elif "MATHCRAFT_GPU" in current_failed_layers:
            text = "⚠️ MATHCRAFT_GPU 验证失败，请使用MATHCRAFT_CPU后端"
            color = theme["warn"]
        elif _gpu_available() and _cuda_toolkit_available():
            text = "✅ 检测到 NVIDIA GPU 和 CUDA Toolkit；可尝试 MATHCRAFT_GPU"
            color = theme["ok"]
        elif _gpu_available():
            text = "⚠️ 未检测到 nvcc/CUDA Toolkit，建议使用 MATHCRAFT_CPU后端"
            color = theme["hint"]
        else:
            text = "⚠️ 未检测到 NVIDIA GPU，建议使用默认 MATHCRAFT_CPU 后端"
            color = theme["hint"]
        gpu_info_label.setText(text)
        gpu_info_label.setStyleSheet(f"color:{color};font-size:12px;margin:4px 0;")

    _refresh_gpu_info_label()
    lay.addWidget(gpu_info_label)

    path_row = QHBoxLayout()
    path_edit = QLineEdit(deps_dir)
    path_edit.setReadOnly(True)
    btn_path = PushButton(FluentIcon.FOLDER, "更改依赖安装/加载路径")
    btn_path.setFixedHeight(36)
    btn_path.setToolTip("更改后会立即刷新当前依赖环境状态")
    path_row.addWidget(QLabel("依赖安装/加载路径:"))
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(btn_path)
    lay.addLayout(path_row)


    mirror_row = QHBoxLayout()
    mirror_row.setContentsMargins(0, 0, 0, 0)
    mirror_row.setSpacing(6)
    mirror_row.addWidget(QLabel("下载源:"))
    mirror_box = ComboBox()
    mirror_box.addItem("官方 PyPI", userData="off")
    mirror_box.addItem("清华镜像", userData="tuna")
    mirror_box.setFixedHeight(30)
    mirror_row.addWidget(mirror_box, 1)
    lay.addLayout(mirror_row)

    def _current_mirror_source() -> str:
        try:
            idx = int(mirror_box.currentIndex())
        except Exception:
            idx = -1
        value = None
        if idx >= 0:
            try:
                value = mirror_box.itemData(idx)
            except Exception:
                value = None
        if value is None:
            try:
                text = str(mirror_box.currentText()).strip()
            except Exception:
                text = ""
            value = "tuna" if "清华" in text else "off"
        value = str(value or "off").strip().lower()
        return "tuna" if value == "tuna" else "off"

    def _load_saved_mirror_source() -> str:
        try:
            cfg_path = _load_config_path()
            if cfg_path.exists():
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    saved = str(data.get("deps_mirror_source", "")).strip().lower()
                    if saved in ("off", "tuna"):
                        return saved
        except Exception:
            pass
        return "off"

    def _save_mirror_source(source: str) -> None:
        try:
            cfg_path = _load_config_path()
            cfg = {}
            if cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    cfg = {}
            cfg["deps_mirror_source"] = source
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    _saved_mirror = _load_saved_mirror_source()
    mirror_box.setCurrentIndex(1 if _saved_mirror == "tuna" else 0)

    def _on_mirror_changed(_index: int) -> None:
        _save_mirror_source(_current_mirror_source())

    mirror_box.currentIndexChanged.connect(_on_mirror_changed)


    btn_row = QHBoxLayout()

    btn_download = PushButton(FluentIcon.DOWNLOAD, "下载")
    btn_download.setFixedHeight(36)
    btn_enter = PushButton(FluentIcon.PLAY, "进入")
    btn_enter.setFixedHeight(36)
    btn_enter.setDefault(True)
    btn_cancel = PushButton(FluentIcon.CLOSE, "退出程序")
    btn_cancel.setFixedHeight(36)
    btn_row.addWidget(btn_download)
    btn_row.addWidget(btn_enter)
    btn_row.addWidget(btn_cancel)
    lay.addLayout(btn_row)


    warn = QLabel("缺少关键依赖层，部分功能将不可用！")
    warn.setStyleSheet(f"color:{theme['warn']};")
    lay.addWidget(warn)


    desc = QLabel(
        "📦 层级说明：\n"
        "• BASIC：基础运行层，包含网络、图像处理和通用工具依赖。\n"
        "• CORE：识别功能层，包含 MathCraft ONNX OCR 及文档导出 / PDF 相关依赖。\n"
        "• MATHCRAFT_CPU：ONNX Runtime CPU 后端，默认推荐，稳定性更高。\n"
        "• MATHCRAFT_GPU：ONNX Runtime GPU 后端，需要本机 NVIDIA 驱动 / CUDA DLL 可用。\n"
        "• PANDOC：可选 Pandoc 导出后端，支持 docx/odt/epub/rtf 等文档格式转换。\n"
        "• 识别功能实际运行需要 BASIC + CORE + 一个 MathCraft 后端。\n"
        "• 默认推荐 BASIC + CORE + MATHCRAFT_CPU；如需 GPU 推理请手动勾选 MATHCRAFT_GPU。\n"
        "\n"
        "⚠️ 重要提示：\n"
        "• MATHCRAFT_CPU 和 MATHCRAFT_GPU 互斥；切换时会自动清理冲突的 onnxruntime 组件。\n"
        "• 已安装层会在进入向导时重新验证；验证失败的层会标记为“需要修复”。\n"
        "• 本向导只管理内置 MathCraft 依赖链，不管理外部模型服务本身。\n"
        "• 若你只使用外部模型，可点击“跳过安装并进入”通过设置页面进行配置。"
    )
    desc.setStyleSheet(f"color:{theme['muted']};font-size:11px;line-height:1.35;")
    lay.addWidget(desc)

    chosen = {
        "layers": None,
        "mirror": False,
        "mirror_source": _current_mirror_source(),
        "deps_path": deps_dir,
        "force_enter": False,
        "verified_in_ui": verified_in_ui,
        "action": None,
    }

    def _current_deps_dir() -> str:
        try:
            text = path_edit.text().strip()
            return text or deps_dir
        except Exception:
            return deps_dir

    def _current_py_ready() -> bool:
        try:
            return bool(_find_existing_python(Path(_current_deps_dir())))
        except Exception:
            return False


    def update_ui():
        required = {"BASIC", "CORE"}
        missing = [required_layer for required_layer in required if required_layer not in installed_layers["layers"]]
        if not any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS):
            missing.append("MATHCRAFT_CPU")
        is_lack_critical = bool(missing)
        py_ready = _current_py_ready()
        if not py_ready:
            btn_enter.setText("不可进入(先初始化)")
            btn_enter.setEnabled(False)
            warn.setVisible(True)
            return
        btn_enter.setEnabled(True)
        btn_enter.setText("跳过安装并进入" if is_lack_critical else "进入")
        warn.setVisible(is_lack_critical)

    update_ui()

    def choose_path():
        nonlocal failed_layer_names, state_file, state_path, pyexe
        import os
        d = _select_existing_directory_with_icon(dlg, "选择依赖安装/加载目录", deps_dir)
        if d:
            normalized = str(_normalize_deps_base_dir(Path(d)))
            path_edit.setText(normalized)
            normalized_path = Path(normalized)
            _default_pyexe_name = "python.exe" if os.name == "nt" else "python3"
            active_pyexe = _find_existing_python(normalized_path) or (normalized_path / "python311" / _default_pyexe_name)
            pyexe = active_pyexe
            state_path = normalized_path / STATE_FILE
            state_file = str(state_path)
            chosen["deps_path"] = normalized
            chosen["verified_in_ui"] = False
            installed_layers["layers"] = []
            failed_layer_names = []
            if os.path.exists(state_file):
                try:
                    state = _load_json(Path(state_file), {"installed_layers": []})
                    state = _sanitize_state_layers(Path(state_file), state)
                    installed_layers["layers"] = state.get("installed_layers", [])
                    failed_layer_names = state.get("failed_layers", [])
                except Exception:
                    pass
            py_ready_local = bool(active_pyexe and Path(active_pyexe).exists())
            status_text, status_color = _build_status_text(
                normalized,
                py_ready_local,
                installed_layers["layers"],
                failed_layer_names,
            )
            env_info.setText(status_text)
            env_info.setStyleSheet(f"color:{status_color};font-size:12px;margin-bottom:4px;")
            effective_default_select = _effective_default_select()
            for layer, cb in checks.items():
                _sync_layer_checkbox(layer, cb, delete_buttons[layer], effective_default_select)
            _refresh_gpu_info_label()

            update_ui()

            config_path = str(_load_config_path())
            cfg = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            cfg["install_base_dir"] = normalized
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                os.environ["LATEXSNIPPER_INSTALL_BASE_DIR"] = normalized
                os.environ["LATEXSNIPPER_DEPS_DIR"] = normalized
                if active_pyexe and Path(active_pyexe).exists():
                    os.environ["LATEXSNIPPER_PYEXE"] = str(active_pyexe)
                print(f"[INFO] 依赖路径已保存并刷新状态: {normalized}")
            except Exception as e:
                print(f"[ERR] 保存配置失败: {e}")

    btn_path.clicked.connect(choose_path)

    def enter():
        """Enter when the environment is complete, or apply the configured skip policy."""
        sel = _normalize_chosen_layers([L for L, c in checks.items() if c.isChecked()])
        mirror_source = _current_mirror_source()
        chosen["layers"] = sel
        chosen["mirror"] = (mirror_source == "tuna")
        chosen["mirror_source"] = mirror_source
        chosen["deps_path"] = path_edit.text()
        _save_mirror_source(mirror_source)

        if not _current_py_ready():
            custom_warning_dialog(
                "不可进入",
                "当前依赖目录尚未检测到可复用的 Python 环境。\n请先点击“下载”初始化依赖环境后再进入主程序。",
                dlg
            )
            return

        print(f"[DEBUG] Selected layers: {sel}")
        required = {"BASIC", "CORE"}
        missing = [required_layer for required_layer in required if required_layer not in installed_layers["layers"]]
        if not any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS):
            missing.append("MATHCRAFT_CPU")


        if not missing:
            chosen["action"] = "enter"
            chosen["layers"] = []
            chosen["force_enter"] = False
            dlg.accept()
            return


        chosen["action"] = "enter"
        chosen["layers"] = []
        chosen["force_enter"] = True
        dlg.done(1)

    btn_enter.clicked.connect(enter)

    def download():
        sel = _normalize_chosen_layers([L for L, c in checks.items() if c.isChecked()])
        if not sel:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning(
                title="提示",
                content="请至少选择一个依赖层进行下载。",
                parent=dlg.parent() if dlg.parent() is not None else dlg,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
            return
        chosen["layers"] = sel
        mirror_source = _current_mirror_source()
        chosen["mirror"] = (mirror_source == "tuna")
        chosen["mirror_source"] = mirror_source
        chosen["deps_path"] = path_edit.text()
        chosen["force_enter"] = False
        chosen["action"] = "download"
        _save_mirror_source(mirror_source)
        dlg.accept()

    btn_download.clicked.connect(download)

    from PyQt6.QtCore import QTimer

    def _ask_exit_confirm() -> QMessageBox.StandardButton:
        return _exec_close_only_message_box(
            dlg,
            "退出确认",
            "确定要退出安装向导并关闭程序吗？",
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )


    def refresh_ui():
        """Refresh dependency state after installation completes."""
        nonlocal failed_layer_names
        try:
            new_state = _sanitize_state_layers(Path(state_path))
            installed_layers["layers"] = new_state.get("installed_layers", [])
            failed_layer_names = new_state.get("failed_layers", [])


            if (
                "BASIC" in installed_layers["layers"]
                and "CORE" in installed_layers["layers"]
                and any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS)
            ):
                warn.setVisible(False)
                btn_enter.setText("进入")
            else:
                warn.setVisible(True)
                btn_enter.setText("跳过安装并进入")


            effective_default_select = _effective_default_select()
            for layer, cb in checks.items():
                _sync_layer_checkbox(layer, cb, delete_buttons[layer], effective_default_select)
            _refresh_gpu_info_label()

            current_dir = _current_deps_dir()
            py_ready_local = bool(_find_existing_python(Path(current_dir)))
            status_text, status_color = _build_status_text(
                current_dir,
                py_ready_local,
                installed_layers["layers"],
                failed_layer_names,
            )
            env_info.setText(status_text)
            env_info.setStyleSheet(f"color:{status_color};font-size:12px;margin-bottom:4px;")
            print("[OK] 依赖状态刷新成功 ✅")
        except Exception as e:
            print(f"[WARN] UI 刷新失败: {e}")


    dlg.refresh_ui = refresh_ui


    _closing_dialog = {"active": False}

    def _exit_app():
        """Confirm and exit the application."""
        if _closing_dialog["active"]:
            return
        reply = _ask_exit_confirm()
        if reply == QMessageBox.StandardButton.Yes:
            _closing_dialog["active"] = True
            try:
                main_mod = sys.modules.get("__main__")
                release_lock = getattr(main_mod, "_release_single_instance_lock", None) if main_mod is not None else None
                if callable(release_lock):
                    release_lock()
            except Exception as e:
                print(f"[WARN] 退出前释放程序锁失败: {e}")
            try:
                dlg.done(QDialog.DialogCode.Rejected)
            except Exception:
                pass
            try:
                app = QApplication.instance()
                if app is not None:
                    app.exit(0)
            except Exception:
                pass
            os._exit(0)

    btn_cancel.clicked.connect(_exit_app)


    def _on_close(evt):
        if _closing_dialog["active"]:
            evt.accept()
            return
        _exit_app()
        evt.ignore()
    dlg.closeEvent = _on_close

    return dlg, chosen


def _progress_dialog():
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QProgressBar, QHBoxLayout, QApplication
    from PyQt6.QtCore import QEvent
    from qfluentwidgets import PushButton, FluentIcon
    _sync_deps_fluent_theme()
    def _is_dark_ui() -> bool:
        try:
            import qfluentwidgets as qfw
            fn = getattr(qfw, "isDarkTheme", None)
            if callable(fn):
                return bool(fn())
        except Exception:
            pass
        app = QApplication.instance()
        if app is None:
            return False
        c = app.palette().window().color()
        return ((c.red() + c.green() + c.blue()) / 3.0) < 128

    def _theme_tokens() -> dict:
        dark = _is_dark_ui()
        return {
            "dark": dark,
            "dialog_bg": "#1b1f27" if dark else "#ffffff",
            "panel_bg": "#232934" if dark else "#f7f9fc",
            "text": "#e7ebf0" if dark else "#222222",
            "muted": "#a9b3bf" if dark else "#666666",
            "border": "#465162" if dark else "#d0d7de",
            "progress_bg": "#232934" if dark else "#ffffff",
            "progress_border": "#465162" if dark else "#cfd6dd",
            "progress_chunk": "#4c9aff" if dark else "#1976d2",
        }

    dlg = QDialog()
    dlg.setWindowTitle("安装进度")
    dlg.resize(680, 440)
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))
    lay = QVBoxLayout(dlg)
    info = QLabel("正在遍历寻找缺失的库，完成后将自动下载，请不要关闭此窗口(๑•̀ㅂ•́)و✧)...")
    logw = QTextEdit()
    logw.setReadOnly(True)
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setFixedHeight(20)
    progress.setMinimumWidth(400)

    btn_cancel = PushButton(FluentIcon.CLOSE, "退出下载")
    btn_cancel.setFixedHeight(32)
    btn_pause = PushButton(FluentIcon.PAUSE, "暂停下载")
    btn_pause.setFixedHeight(32)
    btn_row = QHBoxLayout()
    btn_row.addWidget(btn_pause)
    btn_row.addWidget(btn_cancel)
    lay.addWidget(info)
    lay.addWidget(logw, 1)
    lay.addWidget(progress)
    lay.addLayout(btn_row)

    def _apply_theme_styles(force: bool = False):
        theme = _theme_tokens()
        if (not force) and getattr(dlg, "_theme_is_dark_cached", None) == theme["dark"]:
            return
        dlg._theme_is_dark_cached = theme["dark"]

        info.setStyleSheet(f"color: {theme['muted']};")
        progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid __PROGRESS_BORDER__;
                border-radius: 6px;
                text-align: center;
                background-color: __PROGRESS_BG__;
                color: __TEXT__;
            }
            QProgressBar::chunk {
                background: __PROGRESS_CHUNK__;
                border-radius: 6px;
            }
        """.replace("__PROGRESS_BORDER__", theme["progress_border"])
           .replace("__PROGRESS_BG__", theme["progress_bg"])
           .replace("__TEXT__", theme["text"])
           .replace("__PROGRESS_CHUNK__", theme["progress_chunk"]))

    _apply_theme_styles(force=True)

    _orig_event = dlg.event
    def _event_with_theme_refresh(event):
        if event.type() in (
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            _apply_theme_styles()
        return _orig_event(event)
    dlg.event = _event_with_theme_refresh

    _orig_show_event = dlg.showEvent
    def _show_event_with_theme_refresh(event):
        _apply_theme_styles(force=True)
        _orig_show_event(event)
    dlg.showEvent = _show_event_with_theme_refresh

    return dlg, info, logw, btn_cancel, btn_pause, progress


def _apply_close_only_window_flags(win):
    from PyQt6.QtCore import Qt
    flags = (
        win.windowFlags()
        | Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowSystemMenuHint
    )
    flags = (
        flags
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    win.setWindowFlags(flags)


def _deps_dialog_theme() -> dict:
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    dark = False
    try:
        if app is not None:
            c = app.palette().window().color()
            dark = ((c.red() + c.green() + c.blue()) / 3.0) < 128
    except Exception:
        dark = False
    return {
        "dialog_bg": "#1b1f27" if dark else "#ffffff",
        "text": "#e7ebf0" if dark else "#222222",
        "muted": "#a9b3bf" if dark else "#555555",
        "panel_bg": "#232934" if dark else "#f8fbff",
        "border": "#465162" if dark else "#d0d7de",
        "accent": "#8ec5ff" if dark else "#1976d2",
        "btn_hover": "#344151" if dark else "#eef6ff",
    }


def _sync_deps_fluent_theme() -> None:
    try:
        from qfluentwidgets import setTheme, Theme
        t = _deps_dialog_theme()
        setTheme(Theme.DARK if t["dialog_bg"] == "#1b1f27" else Theme.LIGHT)
    except Exception:
        pass


def _apply_app_window_icon(win) -> None:
    from core.window_icons import apply_app_window_icon
    apply_app_window_icon(win, resource_path("assets/icon.ico"))


def _select_existing_directory_with_icon(parent, title: str, initial_dir: str) -> str:
    from PyQt6.QtWidgets import QFileDialog
    from core.window_icons import schedule_native_dialog_icon

    dlg = QFileDialog(parent, title, initial_dir)
    dlg.setFileMode(QFileDialog.FileMode.Directory)
    dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    _apply_app_window_icon(dlg)
    icon_timer = schedule_native_dialog_icon(title, resource_path("assets/icon.ico"))
    try:
        if dlg.exec() != QFileDialog.DialogCode.Accepted:
            return ""
    finally:
        if icon_timer is not None:
            icon_timer.stop()
    selected = dlg.selectedFiles()
    return selected[0] if selected else ""


def _exec_close_only_message_box(
    parent,
    title: str,
    text: str,
    icon,
    buttons,
    default_button=None,
):
    from PyQt6.QtWidgets import QMessageBox
    msg = QMessageBox(parent)
    _apply_app_window_icon(msg)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon)
    msg.setStandardButtons(buttons)
    if default_button is not None:
        msg.setDefaultButton(default_button)
    _apply_close_only_window_flags(msg)
    return QMessageBox.StandardButton(msg.exec())


def custom_warning_dialog(title, message, parent=None):
    from PyQt6.QtWidgets import QMessageBox as _QMessageBox
    _sync_deps_fluent_theme()
    _exec_close_only_message_box(
        parent,
        title,
        message,
        icon=_QMessageBox.Icon.Warning,
        buttons=_QMessageBox.StandardButton.Ok,
        default_button=_QMessageBox.StandardButton.Ok,
    )
    return True
