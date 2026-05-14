import sys

from runtime import linux_graphics_runtime
from runtime.linux_graphics_runtime import apply_linux_graphics_fallbacks


def test_linux_graphics_fallbacks_skip_normal_x11_gpu_session(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(linux_graphics_runtime, "_looks_virtualized", lambda: False)
    monkeypatch.setattr(linux_graphics_runtime, "_has_dri_render_node", lambda: True)
    env = {"DISPLAY": ":0"}

    apply_linux_graphics_fallbacks(env)

    assert "QT_QPA_PLATFORM" not in env
    assert "QT_OPENGL" not in env
    assert "QTWEBENGINE_CHROMIUM_FLAGS" not in env


def test_linux_graphics_fallbacks_prefer_xcb_for_wayland(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(linux_graphics_runtime, "_looks_virtualized", lambda: False)
    monkeypatch.setattr(linux_graphics_runtime, "_has_dri_render_node", lambda: True)
    env = {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}

    apply_linux_graphics_fallbacks(env)

    assert env["QT_QPA_PLATFORM"] == "xcb"
    assert env["QT_OPENGL"] == "software"
    assert env["QSG_RHI_BACKEND"] == "software"
    assert env["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert "--disable-gpu" in env["QTWEBENGINE_CHROMIUM_FLAGS"]
    assert "--disable-vulkan" in env["QTWEBENGINE_CHROMIUM_FLAGS"]


def test_linux_graphics_fallbacks_apply_for_virtual_machine(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(linux_graphics_runtime, "_looks_virtualized", lambda: True)
    monkeypatch.setattr(linux_graphics_runtime, "_has_dri_render_node", lambda: True)
    env = {"DISPLAY": ":0"}

    apply_linux_graphics_fallbacks(env)

    assert env["QT_QPA_PLATFORM"] == "xcb"
    assert env["QT_OPENGL"] == "software"
    assert env["QSG_RHI_BACKEND"] == "software"
    assert env["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert "--disable-gpu" in env["QTWEBENGINE_CHROMIUM_FLAGS"]
    assert "--disable-vulkan" in env["QTWEBENGINE_CHROMIUM_FLAGS"]


def test_linux_graphics_fallbacks_preserve_explicit_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(linux_graphics_runtime, "_looks_virtualized", lambda: True)
    monkeypatch.setattr(linux_graphics_runtime, "_has_dri_render_node", lambda: True)
    env = {"DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland"}

    apply_linux_graphics_fallbacks(env)

    assert env["QT_QPA_PLATFORM"] == "wayland"


def test_linux_graphics_fallbacks_can_be_disabled(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(linux_graphics_runtime, "_looks_virtualized", lambda: True)
    monkeypatch.setattr(linux_graphics_runtime, "_has_dri_render_node", lambda: False)
    env = {"DISPLAY": ":0", "LATEXSNIPPER_DISABLE_LINUX_GRAPHICS_FALLBACKS": "1"}

    apply_linux_graphics_fallbacks(env)

    assert "QT_QPA_PLATFORM" not in env
