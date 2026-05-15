import re

_GITHUB_RAW_PREFIX = "https://raw.githubusercontent.com/SakuraMathcraft/LaTeXSnipper/main/"
_REL_IMG_PATTERN = re.compile(r'!\[([^\]]*)\]\((?!https?://|data:)([^)]+)\)')
_MARK_TAG_PATTERN = re.compile(r"</?mark\b[^>]*>", re.IGNORECASE)


def _fix_relative_images(md: str) -> str:
    return _REL_IMG_PATTERN.sub(
        lambda m: f"![{m.group(1)}]({_GITHUB_RAW_PREFIX}{m.group(2).lstrip('./')})",
        md
    )


def _prepare_release_markdown(md: str) -> str:
    fixed = _fix_relative_images(md)
    return _MARK_TAG_PATTERN.sub("", fixed)
