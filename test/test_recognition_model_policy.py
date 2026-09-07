from __future__ import annotations


def test_document_recognition_model_policy() -> None:
    from recognition.model_policy import resolve_document_recognition_model

    assert resolve_document_recognition_model("mathcraft") == "mathcraft_mixed"
    assert resolve_document_recognition_model("mathcraft_text") == "mathcraft_mixed"
    assert resolve_document_recognition_model("mathcraft_mixed") == "mathcraft_mixed"
    assert resolve_document_recognition_model("external_model") == "external_model"
