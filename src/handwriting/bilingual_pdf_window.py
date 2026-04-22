from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess
import sys

from PyQt6.QtCore import QEvent, QProcess, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, InfoBar, InfoBarPosition, PushButton, isDarkTheme

from handwriting.pdf_view_fitz import FitzPdfView
from handwriting.pdf_view_poppler import PopplerPdfView, detect_poppler_backend
from utils import resource_path

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None

@dataclass(frozen=True)
class _PagePayload:
    page_no: int
    source_text: str
    translated_text: str
    engine_name: str


class _ArgosModelInstallWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(bool, str)

    def __init__(self, pyexe: str, parent=None):
        super().__init__(parent)
        self._pyexe = str(pyexe or "").strip()

    def run(self) -> None:
        pyexe = self._pyexe
        if not pyexe or (not os.path.exists(pyexe)):
            self.completed.emit(False, "Argos Translate 目标解释器不存在。")
            return
        try:
            self.progress.emit("正在安装 Argos 英译中模型...")
            script = (
                "import json, os\n"
                "download_path = ''\n"
                "try:\n"
                "    import argostranslate.package as p\n"
                "except Exception as exc:\n"
                "    raise RuntimeError(f'Argos Translate Python 包未安装: {exc}')\n"
                "p.update_package_index()\n"
                "packages = list(p.get_available_packages() or [])\n"
                "pkg = next((item for item in packages if getattr(item, 'from_code', '') == 'en' and getattr(item, 'to_code', '') == 'zh'), None)\n"
                "if pkg is None:\n"
                "    raise RuntimeError('未找到官方英译中模型包。')\n"
                "download_path = str(pkg.download() or '')\n"
                "if not download_path:\n"
                "    raise RuntimeError('模型包下载失败。')\n"
                "p.install_from_path(download_path)\n"
                "print(json.dumps({'ok': True, 'message': '英译中模型包安装完成。'}, ensure_ascii=False))\n"
                "if download_path:\n"
                "    try:\n"
                "        os.remove(download_path)\n"
                "    except Exception:\n"
                "        pass\n"
            )
            result = subprocess.run(
                [pyexe, "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1200,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip() or "Argos 模型安装失败。"
                self.completed.emit(False, err)
                return
            message = "英译中模型包安装完成。"
            raw = (result.stdout or "").strip()
            if raw:
                try:
                    payload = json.loads(raw.splitlines()[-1])
                    message = str(payload.get("message", "") or message)
                except Exception:
                    pass
            self.completed.emit(True, message)
        except Exception as exc:
            self.completed.emit(False, str(exc))


class _ArgosStatusProbeWorker(QThread):
    completed = pyqtSignal(str, dict)

    def __init__(self, pyexe: str, parent=None):
        super().__init__(parent)
        self._pyexe = str(pyexe or "").strip()
        self._proc = None

    def stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def run(self) -> None:
        pyexe = self._pyexe
        result: dict[str, object] = {
            "runtime_installed": False,
            "model_ready": False,
            "error": "",
        }
        if not pyexe or (not os.path.exists(pyexe)):
            result["error"] = "python_missing"
            self.completed.emit(pyexe, result)
            return
        script = (
            "import json\n"
            "result = {'runtime_installed': False, 'model_ready': False, 'error': ''}\n"
            "try:\n"
            "    import argostranslate.translate as t\n"
            "    import argostranslate.package as p\n"
            "    result['runtime_installed'] = True\n"
            "    installed = list(t.get_installed_languages() or [])\n"
            "    src = next((lang for lang in installed if getattr(lang, 'code', '') == 'en'), None)\n"
            "    dst = next((lang for lang in installed if getattr(lang, 'code', '') == 'zh'), None)\n"
            "    if src is not None and dst is not None:\n"
            "        try:\n"
            "            src.get_translation(dst)\n"
            "            result['model_ready'] = True\n"
            "        except Exception:\n"
            "            pass\n"
            "except Exception as exc:\n"
            "    result['error'] = str(exc)\n"
            "print(json.dumps(result, ensure_ascii=False))\n"
        )
        try:
            proc = subprocess.Popen(
                [pyexe, "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            self._proc = proc
            try:
                stdout, stderr = proc.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                self.stop()
                stdout, stderr = "", "Argos 状态检测超时。"
            finally:
                self._proc = None
            raw = (stdout or "").strip()
            if proc.returncode == 0 and raw:
                try:
                    payload = json.loads(raw.splitlines()[-1])
                    if isinstance(payload, dict):
                        result.update(payload)
                except Exception:
                    result["error"] = raw
            else:
                result["error"] = (stderr or raw or "").strip()
        except Exception as exc:
            result["error"] = str(exc)
        self.completed.emit(pyexe, result)


_ENGINE_ITEMS = [
    ("source_only", "仅显示原文"),
    ("argos", "Argos Translate"),
    ("azure_translator", "Azure Translator"),
    ("google_cloud", "Google Cloud Translation"),
    ("deepl_api_free", "DeepL API Free"),
]


class BilingualPdfWindow(QDialog):
    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._closing = False
        self._initializing = True
        self._fitz_doc = None
        self._pdf_path = ""
        self._pdf_view = None
        self._pdf_backend_kind = ""
        self._pending_page_sync = False
        self._current_page = 1
        self._page_count = 0
        self._translate_process = None
        self._translate_process_page = None
        self._translate_process_engine = ""
        self._translate_process_silent = False
        self._pending_translate_page = None
        self._translation_cache: dict[tuple[str, int], _PagePayload] = {}
        self._prefetch_queue: list[int] = []
        self._argos_install_worker = None
        self._argos_probe_worker = None
        self._argos_probe_cache: dict[str, dict[str, object]] = {}
        self._theme_is_dark_cached = None
        self.setWindowTitle("双语阅读")
        self.resize(980, 620)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        try:
            icon_path = resource_path("assets/icon.ico")
            if icon_path:
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass
        self._build_ui()
        self._load_saved_preferences()
        self._rebuild_pdf_backend_view(show_feedback=False)
        self._initializing = False

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        self.title_label = QLabel("双语阅读", self)
        self.title_hint_label = QLabel("左侧查看 PDF，右侧按页显示原文与中文对照。", self)
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.title_hint_label)
        title_row.addStretch(1)
        root.addLayout(title_row)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        self.open_pdf_btn = PushButton(FluentIcon.FOLDER, "打开 PDF", self)
        self.translate_current_btn = PushButton(FluentIcon.LANGUAGE, "翻译当前页", self)
        self.page_label = QLabel("未打开 PDF", self)
        self.engine_combo = ComboBox(self)
        self.engine_combo.setFixedWidth(164)
        for key, label in _ENGINE_ITEMS:
            self.engine_combo.addItem(label, userData=key)
        self.config_engine_btn = PushButton(FluentIcon.SETTING, "接口配置", self)
        self.config_engine_btn.setFixedHeight(34)
        self.install_argos_btn = PushButton(FluentIcon.DOWNLOAD, "安装英中模型", self)
        self.install_argos_btn.setFixedHeight(34)
        self.argos_status_label = QLabel("", self)
        self.argos_install_progress = QProgressBar(self)
        self.argos_install_progress.setRange(0, 0)
        self.argos_install_progress.setFixedHeight(6)
        self.argos_install_progress.hide()
        self.pdf_backend_combo = ComboBox(self)
        self.pdf_backend_combo.setFixedWidth(112)
        self.pdf_backend_combo.addItem("自动", userData="auto")
        self.pdf_backend_combo.addItem("Poppler", userData="poppler")
        self.pdf_backend_combo.addItem("Fitz", userData="fitz")
        self.pdf_backend_status_label = QLabel("", self)
        self.pdf_backend_status_label.hide()
        for widget in (self.open_pdf_btn, self.translate_current_btn):
            widget.setFixedHeight(34)
        toolbar.addWidget(self.open_pdf_btn)
        toolbar.addWidget(self.translate_current_btn)
        toolbar.addWidget(self.engine_combo)
        toolbar.addWidget(self.config_engine_btn)
        toolbar.addWidget(self.install_argos_btn)
        toolbar.addWidget(self.argos_status_label)
        toolbar.addWidget(self.pdf_backend_combo)
        toolbar.addWidget(self.page_label)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.argos_progress_row = QHBoxLayout()
        self.argos_progress_row.setContentsMargins(0, 0, 0, 0)
        self.argos_progress_row.setSpacing(8)
        self.argos_progress_text = QLabel("", self)
        self.argos_progress_text.setStyleSheet("font-size: 12px; color: #7a8698;")
        self.argos_progress_row.addWidget(self.argos_install_progress, 1)
        self.argos_progress_row.addWidget(self.argos_progress_text)
        root.addLayout(self.argos_progress_row)

        self.translate_progress_row = QHBoxLayout()
        self.translate_progress_row.setContentsMargins(0, 0, 0, 0)
        self.translate_progress_row.setSpacing(8)
        self.translate_progress = QProgressBar(self)
        self.translate_progress.setRange(0, 0)
        self.translate_progress.setFixedHeight(6)
        self.translate_progress.hide()
        self.translate_progress_text = QLabel("", self)
        self.translate_progress_text.setStyleSheet("font-size: 12px; color: #7a8698;")
        self.translate_progress_row.addWidget(self.translate_progress, 1)
        self.translate_progress_row.addWidget(self.translate_progress_text)
        root.addLayout(self.translate_progress_row)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.preview_host = QWidget(self.main_splitter)
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(0)

        self.text_splitter = QSplitter(Qt.Orientation.Vertical, self.main_splitter)
        self.text_splitter.setChildrenCollapsible(False)
        source_panel = QWidget(self.text_splitter)
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(6)
        self.source_title = QLabel("当前页原文", source_panel)
        self.source_text = QPlainTextEdit(source_panel)
        self.source_text.setReadOnly(True)
        self.source_text.setPlaceholderText("打开 PDF 后，这里显示当前页原文。")
        source_layout.addWidget(self.source_title)
        source_layout.addWidget(self.source_text, 1)
        translated_panel = QWidget(self.text_splitter)
        translated_layout = QVBoxLayout(translated_panel)
        translated_layout.setContentsMargins(0, 0, 0, 0)
        translated_layout.setSpacing(6)
        self.translated_title = QLabel("当前页中文", translated_panel)
        self.translated_text = QPlainTextEdit(translated_panel)
        self.translated_text.setReadOnly(True)
        self.translated_text.setPlaceholderText("当前页译文会显示在这里。")
        translated_layout.addWidget(self.translated_title)
        translated_layout.addWidget(self.translated_text, 1)
        self.text_splitter.setSizes([320, 420])

        self.main_splitter.addWidget(self.preview_host)
        self.main_splitter.addWidget(self.text_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([330, 650])
        root.addWidget(self.main_splitter, 1)

        self.open_pdf_btn.clicked.connect(self.open_pdf_dialog)
        self.translate_current_btn.clicked.connect(self._manual_translate_current_page)
        self.config_engine_btn.clicked.connect(self._open_engine_config_dialog)
        self.install_argos_btn.clicked.connect(self._install_argos_model)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        self.pdf_backend_combo.currentIndexChanged.connect(self._on_pdf_backend_changed)
        self._apply_theme()
        self._refresh_engine_ui_state()

    def _load_saved_preferences(self) -> None:
        if self.cfg is None:
            return
        try:
            engine = str(self.cfg.get("bilingual_reader_engine", "source_only") or "source_only").strip()
            backend = str(self.cfg.get("bilingual_reader_pdf_backend", "auto") or "auto").strip()
            self._set_combo_value(self.engine_combo, engine)
            self._set_combo_value(self.pdf_backend_combo, backend)
        except Exception:
            pass

    def _set_combo_value(self, combo: ComboBox, value: str) -> None:
        target = str(value or "").strip()
        for index in range(combo.count()):
            if str(combo.itemData(index) or "").strip() == target:
                combo.setCurrentIndex(index)
                return

    def _save_preference(self, key: str, value: str) -> None:
        try:
            if self.cfg is not None:
                self.cfg.set(key, value)
        except Exception:
            pass

    def _apply_theme(self) -> None:
        dark = bool(isDarkTheme())
        if self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        muted = "#9aa4b2" if dark else "#6b7280"
        self.title_label.setStyleSheet("font-size: 24px; font-weight: 600;")
        self.title_hint_label.setStyleSheet(f"font-size: 12px; color: {muted};")
        self.page_label.setStyleSheet(f"font-size: 12px; color: {muted};")
        self.pdf_backend_status_label.setStyleSheet(f"font-size: 12px; color: {muted};")
        self.argos_status_label.setStyleSheet(f"font-size: 12px; color: {muted};")
        self.argos_progress_text.setStyleSheet(f"font-size: 12px; color: {muted};")
        self.translate_progress_text.setStyleSheet(f"font-size: 12px; color: {muted};")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        theme_change = getattr(QEvent.Type, "ThemeChange", None)
        refresh_events = {
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        }
        if theme_change is not None:
            refresh_events.add(theme_change)
        if event.type() in refresh_events:
            self._theme_is_dark_cached = None
            self._apply_theme()

    def _current_engine(self) -> str:
        return str(self.engine_combo.currentData() or "source_only").strip()

    def _engine_label(self, engine: str) -> str:
        target = str(engine or "source_only").strip()
        for key, label in _ENGINE_ITEMS:
            if key == target:
                return label
        return target or "未知引擎"

    def _engine_needs_remote_config(self, engine: str) -> bool:
        return str(engine or "").strip() in {"azure_translator", "google_cloud", "deepl_api_free"}

    def _remote_engine_defaults(self, engine: str) -> dict[str, str]:
        target = str(engine or "").strip()
        if target == "azure_translator":
            return {
                "endpoint": "https://api.cognitive.microsofttranslator.com",
                "api_key": "",
                "region": "",
                "timeout_sec": "60",
            }
        if target == "deepl_api_free":
            return {
                "endpoint": "https://api-free.deepl.com",
                "api_key": "",
                "timeout_sec": "60",
            }
        if target == "google_cloud":
            return {
                "endpoint": "https://translation.googleapis.com/language/translate/v2",
                "api_key": "",
                "timeout_sec": "60",
            }
        return {}

    def _remote_engine_config(self, engine: str) -> dict[str, str]:
        defaults = self._remote_engine_defaults(engine)
        if not defaults:
            return {}
        result = dict(defaults)
        if self.cfg is None:
            return result
        for key, default_value in defaults.items():
            try:
                result[key] = str(self.cfg.get(f"bilingual_translate_{engine}_{key}", default_value) or default_value)
            except Exception:
                result[key] = str(default_value)
        return result

    def _save_remote_engine_config(self, engine: str, config: dict[str, str]) -> None:
        if self.cfg is None:
            return
        for key, value in config.items():
            self._save_preference(f"bilingual_translate_{engine}_{key}", str(value or "").strip())

    def _remote_engine_ready(self, engine: str) -> tuple[bool, str]:
        config = self._remote_engine_config(engine)
        if not config:
            return False, "当前翻译引擎不支持配置。"
        if engine == "azure_translator":
            if not config.get("api_key", "").strip():
                return False, "未配置订阅密钥"
            return True, "接口已配置"
        if engine in {"deepl_api_free", "google_cloud"}:
            if not config.get("api_key", "").strip():
                return False, "未配置 API Key"
            return True, "接口已配置"
        return False, "接口未配置"

    def _engine_status_message(self, engine: str) -> str:
        target = str(engine or "source_only").strip()
        if target == "source_only":
            return ""
        if target == "argos":
            return self._argos_status_message()
        ready, message = self._remote_engine_ready(target)
        return f"{self._engine_label(target)}已配置" if ready else f"{self._engine_label(target)}{message}"

    def _open_engine_config_dialog(self) -> None:
        engine = self._current_engine()
        if not self._engine_needs_remote_config(engine):
            InfoBar.info(title="当前引擎无需接口配置", content="该翻译引擎不依赖远程接口配置。", parent=self, position=InfoBarPosition.TOP, duration=2200)
            return
        config = self._remote_engine_config(engine)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{self._engine_label(engine)} 配置")
        dialog.setMinimumWidth(460)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        hint = QLabel("仅对当前双语阅读功能生效。保存后会写入本地配置。", dialog)
        hint.setStyleSheet("font-size: 12px; color: #7a8698;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        site_map = {
            "azure_translator": ("申请入口", "https://portal.azure.com/"),
            "google_cloud": ("申请入口", "https://console.cloud.google.com/apis/library/translate.googleapis.com"),
            "deepl_api_free": ("申请入口", "https://www.deepl.com/pro-api"),
        }
        site_label, site_url = site_map.get(engine, ("", ""))
        if site_url:
            site_link = QLabel(
                f'<a href="{site_url}" style="color:#4f8cff;text-decoration:none;">{site_label}: {site_url}</a>',
                dialog,
            )
            site_link.setOpenExternalLinks(True)
            site_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            site_link.setStyleSheet("font-size: 12px; color: #7a8698;")
            site_link.setWordWrap(True)
            layout.addWidget(site_link)
        fields: dict[str, QLineEdit] = {}

        def add_field(title: str, key: str, placeholder: str, secret: bool = False) -> None:
            layout.addWidget(QLabel(title, dialog))
            edit = QLineEdit(dialog)
            edit.setFixedHeight(32)
            edit.setPlaceholderText(placeholder)
            edit.setText(str(config.get(key, "") or ""))
            if secret:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            layout.addWidget(edit)
            fields[key] = edit

        if engine == "azure_translator":
            add_field("Endpoint", "endpoint", "默认 https://api.cognitive.microsofttranslator.com")
            add_field("订阅密钥", "api_key", "Azure Translator Key", secret=True)
            add_field("区域(可选)", "region", "例如 eastasia")
            add_field("超时(秒)", "timeout_sec", "60")
        elif engine == "deepl_api_free":
            add_field("Endpoint", "endpoint", "默认 https://api-free.deepl.com")
            add_field("API Key", "api_key", "DeepL Key", secret=True)
            add_field("超时(秒)", "timeout_sec", "60")
        elif engine == "google_cloud":
            add_field("Endpoint", "endpoint", "默认 https://translation.googleapis.com/language/translate/v2")
            add_field("API Key", "api_key", "Google Cloud Key", secret=True)
            add_field("超时(秒)", "timeout_sec", "60")

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = PushButton(FluentIcon.CLOSE, "取消", dialog)
        save_btn = PushButton(FluentIcon.SAVE, "保存", dialog)
        cancel_btn.clicked.connect(dialog.reject)

        def save_and_close() -> None:
            payload = {key: widget.text().strip() for key, widget in fields.items()}
            self._save_remote_engine_config(engine, payload)
            self._translation_cache.clear()
            self._prefetch_queue.clear()
            self._refresh_engine_ui_state()
            dialog.accept()
            InfoBar.success(title="配置已保存", content=f"{self._engine_label(engine)} 接口配置已更新。", parent=self, position=InfoBarPosition.TOP, duration=2200)
            if self._pdf_path:
                self._reset_translation_panel_for_page(self._current_page, engine)

        save_btn.clicked.connect(save_and_close)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)
        dialog.setFixedSize(dialog.sizeHint().expandedTo(dialog.minimumSizeHint()))
        dialog.exec()

    def _argos_language_pair_ready(self) -> bool:
        status = self._probe_argos_status()
        return bool(status.get("model_ready"))

    def _argos_status_message(self) -> str:
        status = self._probe_argos_status()
        if status.get("pending"):
            return "正在检测 Argos 环境..."
        if not status.get("runtime_installed"):
            return "Argos 运行库未安装"
        if status.get("model_ready"):
            return "英译中模型已就绪"
        return "未安装英译中模型"

    def _invalidate_argos_probe_cache(self) -> None:
        self._argos_probe_cache.clear()

    def _probe_argos_status(self, force: bool = False) -> dict[str, object]:
        pyexe = self._resolve_translation_python()
        cache_key = str(pyexe or "").strip()
        if (not force) and cache_key in self._argos_probe_cache:
            return dict(self._argos_probe_cache[cache_key])
        result: dict[str, object] = {
            "runtime_installed": False,
            "model_ready": False,
            "error": "",
            "pending": True,
        }
        if not cache_key or (not os.path.exists(cache_key)):
            result["pending"] = False
            result["error"] = "python_missing"
            self._argos_probe_cache[cache_key] = dict(result)
            return result
        self._schedule_argos_probe(cache_key, force=force)
        return result

    def _schedule_argos_probe(self, pyexe: str, force: bool = False) -> None:
        pyexe = str(pyexe or "").strip()
        if not pyexe:
            return
        worker = self._argos_probe_worker
        if worker is not None and worker.isRunning():
            if not force:
                return
            return
        cached = self._argos_probe_cache.get(pyexe)
        if cached and (not force) and (not cached.get("pending", False)):
            return
        self._argos_probe_cache[pyexe] = {
            "runtime_installed": False,
            "model_ready": False,
            "error": "",
            "pending": True,
        }
        worker = _ArgosStatusProbeWorker(pyexe, self)
        self._argos_probe_worker = worker
        worker.completed.connect(self._on_argos_probe_completed)
        worker.finished.connect(self._on_argos_probe_finished)
        worker.start()

    def _on_argos_probe_completed(self, pyexe: str, payload: dict) -> None:
        result = {
            "runtime_installed": bool((payload or {}).get("runtime_installed")),
            "model_ready": bool((payload or {}).get("model_ready")),
            "error": str((payload or {}).get("error", "") or ""),
            "pending": False,
        }
        self._argos_probe_cache[str(pyexe or "").strip()] = result
        self._refresh_engine_ui_state()

    def _on_argos_probe_finished(self) -> None:
        self._argos_probe_worker = None

    def _refresh_engine_ui_state(self) -> None:
        engine = self._current_engine()
        status = self._engine_status_message(engine)
        self.argos_status_label.setText(status)
        installing = self._argos_install_worker is not None and self._argos_install_worker.isRunning()
        argos_status = self._probe_argos_status()
        translating = self._translate_process is not None and self._translate_process.state() != QProcess.ProcessState.NotRunning
        busy_foreground = translating and not self._translate_process_silent
        show_install_button = engine == "argos" and (installing or self._argos_status_message() != "英译中模型已就绪")
        self.install_argos_btn.setVisible(show_install_button)
        self.config_engine_btn.setVisible(self._engine_needs_remote_config(engine))
        self.argos_status_label.setVisible(engine != "source_only")
        can_install = (
            (not argos_status.get("pending"))
            and bool(argos_status.get("runtime_installed"))
            and (not bool(argos_status.get("model_ready")))
            and (not installing)
        )
        self.install_argos_btn.setEnabled(can_install)
        self.argos_install_progress.setVisible(engine == "argos" and installing)
        self.argos_progress_text.setVisible(engine == "argos" and installing)
        if not installing:
            self.argos_progress_text.clear()
        self.translate_current_btn.setEnabled(not busy_foreground)
        self.engine_combo.setEnabled(not busy_foreground)
        self.config_engine_btn.setEnabled(not busy_foreground)
        self.translate_progress.setVisible(busy_foreground)
        self.translate_progress_text.setVisible(busy_foreground)
        if not busy_foreground:
            self.translate_progress_text.clear()

    def _ensure_argos_ready_for_translation(self) -> bool:
        self._refresh_engine_ui_state()
        status = self._probe_argos_status()
        if status.get("pending"):
            self.translated_text.setPlainText("正在检测 Argos 运行环境，请稍候再试。")
            return False
        if bool(status.get("model_ready")):
            return True
        self.translated_text.setPlainText("未安装 Argos 英译中模型，请先点击“安装英中模型”。")
        return False

    def _install_argos_model(self) -> None:
        self._refresh_engine_ui_state()
        status = self._probe_argos_status()
        if status.get("pending"):
            InfoBar.info(title="正在检测", content="正在检测当前依赖环境中的 Argos 状态，请稍后重试。", parent=self, position=InfoBarPosition.TOP, duration=2200)
            return
        if not status.get("runtime_installed"):
            InfoBar.warning(title="运行库未安装", content="当前依赖环境未安装 Argos Translate 运行库。", parent=self, position=InfoBarPosition.TOP, duration=2600)
            return
        if bool(status.get("model_ready")):
            InfoBar.success(title="模型已就绪", content="当前环境已安装 Argos 英译中模型。", parent=self, position=InfoBarPosition.TOP, duration=2200)
            return
        if self._argos_install_worker is not None and self._argos_install_worker.isRunning():
            return
        self.install_argos_btn.setEnabled(False)
        self.argos_status_label.setText("正在安装英译中模型...")
        self.argos_install_progress.show()
        self.argos_progress_text.setText("准备安装...")
        self._invalidate_argos_probe_cache()
        worker = _ArgosModelInstallWorker(self._resolve_translation_python(), self)
        self._argos_install_worker = worker
        worker.progress.connect(self._on_argos_install_progress)
        worker.completed.connect(self._on_argos_install_finished)
        worker.finished.connect(self._on_argos_install_thread_finished)
        worker.start()

    def _on_argos_install_progress(self, message: str) -> None:
        text = str(message or "").strip()
        self.argos_status_label.setText(text)
        self.argos_progress_text.setText(text)

    def _on_argos_install_finished(self, ok: bool, message: str) -> None:
        self._invalidate_argos_probe_cache()
        self._refresh_engine_ui_state()
        if ok:
            self.argos_status_label.setText("英译中模型已就绪")
            self.argos_progress_text.setText("安装完成")
            InfoBar.success(title="安装完成", content=str(message or "Argos 英译中模型已安装。"), parent=self, position=InfoBarPosition.TOP, duration=2600)
            if self._current_engine() == "argos" and self._pdf_path:
                self._translate_current_page()
            return
        self.argos_status_label.setText("未安装英译中模型")
        self.argos_progress_text.setText("安装失败")
        self.translated_text.setPlainText(f"Argos 模型安装失败：{str(message or '').strip()}")
        InfoBar.error(title="安装失败", content=str(message or "Argos 英译中模型安装失败。"), parent=self, position=InfoBarPosition.TOP, duration=3600)

    def _on_argos_install_thread_finished(self) -> None:
        self._argos_install_worker = None
        self._refresh_engine_ui_state()

    def open_pdf_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 PDF", "", "PDF 文件 (*.pdf);;所有文件 (*.*)")
        if path:
            self.set_pdf(path)

    def set_pdf(self, pdf_path: str) -> None:
        if fitz is None:
            InfoBar.error(title="缺少依赖", content="当前环境未安装 PyMuPDF，无法打开 PDF。", parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        path = Path(pdf_path)
        if not path.exists():
            InfoBar.warning(title="文件不存在", content=str(path), parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            InfoBar.error(title="打开失败", content=str(exc), parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        if self._fitz_doc is not None:
            try:
                self._fitz_doc.close()
            except Exception:
                pass
        self._fitz_doc = doc
        self._pdf_path = str(path)
        self._page_count = int(getattr(doc, "page_count", 0) or 0)
        self._current_page = 1
        self._translation_cache.clear()
        self._prefetch_queue.clear()
        self._ensure_pdf_view_loaded()
        if self._pdf_view is not None:
            try:
                self._pdf_view.load_document(self._pdf_path)
            except Exception as exc:
                InfoBar.error(title="预览失败", content=str(exc), parent=self, position=InfoBarPosition.TOP, duration=3200)
                return
        self._apply_single_page_view()
        self._update_page_label()
        self._load_page_texts(1, trigger_translate=True)

    def _desired_pdf_backend(self) -> str:
        return str(self.pdf_backend_combo.currentData() or "auto").strip()

    def _resolve_pdf_backend_kind(self) -> str:
        preferred = self._desired_pdf_backend()
        if preferred == "fitz":
            return "fitz"
        if preferred == "poppler":
            status = detect_poppler_backend()
            return "poppler" if status.ready else "fitz"
        status = detect_poppler_backend()
        return "poppler" if status.ready else "fitz"

    def _describe_active_pdf_backend(self, requested: str, actual: str) -> str:
        if requested == "auto":
            return "PDF 预览: Poppler" if actual == "poppler" else "PDF 预览: Fitz"
        if requested == actual:
            return f"PDF 预览: {actual}"
        return f"PDF 预览: {requested} -> {actual}"

    def _clear_preview_host(self) -> None:
        view = self._pdf_view
        self._pdf_view = None
        if view is None:
            return
        try:
            view.horizontalScrollBar().valueChanged.disconnect(self._schedule_current_page_sync)
        except Exception:
            pass
        try:
            view.verticalScrollBar().valueChanged.disconnect(self._schedule_current_page_sync)
        except Exception:
            pass
        try:
            if self._pdf_backend_kind == "poppler" and hasattr(view, "shutdown_render_worker"):
                view.shutdown_render_worker()
        except Exception:
            pass
        try:
            view.close()
            view.setParent(None)
            view.deleteLater()
        except Exception:
            pass

    def _ensure_pdf_view_loaded(self) -> None:
        kind = self._resolve_pdf_backend_kind()
        requested = self._desired_pdf_backend()
        if kind == self._pdf_backend_kind and self._pdf_view is not None:
            self.pdf_backend_status_label.setText(self._describe_active_pdf_backend(requested, kind))
            return
        self._clear_preview_host()
        self._pdf_backend_kind = kind
        self.pdf_backend_status_label.setText(self._describe_active_pdf_backend(requested, kind))
        try:
            self._pdf_view = PopplerPdfView(self.preview_host) if kind == "poppler" else FitzPdfView(self.preview_host)
        except Exception as exc:
            self._pdf_view = FitzPdfView(self.preview_host) if kind != "fitz" else None
            if self._pdf_view is None:
                InfoBar.error(title="预览初始化失败", content=str(exc), parent=self, position=InfoBarPosition.TOP, duration=3200)
                return
            self._pdf_backend_kind = "fitz"
            self.pdf_backend_status_label.setText(self._describe_active_pdf_backend(requested, "fitz"))
        self.preview_layout.addWidget(self._pdf_view, 1)
        self._apply_single_page_view()
        if kind == "poppler" and hasattr(self._pdf_view, "force_cpu_magnifier"):
            try:
                self._pdf_view.force_cpu_magnifier(show_feedback=False)
            except Exception:
                pass
        try:
            self._pdf_view.horizontalScrollBar().valueChanged.connect(self._schedule_current_page_sync)
            self._pdf_view.verticalScrollBar().valueChanged.connect(self._schedule_current_page_sync)
        except Exception:
            pass

    def _on_pdf_backend_changed(self) -> None:
        self._save_preference("bilingual_reader_pdf_backend", self._desired_pdf_backend())
        if self._initializing:
            self._rebuild_pdf_backend_view(show_feedback=False)
            return
        self._rebuild_pdf_backend_view(show_feedback=True)

    def _rebuild_pdf_backend_view(self, show_feedback: bool = True) -> None:
        current_path = self._pdf_path
        self._ensure_pdf_view_loaded()
        if current_path and self._pdf_view is not None:
            try:
                self._pdf_view.load_document(current_path)
            except Exception:
                pass
        if show_feedback:
            InfoBar.info(title="已切换预览后端", content=self.pdf_backend_status_label.text(), parent=self, position=InfoBarPosition.TOP, duration=1800)

    def _apply_single_page_view(self) -> None:
        if self._pdf_view is None:
            return
        try:
            self._pdf_view.set_page_grid(1, 1)
        except Exception:
            pass
        self._schedule_current_page_sync()

    def _schedule_current_page_sync(self, *_args) -> None:
        if self._pending_page_sync:
            return
        self._pending_page_sync = True
        QTimer.singleShot(80, self._update_current_page_from_view)

    def _update_current_page_from_view(self) -> None:
        self._pending_page_sync = False
        view = self._pdf_view
        if view is None:
            return
        rects = getattr(view, "_page_rects", None) or []
        if not rects:
            return
        try:
            vp = view.viewport()
            center_y = view.verticalScrollBar().value() + vp.height() / 2.0
            best_index = 0
            best_distance = None
            for index, rect in enumerate(rects):
                page_center = float(rect.top() + rect.bottom()) / 2.0
                distance = abs(page_center - center_y)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_index = index
            page_no = max(1, best_index + 1)
        except Exception:
            page_no = self._current_page
        if page_no != self._current_page:
            self._current_page = page_no
            self._load_page_texts(page_no, trigger_translate=True)
        else:
            self._update_page_label()

    def _load_page_texts(self, page_no: int, trigger_translate: bool = False) -> None:
        text = self._extract_page_text(page_no)
        self.source_text.setPlainText(text)
        self._update_page_label()
        if trigger_translate:
            engine = self._current_engine()
            cached = self._get_cached_translation(page_no, engine)
            if cached is not None:
                self._apply_translation_payload(cached)
            else:
                self._reset_translation_panel_for_page(page_no, engine, source_text=text)
            self._translate_current_page()

    def _extract_page_text(self, page_no: int) -> str:
        doc = self._fitz_doc
        if doc is None:
            return ""
        index = max(0, min(int(page_no) - 1, max(0, self._page_count - 1)))
        try:
            page = doc.load_page(index)
            text = str(page.get_text("text") or "")
        except Exception:
            return ""
        lines = [line.rstrip() for line in text.splitlines()]
        compact = [line for line in lines if line.strip()]
        return "\n".join(compact).strip()

    def _on_engine_changed(self) -> None:
        engine = self._current_engine()
        self._save_preference("bilingual_reader_engine", engine)
        self._refresh_engine_ui_state()
        if self._initializing:
            return
        if not self._pdf_path:
            self._reset_translation_panel_for_page(self._current_page, engine, source_text="")
            return
        self._translate_current_page()

    def _translation_cache_key(self, page_no: int, engine: str) -> tuple[str, int]:
        return (str(engine or "source_only").strip(), int(page_no))

    def _get_cached_translation(self, page_no: int, engine: str) -> _PagePayload | None:
        return self._translation_cache.get(self._translation_cache_key(page_no, engine))

    def _store_cached_translation(self, payload: _PagePayload, engine: str) -> None:
        self._translation_cache[self._translation_cache_key(payload.page_no, engine)] = payload

    def _apply_translation_payload(self, payload: _PagePayload) -> None:
        self.source_text.setPlainText(payload.source_text)
        self.translated_text.setPlainText(payload.translated_text)
        self.translated_title.setText(f"当前页中文 ({payload.engine_name})")
        self._update_page_label()

    def _reset_translation_panel_for_page(self, page_no: int, engine: str, source_text: str | None = None) -> None:
        text = str(source_text if source_text is not None else self._extract_page_text(page_no) or "")
        self.source_text.setPlainText(text)
        if not text.strip():
            self.translated_title.setText("当前页中文")
            self.translated_text.clear()
            return
        if str(engine or "source_only").strip() == "source_only":
            self.translated_title.setText("当前页中文 (仅显示原文)")
            self.translated_text.setPlainText("当前页未启用翻译引擎。")
            return
        if self._engine_needs_remote_config(engine):
            ready, message = self._remote_engine_ready(str(engine))
            if not ready:
                self.translated_title.setText(f"当前页中文 ({self._engine_label(engine)})")
                self.translated_text.setPlainText(f"{self._engine_label(engine)} 未就绪：{message}。请先点击“接口配置”。")
                return
        self.translated_title.setText("当前页中文 (等待翻译)")
        self.translated_text.setPlainText("正在准备当前页译文...")

    def _queue_prefetch(self, page_no: int, engine: str) -> None:
        if str(engine) != "argos" or self._page_count <= 1:
            return
        candidates = []
        for offset in (1, 2):
            target = int(page_no) + offset
            if 1 <= target <= int(self._page_count):
                candidates.append(target)
        queued = set(self._prefetch_queue)
        for target in candidates:
            if self._get_cached_translation(target, engine) is not None:
                continue
            if target == int(self._pending_translate_page or 0):
                continue
            if self._translate_process is not None and self._translate_process_page == target and self._translate_process_engine == engine:
                continue
            if target not in queued:
                self._prefetch_queue.append(target)
                queued.add(target)

    def _try_start_prefetch(self) -> None:
        if self._closing:
            return
        if self._translate_process is not None and self._translate_process.state() != QProcess.ProcessState.NotRunning:
            return
        engine = self._current_engine()
        if engine != "argos":
            self._prefetch_queue.clear()
            return
        while self._prefetch_queue:
            page_no = int(self._prefetch_queue.pop(0))
            if self._get_cached_translation(page_no, engine) is not None:
                continue
            text = self._extract_page_text(page_no)
            self._start_translation_process(page_no=page_no, source_text=text, engine=engine, silent=True)
            return

    def _start_translation_process(self, *, page_no: int, source_text: str, engine: str, silent: bool) -> None:
        process = QProcess(self)
        self._translate_process = process
        self._translate_process_page = int(page_no)
        self._translate_process_engine = str(engine or "source_only").strip()
        self._translate_process_silent = bool(silent)
        process.finished.connect(self._on_translate_process_finished)
        process.errorOccurred.connect(self._on_translate_process_error)
        pyexe = self._resolve_translation_python()
        script = (
            "import json,sys\n"
            "import html\n"
            "from urllib import parse, request\n"
            "payload=json.loads(sys.stdin.read() or '{}')\n"
            "page_no=int(payload.get('page_no',1))\n"
            "text=str(payload.get('source_text','') or '').strip()\n"
            "engine=str(payload.get('engine_key','source_only') or 'source_only')\n"
            "cfg=dict(payload.get('engine_config') or {})\n"
            "result={'page_no':page_no,'source_text':text,'translated_text':'','engine_name':''}\n"
            "def read_json(req, timeout):\n"
            "    with request.urlopen(req, timeout=timeout) as resp:\n"
            "        return json.loads(resp.read().decode('utf-8', errors='replace') or '{}')\n"
            "if not text:\n"
            "    result['engine_name']='无文本'\n"
            "elif engine=='source_only':\n"
            "    result['translated_text']='当前页未启用翻译引擎。'\n"
            "    result['engine_name']='仅显示原文'\n"
            "elif engine=='argos':\n"
            "    import argostranslate.translate as t\n"
            "    installed=list(t.get_installed_languages() or [])\n"
            "    src=next((lang for lang in installed if getattr(lang,'code','')=='en'),None)\n"
            "    dst=next((lang for lang in installed if getattr(lang,'code','')=='zh'),None)\n"
            "    result['engine_name']='Argos Translate'\n"
            "    if src is None or dst is None:\n"
            "        result['translated_text']='Argos Translate 已安装，但未检测到英译中模型包。'\n"
            "    else:\n"
            "        translator=src.get_translation(dst)\n"
            "        translated=str(translator.translate(text) or '').strip()\n"
            "        result['translated_text']=translated or '当前页翻译结果为空。'\n"
            "elif engine=='azure_translator':\n"
            "    endpoint=str(cfg.get('endpoint','https://api.cognitive.microsofttranslator.com') or 'https://api.cognitive.microsofttranslator.com').strip().rstrip('/')\n"
            "    api_key=str(cfg.get('api_key','') or '').strip()\n"
            "    region=str(cfg.get('region','') or '').strip()\n"
            "    timeout=max(5,int(str(cfg.get('timeout_sec','60') or '60')))\n"
            "    if not api_key:\n"
            "        raise RuntimeError('Azure Translator 缺少订阅密钥。')\n"
            "    headers={'Content-Type':'application/json','Ocp-Apim-Subscription-Key':api_key}\n"
            "    if region:\n"
            "        headers['Ocp-Apim-Subscription-Region']=region\n"
            "    url=endpoint + '/translate?' + parse.urlencode({'api-version':'3.0','from':'en','to':'zh-Hans'})\n"
            "    req=request.Request(url, data=json.dumps([{'text':text}], ensure_ascii=False).encode('utf-8'), headers=headers, method='POST')\n"
            "    data=read_json(req, timeout)\n"
            "    translated=''\n"
            "    if isinstance(data, list) and data:\n"
            "        translated=str((((data[0] or {}).get('translations') or [{}])[0] or {}).get('text','') or '').strip()\n"
            "    result['engine_name']='Azure Translator'\n"
            "    result['translated_text']=translated or '当前页翻译结果为空。'\n"
            "elif engine=='deepl_api_free':\n"
            "    endpoint=str(cfg.get('endpoint','https://api-free.deepl.com') or 'https://api-free.deepl.com').strip().rstrip('/')\n"
            "    api_key=str(cfg.get('api_key','') or '').strip()\n"
            "    timeout=max(5,int(str(cfg.get('timeout_sec','60') or '60')))\n"
            "    if not api_key:\n"
            "        raise RuntimeError('DeepL API Free 缺少 API Key。')\n"
            "    if not endpoint.endswith('/v2/translate'):\n"
            "        endpoint=endpoint + '/v2/translate'\n"
            "    body=parse.urlencode({'auth_key':api_key,'text':text,'source_lang':'EN','target_lang':'ZH-HANS'}).encode('utf-8')\n"
            "    req=request.Request(endpoint, data=body, headers={'Content-Type':'application/x-www-form-urlencoded'}, method='POST')\n"
            "    data=read_json(req, timeout)\n"
            "    translations=list(data.get('translations') or [])\n"
            "    translated=str((translations[0] or {}).get('text','') or '').strip() if translations else ''\n"
            "    result['engine_name']='DeepL API Free'\n"
            "    result['translated_text']=translated or '当前页翻译结果为空。'\n"
            "elif engine=='google_cloud':\n"
            "    endpoint=str(cfg.get('endpoint','https://translation.googleapis.com/language/translate/v2') or 'https://translation.googleapis.com/language/translate/v2').strip()\n"
            "    api_key=str(cfg.get('api_key','') or '').strip()\n"
            "    timeout=max(5,int(str(cfg.get('timeout_sec','60') or '60')))\n"
            "    if not api_key:\n"
            "        raise RuntimeError('Google Cloud 缺少 API Key。')\n"
            "    url=endpoint + ('&' if '?' in endpoint else '?') + parse.urlencode({'key':api_key})\n"
            "    req=request.Request(url, data=json.dumps({'q':text,'source':'en','target':'zh-CN','format':'text'}, ensure_ascii=False).encode('utf-8'), headers={'Content-Type':'application/json'}, method='POST')\n"
            "    data=read_json(req, timeout)\n"
            "    translations=list((((data or {}).get('data') or {}).get('translations') or []))\n"
            "    translated=str((translations[0] or {}).get('translatedText','') or '').strip() if translations else ''\n"
            "    result['engine_name']='Google Cloud Translation'\n"
            "    result['translated_text']=html.unescape(translated) or '当前页翻译结果为空。'\n"
            "else:\n"
            "    result['translated_text']='当前翻译引擎暂未实现。'\n"
            "    result['engine_name']=engine\n"
            "sys.stdout.write(json.dumps(result, ensure_ascii=False))\n"
        )
        process.start(pyexe, ["-c", script])
        payload = json.dumps(
            {
                "page_no": int(page_no),
                "source_text": source_text,
                "engine_key": engine,
                "engine_config": self._remote_engine_config(engine),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        process.write(payload)
        process.closeWriteChannel()
        self._refresh_engine_ui_state()

    def _manual_translate_current_page(self) -> None:
        self._translate_current_page(force=True, show_feedback=True)

    def _translate_current_page(self, force: bool = False, show_feedback: bool = False) -> None:
        if self._closing:
            return
        if not self._pdf_path:
            InfoBar.info(title="未打开 PDF", content="请先打开 PDF，再执行当前页翻译。", parent=self, position=InfoBarPosition.TOP, duration=2200)
            return
        engine = self._current_engine()
        if engine == "source_only":
            if show_feedback:
                InfoBar.info(title="当前为仅显示原文", content="切换到可用翻译引擎后才能执行中文翻译。", parent=self, position=InfoBarPosition.TOP, duration=2400)
            self._reset_translation_panel_for_page(self._current_page, engine)
            return
        if engine == "argos" and not self._ensure_argos_ready_for_translation():
            return
        if self._engine_needs_remote_config(engine):
            ready, message = self._remote_engine_ready(engine)
            if not ready:
                self._reset_translation_panel_for_page(self._current_page, engine)
                if show_feedback:
                    InfoBar.warning(title="接口未配置", content=f"{self._engine_label(engine)}：{message}。", parent=self, position=InfoBarPosition.TOP, duration=2800)
                return
        if force:
            self._translation_cache.pop(self._translation_cache_key(self._current_page, engine), None)
        cached = self._get_cached_translation(self._current_page, engine)
        if cached is not None:
            self._apply_translation_payload(cached)
            self._queue_prefetch(self._current_page, engine)
            self._try_start_prefetch()
            if show_feedback:
                InfoBar.success(title="已刷新当前页", content="当前页译文已从缓存恢复。", parent=self, position=InfoBarPosition.TOP, duration=1800)
            return
        if self._translate_process is not None and self._translate_process.state() != QProcess.ProcessState.NotRunning:
            self._pending_translate_page = self._current_page
            if show_feedback:
                InfoBar.info(title="翻译进行中", content="当前页翻译任务已加入等待队列。", parent=self, position=InfoBarPosition.TOP, duration=1800)
            return
        source_text = self._extract_page_text(self._current_page)
        if not source_text:
            self.translated_text.clear()
            if show_feedback:
                InfoBar.info(title="当前页无文本", content="该页面没有可翻译的文本层内容。", parent=self, position=InfoBarPosition.TOP, duration=2200)
            return
        self.translated_text.setPlainText("翻译中..." if source_text else "")
        self.translate_progress_text.setText("正在翻译当前页...")
        self._start_translation_process(page_no=self._current_page, source_text=source_text, engine=engine, silent=False)
        if show_feedback:
            InfoBar.success(title="开始翻译", content="已重新翻译当前页。", parent=self, position=InfoBarPosition.TOP, duration=1600)

    def _resolve_translation_python(self) -> str:
        candidate = str(os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
        if candidate and os.path.exists(candidate):
            return candidate
        return sys.executable

    def _teardown_translate_process(self) -> None:
        process = self._translate_process
        self._translate_process = None
        self._translate_process_page = None
        self._translate_process_engine = ""
        self._translate_process_silent = False
        if process is not None:
            try:
                process.deleteLater()
            except Exception:
                pass
        self._refresh_engine_ui_state()
        if self._closing:
            return
        pending = self._pending_translate_page
        self._pending_translate_page = None
        if pending is not None and int(pending) == int(self._current_page):
            self._translate_current_page()
            return
        self._try_start_prefetch()

    def _stop_translate_process(self) -> None:
        process = self._translate_process
        if process is None:
            return
        try:
            process.finished.disconnect(self._on_translate_process_finished)
        except Exception:
            pass
        try:
            process.errorOccurred.disconnect(self._on_translate_process_error)
        except Exception:
            pass
        try:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(1200):
                    process.kill()
                    process.waitForFinished(1200)
        except Exception:
            pass
        self._teardown_translate_process()

    def _on_translate_process_finished(self, _exit_code: int, _exit_status) -> None:
        process = self._translate_process
        page_no = int(self._translate_process_page or self._current_page)
        engine = str(self._translate_process_engine or self.engine_combo.currentData() or "source_only").strip()
        silent = bool(self._translate_process_silent)
        raw = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace") if process is not None else ""
        err = bytes(process.readAllStandardError()).decode("utf-8", errors="replace") if process is not None else ""
        payload = None
        if raw.strip():
            try:
                data = json.loads(raw)
                payload = _PagePayload(
                    page_no=int(data.get("page_no", 1)),
                    source_text=str(data.get("source_text", "") or ""),
                    translated_text=str(data.get("translated_text", "") or ""),
                    engine_name=str(data.get("engine_name", "") or ""),
                )
            except Exception:
                payload = None
        if payload is not None:
            self._store_cached_translation(payload, engine)
        self._teardown_translate_process()
        if payload is not None:
            if not silent:
                self._on_translate_finished(payload)
            self._queue_prefetch(page_no, engine)
            return
        if not silent:
            self._on_translate_failed(err.strip() or "翻译进程返回了无效结果。")

    def _on_translate_process_error(self, _error) -> None:
        process = self._translate_process
        err = bytes(process.readAllStandardError()).decode("utf-8", errors="replace") if process is not None else ""
        self._teardown_translate_process()
        self._on_translate_failed(err.strip() or "翻译进程启动失败。")

    def _on_translate_finished(self, payload: object) -> None:
        if not isinstance(payload, _PagePayload):
            return
        if int(payload.page_no) != int(self._current_page):
            return
        self._apply_translation_payload(payload)

    def _normalize_translate_error(self, error: str) -> str:
        text = str(error or "").strip()
        if not text:
            return "翻译失败：未知错误。"
        low = text.lower()
        if "401" in low or "403" in low or "unauthorized" in low or "forbidden" in low:
            return "翻译失败：鉴权失败，请检查 API Key、订阅密钥、区域或接口权限。"
        if "429" in low or "too many requests" in low or "rate limit" in low or "quota" in low:
            return "翻译失败：接口已触发限流或免费额度不足，请稍后重试或检查额度。"
        if any(code in low for code in ("500", "502", "503", "504", "internal server error", "bad gateway", "service unavailable", "gateway timeout")):
            return "翻译失败：翻译服务暂时异常，请稍后重试。"
        return f"翻译失败：{text}"

    def _on_translate_failed(self, error: str) -> None:
        self.translated_text.setPlainText(self._normalize_translate_error(error))
        self.translate_progress_text.setText("翻译失败")

    def _update_page_label(self) -> None:
        if not self._pdf_path:
            self.page_label.setText("未打开 PDF")
            return
        name = Path(self._pdf_path).name
        self.page_label.setText(f"{name}  第 {self._current_page}/{max(1, self._page_count)} 页")

    def closeEvent(self, event) -> None:
        install_worker = self._argos_install_worker
        if install_worker is not None and install_worker.isRunning():
            event.ignore()
            InfoBar.warning(title="安装进行中", content="Argos 英中模型仍在安装，请等待完成后再关闭窗口。", parent=self, position=InfoBarPosition.TOP, duration=2600)
            return
        probe_worker = self._argos_probe_worker
        if probe_worker is not None and probe_worker.isRunning():
            try:
                probe_worker.finished.disconnect(self._on_argos_probe_finished)
            except Exception:
                pass
            try:
                probe_worker.completed.disconnect(self._on_argos_probe_completed)
            except Exception:
                pass
            probe_worker.setParent(None)
            probe_worker.finished.connect(probe_worker.deleteLater)
            try:
                probe_worker.stop()
                probe_worker.wait(500)
            except Exception:
                pass
            self._argos_probe_worker = None
        self._closing = True
        self._pending_translate_page = None
        self._prefetch_queue.clear()
        self._stop_translate_process()
        if self._fitz_doc is not None:
            try:
                self._fitz_doc.close()
            except Exception:
                pass
            self._fitz_doc = None
        self._clear_preview_host()
        super().closeEvent(event)
