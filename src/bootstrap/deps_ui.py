from localization.manager import translate as tr
import json
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from runtime.app_paths import resource_path
from bootstrap.deps_context import CONFIG_FILE, STATE_FILE, _config_dir_path
from bootstrap.deps_layer_specs import (
    LAYER_MAP,
    MATHCRAFT_RUNTIME_LAYERS,
    _normalize_chosen_layers,
    _sanitize_state_layers,
    layer_display_name,
)
from runtime.dependency_runtime import (
    DEPENDENCY_PYTHON_DIRNAME,
    dependency_venv_python as _dependency_venv_python,
    find_existing_python as _find_existing_python,
)
from bootstrap.deps_runtime_verify import (
    _verify_layer_runtime,
    format_layer_verify_failure,
)
from bootstrap.deps_state import load_json as _load_json, save_json as _save_json
from bootstrap.deps_workers import UninstallLayerWorker
from bootstrap.progress_dialog import InstallProgressDialog
from runtime.macos_local_data_cleanup import (
    cleanup_macos_local_data,
    macos_cleanup_targets,
)
from runtime.dependency_python import (
    normalize_deps_base_dir as _normalize_deps_base_dir,
)


def activate_dependency_dialog(dlg) -> None:
    """Make dependency management visible before entering its event loop."""
    try:
        dlg.setWindowFlag(Qt.WindowType.Window, True)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    except Exception as e:
        print(f"[DEBUG] 设置依赖管理窗口属性失败: {e}")

    def _raise_dialog() -> None:
        try:
            if not dlg.isVisible():
                dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            app = QApplication.instance()
            if app is not None:
                app.alert(dlg, 0)
                app.processEvents()
        except RuntimeError:
            pass
        except Exception as e:
            print(f"[DEBUG] 激活依赖管理窗口失败: {e}")

    _raise_dialog()
    QTimer.singleShot(0, _raise_dialog)
    QTimer.singleShot(250, _raise_dialog)


def _load_config_path():
    return _config_dir_path() / CONFIG_FILE


def _runtime_layer_names() -> tuple[str, ...]:
    if sys.platform == "darwin":
        return ("MATHCRAFT_CPU",)
    return tuple(MATHCRAFT_RUNTIME_LAYERS)


def _visible_layer_names() -> list[str]:
    layers = list(LAYER_MAP.keys())
    if sys.platform == "darwin":
        layers = [layer for layer in layers if layer != "MATHCRAFT_GPU"]
    return layers


