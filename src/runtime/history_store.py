"""Persistent history storage for recognized content."""

from __future__ import annotations

import json
from pathlib import Path

from runtime.config_manager import normalize_content_type


def load_history_store(path: str | Path) -> tuple[list[str], dict[str, str], dict[str, str]]:
    target = Path(path)
    if not target.exists():
        return [], {}, {}

    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return [], {}, {}

    raw_history = data.get("history", [])
    history = [str(x) for x in raw_history if isinstance(x, (str, int, float))]

    raw_names = data.get("formula_names", {})
    formula_names = {str(k): str(v) for k, v in raw_names.items()} if isinstance(raw_names, dict) else {}

    raw_types = data.get("formula_types", {})
    formula_types = (
        {str(k): normalize_content_type(str(v)) for k, v in raw_types.items()}
        if isinstance(raw_types, dict)
        else {}
    )

    return history, formula_names, formula_types


def save_history_store(
    path: str | Path,
    history: list[str],
    formula_names: dict[str, str],
    formula_types: dict[str, str],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "history": history,
        "formula_names": formula_names,
        "formula_types": formula_types,
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
