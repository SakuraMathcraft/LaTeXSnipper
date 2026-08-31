"""Stable UI-language configuration and cross-platform locale resolution."""

from __future__ import annotations

import json
from collections.abc import Iterable

from PyQt6.QtCore import QLocale

from runtime.app_paths import app_config_path

AUTO_LANGUAGE = "auto"
SIMPLIFIED_CHINESE_LANGUAGE = "zh_CN"
ENGLISH_LANGUAGE = "en_US"
SUPPORTED_UI_LANGUAGES = (
    AUTO_LANGUAGE,
    SIMPLIFIED_CHINESE_LANGUAGE,
    ENGLISH_LANGUAGE,
)


def normalize_ui_language(value: object) -> str:
    language = str(value or AUTO_LANGUAGE).strip()
    return language if language in SUPPORTED_UI_LANGUAGES else AUTO_LANGUAGE


def resolve_supported_ui_language(ui_languages: Iterable[str]) -> str:
    """Resolve Qt's ordered UI-language preferences to a supported language."""
    for raw_language in ui_languages:
        language = str(raw_language or "").strip().replace("_", "-").lower()
        primary = language.split("-", 1)[0]
        if primary == "zh":
            return SIMPLIFIED_CHINESE_LANGUAGE
        if primary == "en":
            return ENGLISH_LANGUAGE
    return ENGLISH_LANGUAGE


def system_ui_languages() -> list[str]:
    try:
        return list(QLocale.system().uiLanguages())
    except Exception:
        return []


def effective_ui_language(
    configured_language: object = AUTO_LANGUAGE,
    *,
    ui_languages: Iterable[str] | None = None,
) -> str:
    configured = normalize_ui_language(configured_language)
    if configured != AUTO_LANGUAGE:
        return configured
    preferences = system_ui_languages() if ui_languages is None else list(ui_languages)
    return resolve_supported_ui_language(preferences)


def read_ui_language_from_config() -> str:
    try:
        path = app_config_path()
        if not path.exists():
            return AUTO_LANGUAGE
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return AUTO_LANGUAGE
        return normalize_ui_language(data.get("ui_language", AUTO_LANGUAGE))
    except Exception:
        return AUTO_LANGUAGE
