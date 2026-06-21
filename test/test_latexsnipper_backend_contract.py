from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_backend(tmp_path: Path, request: dict) -> tuple[int, dict, str]:
    request_path = tmp_path / "request.json"
    response_path = tmp_path / "response.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    env = os.environ.copy()
    pythonpath = [str(ROOT), str(ROOT / "src")]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "latexsnipper_backend",
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    response = json.loads(response_path.read_text(encoding="utf-8"))
    stderr = completed.stderr.strip()
    return completed.returncode, response, stderr


def test_backend_health_check_cli_contract(tmp_path: Path) -> None:
    code, response, stderr = _run_backend(tmp_path, {"schema": 1, "command": "health_check"})

    assert code == 0, stderr
    assert response["schema"] == 1
    assert response["ok"] is True
    assert response["result"]["status"] == "ok"
    assert response["result"]["backend"] == "latexsnipper_backend"


def test_backend_runtime_info_is_structured(tmp_path: Path) -> None:
    code, response, stderr = _run_backend(tmp_path, {"schema": 1, "command": "runtime_info"})

    assert code == 0, stderr
    assert response["ok"] is True
    result = response["result"]
    assert result["python_version"].startswith(str(sys.version_info.major))
    assert result["platform"]
    assert result["executable"]


def test_backend_exports_document_with_existing_latex_contract(tmp_path: Path) -> None:
    code, response, stderr = _run_backend(
        tmp_path,
        {
            "schema": 1,
            "command": "export_document",
            "payload": {
                "content": "# Title\n\nEuler: $e^{i\\pi}+1=0$",
                "format": "latex",
                "style": "document",
            },
        },
    )

    assert code == 0, stderr
    assert response["ok"] is True
    output = response["result"]["content"]
    assert "\\documentclass" in output
    assert "\\begin{document}" in output
    assert "Euler" in output


def test_backend_exports_formula_with_existing_format_contract(tmp_path: Path) -> None:
    code, response, stderr = _run_backend(
        tmp_path,
        {
            "schema": 1,
            "command": "export_formula",
            "payload": {
                "latex": "$$x^{2}+y$$",
                "format": "latex_display",
            },
        },
    )

    assert code == 0, stderr
    assert response["ok"] is True
    assert response["result"]["content"] == "\\[\nx^2+y\n\\]"
    assert response["result"]["display_name"] == "LaTeX (display \\[\\])"


def test_backend_recognition_commands_return_structured_not_implemented(tmp_path: Path) -> None:
    for command in ("recognize_image", "recognize_pdf", "render_latex_preview"):
        code, response, stderr = _run_backend(tmp_path, {"schema": 1, "command": command})

        assert code == 0, stderr
        assert response["ok"] is False
        assert response["error"]["code"] == "not_implemented"
        assert response["error"]["details"]["command"] == command


def test_backend_rejects_unknown_command_with_structured_error(tmp_path: Path) -> None:
    code, response, stderr = _run_backend(tmp_path, {"schema": 1, "command": "unknown"})

    assert code == 0, stderr
    assert response["ok"] is False
    assert response["error"]["code"] == "unsupported_command"
    assert response["error"]["details"]["command"] == "unknown"
