# coding: utf-8

FORMULA_DETECTOR_ID = "mathcraft-formula-det"
FORMULA_RECOGNIZER_ID = "mathcraft-formula-rec"
TEXT_DETECTOR_ID = "mathcraft-text-det"
TEXT_RECOGNIZER_ID = "mathcraft-text-rec"

PROFILE_MODEL_IDS = {
    "formula": (FORMULA_DETECTOR_ID, FORMULA_RECOGNIZER_ID),
    "text": (TEXT_DETECTOR_ID, TEXT_RECOGNIZER_ID),
    "mixed": (
        FORMULA_DETECTOR_ID,
        FORMULA_RECOGNIZER_ID,
        TEXT_DETECTOR_ID,
        TEXT_RECOGNIZER_ID,
    ),
}
