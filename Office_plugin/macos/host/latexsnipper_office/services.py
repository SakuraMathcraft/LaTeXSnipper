"""Native services the add-in pages call through ``/api``."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from latexsnipper_office.options import normalize_options, option_catalog
from latexsnipper_office.outlines import OutlineError, SystemFontOutlines
from latexsnipper_office.recognition import AutomationRelay, RecognitionRelayError
from latexsnipper_office.server import OfficeApiError
from latexsnipper_office.typography import (
    COMMON_POINT_SIZES,
    MAXIMUM_POINTS,
    MINIMUM_POINTS,
    NAMED_SIZES,
    HostDefaults,
    SettingsStore,
    Typography,
    TypographyError,
    cjk_font_catalog,
    math_style_catalog,
)
from latexsnipper_office.word_variables import WordVariables, WordVariablesError

MAX_PRESET_FILE_BYTES = 64 * 1024


class FileChooser(Protocol):
    def open_json(self, title: str) -> Path | None: ...

    def save_json(self, title: str, suggested_name: str) -> Path | None: ...


def read_symbol_fonts(mathjax: Path) -> tuple[str, ...]:
    """Read the packaged renderer's font catalog, like ``MathJaxAssetResolver``."""

    config = (mathjax / "config.js").read_text(encoding="utf-8")
    start, end = config.find("{"), config.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Invalid MathJax font configuration.")
    fonts = tuple(json.loads(config[start : end + 1])["fonts"])
    if not fonts:
        raise ValueError("MathJax font catalog is empty.")
    return fonts


