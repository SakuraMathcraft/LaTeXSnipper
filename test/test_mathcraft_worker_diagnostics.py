from __future__ import annotations

import sys

import pytest

from backend.mathcraft.diagnostics import classify_mathcraft_failure
from backend.mathcraft.model import ModelWrapper, _MathCraftWorkerError


@pytest.mark.parametrize(
    ("module", "code"),
    [
        ("rapidocr", "MATHCRAFT_DEP_MISSING"),
        ("omegaconf", "MATHCRAFT_DEP_MISSING"),
        ("mathcraft_ocr", "MATHCRAFT_MISSING"),
        ("onnxruntime", "ONNXRUNTIME_MISSING"),
        ("onnxruntime.capi", "ONNXRUNTIME_BROKEN"),
        ("rapidocr.utils", "MATHCRAFT_DEP_BROKEN"),
    ],
)
def test_missing_import_is_not_inferred_from_traceback_paths(module, code):
    detail = (
        'File "D:/app/mathcraft_ocr/runtime.py", line 10\n'
        "from rapidocr.utils.process_img import get_rotate_crop_image\n"
        f"ModuleNotFoundError: No module named '{module}'"
    )
    assert classify_mathcraft_failure(detail)["code"] == code


def test_arbitrary_index_error_is_not_diagnosed_as_corrupt_weights():
    assert (
        classify_mathcraft_failure("IndexError: list index out of range")["code"]
        == "UNKNOWN"
    )


@pytest.mark.parametrize("component_failure", [False, True])
def test_warmup_persists_remote_traceback(component_failure, monkeypatch, capsys):
    wrapper = ModelWrapper(auto_warmup=False)
    capsys.readouterr()
    trace = "Traceback (most recent call last):\n  worker_specific_frame\nValueError: 中文异常"

    def request(*args, **kwargs):
        if component_failure:
            return {
                "ready": False,
                "component_statuses": [
                    {
                        "model_id": "formula",
                        "ready": False,
                        "detail": "中文异常",
                        "traceback": trace,
                    }
                ],
            }
        raise _MathCraftWorkerError("ValueError", "中文异常", trace)

    monkeypatch.setattr(wrapper, "_send_worker_request", request)
    assert wrapper._lazy_load_mathcraft() is False
    output = capsys.readouterr().out
    assert "[ERR] MathCraft OCR 预热失败" in output
    assert trace in output


def _script_worker(monkeypatch, script):
    wrapper = ModelWrapper(auto_warmup=False)
    monkeypatch.setattr(
        wrapper, "_worker_argv", lambda: [sys.executable, "-u", "-c", script]
    )
    return wrapper


def test_worker_exit_drains_stderr_and_reports_exit_code(monkeypatch, capsys):
    wrapper = _script_worker(
        monkeypatch,
        "import sys; sys.stdin.readline(); "
        'sys.stderr.write("final diagnostic: 中文\\n"); sys.stderr.flush(); sys.exit(7)',
    )
    with pytest.raises(RuntimeError) as caught:
        wrapper._send_worker_request({"action": "warmup"})
    assert "exit_code=7 (0x00000007)" in str(caught.value)
    assert "final diagnostic: 中文" in str(caught.value)
    assert "final diagnostic: 中文" in capsys.readouterr().out
    assert wrapper._worker is None


def test_worker_error_response_keeps_native_stderr_in_log(monkeypatch, capsys):
    wrapper = _script_worker(
        monkeypatch,
        "import sys,json; sys.stdin.readline(); "
        'sys.stderr.write("native diagnostic\\n"); sys.stderr.flush(); '
        'print(json.dumps({"ok":False,"error":{"type":"ValueError","message":"failed","traceback":"remote frame"}}),flush=True); '
        "sys.stdin.readline()",
    )
    try:
        with pytest.raises(_MathCraftWorkerError) as caught:
            wrapper._send_worker_request({"action": "warmup"})
        assert caught.value.remote_traceback == "remote frame"
    finally:
        wrapper._stop_mathcraft_worker()
    assert "native diagnostic" in capsys.readouterr().out


def test_timeout_preserves_stderr_and_terminates_worker(monkeypatch):
    wrapper = _script_worker(
        monkeypatch,
        "import sys,time; sys.stdin.readline(); "
        'sys.stderr.write("before timeout\\n"); sys.stderr.flush(); time.sleep(30)',
    )
    with pytest.raises(RuntimeError) as caught:
        wrapper._send_worker_request({"action": "warmup"}, timeout_sec=1)
    assert "运行进程超时" in str(caught.value)
    assert "before timeout" in str(caught.value)
    assert classify_mathcraft_failure(str(caught.value))["code"] == "WORKER_TIMEOUT"
    assert wrapper._worker is None


@pytest.mark.parametrize("pipe", ["stdin", "stdout"])
def test_broken_pipe_retains_worker_diagnostics(pipe, monkeypatch):
    wrapper = _script_worker(
        monkeypatch,
        'import sys,time; sys.stderr.write("before pipe failure\\n"); sys.stderr.flush(); '
        'print("ready",flush=True); time.sleep(30)',
    )
    assert wrapper._ensure_worker()
    proc = wrapper._worker
    assert proc.stdout.readline().strip() == "ready"
    getattr(proc, pipe).close()
    with pytest.raises(RuntimeError) as caught:
        wrapper._send_worker_request({"action": "warmup"})
    assert "before pipe failure" in str(caught.value)
    assert "pid=" in str(caught.value)
    assert proc.poll() is not None


def test_warmup_preserves_classification_for_ui(monkeypatch):
    wrapper = ModelWrapper(auto_warmup=False)

    def fail(*args, **kwargs):
        raise _MathCraftWorkerError("ModuleNotFoundError", "No module named 'rapidocr'")

    monkeypatch.setattr(wrapper, "_send_worker_request", fail)
    assert not wrapper._lazy_load_mathcraft()
    info = wrapper.get_failure_info()
    assert info["code"] == "MATHCRAFT_DEP_MISSING"
    assert "rapidocr" in info["log_message"]
    wrapper._clear_error()
    assert wrapper.get_failure_info() == {}
