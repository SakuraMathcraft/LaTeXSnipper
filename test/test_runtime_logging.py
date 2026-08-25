from __future__ import annotations

# ruff: noqa: E402

import logging
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime.log_record import PERSISTENT_LOG_LEVEL, parse_print_log_record
from runtime.log_lifecycle import cleanup_stale_fallback_logs, rotate_before_append


def test_print_log_prefix_is_converted_without_duplication() -> None:
    assert PERSISTENT_LOG_LEVEL == logging.INFO
    assert parse_print_log_record("[DEBUG] 诊断") == (logging.DEBUG, "诊断")
    assert parse_print_log_record("[INFO] 已启动") == (logging.INFO, "已启动")
    assert parse_print_log_record(" [WARN] 连接失败") == (logging.WARNING, "连接失败")
    assert parse_print_log_record("[ERR] 安装失败") == (logging.ERROR, "安装失败")
    assert parse_print_log_record("普通消息") == (logging.INFO, "普通消息")


def test_persistent_log_excludes_debug_and_strips_prefixes(tmp_path: Path) -> None:
    code = """
import logging
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
import runtime.runtime_logging as runtime_logging

target = Path(sys.argv[1])
runtime_logging.app_log_dir = lambda: target
runtime_logging.app_state_dir = lambda: target / "state"
runtime_logging.init_app_logging()
print("[DEBUG] debug-only")
print("[INFO] ready")
logging.shutdown()
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(SRC), env.get("PYTHONPATH", ""))))
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), str(SRC)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "debug-only" not in text
    assert "[INFO] [INFO] ready" not in text
    assert text.count("ready") == 1


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
