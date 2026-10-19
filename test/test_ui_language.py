from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from localization.language import (
    AUTO_LANGUAGE,
    ENGLISH_LANGUAGE,
    SIMPLIFIED_CHINESE_LANGUAGE,
    effective_ui_language,
    normalize_ui_language,
    resolve_supported_ui_language,
)
from localization.manager import install_application_translators, translate

ROOT = Path(__file__).resolve().parents[1]


def test_ui_language_values_are_normalized_to_stable_config_values():
    assert normalize_ui_language(None) == AUTO_LANGUAGE
    assert normalize_ui_language(SIMPLIFIED_CHINESE_LANGUAGE) == (
        SIMPLIFIED_CHINESE_LANGUAGE
    )
    assert normalize_ui_language(ENGLISH_LANGUAGE) == ENGLISH_LANGUAGE
    assert normalize_ui_language("unsupported") == AUTO_LANGUAGE


def test_system_ui_language_preferences_use_first_supported_language():
    assert (
        resolve_supported_ui_language(["ja-JP", "zh-Hans-CN", "en-US"])
        == SIMPLIFIED_CHINESE_LANGUAGE
    )
    assert (
        resolve_supported_ui_language(["de-DE", "en-GB", "zh-CN"]) == ENGLISH_LANGUAGE
    )
    assert resolve_supported_ui_language(["fr-FR"]) == ENGLISH_LANGUAGE


def test_explicit_ui_language_overrides_system_preferences():
    assert (
        effective_ui_language("zh_CN", ui_languages=["en-US"])
        == SIMPLIFIED_CHINESE_LANGUAGE
    )
    assert effective_ui_language("en_US", ui_languages=["zh-CN"]) == ENGLISH_LANGUAGE


def test_compiled_catalog_is_loaded_at_runtime():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert install_application_translators(app, ENGLISH_LANGUAGE) == ENGLISH_LANGUAGE
    assert translate("设置") == "Settings"
    assert translate("截图识别") == "Capture & Recognize"
    assert translate("应用诊断") == "App diagnostics"

    from backend.external_model.errors import ExternalModelConnectionError
    from recognition.error_messages import (
        EMPTY_FORMULA_MESSAGE,
        EMPTY_RESULT_MESSAGE,
        external_model_test_error_user_message,
        recognition_error_code_user_message,
        recognition_failure_user_message,
        translate_image_input_error,
    )

    assert recognition_error_code_user_message("empty_content") == (
        "No recognizable content detected"
    )
    localized_empty_formula = recognition_error_code_user_message("empty_formula")
    assert localized_empty_formula == "No formula content recognized"
    assert (
        recognition_failure_user_message(EMPTY_FORMULA_MESSAGE)
        == localized_empty_formula
    )
    assert recognition_failure_user_message(EMPTY_RESULT_MESSAGE) == (
        "The recognition result is empty"
    )
    assert translate_image_input_error("图片内容为空。") == "The image is empty."
    connection_error = ExternalModelConnectionError(
        "internal diagnostic",
        user_code="connection_unreachable",
        user_context={"target": "127.0.0.1:8185"},
    )
    assert external_model_test_error_user_message(connection_error) == (
        "Cannot connect to 127.0.0.1:8185. Make sure the service is running "
        "and that the address and port are correct."
    )

    install_application_translators(app, SIMPLIFIED_CHINESE_LANGUAGE)
    assert translate("设置") == "设置"


def test_business_payload_contains_compiled_localization_assets(tmp_path):
    import sys
    from argparse import Namespace

    sys.path.insert(0, str(ROOT / "scripts"))
    from build_application_resources import assemble

    output = tmp_path / "application"
    assemble(Namespace(application=output, target="windows-x86_64"))
    catalog = output / "assets/i18n/latexsnipper_en_US.qm"
    assert (
        catalog.read_bytes()
        == (ROOT / "src/assets/i18n/latexsnipper_en_US.qm").read_bytes()
    )
