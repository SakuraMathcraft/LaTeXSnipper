import hashlib
import json
import os
from pathlib import Path

from update.release_assets import _normalize_download_asset
from update.release_types import ReleaseInfo, _normalize_sha256


def _update_dir() -> Path:
    update_dir = Path.home() / ".latexsnipper" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    return update_dir


def _installer_meta_path() -> Path:
    return _update_dir() / "installer_meta.json"


def _asset_fingerprint(info: ReleaseInfo) -> dict:
    return {
        "latest": str(info.latest or ""),
        "asset_url": str(info.asset_url or ""),
        "asset_name": str(info.asset_name or ""),
        "asset_id": str(info.asset_id or ""),
        "asset_size": int(info.asset_size or 0),
        "asset_updated_at": str(info.asset_updated_at or ""),
        "asset_sha256": _normalize_sha256(info.asset_sha256),
    }


def _load_installer_meta() -> dict:
    try:
        with _installer_meta_path().open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_installer_meta(info: ReleaseInfo, path: str, sha256_hex: str) -> None:
    payload = _asset_fingerprint(info)
    payload["path"] = str(path or "")
    payload["sha256"] = str(sha256_hex or "")
    try:
        with _installer_meta_path().open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _clear_installer_meta() -> None:
    try:
        _installer_meta_path().unlink(missing_ok=True)
    except Exception:
        pass



def _compute_file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if chunk:
                h.update(chunk)
    return h.hexdigest()


def _download_target(info: ReleaseInfo) -> tuple[str, str]:
    url, name = _normalize_download_asset(info.asset_url, info.asset_name)
    if not url or not name:
        return "", ""
    return url, str(_update_dir() / name)


def _download_paths(info: ReleaseInfo) -> tuple[str, str, str]:
    url, dest = _download_target(info)
    return url, dest, dest + ".part"


def _remove_path(path: str) -> None:
    try:
        p = Path(path)
        if p.exists() and p.is_file():
            p.unlink()
    except Exception:
        pass


def _prune_update_dir(info: ReleaseInfo) -> None:
    _, dest, tmp_path = _download_paths(info)
    keep = {
        str(Path(dest)),
        str(Path(tmp_path)),
        str(_installer_meta_path()),
    }
    for child in _update_dir().iterdir():
        child_str = str(child)
        if child_str in keep:
            continue
        try:
            if child.is_file():
                child.unlink()
        except Exception:
            pass


def _local_installer_valid(info: ReleaseInfo) -> bool:
    _, dest, _ = _download_paths(info)
    dest_path = Path(dest)
    if not dest_path.is_file():
        return False
    meta = _load_installer_meta()
    if not meta:
        return False
    if str(meta.get("path", "")) != str(dest_path):
        return False
    if any(str(meta.get(k, "")) != str(v) for k, v in _asset_fingerprint(info).items() if k != "asset_size"):
        return False
    if int(meta.get("asset_size", 0) or 0) != int(info.asset_size or 0):
        return False
    if info.asset_size and dest_path.stat().st_size != int(info.asset_size):
        return False
    saved_sha256 = str(meta.get("sha256", "") or "").strip().lower()
    if not saved_sha256:
        return False
    return _compute_file_sha256(str(dest_path)).lower() == saved_sha256


def _ensure_latest_installer_only(info: ReleaseInfo) -> bool:
    _prune_update_dir(info)
    _, dest, tmp_path = _download_paths(info)
    if os.path.exists(tmp_path) and not os.path.exists(dest):
        return False
    if _local_installer_valid(info):
        return True
    _remove_path(dest)
    _remove_path(tmp_path)
    _clear_installer_meta()
    return False
