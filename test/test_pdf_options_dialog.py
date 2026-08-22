from __future__ import annotations

import pytest

from backend.external_model.schemas import ExternalModelConfig
from ui import pdf_options_dialog


def test_mineru_parse_mode_skips_pdf_dpi_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_dialog_is_created(*_args, **_kwargs):
        pytest.fail("MinerU native PDF parsing must not create a DPI dialog")

    monkeypatch.setattr(pdf_options_dialog, "QDialog", fail_if_dialog_is_created)

    result = pdf_options_dialog.prompt_pdf_output_options(
        None,
        "external_model",
        ExternalModelConfig(provider="mineru"),
    )

    assert result == ("markdown", None, "parse")
