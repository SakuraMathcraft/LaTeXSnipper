"""Verify dependency-process DLL isolation without loading the OCR runtime."""

import ctypes
import json
import os
import subprocess
import sys

import pytest

from runtime.native_runtime import isolated_python_code


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DLL search state")
def test_child_resets_dll_directory_without_changing_parent(monkeypatch, tmp_path):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    setter = kernel32.SetDllDirectoryW
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_int
    getter = kernel32.GetDllDirectoryW
    getter.argtypes = [ctypes.c_uint, ctypes.c_wchar_p]
    getter.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    getter(len(buffer), buffer)
    original = buffer.value
    bundle = str(tmp_path)
    seed = str(tmp_path / "deps" / "python311")
    cuda = str(tmp_path / "cuda" / "bin")
    monkeypatch.setattr(sys, "_MEIPASS", bundle, raising=False)
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([bundle, str(tmp_path / "PyQt6" / "Qt6" / "bin"), seed, cuda])
    code = isolated_python_code(
        "import json\n"
        "buffer = ctypes.create_unicode_buffer(32768)\n"
        "ctypes.windll.kernel32.GetDllDirectoryW(len(buffer), buffer)\n"
        "print(json.dumps([buffer.value, os.environ['PATH']]))\n"
    )
    try:
        assert setter(bundle)
        result = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True,
        )
        getter(len(buffer), buffer)
        assert buffer.value == bundle
    finally:
        assert setter(original or None)
    assert json.loads(result.stdout) == ["", os.pathsep.join([seed, cuda])]


def test_non_windows_code_is_unchanged(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert isolated_python_code("print('ready')") == "print('ready')"