def _build_layers_ui(
    pyexe,
    deps_dir,
    installed_layers,
    default_select,
    chosen,
    state_path,
    from_settings=False,
    skip_runtime_verify_once=False,
):

    from PyQt6.QtGui import QColor, QPalette
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QCheckBox,
        QLabel,
        QHBoxLayout,
        QLineEdit,
        QMessageBox,
        QApplication,
        QToolButton,
    )
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
        text_color = (
            theme["warn"]
            if warn_text
            else (theme["text"] if cb.isEnabled() else theme["muted"])
        )
        disabled_color = theme["muted"]
        pal = cb.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.WindowText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.Text, QColor(text_color))
        pal.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.WindowText,
            QColor(disabled_color),
        )
        pal.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(disabled_color),
        )
        pal.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
            QColor(disabled_color),
        )
        cb.setPalette(pal)
        cb.setStyleSheet(
            f"QCheckBox {{ color: {text_color}; font-size: 13px; spacing: 3px; padding-left: 3px; }}"
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
            f"QCheckBox {{ color: {theme['muted']}; font-size: 13px; spacing: 3px; padding-left: 3px; }}"
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
        btn.setToolTip(tr("删除该依赖层"))
        btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: {theme["muted"]};
                padding: 0px;
                margin: 0px;
            }}
            QToolButton:hover {{
                background: {theme["btn_hover"]};
                color: {theme["warn"]};
                border: 1px solid {theme["warn"]};
            }}
            QToolButton:pressed {{
                background: {theme["input_bg"]};
                color: {theme["warn"]};
                border: 1px solid {theme["warn"]};
            }}
        """)

    dlg = QDialog()
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))
    dlg.setWindowTitle(tr("依赖管理"))
    lay = QVBoxLayout(dlg)
    lay.setSpacing(8)
    lay.setContentsMargins(16, 16, 16, 12)

    def _force_quit():

        try:
            global stop_event
            if "stop_event" in globals():
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
            print("[DEBUG] 正在验证已安装依赖")
            for layer in claimed_layers:
                ok, err = _verify_layer_runtime(pyexe, layer, timeout=30)
                if ok:
                    verified_layers.append(layer)
                    print(f"[DEBUG] {layer_display_name(layer)}验证通过")
                else:
                    failed_layers.append((layer, err))
                    print(format_layer_verify_failure(layer, err))
            installed_layers["layers"] = verified_layers
            if failed_layers:
                failed_layer_names = [layer for layer, _ in failed_layers]
            try:
                payload = {"installed_layers": verified_layers}
                if failed_layers:
                    payload["failed_layers"] = [layer for layer, _ in failed_layers]
                _save_json(state_file, payload)
                if failed_layers:
                    labels = "、".join(
                        layer_display_name(layer) for layer, _ in failed_layers
                    )
                    print(f"[WARN] 已从依赖状态中移除验证失败项：{labels}")
            except Exception as e:
                print(f"[WARN] 更新状态文件失败: {e}")
        else:
            installed_layers["layers"] = claimed_layers

    py_ready = bool(pyexe and os.path.exists(str(pyexe)))

    def _build_status_text(
        current_py_ready: bool, current_failed_layers: list[str]
    ) -> tuple[str, str]:
        visible_layers = set(_visible_layer_names())
        display_failed_layers = [
            layer for layer in current_failed_layers if layer in visible_layers
        ]
        if not current_py_ready:
            return (
                tr("未检测到依赖环境，请点击“下载”进行初始化。"),
                theme["hint"],
            )
        if display_failed_layers:
            return (
                tr("以下依赖需要修复：")
                + "、".join(
                    layer_display_name(layer) for layer in display_failed_layers
                ),
                theme["warn"],
            )
        return "", theme["muted"]

    status_text, status_color = _build_status_text(
        py_ready,
        failed_layer_names,
    )

    env_info = QLabel(status_text)
    env_info.setStyleSheet(f"color:{status_color};font-size:13px;margin-bottom:4px;")
    env_info.setVisible(bool(status_text))
    lay.addWidget(env_info)

    def _set_environment_notice(
        current_py_ready: bool, current_failed_layers: list[str]
    ) -> None:
        text, color = _build_status_text(current_py_ready, current_failed_layers)
        env_info.setText(text)
        env_info.setStyleSheet(f"color:{color};font-size:13px;margin-bottom:4px;")
        env_info.setVisible(bool(text))

    layer_heading = QLabel(tr("选择需要安装的功能层:"))
    layer_heading.setStyleSheet("font-size:13px;")
    lay.addWidget(layer_heading)

    failed_layer_names = list(dict.fromkeys(failed_layer_names))

    checks = {}
    delete_buttons = {}

    def _effective_default_select() -> set[str]:
        defaults = {"BASIC", "CORE"}
        active_runtime = {
            str(x)
            for x in (installed_layers.get("layers", []) or [])
            if str(x) in _runtime_layer_names()
        }
        active_runtime.update(
            str(x)
            for x in (failed_layer_names or [])
            if str(x) in _runtime_layer_names()
        )
        if not active_runtime:
            defaults.add("MATHCRAFT_CPU")
        return defaults

    def _sync_layer_checkbox(
        layer: str, cb, del_btn, effective_defaults: set[str]
    ) -> None:
        if layer in failed_layer_names:
            cb.setChecked(True)
            cb.setEnabled(True)
            cb.setText(
                tr("{layer}（需要修复）").format(layer=layer_display_name(layer))
            )
            _style_layer_checkbox(cb, warn_text=True)
            del_btn.setVisible(True)
            del_btn.setEnabled(True)
        elif layer in installed_layers["layers"]:
            cb.setChecked(False)
            cb.setEnabled(False)
            cb.setText(tr("{layer}（已安装）").format(layer=layer_display_name(layer)))
            _style_installed_layer_label(cb)
            del_btn.setVisible(True)
            del_btn.setEnabled(True)
        else:
            cb.setEnabled(True)
            cb.setChecked(layer in effective_defaults)
            cb.setText(layer_display_name(layer))
            _style_layer_checkbox(cb)
            del_btn.setVisible(False)
            del_btn.setEnabled(False)

    def make_del_func(layer_name):
        def _del():
            layer_label = layer_display_name(layer_name)
            reply = _exec_close_only_message_box(
                dlg,
                tr("删除确认"),
                tr(
                    "确定要删除“{layer}”及其所有依赖包吗？\n\n"
                    "确认后将打开卸载进度窗口。"
                ).format(layer=layer_label),
                icon=QMessageBox.Icon.Warning,
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                pkgs = list(LAYER_MAP.get(layer_name, []))
                pkg_names = []
                for pkg in pkgs:
                    pkg_name = (
                        pkg.split("~")[0]
                        .split("=")[0]
                        .split(">")[0]
                        .split("<")[0]
                        .strip()
                    )
                    if pkg_name and pkg_name not in pkg_names:
                        pkg_names.append(pkg_name)
                pdlg = InstallProgressDialog()
                info2 = pdlg.info_label
                logw2 = pdlg.log_view
                btn_cancel2 = pdlg.cancel_button
                btn_pause2 = pdlg.pause_button
                progress2 = pdlg.progress_bar
                pdlg.setWindowTitle(tr("卸载进度"))
                info2.setText(
                    tr("正在卸载{layer}，请不要关闭此窗口...").format(layer=layer_label)
                )
                btn_pause2.hide()
                btn_cancel2.setText(tr("关闭"))
                btn_cancel2.setEnabled(False)

                worker = UninstallLayerWorker(
                    str(pyexe), state_file, layer_name, pkg_names
                )
                worker.log_updated.connect(logw2.append)
                worker.progress_updated.connect(progress2.setValue)

                def _on_done(success: bool, removed_layer: str):
                    btn_cancel2.setEnabled(True)
                    btn_cancel2.setText(tr("完成"))
                    try:
                        btn_cancel2.clicked.disconnect()
                    except Exception:
                        pass
                    btn_cancel2.clicked.connect(lambda: pdlg.accept())
                    if success:
                        info2.setText(
                            tr("{layer}已卸载。").format(
                                layer=layer_display_name(removed_layer)
                            )
                        )
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
                        info2.setText(
                            tr("{layer}卸载失败，请查看日志。").format(
                                layer=layer_display_name(removed_layer)
                            )
                        )
                    progress2.setValue(100)

                worker.done.connect(_on_done)
                worker.start()
                pdlg.exec()

        return _del

    effective_default_select = _effective_default_select()
    for layer in _visible_layer_names():
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
        if (
            state
            and checks.get("MATHCRAFT_GPU")
            and checks["MATHCRAFT_GPU"].isEnabled()
        ):
            checks["MATHCRAFT_GPU"].setChecked(False)

    def on_mathcraft_gpu_changed(state):
        if (
            state
            and checks.get("MATHCRAFT_CPU")
            and checks["MATHCRAFT_CPU"].isEnabled()
        ):
            checks["MATHCRAFT_CPU"].setChecked(False)

    if "MATHCRAFT_CPU" in checks:
        checks["MATHCRAFT_CPU"].stateChanged.connect(on_mathcraft_cpu_changed)
    if "MATHCRAFT_GPU" in checks:
        checks["MATHCRAFT_GPU"].stateChanged.connect(on_mathcraft_gpu_changed)

    path_row = QHBoxLayout()
    path_edit = QLineEdit(deps_dir)
    path_edit.setReadOnly(True)
    btn_path = PushButton(FluentIcon.FOLDER, tr("更改路径"))
    btn_path.setFixedHeight(32)
    btn_path.setToolTip(tr("更改后重新检测依赖"))
    path_label = QLabel(tr("依赖安装/加载路径:"))
    path_label.setStyleSheet("font-size:13px;")
    path_row.addWidget(path_label)
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(btn_path)
    lay.addLayout(path_row)

    btn_cleanup_macos_local_data = None
    if sys.platform == "darwin":
        cleanup_row = QHBoxLayout()
        cleanup_row.setContentsMargins(0, 0, 0, 0)
        cleanup_row.setSpacing(6)
        btn_cleanup_macos_local_data = PushButton(
            FluentIcon.BROOM, tr("清理本机依赖与缓存")
        )
        btn_cleanup_macos_local_data.setFixedHeight(36)
        btn_cleanup_macos_local_data.setToolTip(
            tr("移除本机下载的依赖、缓存和日志；默认保留应用设置")
        )
        cleanup_row.addWidget(btn_cleanup_macos_local_data, 1)
        lay.addLayout(cleanup_row)

    mirror_row = QHBoxLayout()
    mirror_row.setContentsMargins(0, 0, 0, 0)
    mirror_row.setSpacing(6)
    mirror_label = QLabel(tr("下载源:"))
    mirror_label.setStyleSheet("font-size:13px;")
    mirror_row.addWidget(mirror_label)
    mirror_box = ComboBox()
    mirror_box.addItem(tr("官方 PyPI"), userData="off")
    mirror_box.addItem(tr("清华镜像"), userData="tuna")
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
            cfg_path.write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    _saved_mirror = _load_saved_mirror_source()
    mirror_box.setCurrentIndex(1 if _saved_mirror == "tuna" else 0)

    def _on_mirror_changed(_index: int) -> None:
        _save_mirror_source(_current_mirror_source())

    mirror_box.currentIndexChanged.connect(_on_mirror_changed)

    btn_row = QHBoxLayout()

    btn_download = PushButton(FluentIcon.DOWNLOAD, tr("下载"))
    btn_download.setFixedHeight(32)
    btn_enter = PushButton(FluentIcon.PLAY, tr("进入"))
    btn_enter.setFixedHeight(32)
    btn_enter.setDefault(True)
    btn_cancel = PushButton(FluentIcon.CLOSE, tr("退出程序"))
    btn_cancel.setFixedHeight(32)
    btn_row.addWidget(btn_download)
    btn_row.addWidget(btn_enter)
    btn_row.addWidget(btn_cancel)
    lay.addLayout(btn_row)

    warn = QLabel(tr("内置识别依赖未完整安装"))
    warn.setStyleSheet(f"color:{theme['warn']};font-size:13px;")
    lay.addWidget(warn)

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
        missing = [
            required_layer
            for required_layer in required
            if required_layer not in installed_layers["layers"]
        ]
        if not any(
            layer in installed_layers["layers"] for layer in _runtime_layer_names()
        ):
            missing.append("MATHCRAFT_CPU")
        is_lack_critical = bool(missing)
        py_ready = _current_py_ready()
        if not py_ready:
            btn_enter.setText(tr("不可进入(先初始化)"))
            btn_enter.setEnabled(False)
            warn.setVisible(True)
            return
        btn_enter.setEnabled(True)
        btn_enter.setText(tr("跳过安装并进入") if is_lack_critical else tr("进入"))
        warn.setVisible(is_lack_critical)

    update_ui()

    def choose_path():
        nonlocal failed_layer_names, state_file, state_path, pyexe
        import os

        d = _select_existing_directory_with_icon(
            dlg, tr("选择依赖安装/加载目录"), deps_dir
        )
        if d:
            normalized = str(_normalize_deps_base_dir(Path(d)))
            path_edit.setText(normalized)
            normalized_path = Path(normalized)
            active_pyexe = _find_existing_python(normalized_path) or (
                _dependency_venv_python(normalized_path / DEPENDENCY_PYTHON_DIRNAME)
            )
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
            _set_environment_notice(py_ready_local, failed_layer_names)
            effective_default_select = _effective_default_select()
            for layer, cb in checks.items():
                _sync_layer_checkbox(
                    layer, cb, delete_buttons[layer], effective_default_select
                )

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
                if active_pyexe and Path(active_pyexe).exists():
                    os.environ["LATEXSNIPPER_PYEXE"] = str(active_pyexe)
                print(f"[DEBUG] 依赖路径已保存: {normalized}")
            except Exception as e:
                print(f"[ERR] 保存配置失败: {e}")

    btn_path.clicked.connect(choose_path)

    def cleanup_local_data():
        nonlocal failed_layer_names, pyexe, state_path, state_file
        target_lines = "\n".join(f"• {path}" for path in macos_cleanup_targets())
        reply = _exec_close_only_message_box(
            dlg,
            tr("清理本机依赖与缓存"),
            tr(
                "这会移除 LaTeXSnipper 在本机下载的依赖、缓存和日志。\n"
                "应用本身和设置会保留；下次使用内置识别时可能需要重新下载依赖。\n\n"
                "将清理：\n{targets}\n\n是否继续？"
            ).format(targets=target_lines),
            icon=QMessageBox.Icon.Warning,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        result = cleanup_macos_local_data()
        if result.failed:
            first_path, first_error = result.failed[0]
            show_info_bar(
                dlg,
                tr("清理未完成"),
                tr("{count} 个项目清理失败。\n\n示例：{path}\n{error}").format(
                    count=len(result.failed), path=first_path, error=first_error
                ),
                "error",
                6000,
            )
            return

        current_deps_dir = Path(_current_deps_dir()).expanduser().absolute()
        removed_paths = {Path(path).expanduser().absolute() for path in result.removed}
        if current_deps_dir in removed_paths:
            installed_layers["layers"] = []
            failed_layer_names = []
            state_path = current_deps_dir / STATE_FILE
            state_file = str(state_path)
            pyexe = _find_existing_python(current_deps_dir)
            chosen["verified_in_ui"] = False

        try:
            dlg.refresh_ui()
        except Exception:
            update_ui()

        from qfluentwidgets import InfoBar, InfoBarPosition

        if result.removed:
            InfoBar.success(
                title=tr("清理完成"),
                content=tr(
                    "已清理 {count} 个项目；设置已保留，请按需重新下载依赖。"
                ).format(count=len(result.removed)),
                parent=dlg,
                duration=4000,
                position=InfoBarPosition.TOP,
            )
        else:
            InfoBar.info(
                title=tr("无需清理"),
                content=tr("没有发现已下载的本机依赖、缓存或日志。"),
                parent=dlg,
                duration=3000,
                position=InfoBarPosition.TOP,
            )

    if btn_cleanup_macos_local_data is not None:
        btn_cleanup_macos_local_data.clicked.connect(cleanup_local_data)

    def enter():
        """Enter when the environment is complete, or apply the configured skip policy."""
        sel = _normalize_chosen_layers([L for L, c in checks.items() if c.isChecked()])
        mirror_source = _current_mirror_source()
        chosen["layers"] = sel
        chosen["mirror"] = mirror_source == "tuna"
        chosen["mirror_source"] = mirror_source
        chosen["deps_path"] = path_edit.text()
        _save_mirror_source(mirror_source)

        if not _current_py_ready():
            show_info_bar(
                dlg,
                tr("不可进入"),
                tr(
                    "当前依赖目录尚未检测到可复用的 Python 环境。\n"
                    "请先点击“下载”初始化依赖环境后再进入主程序。"
                ),
                "warning",
            )
            return

        if sel:
            print(f"[DEBUG] 已选择依赖: {', '.join(sel)}")
        required = {"BASIC", "CORE"}
        missing = [
            required_layer
            for required_layer in required
            if required_layer not in installed_layers["layers"]
        ]
        if not any(
            layer in installed_layers["layers"] for layer in _runtime_layer_names()
        ):
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
                title=tr("提示"),
                content=tr("请至少选择一个依赖层进行下载。"),
                parent=dlg.parent() if dlg.parent() is not None else dlg,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
            return
        chosen["layers"] = sel
        mirror_source = _current_mirror_source()
        chosen["mirror"] = mirror_source == "tuna"
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
            tr("退出确认"),
            tr("确定要退出安装向导并关闭程序吗？"),
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
                and any(
                    layer in installed_layers["layers"]
                    for layer in _runtime_layer_names()
                )
            ):
                warn.setVisible(False)
                btn_enter.setText(tr("进入"))
            else:
                warn.setVisible(True)
                btn_enter.setText(tr("跳过安装并进入"))

            effective_default_select = _effective_default_select()
            for layer, cb in checks.items():
                _sync_layer_checkbox(
                    layer, cb, delete_buttons[layer], effective_default_select
                )

            current_dir = _current_deps_dir()
            py_ready_local = bool(_find_existing_python(Path(current_dir)))
            _set_environment_notice(py_ready_local, failed_layer_names)
        except Exception as e:
            print(f"[WARN] 刷新依赖管理失败: {e}")

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
                release_lock = (
                    getattr(main_mod, "_release_single_instance_lock", None)
                    if main_mod is not None
                    else None
                )
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
    from ui.window_icons import apply_app_window_icon

    apply_app_window_icon(win, resource_path("assets/icon.ico"))


def _select_existing_directory_with_icon(parent, title: str, initial_dir: str) -> str:
    from PyQt6.QtWidgets import QFileDialog
    from ui.window_icons import schedule_native_dialog_icon

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


def show_info_bar(
    parent,
    title: str,
    content: str,
    level: str = "info",
    duration: int = 4000,
):
    """Show a categorized, non-blocking Fluent notification."""
    from qfluentwidgets import InfoBar, InfoBarPosition

    _sync_deps_fluent_theme()
    notifier = {
        "success": InfoBar.success,
        "warning": InfoBar.warning,
        "error": InfoBar.error,
    }.get(level, InfoBar.info)
    return notifier(
        title=title,
        content=content,
        parent=parent,
        duration=duration,
        position=InfoBarPosition.TOP,
    )


def show_user_notice(title, message, parent=None):
    """Show a non-blocking warning/error when a host window is available."""
    if parent is not None:
        error_titles = {tr("错误"), tr("权限不足"), tr("清理未完成")}
        level = "error" if title in error_titles else "warning"
        show_info_bar(parent, title, message, level, 5000)
        return True

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
