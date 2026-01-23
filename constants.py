# -*- coding: utf-8 -*-
"""应用程序常量定义"""

import os
import sys
from pathlib import Path

# 全局配置文件名
CONFIG_FILENAME = "LaTeXSnipper_config.json"

# 默认历史记录和收藏文件名
DEFAULT_HISTORY_NAME = "latexsnipper_history.json"
DEFAULT_FAVORITES_NAME = "latexsnipper_favorites.json"

# 是否禁用全局热键（某些环境下可能有冲突）
DISABLE_GLOBAL_HOTKEY = False


def _get_app_root() -> Path:
    """获取应用程序根目录，兼容 PyInstaller 打包与源码运行"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


# 应用程序目录
APP_DIR = _get_app_root()

# 模型目录（可通过环境变量覆盖）
_model_env = os.environ.get("LATEXSNIPPER_MODEL_DIR")
MODEL_DIR = Path(_model_env) if _model_env else (APP_DIR / "models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# 依赖目录（可通过环境变量覆盖）
_deps_env = os.environ.get("LATEXSNIPPER_DEPS_DIR")
DEPS_DIR = Path(_deps_env) if _deps_env else (APP_DIR / "deps")
DEPS_DIR.mkdir(parents=True, exist_ok=True)
