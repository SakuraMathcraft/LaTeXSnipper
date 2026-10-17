from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from backend.mathcraft.diagnostics import classify_mathcraft_failure
from backend.mathcraft.model import ModelWrapper, _MathCraftWorkerError
from mathcraft_ocr.hardware import _run_powershell_json
from runtime.installed_resources import worker_command, worker_environment

ROOT = Path(__file__).resolve().parents[1]
UNICODE_TEXT = "中文 − ∑ 𝛼 🙂 café"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell transport")
def test_powershell_json_preserves_unicode():
    result = _run_powershell_json(
        f"[pscustomobject]@{{Name='{UNICODE_TEXT}'}} | ConvertTo-Json -Compress"
    )
    assert result == {"Name": UNICODE_TEXT}


def test_isolated_worker_launch_uses_utf8_despite_locale_environment():
    command = worker_command(None)
    command[-1] = """
import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({
    'request': request,
    'encodings': [sys.stdin.encoding, sys.stdout.encoding, sys.stderr.encoding],
    'utf8_mode': sys.flags.utf8_mode,
}, ensure_ascii=False), flush=True)
sys.stderr.write(request['text'])
"""
    environment = worker_environment(None)
    environment.update(PYTHONUTF8="0", PYTHONIOENCODING="gbk")
    request = {"text": UNICODE_TEXT, "image": "中文目录/𝛼−🙂.png"}
    result = subprocess.run(
        command,
        input=(json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"),
        capture_output=True,
        env=environment,
        timeout=30,
        check=True,
    )
    response = json.loads(result.stdout.decode("utf-8"))
    assert response["request"] == request
    assert response["encodings"] == ["utf-8"] * 3
    assert response["utf8_mode"] == 1
    assert result.stderr.decode("utf-8") == UNICODE_TEXT


def test_standalone_worker_utf8_roundtrip_and_errors_from_gbk_streams():
    code = """
import sys
sys.path.insert(0, sys.argv[1])
for stream in (sys.stdin, sys.stdout, sys.stderr):
    stream.reconfigure(encoding='gbk')
from mathcraft_ocr import worker
worker.MathCraftRuntime = lambda **kwargs: object()
def handle(self, request):
    if request['action'] == 'fail':
        raise ValueError(request['text'])
    print(request['text'], flush=True)
    return {'text': request['text']}
worker.MathCraftWorker._handle_result = handle
raise SystemExit(worker.serve_jsonl())
"""
    requests = [
        {"protocol": 1, "id": f"中文−{index}", "action": action, "text": UNICODE_TEXT}
        for index, action in enumerate(("echo", "fail", "echo"))
    ]
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8=0", "-c", code, str(ROOT)],
        input="".join(
            json.dumps(r, ensure_ascii=False) + "\n" for r in requests
        ).encode("utf-8"),
        capture_output=True,
        timeout=30,
        check=True,
    )
    responses = [
        json.loads(line) for line in result.stdout.decode("utf-8").splitlines()
    ]
    assert [r["id"] for r in responses] == [r["id"] for r in requests]
    assert responses[0]["result"]["text"] == UNICODE_TEXT
    assert responses[1]["error"]["message"] == UNICODE_TEXT
    assert UNICODE_TEXT in responses[1]["error"]["traceback"]
    assert responses[2]["result"]["text"] == UNICODE_TEXT
    assert result.stderr.decode("utf-8").splitlines() == [UNICODE_TEXT] * 2


