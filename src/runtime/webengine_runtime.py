"""Qt WebEngine runtime configuration and diagnostics."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(f"latexsnipper.{__name__}")


def configure_default_webengine_profile() -> None:
    """Apply MathJax-friendly WebEngine settings after QApplication exists."""
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings

        profile = QWebEngineProfile.defaultProfile()
        assert profile is not None
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)

        settings = profile.settings()
        assert settings is not None
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
    except Exception as e:
        logger.warning("QWebEngine 配置失败: %s", e)


def _log_webengine_diagnostics(app_dir: Path | None = None) -> None:
    """Report runtime paths only after a WebEngine import failure."""

    def _fmt(path: Path | None) -> str:
        try:
            return str(path) if path else "<none>"
        except Exception:
            return "<invalid>"

    logger.warning(
        f"WebEngine frozen={getattr(sys, 'frozen', False)} _MEIPASS={getattr(sys, '_MEIPASS', None)}"
    )
    logger.warning(f"WebEngine executable={sys.executable}")
    logger.warning(f"WebEngine APP_DIR={_fmt(app_dir)}")

    exe_name = "QtWebEngineProcess.exe" if os.name == "nt" else "QtWebEngineProcess"
    candidates = []
    try:
        if hasattr(sys, "_MEIPASS"):
            mp = Path(getattr(sys, "_MEIPASS", ""))
            candidates.extend(
                [
                    mp / "Qt6" / "bin" / exe_name,
                    mp / "PyQt6" / "Qt6" / "bin" / exe_name,
                ]
            )
        exe_dir = Path(sys.executable).parent
        candidates.extend(
            [
                exe_dir / "Qt6" / "bin" / exe_name,
                exe_dir / "PyQt6" / "Qt6" / "bin" / exe_name,
                exe_dir / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin" / exe_name,
            ]
        )
    except Exception:
        candidates = []

    found = next((p for p in candidates if p.exists()), None)
    logger.warning(f"WebEngine QtWebEngineProcess found={_fmt(found)}")
    if not found and candidates:
        logger.warning(
            f"未找到 QtWebEngineProcess，候选路径: {', '.join(_fmt(p) for p in candidates)}"
        )

    resource_dirs = []
    try:
        if hasattr(sys, "_MEIPASS"):
            resource_dirs.append(
                Path(getattr(sys, "_MEIPASS", "")) / "Qt6" / "resources"
            )
            resource_dirs.append(
                Path(getattr(sys, "_MEIPASS", "")) / "PyQt6" / "Qt6" / "resources"
            )
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
        logger.warning(
            f"WebEngine resources_dir={_fmt(rdir)} missing={missing or '<none>'} optional={present_opt or '<none>'}"
        )

    locale_dirs = []
    try:
        if hasattr(sys, "_MEIPASS"):
            locale_dirs.append(
                Path(getattr(sys, "_MEIPASS", ""))
                / "Qt6"
                / "translations"
                / "qtwebengine_locales"
            )
            locale_dirs.append(
                Path(getattr(sys, "_MEIPASS", ""))
                / "PyQt6"
                / "Qt6"
                / "translations"
                / "qtwebengine_locales"
            )
            locale_dirs.append(
                Path(getattr(sys, "_MEIPASS", ""))
                / "Qt6"
                / "resources"
                / "qtwebengine_locales"
            )
            locale_dirs.append(
                Path(getattr(sys, "_MEIPASS", ""))
                / "PyQt6"
                / "Qt6"
                / "resources"
                / "qtwebengine_locales"
            )
        exe_dir = Path(sys.executable).parent
        locale_dirs.append(exe_dir / "Qt6" / "translations" / "qtwebengine_locales")
        locale_dirs.append(
            exe_dir / "PyQt6" / "Qt6" / "translations" / "qtwebengine_locales"
        )
        locale_dirs.append(exe_dir / "Qt6" / "resources" / "qtwebengine_locales")
        locale_dirs.append(
            exe_dir / "PyQt6" / "Qt6" / "resources" / "qtwebengine_locales"
        )
    except Exception:
        locale_dirs = []

    for ldir in locale_dirs:
        if not ldir.exists():
            continue
        try:
            pak_count = len(list(ldir.glob("*.pak")))
        except Exception:
            pak_count = 0
        logger.warning(f"WebEngine locales_dir={_fmt(ldir)} pak_count={pak_count}")


_QWEBENGINE_VIEW = None


def load_webengine_view(app_dir: Path | None = None):
    """Import and return QWebEngineView, or None if the runtime is unavailable."""
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        return QWebEngineView
    except Exception as e:
        logger.warning("WebEngine 未就绪: %s", e, exc_info=True)
        _log_webengine_diagnostics(app_dir)
        return None


def ensure_webengine_loaded(app_dir: Path | None = None) -> bool:
    """Delay-load and cache QWebEngineView for all UI controllers."""
    global _QWEBENGINE_VIEW
    if _QWEBENGINE_VIEW is not None:
        return True
    _QWEBENGINE_VIEW = load_webengine_view(app_dir)
    return _QWEBENGINE_VIEW is not None


def get_webengine_view_class():
    """Return the cached QWebEngineView class, or None if unavailable."""
    return _QWEBENGINE_VIEW
