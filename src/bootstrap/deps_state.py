"""Dependency layer state file helpers."""

from __future__ import annotations

import json
from pathlib import Path


def load_json(path: Path, default):
    path = Path(path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data, log_q=None) -> None:
    try:
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        msg = f"[Deps] 写文件失败: {e}"
        print(msg)
        if log_q:
            log_q.put(msg)


def sanitize_state_layers(
    state_path: Path,
    *,
    valid_layers: set[str],
    runtime_layers: tuple[str, ...],
    state: dict | None = None,
) -> dict:
    """Normalize layer state and enforce mutually exclusive MathCraft runtimes."""
    if state is None:
        state = load_json(state_path, {"installed_layers": []})

    raw_installed = state.get("installed_layers", [])
    raw_failed = state.get("failed_layers", [])

    if not isinstance(raw_installed, list):
        raw_installed = []
    if not isinstance(raw_failed, list):
        raw_failed = []

    installed = [layer for layer in raw_installed if layer in valid_layers]
    failed = [layer for layer in raw_failed if layer in valid_layers]

    present_runtime = {x for x in runtime_layers if x in installed or x in failed}
    if len(present_runtime) > 1:
        if "MATHCRAFT_GPU" in installed and "MATHCRAFT_CPU" not in installed:
            keep_runtime = "MATHCRAFT_GPU"
        elif "MATHCRAFT_CPU" in installed and "MATHCRAFT_GPU" not in installed:
            keep_runtime = "MATHCRAFT_CPU"
        elif "MATHCRAFT_GPU" in failed and "MATHCRAFT_CPU" not in failed:
            keep_runtime = "MATHCRAFT_GPU"
        elif "MATHCRAFT_CPU" in failed and "MATHCRAFT_GPU" not in failed:
            keep_runtime = "MATHCRAFT_CPU"
        else:
            keep_runtime = "MATHCRAFT_GPU"
        installed = [layer for layer in installed if layer not in runtime_layers or layer == keep_runtime]
        failed = [layer for layer in failed if layer not in runtime_layers or layer == keep_runtime]

    changed = (installed != raw_installed) or (failed != raw_failed)
    payload = {"installed_layers": installed}
    if failed:
        payload["failed_layers"] = failed

    if changed:
        save_json(state_path, payload)
        dropped = sorted(set(raw_installed + raw_failed) - set(installed + failed))
        if dropped:
            print(f"[INFO] 已忽略并移除废弃/未知层: {', '.join(dropped)}")

    return payload


def normalize_chosen_layers(layers: list[str] | None, *, valid_layers: set[str]) -> list[str]:
    """Normalize selected layers and enforce MathCraft CPU/GPU backend mutual exclusion."""
    ordered: list[str] = []
    seen: set[str] = set()
    for layer in layers or []:
        name = str(layer)
        if name not in valid_layers or name in seen:
            continue
        if name == "MATHCRAFT_CPU" and "MATHCRAFT_GPU" in seen:
            continue
        if name == "MATHCRAFT_GPU" and "MATHCRAFT_CPU" in seen:
            ordered = [x for x in ordered if x != "MATHCRAFT_CPU"]
            seen.discard("MATHCRAFT_CPU")
        ordered.append(name)
        seen.add(name)
    return ordered
