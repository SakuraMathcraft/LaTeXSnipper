from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import (
        FormulaRecognitionResult,
        MathCraftBlock,
        MathCraftRuntime,
        MixedRecognitionResult,
        OCRRegion,
    )
    from .doctor import DoctorReport, run_doctor
    from .errors import MathCraftError
    from .providers import ProviderInfo, ProviderSpec

__version__ = "0.3.2"

__all__ = [
    "DoctorReport",
    "FormulaRecognitionResult",
    "MathCraftBlock",
    "MathCraftError",
    "MathCraftRuntime",
    "MixedRecognitionResult",
    "OCRRegion",
    "ProviderInfo",
    "ProviderSpec",
    "__version__",
    "run_doctor",
]


def __getattr__(name: str) -> object:
    if name in {
        "FormulaRecognitionResult",
        "MathCraftBlock",
        "MathCraftRuntime",
        "MixedRecognitionResult",
        "OCRRegion",
    }:
        from . import api

        return getattr(api, name)
    if name in {"DoctorReport", "run_doctor"}:
        from . import doctor

        return getattr(doctor, name)
    if name in {"ProviderInfo", "ProviderSpec"}:
        from . import providers

        return getattr(providers, name)
    if name == "MathCraftError":
        from .errors import MathCraftError

        return MathCraftError
    raise AttributeError(name)
