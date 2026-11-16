"""Per-host add-in options besides typography.

Word keeps the numbering options of ``WordPluginSettings``; Word for Mac only
inserts OMML, so it has no insertion backend. PowerPoint chooses between PNG
(the default, which matches the Windows shape-tag contract) and SVG pictures.
Unknown values fall back to the defaults, as the Windows settings readers do.
"""

from __future__ import annotations

from typing import Any

_CHOICES: dict[str, dict[str, tuple[str, ...]]] = {
    "word": {
        "numberPlacement": ("Right", "Left"),
        "numberEnclosure": ("Parentheses", "SquareBrackets", "Braces", "None"),
        "numberSeparator": ("-", ".", "·", ":", "/"),
    },
    "powerpoint": {"insertionBackend": ("Png", "Svg")},
}
_FLAGS: dict[str, tuple[str, ...]] = {
    "word": (
        "includeChapter",
        "includeSection",
        "hideChapterBoundary",
        "hideSectionBoundary",
    ),
    "powerpoint": (),
}


def default_options(host: str) -> dict[str, Any]:
    options: dict[str, Any] = {
        name: values[0] for name, values in _CHOICES[host].items()
    }
    options.update(dict.fromkeys(_FLAGS[host], False))
    return options


def normalize_options(host: str, payload: Any) -> dict[str, Any]:
    """The host's options from ``payload``; missing or unknown values become defaults."""

    source = payload if isinstance(payload, dict) else {}
    options = default_options(host)
    for name, values in _CHOICES[host].items():
        if source.get(name) in values:
            options[name] = source[name]
    for name in _FLAGS[host]:
        if isinstance(source.get(name), bool):
            options[name] = source[name]
    return options


def option_catalog() -> dict[str, dict[str, list[str]]]:
    return {
        host: {name: list(values) for name, values in choices.items()}
        for host, choices in _CHOICES.items()
    }


__all__ = ["default_options", "normalize_options", "option_catalog"]
