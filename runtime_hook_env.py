# runtime_hook_env.py
import os, sys

def _needs_webengine():
    # 轻量探测：只在已导入或后续很可能需要时设置; 不做重量级导入
    return True  # 若你确定始终会用 WebEngine，可以保持 True

def _set_qtwebengine_env():
    if not getattr(sys, "frozen", False):
        return
    if not _needs_webengine():
        return
    base = getattr(sys, "_MEIPASS", None)
    if base and "QTWEBENGINEPROCESS_PATH" not in os.environ:
        os.environ["QTWEBENGINEPROCESS_PATH"] = base
    # 仅在 Windows 非管理员情况下默认禁用沙箱
    if os.name == "nt" and "QTWEBENGINE_DISABLE_SANDBOX" not in os.environ:
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
        if not is_admin:
            os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

_set_qtwebengine_env()
