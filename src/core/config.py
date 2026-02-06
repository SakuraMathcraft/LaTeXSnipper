# -*- coding: utf-8 -*-
"""配置管理器"""

import os
import json
from .constants import CONFIG_FILENAME


class ConfigManager:
    """用户配置管理器，保存到用户目录"""
    
    def __init__(self):
        self.path = os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)
        self.data = {}
        self.load()

    def load(self):
        """加载配置文件"""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if not isinstance(self.data, dict):
                    self.data = {}
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def get(self, key, default=None):
        """获取配置项"""
        return self.data.get(key, default)

    def set(self, key, value):
        """设置配置项并保存"""
        self.data[key] = value
        self.save()

    def save(self):
        """保存配置到文件"""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Config] 保存失败: {e}")
