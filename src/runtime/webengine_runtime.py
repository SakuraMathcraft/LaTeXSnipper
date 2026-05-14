"""Qt WebEngine runtime configuration and diagnostics."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def configure_default_webengine_profile() -> None:
    """Apply MathJax-friendly WebEngine settings after QApplication exists."""
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings

        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)

        settings = profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        print("[MathJax] QWebEngine 配置已应用（支持本地文件+CDN 备选）")
    except Exception as e:
        print(f"[WARN] QWebEngine 配置失败: {e}")


def _webengine_diag_enabled() -> bool:
    return str(os.environ.get("LATEXSNIPPER_WEBENGINE_DIAG", "0")).strip() in ("1", "true", "yes", "on")


def log_webengine_diagnostics(stage: str, err: Exception | None = None, app_dir: Path | None = None) -> None:
    """Output diagnostics for packaged WebEngine failures."""
    if err is None and not _webengine_diag_enabled():
        return
    try:
        logger = logging.getLogger("webengine")
        log_info = logger.info
        log_warn = logger.warning
    except Exception:
        log_info = print
        log_warn = print

    def _fmt(path: Path | None) -> str:
        try:
            return str(path) if path else "<none>"
        except Exception:
            return "<invalid>"

    log_info(f"[WebEngine] 诊断阶段: {stage}")
    if err is not None:
        log_warn(f"[WebEngine] 异常: {err}")

    log_info(f"[WebEngine] frozen={getattr(sys, 'frozen', False)} _MEIPASS={getattr(sys, '_MEIPASS', None)}")
    log_info(f"[WebEngine] executable={sys.executable}")
    log_info(f"[WebEngine] APP_DIR={_fmt(app_dir)}")

    exe_name = "QtWebEngineProcess.exe" if os.name == "nt" else "QtWebEngineProcess"
    candidates = []
    try:
        if hasattr(sys, "_MEIPASS"):
            mp = Path(sys._MEIPASS)
            candidates.extend([
                mp / "Qt6" / "bin" / exe_name,
                mp / "PyQt6" / "Qt6" / "bin" / exe_name,
            ])
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "Qt6" / "bin" / exe_name,
            exe_dir / "PyQt6" / "Qt6" / "bin" / exe_name,
            exe_dir / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin" / exe_name,
        ])
        pyexe_env = os.environ.get("LATEXSNIPPER_PYEXE", "")
        if pyexe_env:
            pyexe_dir = Path(pyexe_env).parent
            candidates.extend([
                pyexe_dir / "Qt6" / "bin" / exe_name,
                pyexe_dir / "PyQt6" / "Qt6" / "bin" / exe_name,
                pyexe_dir / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin" / exe_name,
            ])
    except Exception:
        candidates = []

    found = next((p for p in candidates if p.exists()), None)
    log_info(f"[WebEngine] QtWebEngineProcess found={_fmt(found)}")
    if not found and candidates:
        log_warn(f"[WebEngine] QtWebEngineProcess candidates={', '.join(_fmt(p) for p in candidates)}")

    resource_dirs = []
    try:
        if hasattr(sys, "_MEIPASS"):
            resource_dirs.append(Path(sys._MEIPASS) / "Qt6" / "resources")
            resource_dirs.append(Path(sys._MEIPASS) / "PyQt6" / "Qt6" / "resources")
        exe_dir = Path(sys.executable).parent
        resource_dirs.append(exe_dir / "Qt6" / "resources")
        resource_dirs.append(exe_dir / "PyQt6" / "Qt6" / "resources")
    except Exception:
        resource_dirs = []

    required = [
        "qtwebengine_resources.pak",
        "qtwebengine_resources_100p.pak",
        "qtwebengine_resources_200p.pak",
        "icudtl.dat",
    ]
    optional = ["qtwebengine_devtools_resources.pak"]

    for rdir in resource_dirs:
        if not rdir.exists():
            continue
        missing = [f for f in required if not (rdir / f).exists()]
        present_opt = [f for f in optional if (rdir / f).exists()]
        log_info(f"[WebEngine] resources_dir={_fmt(rdir)} missing={missing or '<none>'} optional={present_opt or '<none>'}")

    locale_dirs = []
    try:
        if hasattr(sys, "_MEIPASS"):
            locale_dirs.append(Path(sys._MEIPASS) / "Qt6" / "translations" / "qtwebengine_locales")
            locale_dirs.append(Path(sys._MEIPASS) / "PyQt6" / "Qt6" / "translations" / "qtwebengine_locales")
            locale_dirs.append(Path(sys._MEIPASS) / "Qt6" / "resources" / "qtwebengine_locales")
            locale_dirs.append(Path(sys._MEIPASS) / "PyQt6" / "Qt6" / "resources" / "qtwebengine_locales")
        exe_dir = Path(sys.executable).parent
        locale_dirs.append(exe_dir / "Qt6" / "translations" / "qtwebengine_locales")
        locale_dirs.append(exe_dir / "PyQt6" / "Qt6" / "translations" / "qtwebengine_locales")
        locale_dirs.append(exe_dir / "Qt6" / "resources" / "qtwebengine_locales")
        locale_dirs.append(exe_dir / "PyQt6" / "Qt6" / "resources" / "qtwebengine_locales")
    except Exception:
        locale_dirs = []

    for ldir in locale_dirs:
        if not ldir.exists():
            continue
        try:
            pak_count = len(list(ldir.glob("*.pak")))
        except Exception:
            pak_count = 0
        log_info(f"[WebEngine] locales_dir={_fmt(ldir)} pak_count={pak_count}")


_QWEBENGINE_VIEW = None


def load_webengine_view(app_dir: Path | None = None):
    """Import and return QWebEngineView, or None if the runtime is unavailable."""
    try:
        log_webengine_diagnostics("before-import", app_dir=app_dir)
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        print("[DEBUG] WebEngine 成功导入")
        log_webengine_diagnostics("import-ok", app_dir=app_dir)
        return QWebEngineView
    except Exception as e:
        print(f"[WARN] WebEngine 未就绪: {e}")
        import traceback

        traceback.print_exc()
        log_webengine_diagnostics("import-failed", e, app_dir=app_dir)
        return None


def ensure_webengine_loaded(app_dir: Path | None = None) -> bool:
    """Delay-load and cache QWebEngineView for all UI controllers."""
    global _QWEBENGINE_VIEW
    if _QWEBENGINE_VIEW is not None:
        print("[DEBUG] WebEngine 已加载")
        return True
    _QWEBENGINE_VIEW = load_webengine_view(app_dir)
    return _QWEBENGINE_VIEW is not None


def get_webengine_view_class():
    """Return the cached QWebEngineView class, or None if unavailable."""
    return _QWEBENGINE_VIEW
