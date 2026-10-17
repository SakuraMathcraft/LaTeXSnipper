"""Host-independent access to the shared, pinned MathJax browser runtime."""

import json
from functools import lru_cache
from pathlib import Path

from runtime.app_paths import resource_path

ASSET_ROOT = Path(resource_path("assets/MathJax"))


@lru_cache(maxsize=1)
def shared_script() -> str:
    return "\n".join(
        (ASSET_ROOT / name).read_text(encoding="utf-8")
        for name in ("config.js", "runtime.js")
    )


@lru_cache(maxsize=1)
def runtime_version() -> str:
    return json.loads((ASSET_ROOT / "resources.json").read_text(encoding="utf-8"))[
        "version"
    ]


def cdn_root() -> str:
    return f"https://cdn.jsdelivr.net/npm/mathjax@{runtime_version()}"


def cdn_loader_script() -> str:
    """Load portable HTML exports and fonts from the pinned CDN release."""
    version = runtime_version()
    return _loader(
        dict(
            root=cdn_root(),
            fontRoot="https://cdn.jsdelivr.net/npm/@mathjax",
            fontVersion="@" + version,
        )
    )


def _loader(settings: dict) -> str:
    payload = json.dumps(settings).replace("<", "\\u003c")
    return (
        "<script>\n"
        + shared_script()
        + "\nLaTeXSnipperMathJax.load("
        + payload
        + ");\n</script>"
    )


def loader_script(
    *,
    output: str = "chtml",
    scale: float = 1,
    options: dict | None = None,
    typeset: bool = True,
    font: str | None = None,
) -> str:
    settings = dict(
        root=ASSET_ROOT.resolve().as_uri() + "/",
        output=output,
        scale=scale,
        options=options or {},
        typeset=typeset,
    )
    if font is not None:
        settings["font"] = font
    return _loader(settings)
