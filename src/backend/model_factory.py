import os

from backend.model import ModelWrapper


def _use_daemon_mode() -> bool:
    raw = (os.environ.get("LATEXSNIPPER_USE_DAEMON", "") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    # v1 phase-1: 默认使用 daemon，显式设置 LATEXSNIPPER_USE_DAEMON=0 可回退。
    return True


def create_model_wrapper(default_model: str | None = None):
    if not _use_daemon_mode():
        print("[INFO] model runtime: local wrapper (daemon disabled by env)")
        return ModelWrapper(default_model)
    try:
        from backend.model_daemon_adapter import DaemonModelWrapper

        print("[INFO] model runtime: daemon wrapper")
        return DaemonModelWrapper(default_model)
    except Exception as e:
        print(f"[WARN] daemon adapter unavailable, fallback local wrapper: {e}")
        return ModelWrapper(default_model)
