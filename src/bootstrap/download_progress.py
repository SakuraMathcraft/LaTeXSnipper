"""Parsing and formatting for dependency download progress."""

from __future__ import annotations

import re
from typing import TypedDict


class TransferStatus(TypedDict):
    speed_text: str
    eta_text: str
    progress_text: str


def format_transfer_speed(bytes_per_second: object) -> str:
    try:
        speed = float(bytes_per_second)
    except (TypeError, ValueError):
        return ""
    if speed < 1024:
        return f"{speed:.0f} B/s"
    if speed < 1024 * 1024:
        return f"{speed / 1024:.1f} KB/s"
    if speed < 1024 * 1024 * 1024:
        return f"{speed / (1024 * 1024):.1f} MB/s"
    return f"{speed / (1024 * 1024 * 1024):.2f} GB/s"


def parse_pip_transfer_status(line: str) -> TransferStatus | None:
    text = str(line or "").strip().replace("\r", " ")
    if not text:
        return None
    speed_match = re.search(r"(\d+(?:\.\d+)?)\s*([kmg]?i?B/s)", text, re.IGNORECASE)
    if not speed_match:
        return None
    eta_match = re.search(r"(\d+:\d{2}:\d{2}|\d+:\d{2})", text)
    progress_match = re.search(
        r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([kmg]?i?B)",
        text,
        re.IGNORECASE,
    )
    progress_text = ""
    if progress_match:
        progress_text = f"{progress_match.group(1)}/{progress_match.group(2)} {progress_match.group(3)}"
    return {
        "speed_text": f"{speed_match.group(1)} {speed_match.group(2)}",
        "eta_text": eta_match.group(1) if eta_match else "",
        "progress_text": progress_text,
    }
