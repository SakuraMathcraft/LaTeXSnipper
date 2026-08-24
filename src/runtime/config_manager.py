"""Application configuration and user data path helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from runtime.app_paths import app_config_path, app_state_dir
from runtime.private_files import ensure_private_directory


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

    def set_many(self, values: dict) -> None:
        self.data.update(values)
        self.save()

    def save(self):
        target = Path(self.path)
        temp_path = None
        try:
            ensure_private_directory(target.parent)
            descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            temp_path = Path(temp_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, target)
        except Exception as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            print(f"[WARN] 配置保存失败: {exc}")


def default_user_data_file(file_name: str) -> Path:
    root = app_state_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return root / file_name
