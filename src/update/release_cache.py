import json
import time

from runtime.app_paths import app_state_dir
from update.release_types import ReleaseInfo

_ETAG_PATH = app_state_dir() / "release_etag_cache.json"
_RELEASE_CACHE_SCHEMA_VERSION = 2


def _load_cached_info():
    try:
        with open(_ETAG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if int(data.get("asset_policy_version", 0) or 0) != _RELEASE_CACHE_SCHEMA_VERSION:
            return None, 0, None
        etag = data.get("etag")
        ts = data.get("ts", 0)
        info_dict = data.get("info")
        if info_dict:
            info = ReleaseInfo(**info_dict)
        else:
            info = None
        return etag, ts, info
    except Exception:
        return None, 0, None


def _save_cached_info(etag: str, info: ReleaseInfo):
    try:
        with open(_ETAG_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "asset_policy_version": _RELEASE_CACHE_SCHEMA_VERSION,
                "etag": etag,
                "ts": int(time.time()),
                "info": {
                    "latest": info.latest,
                    "url": info.url,
                    "changelog": info.changelog,
                    "asset_url": info.asset_url,
                    "asset_name": info.asset_name,
                    "asset_id": info.asset_id,
                    "asset_size": info.asset_size,
                    "asset_updated_at": info.asset_updated_at,
                    "asset_sha256": info.asset_sha256,
                }
            }, f)
    except Exception:
        pass
