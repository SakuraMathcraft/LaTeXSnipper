# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass


Box4P = tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]


@dataclass(frozen=True)
class FormulaRecognitionResult:
    text: str
    score: float
    provider: str | None


@dataclass(frozen=True)
class OCRRegion:
    box: Box4P
    text: str
    score: float


@dataclass(frozen=True)
class MathCraftBlock:
    kind: str
    box: Box4P
    text: str
    score: float


@dataclass(frozen=True)
class MixedRecognitionResult:
    text: str
    regions: tuple[OCRRegion, ...]
    blocks: tuple[MathCraftBlock, ...]
    provider: str | None
