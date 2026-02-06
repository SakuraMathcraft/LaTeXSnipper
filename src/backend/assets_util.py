# 文件: `src/backend/assets_util.py`
from importlib import resources
from pathlib import Path

def get_asset_path(name: str) -> Path:
    # 这里的 "assets" 是包名，确保 `src/assets/__init__.py` 存在
    with resources.as_file(resources.files("assets") / name) as p:
        return p

def read_text(name: str, encoding: str = "utf-8") -> str:
    return (get_asset_path(name)).read_text(encoding=encoding)

def read_bytes(name: str) -> bytes:
    return (get_asset_path(name)).read_bytes()
