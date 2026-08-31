"""Application localization services."""

from localization.language import (
    AUTO_LANGUAGE,
    ENGLISH_LANGUAGE,
    SIMPLIFIED_CHINESE_LANGUAGE,
    effective_ui_language,
    normalize_ui_language,
    read_ui_language_from_config,
)
from localization.manager import (
    current_ui_language,
    install_application_translators,
    mark_for_translation,
    translate,
)

__all__ = [
    "AUTO_LANGUAGE",
    "ENGLISH_LANGUAGE",
    "SIMPLIFIED_CHINESE_LANGUAGE",
    "current_ui_language",
    "effective_ui_language",
    "install_application_translators",
    "mark_for_translation",
    "normalize_ui_language",
    "read_ui_language_from_config",
    "translate",
]
