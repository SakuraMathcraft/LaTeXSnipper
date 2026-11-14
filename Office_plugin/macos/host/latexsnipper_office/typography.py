"""Typography contract shared with the Windows Office plugin.

Field names, validation and the ``settings.json`` schema match
``LaTeXSnipper.OfficePlugin.Abstractions`` and ``TypographySettingsStore`` so
presets exported on one platform import on the other.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latexsnipper_office.options import default_options, normalize_options

TYPOGRAPHY_VERSION = 1
SETTINGS_SCHEMA = 2
MAX_PRESET_BYTES = 64 * 1024
MINIMUM_POINTS = 1.0
MAXIMUM_POINTS = 1638.0
HOSTS = ("word", "powerpoint")

MATH_STYLES = (
    ("Automatic", "自动数学样式", "Automatic"),
    ("Upright", "正体", "Upright"),
    ("Bold", "粗体", "Bold"),
    ("Italic", "斜体", "Italic"),
    ("BoldItalic", "粗斜体", "Bold Italic"),
    ("SansSerif", "无衬线", "Sans Serif"),
    ("SansSerifBold", "无衬线粗体", "Sans Serif Bold"),
    ("SansSerifItalic", "无衬线斜体", "Sans Serif Italic"),
    ("SansSerifBoldItalic", "无衬线粗斜体", "Sans Serif Bold Italic"),
    ("Monospace", "等宽", "Monospace"),
    ("Calligraphic", "花体", "Calligraphic"),
    ("BoldCalligraphic", "粗花体", "Bold Calligraphic"),
    ("Script", "手写体", "Script"),
    ("BoldScript", "粗手写体", "Bold Script"),
    ("Fraktur", "哥特体", "Fraktur"),
    ("BoldFraktur", "哥特粗体", "Bold Fraktur"),
    ("Blackboard", "双线体", "Blackboard Bold"),
)
MATH_STYLE_IDS = tuple(style[0] for style in MATH_STYLES)

NAMED_SIZES = {
    "初号": 42,
    "小初": 36,
    "一号": 26,
    "小一": 24,
    "二号": 22,
    "小二": 18,
    "三号": 16,
    "小三": 15,
    "四号": 14,
    "小四": 12,
    "五号": 10.5,
    "小五": 9,
    "六号": 7.5,
    "小六": 6.5,
    "七号": 5.5,
    "八号": 5,
}
COMMON_POINT_SIZES = (
    5,
    5.5,
    6.5,
    7.5,
    8,
    9,
    10,
    10.5,
    11,
    12,
    13,
    14,
    15,
    16,
    18,
    20,
    22,
    24,
    26,
    28,
    36,
    42,
    48,
    72,
)

# A fixed list, shown in this order and never probed, like the Windows list.
# These are the Chinese families macOS and Office for Mac provide.
CJK_FONTS = (
    ("PingFang SC", "苹方-简"),
    ("Hiragino Sans GB", "冬青黑体简体中文"),
    ("Heiti SC", "黑体-简"),
    ("STHeiti", "华文黑体"),
    ("Songti SC", "宋体-简"),
    ("STSong", "华文宋体"),
    ("Kaiti SC", "楷体-简"),
    ("STKaiti", "华文楷体"),
    ("STFangsong", "华文仿宋"),
    ("Yuanti SC", "圆体-简"),
    ("Lantinghei SC", "兰亭黑-简"),
    ("Libian SC", "隶变-简"),
    ("Xingkai SC", "行楷-简"),
    ("Weibei SC", "魏碑-简"),
    ("Baoli SC", "报隶-简"),
    ("Hannotate SC", "手札体-简"),
    ("Wawati SC", "娃娃体-简"),
    ("Microsoft YaHei", "微软雅黑"),
    ("SimSun", "宋体"),
    ("SimHei", "黑体"),
    ("KaiTi", "楷体"),
    ("FangSong", "仿宋"),
    ("DengXian", "等线"),
)
DEFAULT_CJK_FONT = "PingFang SC"

_SYMBOL_FONT = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_COLOR = re.compile(r"\A#[0-9a-fA-F]{6}\Z")
_UNSAFE_FAMILY = re.compile(r"[<>;:/\\]|url\(|@import", re.IGNORECASE)


class TypographyError(ValueError):
    pass


@dataclass(frozen=True)
class Typography:
    symbol_font_id: str = "mathjax-tex"
    number_font_family: str | None = None
    cjk_font_family: str = DEFAULT_CJK_FONT
    default_math_style: str = "Automatic"
    font_size_points: float = 12.0
    color: str = "#000000"

    def __post_init__(self) -> None:
        if not isinstance(self.symbol_font_id, str) or not _SYMBOL_FONT.match(
            self.symbol_font_id
        ):
            raise TypographyError("数学字体必须使用稳定的字体方案 ID。")
        if self.default_math_style not in MATH_STYLE_IDS:
            raise TypographyError("无效的数学样式。")
        object.__setattr__(self, "cjk_font_family", _family(self.cjk_font_family))
        if self.number_font_family is not None:
            object.__setattr__(
                self, "number_font_family", _family(self.number_font_family)
            )
        object.__setattr__(
            self, "font_size_points", validate_points(self.font_size_points)
        )
        if not isinstance(self.color, str) or not _COLOR.match(self.color):
            raise TypographyError("颜色必须为 #RRGGBB 格式。")
        object.__setattr__(self, "color", self.color.upper())

    def to_fields(self) -> dict[str, Any]:
        return {
            "typographyVersion": TYPOGRAPHY_VERSION,
            "symbolFontId": self.symbol_font_id,
            "numberFontFamily": self.number_font_family or "",
            "cjkFontFamily": self.cjk_font_family,
            "defaultMathStyle": self.default_math_style,
            "fontSizePoints": self.font_size_points,
            "color": self.color,
        }

    @classmethod
    def from_fields(cls, fields: Any) -> Typography:
        if not isinstance(fields, dict):
            raise TypographyError("预设缺少字体样式。")

        def required(name: str) -> Any:
            if fields.get(name) is None:
                raise TypographyError(f"缺少公式样式字段：{name}")
            return fields[name]

        if str(required("typographyVersion")) != str(TYPOGRAPHY_VERSION):
            raise TypographyError("不支持的公式样式版本。")
        number = str(required("numberFontFamily"))
        return cls(
            symbol_font_id=str(required("symbolFontId")),
            number_font_family=number or None,
            cjk_font_family=str(required("cjkFontFamily")),
            default_math_style=str(required("defaultMathStyle")),
            font_size_points=parse_points(required("fontSizePoints")),
            color=str(required("color")),
        )


@dataclass(frozen=True)
class HostDefaults:
    typography: Typography = field(default_factory=lambda: Typography())
    follow_host_font_size: bool = False

    def to_preset(self) -> dict[str, Any]:
        return {
            "schema": SETTINGS_SCHEMA,
            "followHostFontSize": self.follow_host_font_size,
            "typography": self.typography.to_fields(),
        }

    @classmethod
    def from_preset(cls, data: Any) -> HostDefaults:
        if not isinstance(data, dict) or data.get("schema") != SETTINGS_SCHEMA:
            raise TypographyError("不支持的用户配置版本。")
        follow = data.get("followHostFontSize")
        if not isinstance(follow, bool):
            raise TypographyError("无效的预设字号模式。")
        return cls(Typography.from_fields(data.get("typography")), follow)


def validate_points(points: Any) -> float:
    if isinstance(points, bool) or not isinstance(points, (int, float)):
        raise TypographyError("公式字号无效。")
    value = float(points)
    if not MINIMUM_POINTS <= value <= MAXIMUM_POINTS:
        raise TypographyError(
            f"公式字号必须在 {MINIMUM_POINTS:g}–{MAXIMUM_POINTS:g} pt 之间。"
        )
    return value


def parse_points(value: Any) -> float:
    if isinstance(value, str):
        text = value.strip()
        if text in NAMED_SIZES:
            return float(NAMED_SIZES[text])
        if not re.fullmatch(r"\d+(?:\.\d+)?", text):
            raise TypographyError("请输入有效的数字字号或中文字号名称。")
        return validate_points(float(text))
    return validate_points(value)


def _family(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypographyError("字体家族不能为空。")
    family = value.strip()
    if any(ord(character) < 32 for character in family):
        raise TypographyError("字体家族包含控制字符。")
    if len(family) > 128 or _UNSAFE_FAMILY.search(family):
        raise TypographyError("预设包含无效的字体家族描述。")
    return family


def math_style_catalog() -> list[dict[str, str]]:
    return [{"id": style, "zh": zh, "en": en} for style, zh, en in MATH_STYLES]


def cjk_font_catalog() -> list[dict[str, str]]:
    return [{"id": family, "label": label} for family, label in CJK_FONTS]


class SettingsStore:
    """Per-host formula defaults and add-in options in one private JSON file."""

    def __init__(self, path: Path, symbol_fonts: tuple[str, ...]) -> None:
        self.path = path
        self.symbol_fonts = symbol_fonts
        self._lock = threading.Lock()

    def load(self, host: str) -> tuple[HostDefaults, dict[str, Any]]:
        _validate_host(host)
        with self._lock:
            settings = self._read()
        return settings[host]

    def save(self, host: str, defaults: HostDefaults, options: dict[str, Any]) -> None:
        _validate_host(host)
        self._validate(defaults)
        with self._lock:
            settings = self._read()
            settings[host] = (defaults, normalize_options(host, options))
            self._write(settings)

    def import_preset(self, host: str, raw: bytes) -> HostDefaults:
        if len(raw) > MAX_PRESET_BYTES:
            raise TypographyError("预设文件过大。")
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TypographyError("预设不是有效的 JSON。") from error
        defaults = HostDefaults.from_preset(data)
        self._validate(defaults)
        _, options = self.load(host)
        self.save(host, defaults, options)
        return defaults

    def export_preset(self, host: str) -> str:
        defaults, _ = self.load(host)
        return json.dumps(defaults.to_preset(), ensure_ascii=False, indent=2)

    def _validate(self, defaults: HostDefaults) -> None:
        if defaults.typography.symbol_font_id not in self.symbol_fonts:
            raise TypographyError(
                "预设使用未打包的数学符号字体：" + defaults.typography.symbol_font_id
            )

    def _read(self) -> dict[str, tuple[HostDefaults, dict[str, Any]]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != SETTINGS_SCHEMA:
                raise TypographyError("不支持的用户配置版本。")
            result = {}
            for host in HOSTS:
                entry = data.get(host)
                defaults = HostDefaults.from_preset(entry)
                self._validate(defaults)
                result[host] = (defaults, normalize_options(host, entry.get("options")))
            return result
        except FileNotFoundError:
            return self._defaults()
        except (OSError, ValueError, AttributeError):
            # Like the Windows store: unsupported or corrupt user settings are
            # rebuilt from current defaults rather than migrated.
            settings = self._defaults()
            self._write(settings)
            return settings

    def _defaults(self) -> dict[str, tuple[HostDefaults, dict[str, Any]]]:
        return {host: (HostDefaults(), default_options(host)) for host in HOSTS}

    def _write(self, settings: dict[str, tuple[HostDefaults, dict[str, Any]]]) -> None:
        payload: dict[str, Any] = {"schema": SETTINGS_SCHEMA}
        for host, (defaults, options) in settings.items():
            payload[host] = {**defaults.to_preset(), "options": options}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".settings-", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


def _validate_host(host: str) -> None:
    if host not in HOSTS:
        raise TypographyError("未知 Office 宿主。")


__all__ = [
    "COMMON_POINT_SIZES",
    "HOSTS",
    "HostDefaults",
    "MAXIMUM_POINTS",
    "MINIMUM_POINTS",
    "NAMED_SIZES",
    "SettingsStore",
    "Typography",
    "TypographyError",
    "cjk_font_catalog",
    "math_style_catalog",
]
