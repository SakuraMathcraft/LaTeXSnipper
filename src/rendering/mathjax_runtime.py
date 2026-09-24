"""Host-independent access to the shared, pinned MathJax browser runtime."""

from functools import lru_cache
import json
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'MathJax'


@lru_cache(maxsize=1)
def runtime_version() -> str:
    return json.loads((ASSET_ROOT / 'resources.json').read_text(encoding='utf-8'))['version']


def cdn_roots() -> tuple[str, str]:
    version = runtime_version()
    return (f'https://cdn.jsdelivr.net/npm/mathjax@{version}',
            f'https://unpkg.com/mathjax@{version}')


@lru_cache(maxsize=1)
def shared_script() -> str:
    return '\n'.join((ASSET_ROOT / name).read_text(encoding='utf-8')
                     for name in ('config.js', 'runtime.js'))


def loader_script(*, output: str = 'chtml', scale: float = 1,
                  options: dict | None = None, typeset: bool = True,
                  root: str | None = None, fallback: bool = True,
                  font: str | None = None) -> str:
    settings = dict(output=output, scale=scale, options=options or {}, typeset=typeset)
    if root is not None:
        settings['root'] = root
    if font is not None:
        settings['font'] = font
    if fallback:
        settings['fallbackRoots'] = cdn_roots()
    payload = json.dumps(settings).replace('<', '\\u003c')
    return ('<script>\n' + shared_script() + '\nLaTeXSnipperMathJax.load('
            + '{root: document.baseURI, ...' + payload + '});\n</script>')
