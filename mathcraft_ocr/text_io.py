"""UTF-8 streams for the standalone CLI and worker protocol."""

from io import TextIOWrapper
from typing import TextIO


def utf8_stream(stream: TextIO | None, *, errors: str = "strict") -> TextIO | None:
    if isinstance(stream, TextIOWrapper):
        stream.reconfigure(encoding="utf-8", errors=errors)
    return stream
