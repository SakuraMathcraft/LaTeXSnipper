from __future__ import annotations

# ruff: noqa: E402

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bootstrap.deps_runtime_verify import (
    format_layer_verify_failure,
    normalize_dependency_log_text,
    tail_dependency_log_text,
)


def test_dependency_log_normalization_removes_control_sequences() -> None:
    raw = "\x1b[31m错误\x1b[0m\r\nModule\x00NotFound\tError\ufffd"

    assert normalize_dependency_log_text(raw) == "错误\nModule NotFound Error?"


def test_layer_verify_failure_log_keeps_traceback_tail() -> None:
    err = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "<string>", line 2, in <module>',
            "ModuleNotFoundError: No module named 'onnxruntime'",
        ]
    )

    message = format_layer_verify_failure("MATHCRAFT_GPU", err)

    assert message.startswith("  [ERR] MATHCRAFT_GPU 验证失败:\n")
    assert "ModuleNotFoundError: No module named 'onnxruntime'" in message
    assert not message.rstrip().endswith("No mo")


def test_dependency_log_tail_uses_single_shared_limit() -> None:
    long_log = "\n".join(f"line {idx}" for idx in range(400))

    text = tail_dependency_log_text(long_log, limit=120)

    assert text.startswith("...\n")
    assert "line 399" in text
    assert "line 0" not in text


def test_layer_verify_callers_use_shared_formatter() -> None:
    deps_ui = (SRC / "bootstrap" / "deps_ui.py").read_text(encoding="utf-8")
    deps_workers = (SRC / "bootstrap" / "deps_workers.py").read_text(encoding="utf-8")
    deps_runtime_verify = (SRC / "bootstrap" / "deps_runtime_verify.py").read_text(encoding="utf-8")

    assert "err[:100]" not in deps_ui
    assert "(v_err or '')[:1000]" not in deps_workers
    assert "err[:200]" not in deps_runtime_verify
    assert "format_layer_verify_failure(layer, err)" in deps_ui
    assert "format_layer_verify_failure(lyr, v_err)" in deps_workers
