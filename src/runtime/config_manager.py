"""Application configuration and user data path helpers."""

from __future__ import annotations

import json
from pathlib import Path

from runtime.app_paths import app_config_path, app_state_dir


class ConfigManager:
    def __init__(self):
        self.path = str(app_config_path())
        self.data = {}
        self.load()

    def load(self):
        path = Path(self.path)
        if not path.exists():
            self.data = {}
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.data = data if isinstance(data, dict) else {}
        except Exception:
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        try:
            Path(self.path).write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print("[Config] 保存失败:", exc)


def default_user_data_file(file_name: str) -> Path:
    root = app_state_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return root / file_name


def resolve_user_data_file(cfg: ConfigManager, key: str, default_name: str) -> str:
    value = str(cfg.get(key, "") or "").strip()
    if value:
        return value
    target = default_user_data_file(default_name)
    cfg.set(key, str(target))
    return str(target)


def normalize_content_type(content_type: str | None) -> str:
    """Limit content types to built-in MathCraft modes."""
    value = (content_type or "").strip().lower()
    allowed = {"mathcraft", "mathcraft_text", "mathcraft_mixed"}
    return value if value in allowed else "mathcraft"
