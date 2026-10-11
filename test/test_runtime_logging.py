from __future__ import annotations

# ruff: noqa: E402

import re
import pytest
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime.log_lifecycle import cleanup_stale_fallback_logs, rotate_before_append


@pytest.mark.parametrize("packaged", [False, True])
def test_application_log_routes_levels_formats_and_tracebacks(tmp_path: Path, packaged: bool) -> None:
    code = """
import logging
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
import runtime.runtime_logging as runtime_logging
from runtime.std_streams import ensure_std_streams

if sys.argv[3] == "True":
    sys.frozen = True
    sys.stdout = sys.stderr = sys.__stdout__ = sys.__stderr__ = None
ensure_std_streams()
target = Path(sys.argv[1])
runtime_logging.app_log_dir = lambda: target
runtime_logging.runtime_log_path().write_text("previous-session", encoding="utf-8")
runtime_logging.init_app_logging()
runtime_logging.init_app_logging()
assert runtime_logging.runtime_log_path().read_text(encoding="utf-8") == "previous-session"
runtime_logging.start_runtime_log_session()
runtime_logging.start_runtime_log_session()
logger = logging.getLogger("latexsnipper.test")
logger.debug("debug-only")
logger.info("ready")
logger.warning("warning-record")
logging.getLogger("thirdparty").debug("thirdparty-debug")
logging.getLogger("thirdparty").info("thirdparty-info")
try:
    raise ValueError("diagnostic failure")
except ValueError:
    logger.exception("exception-record")
print("stdout-record", flush=True)
sys.stderr.write("stderr-record\\n")
assert "ready" in runtime_logging.runtime_log_path().read_text(encoding="utf-8")
sys.stdout.flush()
sys.stderr.flush()
runtime_logging.cleanup_runtime_log_session()
runtime_logging.cleanup_runtime_log_session()
logger.info("after-session")
logging.shutdown()
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(SRC), env.get("PYTHONPATH", ""))))
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), str(SRC), str(packaged)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    persistent = (tmp_path / "app.log").read_text(encoding="utf-8")
    session = (tmp_path / "runtime-session.log").read_text(encoding="utf-8")
    assert re.search(r"^\[\d{4}-\d{2}-\d{2} [^\]]+\] \[INFO\] ready$", persistent, re.MULTILINE)
    assert "[DEBUG] debug-only" in session
    assert "debug-only" not in persistent
    assert "thirdparty-debug" not in session
    assert "thirdparty-debug" not in persistent
    assert "previous-session" not in session
    for message in ("ready", "warning-record", "thirdparty-info", "exception-record", "LaTeXSnipper 启动 pid="):
        assert session.count(message) == 1
        assert persistent.count(message) == 1
    assert "[INFO] ready\n" in session
    assert "[WARNING] warning-record\n" in session
    assert "[ERROR] exception-record\nTraceback" in session
    assert "ValueError: diagnostic failure" in session
    assert "ValueError: diagnostic failure" in persistent
    for message in ("stdout-record", "stderr-record"):
        assert message in session
        assert message not in persistent
    assert "after-session" in persistent
    assert "after-session" not in session
    if not packaged:
        assert result.stdout.count("[INFO] ready") == 1


def test_plain_log_rotation_is_bounded(tmp_path: Path) -> None:
    log = tmp_path / "crash-native.log"
    log.write_text("current", encoding="utf-8")
    (tmp_path / "crash-native.log.1").write_text("previous", encoding="utf-8")
    (tmp_path / "crash-native.log.2").write_text("oldest", encoding="utf-8")

    assert rotate_before_append(log, max_bytes=len("current"), backup_count=2)
    assert not log.exists()
    assert (tmp_path / "crash-native.log.1").read_text(encoding="utf-8") == "current"
    assert (tmp_path / "crash-native.log.2").read_text(encoding="utf-8") == "previous"


def test_plain_log_below_limit_is_not_rotated(tmp_path: Path) -> None:
    log = tmp_path / "crash-native.log"
    log.write_text("current", encoding="utf-8")

    assert not rotate_before_append(log, max_bytes=1024, backup_count=2)
    assert log.read_text(encoding="utf-8") == "current"


def test_only_expired_pid_fallback_logs_are_removed(tmp_path: Path) -> None:
    now = time.time()
    old_log = tmp_path / "app-123.log"
    old_backup = tmp_path / "app-123.log.1"
    recent_log = tmp_path / "app-456.log"
    unrelated = tmp_path / "other.log"
    for path in (old_log, old_backup, recent_log, unrelated):
        path.write_text(path.name, encoding="utf-8")
    os.utime(old_log, (now - 100, now - 100))
    os.utime(old_backup, (now - 100, now - 100))

    assert cleanup_stale_fallback_logs(tmp_path, max_age_seconds=60, now=now) == 2
    assert not old_log.exists()
    assert not old_backup.exists()
    assert recent_log.exists()
    assert unrelated.exists()


def test_session_capture_requires_instance_lock(monkeypatch):
    import pytest
    from application import bootstrap

    events = []
    monkeypatch.setattr(bootstrap.atexit, "register", lambda callback: None)
    monkeypatch.setattr(bootstrap, "start_runtime_log_session", lambda: events.append("session"))
    monkeypatch.setattr(bootstrap, "_show_already_running_message", lambda app: None)
    monkeypatch.setattr(bootstrap, "ensure_single_instance", lambda: False)
    with pytest.raises(SystemExit):
        bootstrap._ensure_single_instance(None)
    assert events == []
    monkeypatch.setattr(bootstrap, "ensure_single_instance", lambda: True)
    bootstrap._ensure_single_instance(None)
    assert events == ["session"]
