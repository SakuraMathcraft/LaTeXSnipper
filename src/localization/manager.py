"""Qt translator installation and application-language lifecycle."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator
from PyQt6.QtWidgets import QApplication

from localization.language import (
    effective_ui_language,
    read_ui_language_from_config,
)
from runtime.app_paths import resource_path

_TRANSLATOR_ATTRIBUTE = "_latexsnipper_translators"
_LANGUAGE_ATTRIBUTE = "_latexsnipper_ui_language"


def _remove_installed_translators(app: QApplication) -> None:
    for translator in getattr(app, _TRANSLATOR_ATTRIBUTE, ()):
        try:
            app.removeTranslator(translator)
        except Exception:
            pass
    setattr(app, _TRANSLATOR_ATTRIBUTE, [])


def _load_qt_translator(locale: QLocale, app: QApplication) -> QTranslator | None:
    translator = QTranslator(app)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(locale, "qtbase", "_", translations_path):
        return translator
    return None


def _load_fluent_translator(locale: QLocale, app: QApplication) -> QTranslator | None:
    try:
        from qfluentwidgets import FluentTranslator

        translator = FluentTranslator(locale, app)
        return None if translator.isEmpty() else translator
    except Exception:
        return None


def _load_application_translator(
    locale: QLocale, app: QApplication
) -> QTranslator | None:
    translator = QTranslator(app)
    catalog_dir = Path(resource_path("assets/i18n"))
    if translator.load(locale, "latexsnipper", "_", str(catalog_dir)):
        return translator
    return None


def install_application_translators(
    app: QApplication | None = None,
    configured_language: object | None = None,
) -> str:
    """Install all UI translators and return the effective language."""
    application = app or QApplication.instance()
    if application is None:
        raise RuntimeError("QApplication must exist before installing translations")

    configured = (
        read_ui_language_from_config()
        if configured_language is None
        else configured_language
    )
    language = effective_ui_language(configured)
    if (
        getattr(application, _LANGUAGE_ATTRIBUTE, None) == language
        and getattr(application, _TRANSLATOR_ATTRIBUTE, None) is not None
    ):
        return language

    _remove_installed_translators(application)
    locale = QLocale(language)
    translators = [
        _load_qt_translator(locale, application),
        _load_fluent_translator(locale, application),
        _load_application_translator(locale, application),
    ]
    installed: list[QTranslator] = []
    for translator in translators:
        if translator is None:
            continue
        application.installTranslator(translator)
        installed.append(translator)
    setattr(application, _TRANSLATOR_ATTRIBUTE, installed)
    setattr(application, _LANGUAGE_ATTRIBUTE, language)
    return language


def current_ui_language() -> str:
    app = QApplication.instance()
    if app is not None:
        language = getattr(app, _LANGUAGE_ATTRIBUTE, None)
        if language:
            return str(language)
    return effective_ui_language(read_ui_language_from_config())


def translate(source_text: str, *, context: str = "LaTeXSnipper") -> str:
    return QCoreApplication.translate(context, source_text)


def mark_for_translation(source_text: str) -> str:
    """Mark a deferred source string for catalog extraction without translating it."""
    return source_text
