from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from latexsnipper_backend import SCHEMA_VERSION


NOT_IMPLEMENTED_COMMANDS = {
    "recognize_image",
    "recognize_pdf",
    "render_latex_preview",
}

PURE_FORMULA_FORMATS = {
    "latex",
    "latex_display",
    "latex_equation",
    "markdown_inline",
    "markdown_block",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="latexsnipper_backend")
    parser.add_argument("--request", required=True, help="Path to a UTF-8 JSON request file.")
    parser.add_argument("--response", help="Path where a UTF-8 JSON response should be written.")
    args = parser.parse_args(argv)

    try:
        request = _read_json(Path(args.request))
        response = handle_request(request)
    except Exception as exc:
        response = _error("backend_failure", str(exc))
        _write_response(args.response, response)
        return 2

    _write_response(args.response, response)
    return 0


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    command = str(request.get("command") or "").strip()
    if not command:
        return _error("invalid_request", "Request is missing a command.")

    payload = request.get("payload") or {}
    if not isinstance(payload, dict):
        return _error("invalid_request", "Request payload must be an object.", payload_type=type(payload).__name__)

    if command == "health_check":
        return _ok({"backend": "latexsnipper_backend", "schema": SCHEMA_VERSION, "status": "ok"})
    if command == "runtime_info":
        return _ok(_runtime_info())
    if command == "export_document":
        return _export_document(payload)
    if command == "export_formula":
        return _export_formula(payload)
    if command in NOT_IMPLEMENTED_COMMANDS:
        return _error(
            "not_implemented",
            f"{command} is reserved in the backend contract but is not implemented yet.",
            command=command,
        )
    return _error("unsupported_command", f"Unsupported backend command: {command}", command=command)


def _runtime_info() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
    }


def _export_document(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_src_path()
    from core.pdf_output_contract import wrap_document_output

    content = str(payload.get("content") or "")
    fmt = str(payload.get("format") or "latex")
    style = str(payload.get("style") or "document")
    output = wrap_document_output(content, fmt, style)
    return _ok({"content": output, "format": fmt, "style": style})


def _export_formula(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_src_path()
    from exporting.formula_export import build_formula_export

    fmt = str(payload.get("format") or "latex")
    if fmt not in PURE_FORMULA_FORMATS:
        return _error(
            "unsupported_format",
            f"Formula format requires an external converter and is not enabled in this CLI contract yet: {fmt}",
            format=fmt,
        )

    latex = str(payload.get("latex") or "")
    content, display_name = build_formula_export(
        fmt,
        latex,
        mathml_converter=_converter_not_available,
        omml_converter=_converter_not_available,
        svg_converter=_converter_not_available,
    )
    if not display_name:
        return _error("unsupported_format", f"Unsupported formula format: {fmt}", format=fmt)
    return _ok({"content": content, "format": fmt, "display_name": display_name})


def _converter_not_available(_: str) -> str:
    raise RuntimeError("This backend CLI command only supports pure formula export formats for now.")


def _ensure_src_path() -> None:
    src_path = Path(__file__).resolve().parents[1] / "src"
    if src_path.exists():
        src = str(src_path)
        if src not in sys.path:
            sys.path.insert(0, src)


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Request JSON root must be an object.")
    return data


def _write_response(response_path: str | None, response: dict[str, Any]) -> None:
    encoded = json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True)
    if response_path:
        Path(response_path).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    return {"schema": SCHEMA_VERSION, "ok": True, "result": result}


def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
