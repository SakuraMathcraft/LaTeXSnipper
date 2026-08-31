"""Fluent Automation API access and security settings."""

from __future__ import annotations

from localization.manager import mark_for_translation, translate as tr

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    SimpleCardWidget,
    SpinBox,
    SubtitleLabel,
    ToolButton,
)

from integration.automation import (
    AutomationApiAuth,
    AutomationApiSettings,
    AutomationApiSettingsError,
)
from ui.automation_api_controller import (
    AUTOMATION_API_ACCESS_SCOPE_KEY,
    AUTOMATION_API_ALLOWED_ORIGINS_KEY,
    AUTOMATION_API_BIND_ADDRESS_KEY,
    AUTOMATION_API_PORT_KEY,
    AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY,
    AUTOMATION_API_REMOTE_KEY,
    AUTOMATION_API_REMOTE_SECURITY_KEY,
    AUTOMATION_API_REMOTE_WARNING_ACKNOWLEDGED_KEY,
    AUTOMATION_API_TLS_CERT_PATH_KEY,
    AUTOMATION_API_TLS_KEY_PATH_KEY,
    DEFAULT_AUTOMATION_API_PORT,
)
from ui.settings_dialog_helpers import _select_open_file_with_icon
from ui.window_helpers import apply_no_minimize_window_flags


_AUTOMATION_SETTINGS_ERROR_MESSAGES = frozenset(
    (
        mark_for_translation("Automation API 端口必须在 0 到 65535 之间。"),
        mark_for_translation("Automation API 访问范围必须为仅本机或远程。"),
        mark_for_translation("仅本机模式必须监听本机回环地址。"),
        mark_for_translation("远程模式必须使用安全隧道或 HTTPS。"),
        mark_for_translation("远程模式必须配置访问密钥。"),
        mark_for_translation("远程模式必须填写明确的网卡 IP 地址。"),
        mark_for_translation("远程模式必须监听明确的非回环网卡地址。"),
        mark_for_translation("HTTPS 模式必须提供有效的证书和私钥文件。"),
    )
)


