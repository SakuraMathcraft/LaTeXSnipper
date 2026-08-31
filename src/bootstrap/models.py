"""Typed values exchanged between dependency management and the installer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DependencyPlan:
    layers: tuple[str, ...]
    deps_path: Path
    action: str
    mirror_source: str
    force_enter: bool
    verified_in_ui: bool

    @classmethod
    def from_mapping(cls, values: Mapping[str, object], *, default_path: Path) -> "DependencyPlan":
        raw_layers = values.get("layers", ())
        layers = tuple(str(layer) for layer in raw_layers) if isinstance(raw_layers, (list, tuple)) else ()
        mirror_source = str(values.get("mirror_source", "") or "").strip().lower()
        if mirror_source not in {"off", "tuna"}:
            mirror_source = "tuna" if bool(values.get("mirror", False)) else "off"
        path_value = str(values.get("deps_path", "") or "").strip()
        return cls(
            layers=layers,
            deps_path=Path(path_value) if path_value else default_path,
            action=str(values.get("action", "") or ""),
            mirror_source=mirror_source,
            force_enter=bool(values.get("force_enter", False)),
            verified_in_ui=bool(values.get("verified_in_ui", False)),
        )
