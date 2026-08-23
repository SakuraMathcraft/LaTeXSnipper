"""Automation API access-scope and security configuration dialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from integration.automation import AutomationApiAuth, AutomationApiSettings, AutomationApiSettingsError
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


class AutomationAccessDialog(QDialog):
    def __init__(self, window, parent=None) -> None:
        super().__init__(parent)
        self._window = window
        self._cfg = window.cfg
        self.setWindowTitle("Automation API 配置")
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.scope = QComboBox()
        self.scope.addItem("仅本机", "local")
        self.scope.addItem("远程", "remote")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.bind_address = QLineEdit()
        self.security = QComboBox()
        self.security.addItem("安全隧道（推荐）", "tunnel")
        self.security.addItem("HTTPS", "https")
        self.remote_key = QLineEdit()
        self.remote_key.setEchoMode(QLineEdit.EchoMode.Password)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.remote_key, 1)
        for title, handler in (("复制", self._copy_key), ("重新生成", self._regenerate_key), ("撤销", self._revoke_key)):
            button = QPushButton(title)
            button.clicked.connect(handler)
            key_layout.addWidget(button)
        self.cert_path = QLineEdit()
        self.key_path = QLineEdit()
        self.origins = QLineEdit()
        self.origins.setPlaceholderText("https://example.com, https://app.example.com")
        self.remote_external = QCheckBox("允许已授权远程设备调用已配置的外部模型（可能产生费用）")
        self.status = QLabel()
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form.addRow("访问范围", self.scope)
        form.addRow("端口", self.port)
        form.addRow("监听地址", self.bind_address)
        form.addRow("远程安全方式", self.security)
        form.addRow("远程访问密钥", key_row)
        form.addRow("HTTPS 证书", self.cert_path)
        form.addRow("HTTPS 私钥", self.key_path)
        form.addRow("CORS Origin 白名单", self.origins)
        form.addRow("远程外部模型", self.remote_external)
        form.addRow("当前状态", self.status)
        layout.addLayout(form)
        note = QLabel("远程模式必须使用安全隧道或 HTTPS，并始终要求独立的 Bearer 访问密钥。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.scope.currentIndexChanged.connect(self._sync_visibility)
        self.security.currentIndexChanged.connect(self._sync_visibility)
        self._load()

    def _select_combo(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def _load(self) -> None:
        self._select_combo(self.scope, str(self._cfg.get(AUTOMATION_API_ACCESS_SCOPE_KEY, "local") or "local"))
        self.port.setValue(int(self._cfg.get(AUTOMATION_API_PORT_KEY, DEFAULT_AUTOMATION_API_PORT)))
        self.bind_address.setText(str(self._cfg.get(AUTOMATION_API_BIND_ADDRESS_KEY, "127.0.0.1") or ""))
        self._select_combo(self.security, str(self._cfg.get(AUTOMATION_API_REMOTE_SECURITY_KEY, "tunnel") or "tunnel"))
        self.remote_key.setText(str(self._cfg.get(AUTOMATION_API_REMOTE_KEY, "") or ""))
        self.cert_path.setText(str(self._cfg.get(AUTOMATION_API_TLS_CERT_PATH_KEY, "") or ""))
        self.key_path.setText(str(self._cfg.get(AUTOMATION_API_TLS_KEY_PATH_KEY, "") or ""))
        values = self._cfg.get(AUTOMATION_API_ALLOWED_ORIGINS_KEY, [])
        self.origins.setText(", ".join(values) if isinstance(values, list) else str(values or ""))
        self.remote_external.setChecked(bool(self._cfg.get(AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY, False)))
        self.status.setText(self._window.automation_api_status_text())
        self._sync_visibility()

    def _sync_visibility(self) -> None:
        remote = self.scope.currentData() == "remote"
        https = remote and self.security.currentData() == "https"
        self.security.setVisible(remote)
        self.remote_key.setEnabled(remote)
        self.cert_path.setVisible(https)
        self.key_path.setVisible(https)
        self.remote_external.setVisible(remote)
        if not remote:
            self.bind_address.setText("127.0.0.1")

    def _copy_key(self) -> None:
        if self.remote_key.text():
            QApplication.clipboard().setText(self.remote_key.text())

    def _regenerate_key(self) -> None:
        self.remote_key.setText(AutomationApiAuth.generate_remote_key())

    def _revoke_key(self) -> None:
        self.remote_key.clear()
        self._select_combo(self.scope, "local")
        self.bind_address.setText("127.0.0.1")

    def _save(self) -> None:
        remote = self.scope.currentData() == "remote"
        acknowledged = bool(self._cfg.get(AUTOMATION_API_REMOTE_WARNING_ACKNOWLEDGED_KEY, False))
        if remote and not acknowledged:
            answer = QMessageBox.warning(
                self,
                "启用远程访问",
                "远程访问会允许持有访问密钥的设备提交图片。请确认监听地址属于安全隧道，或配置可信 HTTPS 证书。",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Ok:
                return
            acknowledged = True
        origins = [value.strip() for value in self.origins.text().split(",") if value.strip()]
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
            AUTOMATION_API_REMOTE_WARNING_ACKNOWLEDGED_KEY: acknowledged,
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
                remote_external_enabled=bool(values[AUTOMATION_API_REMOTE_EXTERNAL_ENABLED_KEY]),
            ).validate()
        except AutomationApiSettingsError as exc:
            QMessageBox.critical(self, "配置无效", exc.user_message)
            return
        except Exception:
            QMessageBox.critical(self, "配置无效", "无法验证 Automation API 配置，请检查填写内容。")
            return

        def done(ok: bool, message: str) -> None:
            if not ok:
                QMessageBox.critical(self, "Automation API 启动失败", message)
                self.status.setText(self._window.automation_api_status_text())
                return
            self.accept()

        self._window.update_automation_api_settings_async(values, done)
