# -*- coding: utf-8 -*-
"""工具函数"""

import os
import sys
from pathlib import Path


def resource_path(relative: str) -> str:
    """获取资源文件的绝对路径，兼容 PyInstaller 打包"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base, relative)


def get_app_dir() -> Path:
    """获取应用程序目录"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def apply_theme(mode: str = "AUTO") -> bool:
    """安全设置 QFluentWidgets 主题"""
    try:
        import importlib
        import qfluentwidgets.common.config as cfg
        import qfluentwidgets.common.style_sheet as ss
        theme = getattr(cfg.Theme, mode)
        try:
            ss.setTheme(theme)
            return True
        except RuntimeError:
            cfg = importlib.reload(cfg)
            ss = importlib.reload(ss)
            theme = getattr(cfg.Theme, mode)
            ss.setTheme(theme)
            return True
    except Exception as e:
        print(f"[WARN] 应用主题失败: {e}")
        return False
