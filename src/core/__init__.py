# -*- coding: utf-8 -*-
"""核心模块 - 配置、常量、工具函数"""

from .config import ConfigManager, CONFIG_FILENAME
from .constants import (
    APP_DIR, MODEL_DIR, DEPS_DIR,
    DEFAULT_HISTORY_NAME, DEFAULT_FAVORITES_NAME,
    DISABLE_GLOBAL_HOTKEY
)
from .utils import resource_path, get_app_dir, apply_theme

__all__ = [
    'ConfigManager', 'CONFIG_FILENAME',
    'APP_DIR', 'MODEL_DIR', 'DEPS_DIR',
    'DEFAULT_HISTORY_NAME', 'DEFAULT_FAVORITES_NAME',
    'DISABLE_GLOBAL_HOTKEY',
    'resource_path', 'get_app_dir', 'apply_theme'
]
