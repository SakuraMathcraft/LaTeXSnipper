import re

_GITHUB_RAW_PREFIX = "https://raw.githubusercontent.com/SakuraMathcraft/LaTeXSnipper/main/"
_REL_IMG_PATTERN = re.compile(r'!\[([^\]]*)\]\((?!https?://|data:)([^)]+)\)')


def _fix_relative_images(md: str) -> str:
    return _REL_IMG_PATTERN.sub(
        lambda m: f"![{m.group(1)}]({_GITHUB_RAW_PREFIX}{m.group(2).lstrip('./')})",
        md
    )