class AutomationAccessDialog(QDialog):
    def __init__(self, window, parent=None) -> None:
        super().__init__(parent)
        self._window = window
        self._cfg = window.cfg
        self.setWindowTitle(tr("自动化接口"))
        self.resize(500, 480)
        self.setMinimumWidth(500)
        apply_no_minimize_window_flags(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        content = QWidget(self.scroll_area)
        content.setObjectName("automationAccessContent")
        content.setStyleSheet(
            "QWidget#automationAccessContent { background: transparent; }"
        )
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(SubtitleLabel(tr("自动化接口")))
        introduction = CaptionLabel(
            tr("配置本机自动化工具，以及经你明确授权的远程设备。")
        )
        introduction.setWordWrap(True)
        content_layout.addWidget(introduction)

        connection_card = SimpleCardWidget(self)
        connection_layout = QVBoxLayout(connection_card)
        connection_layout.setContentsMargins(16, 14, 16, 16)
        connection_layout.setSpacing(12)
        connection_layout.addWidget(BodyLabel(tr("连接设置")))
        self.scope = ComboBox()
        self.scope.addItem(tr("仅本机"), userData="local")
        self.scope.addItem(tr("远程设备"), userData="remote")
        connection_layout.addWidget(self._field(tr("访问范围"), self.scope))

        self.port = SpinBox()
        self.port.setRange(1024, 65535)
        self.bind_address = LineEdit()
        self.bind_address.setPlaceholderText("127.0.0.1")
        endpoint_row = QWidget()
        endpoint_layout = QHBoxLayout(endpoint_row)
        endpoint_layout.setContentsMargins(0, 0, 0, 0)
        endpoint_layout.setSpacing(12)
        endpoint_layout.addWidget(self._field(tr("端口"), self.port), 1)
        endpoint_layout.addWidget(self._field(tr("监听地址"), self.bind_address), 2)
        connection_layout.addWidget(endpoint_row)
        content_layout.addWidget(connection_card)

        self.remote_card = SimpleCardWidget(self)
        remote_layout = QVBoxLayout(self.remote_card)
        remote_layout.setContentsMargins(16, 14, 16, 16)
        remote_layout.setSpacing(12)
        remote_layout.addWidget(BodyLabel(tr("远程访问")))
        remote_note = CaptionLabel(
            tr("仅允许安全隧道或 HTTPS，并始终使用独立访问密钥。")
        )
        remote_note.setWordWrap(True)
        remote_layout.addWidget(remote_note)
        self.security = ComboBox()
        self.security.addItem(tr("安全隧道（推荐）"), userData="tunnel")
        self.security.addItem("HTTPS", userData="https")
        remote_layout.addWidget(self._field(tr("安全方式"), self.security))

        self.remote_key = PasswordLineEdit()
        self.remote_key.setPlaceholderText(tr("生成独立的远程访问密钥"))
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)
        key_layout.addWidget(self.remote_key, 1)
        for icon, tooltip, handler in (
            (FluentIcon.COPY, tr("复制访问密钥"), self._copy_key),
            (FluentIcon.SYNC, tr("重新生成访问密钥"), self._regenerate_key),
            (FluentIcon.DELETE, tr("撤销远程访问密钥"), self._revoke_key),
        ):
            button = ToolButton(icon, key_row)
            button.setToolTip(tooltip)
            button.clicked.connect(handler)
            key_layout.addWidget(button)
        remote_layout.addWidget(self._field(tr("远程访问密钥"), key_row))

        self.cert_path = LineEdit()
        self.cert_path.setPlaceholderText(tr("选择 HTTPS 证书"))
        self.cert_row = self._path_field(
            tr("HTTPS 证书"),
            self.cert_path,
            tr("选择 HTTPS 证书"),
            tr("证书文件 (*.pem *.crt *.cer);;所有文件 (*)"),
        )
        remote_layout.addWidget(self.cert_row)
        self.key_path = LineEdit()
        self.key_path.setPlaceholderText(tr("选择 HTTPS 私钥"))
        self.private_key_row = self._path_field(
            tr("HTTPS 私钥"),
            self.key_path,
            tr("选择 HTTPS 私钥"),
            tr("私钥文件 (*.pem *.key);;所有文件 (*)"),
        )
        remote_layout.addWidget(self.private_key_row)

        self.origins = LineEdit()
        self.origins.setPlaceholderText("https://example.com, https://app.example.com")
        remote_layout.addWidget(
            self._field(
                tr("浏览器 Origin 白名单"),
                self.origins,
                tr("仅浏览器跨域调用需要填写，多个地址使用逗号分隔。"),
            )
        )
        self.remote_external = CheckBox(
            tr("允许远程设备调用已配置的外部模型（可能产生费用）")
        )
        remote_layout.addWidget(self.remote_external)
        self.remote_ack = CheckBox(
            tr("我已了解远程设备可向本机提交图片，并确认连接方式安全")
        )
        remote_layout.addWidget(self.remote_ack)
        content_layout.addWidget(self.remote_card)

        status_card = SimpleCardWidget(self)
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(4)
        status_layout.addWidget(CaptionLabel(tr("当前状态")))
        self.status = BodyLabel()
        self.status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        status_layout.addWidget(self.status)
        content_layout.addWidget(status_card)
        content_layout.addStretch()
        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_button = PushButton(FluentIcon.CANCEL, tr("取消"))
        self.save_button = PrimaryPushButton(FluentIcon.SAVE, tr("保存"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        root.addLayout(button_row)

        self.scope.currentIndexChanged.connect(self._sync_visibility)
        self.security.currentIndexChanged.connect(self._sync_visibility)
        self._load()

    @staticmethod
    def _field(title: str, control: QWidget, hint: str = "") -> QWidget:
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(BodyLabel(title))
        if hint:
            caption = CaptionLabel(hint)
            caption.setWordWrap(True)
            layout.addWidget(caption)
        layout.addWidget(control)
        return field

    def _path_field(
        self, title: str, editor: LineEdit, dialog_title: str, file_filter: str
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(editor, 1)
        browse = PushButton(FluentIcon.FOLDER, tr("选择"))
        browse.clicked.connect(
            lambda: self._select_path(editor, dialog_title, file_filter)
        )
        layout.addWidget(browse)
        return self._field(title, row)

    def _select_path(self, editor: LineEdit, title: str, file_filter: str) -> None:
        path, _selected_filter = _select_open_file_with_icon(
            self,
            title,
            editor.text().strip(),
            file_filter,
        )
        if path:
            editor.setText(path)

    @staticmethod
    def _select_combo(combo: ComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def _load(self) -> None:
        self._select_combo(
            self.scope,
            str(self._cfg.get(AUTOMATION_API_ACCESS_SCOPE_KEY, "local") or "local"),
        )
        self.port.setValue(
            int(self._cfg.get(AUTOMATION_API_PORT_KEY, DEFAULT_AUTOMATION_API_PORT))
        )
        self.bind_address.setText(
            str(self._cfg.get(AUTOMATION_API_BIND_ADDRESS_KEY, "127.0.0.1") or "")
        )
        self._select_combo(
            self.security,
            str(
                self._cfg.get(AUTOMATION_API_REMOTE_SECURITY_KEY, "tunnel") or "tunnel"
            ),
        )
        self.remote_key.setText(str(self._cfg.get(AUTOMATION_API_REMOTE_KEY, "") or ""))
        self.cert_path.setText(
            str(self._cfg.get(AUTOMATION_API_TLS_CERT_PATH_KEY, "") or "")
        )
        self.key_path.setText(
            str(self._cfg.get(AUTOMATION_API_TLS_KEY_PATH_KEY, "") or "")
        )
        values = self._cfg.get(AUTOMATION_API_ALLOWED_ORIGINS_KEY, [])
        self.origins.setText(
            ", ".join(values) if isinstance(values, list) else str(values or "")
        )
        self.remote_external.setChecked(
            bool(self._cfg.get(AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY, False))
        )
        self.remote_ack.setChecked(
            bool(self._cfg.get(AUTOMATION_API_REMOTE_WARNING_ACKNOWLEDGED_KEY, False))
        )
        self.status.setText(self._window.automation_api.automation_api_status_text())
        self._sync_visibility()

    def _sync_visibility(self, *_args) -> None:
        remote = self.scope.currentData() == "remote"
        https = remote and self.security.currentData() == "https"
        self.remote_card.setVisible(remote)
        self.cert_row.setVisible(https)
        self.private_key_row.setVisible(https)
        if not remote:
            self.bind_address.setText("127.0.0.1")
        QTimer.singleShot(0, self._fit_height)

    def _fit_height(self) -> None:
        content = self.scroll_area.widget()
        if content is None:
            return
        desired = content.sizeHint().height() + 92
        screen = self.screen() or QApplication.primaryScreen()
        maximum = int(screen.availableGeometry().height() * 0.88) if screen else 760
        self.resize(self.width(), max(430, min(desired, maximum)))

    def _show_info(self, title: str, content: str, level: str = "info") -> None:
        notifier = {
            "success": InfoBar.success,
            "warning": InfoBar.warning,
            "error": InfoBar.error,
        }.get(level, InfoBar.info)
        notifier(
            title=title,
            content=content,
            parent=self,
            duration=4000,
            position=InfoBarPosition.TOP,
        )

    def _notify_parent(self, title: str, content: str, level: str) -> None:
        notify = getattr(self.parent(), "_show_info", None)
        if callable(notify):
            notify(title, content, level)
        else:
            self._show_info(title, content, level)

    def _copy_key(self) -> None:
        value = self.remote_key.text().strip()
        if not value:
            self._show_info(
                tr("没有可复制的密钥"), tr("请先生成远程访问密钥。"), "warning"
            )
            return
        QApplication.clipboard().setText(value)
        self._show_info(tr("已复制"), tr("远程访问密钥已复制到剪贴板。"), "success")

    def _regenerate_key(self) -> None:
        self.remote_key.setText(AutomationApiAuth.generate_remote_key())
        self._show_info(tr("密钥已更新"), tr("保存配置后新密钥才会生效。"), "info")

    def _revoke_key(self) -> None:
        self.remote_key.clear()
        self._select_combo(self.scope, "local")
        self.bind_address.setText("127.0.0.1")
        self.remote_ack.setChecked(False)
        self._show_info(
            tr("远程访问已撤销"),
            tr("保存后接口将恢复为仅本机访问。"),
            "warning",
        )

    def _save(self) -> None:
        remote = self.scope.currentData() == "remote"
        if remote and not self.remote_ack.isChecked():
            self._show_info(
                tr("需要确认远程访问风险"),
                tr("请确认连接方式安全，并勾选远程访问确认项。"),
                "warning",
            )
            return

        origins = [
            value.strip() for value in self.origins.text().split(",") if value.strip()
        ]
        values: dict[str, object] = {
            AUTOMATION_API_ACCESS_SCOPE_KEY: self.scope.currentData(),
            AUTOMATION_API_PORT_KEY: self.port.value(),
            AUTOMATION_API_BIND_ADDRESS_KEY: self.bind_address.text().strip(),
            AUTOMATION_API_REMOTE_SECURITY_KEY: self.security.currentData(),
            AUTOMATION_API_REMOTE_KEY: self.remote_key.text().strip(),
            AUTOMATION_API_TLS_CERT_PATH_KEY: self.cert_path.text().strip(),
            AUTOMATION_API_TLS_KEY_PATH_KEY: self.key_path.text().strip(),
            AUTOMATION_API_ALLOWED_ORIGINS_KEY: origins,
            AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY: self.remote_external.isChecked(),
            AUTOMATION_API_REMOTE_WARNING_ACKNOWLEDGED_KEY: self.remote_ack.isChecked(),
        }
        try:
            AutomationApiSettings(
                host=str(values[AUTOMATION_API_BIND_ADDRESS_KEY]),
                port=int(values[AUTOMATION_API_PORT_KEY]),
                access_scope=str(values[AUTOMATION_API_ACCESS_SCOPE_KEY]),
                remote_security=str(values[AUTOMATION_API_REMOTE_SECURITY_KEY]),
                remote_key=str(values[AUTOMATION_API_REMOTE_KEY]),
                tls_cert_path=str(values[AUTOMATION_API_TLS_CERT_PATH_KEY]),
                tls_key_path=str(values[AUTOMATION_API_TLS_KEY_PATH_KEY]),
                allowed_origins=tuple(origins),
                remote_external_enabled=bool(
                    values[AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY]
                ),
            ).validate()
        except AutomationApiSettingsError as exc:
            message = str(exc.user_message or "")
            if message in _AUTOMATION_SETTINGS_ERROR_MESSAGES:
                message = tr(message)
            self._show_info(tr("配置无效"), message, "error")
            return
        except Exception:
            self._show_info(
                tr("配置无效"),
                tr("无法验证自动化接口配置，请检查填写内容。"),
                "error",
            )
            return

        self.save_button.setEnabled(False)
        self.save_button.setText(tr("正在保存..."))

        def done(ok: bool, message: str) -> None:
            self.save_button.setEnabled(True)
            self.save_button.setText(tr("保存"))
            self.status.setText(
                self._window.automation_api.automation_api_status_text()
            )
            if not ok:
                self._show_info(tr("自动化接口启动失败"), message, "error")
                return
            self._notify_parent(
                tr("自动化接口"), message or tr("配置已保存"), "success"
            )
            self.accept()

        try:
            self._window.automation_api.update_automation_api_settings_async(
                values, done
            )
        except Exception:
            self.save_button.setEnabled(True)
            self.save_button.setText(tr("保存"))
            self._show_info(tr("保存失败"), tr("无法更新自动化接口配置。"), "error")
