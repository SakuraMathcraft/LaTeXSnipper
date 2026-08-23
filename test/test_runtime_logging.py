from __future__ import annotations

# ruff: noqa: E402

import logging
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime.log_record import PERSISTENT_LOG_LEVEL, parse_print_log_record


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
