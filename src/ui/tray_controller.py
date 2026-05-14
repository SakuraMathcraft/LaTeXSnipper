"""Tray menu and capture display selection mixin."""

from __future__ import annotations

from PyQt6.QtGui import QGuiApplication

from backend.platform import TrayMenuHandlers


class TrayControllerMixin:
    def update_tray_tooltip(self):
        hk = self.cfg.get("hotkey", "Ctrl+F")
        mode = self._get_capture_display_mode()
        if mode == "index":
            idx = self._get_capture_display_index()
            disp = f"屏幕{idx + 1}" if idx is not None else "指定屏幕"
        else:
            disp = "自动屏幕"
        if getattr(self, "tray_icon", None):
            self.system_provider.set_tray_tooltip(self.tray_icon, f"LaTeXSnipper - 截图识别快捷键: {hk} | {disp}")

    def _get_capture_display_mode(self) -> str:
        mode = str(self.cfg.get("capture_display_mode", "auto") or "auto").strip().lower()
        return mode if mode in ("auto", "index") else "auto"

    def _get_capture_display_index(self) -> int | None:
        try:
            idx = int(self.cfg.get("capture_display_index", 0))
            return idx if idx >= 0 else 0
        except Exception:
            return 0

    def _set_capture_display_mode(self, mode: str, index: int | None = None):
        m = (mode or "auto").strip().lower()
        if m not in ("auto", "index"):
            m = "auto"
        self.cfg.set("capture_display_mode", m)
        if index is not None:
            try:
                self.cfg.set("capture_display_index", max(0, int(index)))
            except Exception:
                pass
        self.update_tray_tooltip()
        self.update_tray_menu()
        if m == "auto":
            self.set_action_status("截图屏幕模式: 自动")
        else:
            idx = self._get_capture_display_index() or 0
            self.set_action_status(f"截图屏幕模式: 屏幕 {idx + 1}")

    def _build_capture_display_submenu(self, tray_menu):
        submenu = tray_menu.addMenu("截图屏幕模式")
        mode = self._get_capture_display_mode()
        idx = self._get_capture_display_index() or 0

        act_auto = submenu.addAction("自动（按鼠标释放点）")
        act_auto.setCheckable(True)
        act_auto.setChecked(mode == "auto")
        act_auto.triggered.connect(lambda _=False: self._set_capture_display_mode("auto"))

        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            g = screen.geometry()
            title = f"屏幕 {i + 1}: {screen.name()} ({g.width()}x{g.height()} @ {g.x()},{g.y()})"
            act = submenu.addAction(title)
            act.setCheckable(True)
            act.setChecked(mode == "index" and idx == i)
            act.triggered.connect(lambda _=False, screen_idx=i: self._set_capture_display_mode("index", screen_idx))

    def update_tray_menu(self):
        hk = self.cfg.get("hotkey", "Ctrl+F")
        handlers = TrayMenuHandlers(
            on_open=self.show_window,
            on_capture=self.start_capture,
            on_exit=self.truly_exit,
            build_capture_submenu=self._build_capture_display_submenu,
        )
        self.system_provider.update_tray_menu(self.tray_icon, hk, handlers)
