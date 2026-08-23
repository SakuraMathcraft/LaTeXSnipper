from __future__ import annotations

import logging


PERSISTENT_LOG_LEVEL = logging.INFO


_PRINT_LEVEL_PREFIXES = {
    "[DEBUG]": logging.DEBUG,
    "[WARN]": logging.WARNING,
    "[ERR]": logging.ERROR,
    "[INFO]": logging.INFO,
    "[OK]": logging.INFO,
}


def parse_print_log_record(message: str) -> tuple[int, str]:
    """Return the logging level and message without its level prefix."""
    text = str(message or "").lstrip()
    for prefix, level in _PRINT_LEVEL_PREFIXES.items():
        if text.startswith(prefix):
            return level, text.removeprefix(prefix).lstrip()
    return PERSISTENT_LOG_LEVEL, text
