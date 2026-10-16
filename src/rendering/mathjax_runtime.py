"""Host-independent access to the shared, pinned MathJax browser runtime."""

from functools import lru_cache
import json
from runtime.app_paths import resource_path
from pathlib import Path

ASSET_ROOT = Path(resource_path('assets/MathJax'))


@lru_cache(maxsize=1)
def shared_script() -> str:
    return '\n'.join((ASSET_ROOT / name).read_text(encoding='utf-8')
                     for name in ('config.js', 'runtime.js'))


def loader_script(*, output: str = 'chtml', scale: float = 1,
                  options: dict | None = None, typeset: bool = True,
                  font: str | None = None) -> str:
    settings = dict(root=ASSET_ROOT.resolve().as_uri() + '/', output=output, scale=scale,
                    options=options or {}, typeset=typeset)
    if font is not None:
        settings['font'] = font
    payload = json.dumps(settings).replace('<', '\\u003c')
    return ('<script>\n' + shared_script() + '\nLaTeXSnipperMathJax.load('
            + payload + ');\n</script>')