class OfficeAddinServiceImpl:
    def __init__(
        self,
        *,
        settings: SettingsStore,
        outlines: SystemFontOutlines,
        relay: AutomationRelay,
        word_variables: WordVariables,
        files: FileChooser | None,
        mathjax_version: str,
    ) -> None:
        self.settings = settings
        self.outlines = outlines
        self.relay = relay
        self.word_variables = word_variables
        self.files = files
        self.mathjax_version = mathjax_version

    # Catalog -----------------------------------------------------------------

    def catalog(self) -> dict[str, Any]:
        return {
            "symbolFonts": list(self.settings.symbol_fonts),
            "systemFonts": self.outlines.families(),
            "cjkFonts": cjk_font_catalog(),
            "namedSizes": NAMED_SIZES,
            "commonPointSizes": list(COMMON_POINT_SIZES),
            "minimumPoints": MINIMUM_POINTS,
            "maximumPoints": MAXIMUM_POINTS,
            "mathStyles": math_style_catalog(),
            "options": option_catalog(),
            "mathjaxVersion": self.mathjax_version,
        }

    # Rendering ---------------------------------------------------------------

    def font_outlines(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return {"outlines": self.outlines.shape_runs(runs)}
        except OutlineError as error:
            raise OfficeApiError(422, "font_unavailable", str(error)) from None

    def mathml_to_omml(self, mathml: str, typography: dict[str, Any]) -> str:
        from latexsnipper_office import omml

        style = _typography(typography)
        try:
            return omml.convert(mathml, style)
        except omml.StylesheetUnavailable:
            raise OfficeApiError(
                500,
                "omml_unavailable",
                "未找到 Microsoft Word 的 mathml2omml.xsl，无法生成 Word 原生公式。请确认 Word 已安装在“应用程序”文件夹。",
            ) from None
        except ValueError:
            raise OfficeApiError(
                422, "omml_failed", "MathML 无法转换为 Word 公式。"
            ) from None

    # Settings ----------------------------------------------------------------

    def load_settings(self, host: str) -> dict[str, Any]:
        defaults, options = self.settings.load(host)
        return settings_payload(defaults, options)

    def save_settings(self, host: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            number = str(payload.get("numberFontFamily") or "")
            typography = Typography(
                symbol_font_id=str(payload.get("symbolFontId") or ""),
                number_font_family=number or None,
                cjk_font_family=str(payload.get("cjkFontFamily") or ""),
                default_math_style=str(payload.get("formulaMathStyle") or ""),
                font_size_points=payload.get("formulaFontSizePoints"),
                color=str(payload.get("formulaColor") or ""),
            )
            follow = payload.get("followHostFontSize")
            if not isinstance(follow, bool):
                raise TypographyError("无效的预设字号模式。")
            defaults = HostDefaults(typography, follow)
            self.settings.save(host, defaults, normalize_options(host, payload))
        except TypographyError as error:
            raise OfficeApiError(422, "invalid_settings", str(error)) from None
        return self.load_settings(host)

    def import_settings(self, host: str) -> dict[str, Any]:
        path = self._choose("open", host)
        if path is None:
            return {"canceled": True}
        try:
            if path.stat().st_size > MAX_PRESET_FILE_BYTES:
                raise TypographyError("预设文件过大：" + path.name)
            self.settings.import_preset(host, path.read_bytes())
        except OSError:
            raise OfficeApiError(422, "invalid_preset", "无法读取预设文件。") from None
        except TypographyError as error:
            raise OfficeApiError(422, "invalid_preset", str(error)) from None
        return {
            "kind": "import",
            "name": path.stem,
            "settings": self.load_settings(host),
        }

    def export_settings(self, host: str) -> dict[str, Any]:
        path = self._choose("save", host)
        if path is None:
            return {"canceled": True}
        try:
            path.write_text(self.settings.export_preset(host), encoding="utf-8")
        except OSError:
            raise OfficeApiError(500, "export_failed", "无法写入预设文件。") from None
        return {"kind": "export", "name": path.stem}

    def _choose(self, mode: str, host: str) -> Path | None:
        if self.files is None:
            raise OfficeApiError(503, "dialog_unavailable", "当前无法打开文件对话框。")
        label = "Word" if host == "word" else "PowerPoint"
        if mode == "open":
            return self.files.open_json(f"导入 {label} 公式预设")
        return self.files.save_json(
            f"导出 {label} 公式预设", f"LaTeXSnipper {label} 公式.json"
        )

    # Word document variables -------------------------------------------------

    def write_word_variables(self, marker: Any, values: Any) -> dict[str, Any]:
        try:
            return self.word_variables.write(marker, values)
        except WordVariablesError as error:
            raise OfficeApiError(error.status, error.code, error.message) from None

    # Recognition -------------------------------------------------------------

    def recognition_config(self) -> dict[str, Any]:
        return self._relay(self.relay.config)

    def create_next_result_job(self, timeout: int) -> dict[str, Any]:
        return self._relay(lambda: self.relay.next_result(timeout))

    def recognition_job(self, job_id: str) -> dict[str, Any]:
        return self._relay(lambda: self.relay.job(job_id))

    def cancel_recognition_job(self, job_id: str) -> dict[str, Any]:
        return self._relay(lambda: self.relay.cancel(job_id))

    @staticmethod
    def _relay(action) -> dict[str, Any]:
        try:
            return action()
        except RecognitionRelayError as error:
            raise OfficeApiError(error.status, error.code, error.message) from None


def settings_payload(defaults: HostDefaults, options: dict[str, Any]) -> dict[str, Any]:
    typography = defaults.typography
    return {
        **options,
        "followHostFontSize": defaults.follow_host_font_size,
        "formulaColor": typography.color,
        "formulaMathStyle": typography.default_math_style,
        "formulaFontSizePoints": typography.font_size_points,
        "symbolFontId": typography.symbol_font_id,
        "numberFontFamily": typography.number_font_family or "",
        "cjkFontFamily": typography.cjk_font_family,
        "typography": typography.to_fields(),
    }


def _typography(fields: Any) -> Typography:
    try:
        return Typography.from_fields(fields)
    except TypographyError as error:
        raise OfficeApiError(422, "invalid_typography", str(error)) from None


def mathjax_version(mathjax: Path) -> str:
    data = json.loads((mathjax / "resources.json").read_text(encoding="utf-8"))
    version = str(data["version"])
    if not re.fullmatch(r"[0-9A-Za-z.+-]{1,32}", version):
        raise ValueError("Invalid MathJax version.")
    return version