def test_cli_unicode_output_json_and_export_from_gbk_streams(tmp_path):
    code = """
import sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from mathcraft_ocr import cli, runtime
result = SimpleNamespace(text=sys.argv[2], score=0.9, provider='CPUExecutionProvider')
runtime.MathCraftRuntime = lambda **kwargs: SimpleNamespace(recognize_formula=lambda *_: result)
for arguments in ([], ['--json'], ['--output', sys.argv[3]]):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding='gbk')
    assert cli.main(['ocr', '中文−𝛼🙂.png', '--profile', 'formula', *arguments]) == 0
"""
    output = tmp_path / "中文−𝛼🙂.md"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8=0",
            "-c",
            code,
            str(ROOT),
            UNICODE_TEXT,
            str(output),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    lines = result.stdout.decode("utf-8").splitlines()
    plain, encoded = lines[0], "\n".join(lines[1:])
    assert plain == UNICODE_TEXT
    assert json.loads(encoded)["text"] == UNICODE_TEXT
    assert output.read_bytes() == UNICODE_TEXT.encode("utf-8")
    assert str(output) in result.stderr.decode("utf-8")


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
def test_warmup_persists_remote_traceback(component_failure, monkeypatch, caplog):
    wrapper = ModelWrapper(auto_warmup=False)
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
    assert wrapper.warmup() is False
    output = caplog.text
    assert "MathCraft OCR 预热失败" in output
    assert trace in output


def _script_worker(monkeypatch, script):
    wrapper = ModelWrapper(auto_warmup=False)
    monkeypatch.setattr(
        wrapper, "_worker_argv", lambda: [sys.executable, "-u", "-c", script]
    )
    return wrapper


def test_worker_exit_drains_stderr_and_reports_exit_code(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="latexsnipper.backend.mathcraft.model")
    wrapper = _script_worker(
        monkeypatch,
        "import sys; sys.stdin.readline(); "
        'sys.stderr.write("final diagnostic: 中文\\n"); sys.stderr.flush(); sys.exit(7)',
    )
    with pytest.raises(RuntimeError) as caught:
        wrapper._send_worker_request({"action": "warmup"})
    assert "exit_code=7 (0x00000007)" in str(caught.value)
    assert "final diagnostic: 中文" in str(caught.value)
    assert "final diagnostic: 中文" in caplog.text
    assert wrapper._worker is None


def test_worker_error_response_keeps_native_stderr_in_log(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="latexsnipper.backend.mathcraft.model")
    wrapper = _script_worker(
        monkeypatch,
        "import sys,json; request=json.loads(sys.stdin.readline()); "
        'sys.stderr.write("native diagnostic\\n"); sys.stderr.flush(); '
        'print(json.dumps({"protocol":1,"id":request["id"],"ok":False,"error":{"type":"ValueError","message":"failed","traceback":"remote frame"}}),flush=True); '
        "sys.stdin.readline()",
    )
    try:
        with pytest.raises(_MathCraftWorkerError) as caught:
            wrapper._send_worker_request({"action": "warmup"})
        assert caught.value.remote_traceback == "remote frame"
    finally:
        wrapper.stop()
    assert "native diagnostic" in caplog.text


def test_invalid_utf8_response_is_reported_instead_of_replaced(monkeypatch):
    wrapper = _script_worker(
        monkeypatch,
        "import sys; sys.stdin.readline(); sys.stdout.buffer.write(b'\\xff\\n'); sys.stdout.flush()",
    )
    with pytest.raises(RuntimeError, match="响应读取失败.*utf-8"):
        wrapper._send_worker_request({"action": "hello"})
    assert wrapper._worker is None


def test_timeout_preserves_stderr_and_terminates_worker(monkeypatch):
    wrapper = _script_worker(
        monkeypatch,
        "import sys,time; sys.stdin.readline(); "
        'sys.stderr.write("before timeout\\n"); sys.stderr.flush(); time.sleep(30)',
    )
    with pytest.raises(RuntimeError) as caught:
        wrapper._send_worker_request({"action": "hello"}, timeout_sec=1)
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
    assert not wrapper.warmup()
    info = wrapper.get_failure_info()
    assert info["code"] == "MATHCRAFT_DEP_MISSING"
    assert "rapidocr" in info["log_message"]
    wrapper._clear_error()
    assert wrapper.get_failure_info() == {}
