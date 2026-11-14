"""Setup window shown when LaTeXSnipper Office.app is opened by the user.

It installs (or repairs) the add-in, reports whether the host and the
desktop recognition service are reachable, and uninstalls. The host itself
runs as a separate LaunchAgent process.
"""

from __future__ import annotations

import json
import ssl
import urllib.request

from latexsnipper_office import install
from latexsnipper_office.certificate import certificate_paths
from latexsnipper_office.paths import automation_connection_file, state_directory
from latexsnipper_office.server import API_HEADER, DEFAULT_PORT

TEXT = {
    "title": "LaTeXSnipper Office",
    "intro": "为 Word 和 PowerPoint for Mac 提供 LaTeXSnipper 公式插件。安装后插件随登录自动运行，无需打开 LaTeXSnipper 桌面端。",
    "install": "安装 / 修复",
    "uninstall": "卸载",
    "close": "关闭",
    "ready": "插件已就绪。重新打开 Word 或 PowerPoint，在“开始 › 加载项”中选择 LaTeXSnipper。",
    "not_installed": "尚未安装。点击“安装”，macOS 会请求信任一张仅用于 localhost 的证书。",
    "installed_not_running": "已安装，但插件服务未响应。点击“安装 / 修复”重新启动。",
    "ocr_ready": "截图识别：已连接 LaTeXSnipper 桌面端。",
    "ocr_missing": "截图识别：需要运行 LaTeXSnipper 桌面端并开启“自动化接口”。其他功能不受影响。",
    "installing": "正在安装…",
    "uninstalled": "已卸载，Office 中的插件和证书信任均已移除。",
    "failed": "操作失败：",
}


def host_reachable(timeout: float = 2.0) -> bool:
    # Python's TLS does not read the macOS keychain; verify against our own certificate.
    identity = certificate_paths(state_directory())
    if not identity.certificate.is_file():
        return False
    context = ssl.create_default_context(cafile=str(identity.certificate))
    request = urllib.request.Request(
        f"https://localhost:{DEFAULT_PORT}/api/health", headers={API_HEADER: "1"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=context
        ) as response:
            return json.loads(response.read()).get("ok") is True
    except (OSError, ValueError):
        return False


def desktop_recognition_available() -> bool:
    try:
        data = json.loads(automation_connection_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(data, dict)
        and bool(data.get("base_url"))
        and bool(data.get("token"))
    )


def status_text() -> str:
    if not install.is_installed():
        host = TEXT["not_installed"]
    elif host_reachable():
        host = TEXT["ready"]
    else:
        host = TEXT["installed_not_running"]
    ocr = TEXT["ocr_ready"] if desktop_recognition_available() else TEXT["ocr_missing"]
    return f"{host}\n\n{ocr}"


def wait_until_reachable(attempts: int = 40) -> bool:
    import time

    for _ in range(attempts):
        if host_reachable(timeout=0.5):
            return True
        time.sleep(0.25)
    return False


def run_setup() -> int:
    import objc
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyRegular,
        NSBackingStoreBuffered,
        NSButton,
        NSFont,
        NSMakeRect,
        NSObject,
        NSTextField,
        NSWindow,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskTitled,
    )
    from PyObjCTools import AppHelper

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    def label(frame, text: str, size: float = 13, bold: bool = False):
        field = NSTextField.alloc().initWithFrame_(frame)
        field.setStringValue_(text)
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        field.setEditable_(False)
        field.setSelectable_(False)
        field.setFont_(
            NSFont.boldSystemFontOfSize_(size)
            if bold
            else NSFont.systemFontOfSize_(size)
        )
        field.cell().setWraps_(True)
        return field

    class Controller(NSObject):
        def refresh(self):
            self.status.setStringValue_(status_text())

        @objc.python_method
        def run(self, action, done_text: str | None = None) -> None:
            self.status.setStringValue_(TEXT["installing"])
            for button in self.buttons:
                button.setEnabled_(False)

            def finish(message: str) -> None:
                for button in self.buttons:
                    button.setEnabled_(True)
                self.status.setStringValue_(message)

            def work() -> None:
                try:
                    action()
                    if done_text is None:
                        wait_until_reachable()
                    message = done_text or status_text()
                except Exception as error:  # surfaced to the user verbatim
                    message = TEXT["failed"] + str(error)
                AppHelper.callAfter(finish, message)

            import threading

            threading.Thread(target=work, daemon=True).start()

        def install_(self, _sender):
            self.run(install.install)

        def uninstall_(self, _sender):
            self.run(install.uninstall, TEXT["uninstalled"])

        def close_(self, _sender):
            app.terminate_(None)

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 480, 300),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
        NSBackingStoreBuffered,
        False,
    )
    window.setTitle_(TEXT["title"])
    window.setReleasedWhenClosed_(False)
    content = window.contentView()
    content.addSubview_(
        label(NSMakeRect(24, 246, 432, 28), TEXT["title"], 18, bold=True)
    )
    content.addSubview_(label(NSMakeRect(24, 196, 432, 44), TEXT["intro"]))
    controller = Controller.alloc().init()
    controller.status = label(NSMakeRect(24, 70, 432, 120), "")
    content.addSubview_(controller.status)
    controller.buttons = []
    for index, (title, action) in enumerate(
        (("install", "install:"), ("uninstall", "uninstall:"), ("close", "close:"))
    ):
        button = NSButton.alloc().initWithFrame_(
            NSMakeRect(24 + index * 148, 20, 136, 32)
        )
        button.setTitle_(TEXT[title])
        button.setBezelStyle_(1)
        button.setTarget_(controller)
        button.setAction_(action)
        content.addSubview_(button)
        controller.buttons.append(button)
    controller.buttons[0].setKeyEquivalent_("\r")
    controller.refresh()
    window.center()
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)

    class Delegate(NSObject):
        def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
            return True

    delegate = Delegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()
    return 0
