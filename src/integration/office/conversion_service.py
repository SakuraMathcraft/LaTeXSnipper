"""LaTeX conversion service for Office insertion targets."""

from __future__ import annotations

import base64
from collections import OrderedDict
from io import BytesIO
from typing import Any, Callable


Converter = Callable[[str], str]
ConversionCacheKey = tuple[str, bool, tuple[str, ...]]


class OfficeConversionService:
    def __init__(
        self,
        *,
        latex_to_omml: Converter | None = None,
        latex_to_mathml: Converter | None = None,
        latex_to_svg: Converter | None = None,
        normalize_latex: Converter | None = None,
        cache_size: int = 128,
    ) -> None:
        self._latex_to_omml = latex_to_omml
        self._latex_to_mathml = latex_to_mathml
        self._latex_to_svg = latex_to_svg
        self._normalize_latex = normalize_latex
        self._cache_size = max(0, cache_size)
        self._cache: OrderedDict[ConversionCacheKey, dict[str, Any]] = OrderedDict()

    def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
        latex = str(payload.get("latex") or "").strip()
        if not latex:
            raise ValueError("latex is required")

        targets = self._normalize_targets(payload.get("targets"))
        normalized = self._normalize(latex)
        display = bool(payload.get("display", True))
        cache_key = (normalized, display, targets)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        result: dict[str, Any] = {
            "latex": normalized,
            "display": display,
            "warnings": [],
        }

        if "omml" in targets:
            result["omml"] = self._omml(normalized)
        if "mathml" in targets:
            result["mathml"] = self._mathml(normalized)
        if "svg" in targets:
            result["svg"] = self._svg(normalized)
        if "png" in targets:
            result["png_base64"] = self._png_base64(normalized)

        self._store_cached(cache_key, result)
        return self._clone_result(result)

    def _get_cached(self, key: ConversionCacheKey) -> dict[str, Any] | None:
        if self._cache_size == 0:
            return None
        result = self._cache.get(key)
        if result is None:
            return None
        self._cache.move_to_end(key)
        return self._clone_result(result)

    def _store_cached(self, key: ConversionCacheKey, result: dict[str, Any]) -> None:
        if self._cache_size == 0:
            return
        self._cache[key] = self._clone_result(result)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _clone_result(self, result: dict[str, Any]) -> dict[str, Any]:
        cloned = dict(result)
        cloned["warnings"] = list(result.get("warnings", []))
        return cloned

    def _normalize_targets(self, raw_targets: Any) -> tuple[str, ...]:
        allowed = {"omml", "mathml", "svg", "png"}
        if not raw_targets:
            return ("omml", "svg")
        if not isinstance(raw_targets, list):
            raise ValueError("targets must be a list")
        targets = []
        for item in raw_targets:
            target = str(item or "").strip().lower()
            if target not in allowed:
                raise ValueError(f"unsupported conversion target: {target}")
            if target not in targets:
                targets.append(target)
        return tuple(targets or ("omml", "svg"))

    def _normalize(self, latex: str) -> str:
        converter = self._normalize_latex
        if converter is None:
            from exporting.formula_format_helpers import normalize_latex_for_export

            converter = normalize_latex_for_export
        return converter(latex)

    def _omml(self, latex: str) -> str:
        converter = self._latex_to_omml
        if converter is None:
            from exporting.formula_converters import latex_to_omml

            converter = latex_to_omml
        return converter(latex)

    def _mathml(self, latex: str) -> str:
        converter = self._latex_to_mathml
        if converter is None:
            from exporting.formula_converters import latex_to_mathml

            converter = latex_to_mathml
        return converter(latex)

    def _svg(self, latex: str) -> str:
        converter = self._latex_to_svg
        if converter is None:
            from exporting.formula_converters import latex_to_svg_code

            converter = latex_to_svg_code
        return converter(latex)

    def _png_base64(self, latex: str) -> str:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 1), dpi=180)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.text(0.5, 0.5, f"${latex}$", ha="center", va="center", fontsize=18, transform=ax.transAxes)
        buffer = BytesIO()
        try:
            plt.savefig(
                buffer,
                format="png",
                bbox_inches="tight",
                pad_inches=0.12,
                transparent=True,
            )
            return base64.b64encode(buffer.getvalue()).decode("ascii")
        finally:
            plt.close(fig)
