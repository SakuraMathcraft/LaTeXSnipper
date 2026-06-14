import subprocess
import sys
from pathlib import Path


_MACOS_PACKAGE_SUFFIXES = (".dmg", ".app.zip", ".zip")


def update_asset_action(path: str | Path, *, platform: str | None = None) -> str:
    value = (platform or sys.platform or "").lower()
    name = str(Path(path).name or "").lower()
    if value == "darwin" and any(name.endswith(suffix) for suffix in _MACOS_PACKAGE_SUFFIXES):
        return "open_macos_package"
    return "keep_downloaded"


def macos_update_guidance(path: str | Path) -> str:
    name = Path(path).name or "LaTeXSnipper 更新包"
    return (
        f"已下载 {name}。请在打开的 Finder 窗口中退出当前 LaTeXSnipper，"
        "然后将新版 LaTeXSnipper.app 拖到 Applications 并替换旧版本。"
    )


def open_downloaded_update_asset(path: str | Path, *, platform: str | None = None) -> bool:
    target = Path(path)
    if update_asset_action(target, platform=platform) != "open_macos_package":
        return False
    try:
        subprocess.Popen(["open", str(target)])
        return True
    except Exception:
        return False
