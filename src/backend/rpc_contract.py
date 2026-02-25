import json
from pathlib import Path
from typing import Any


_FALLBACK_CONTRACT: dict[str, Any] = {
    "name": "latexsnipper-daemon-rpc",
    "version": "1.0.0",
    "enums": {
        "methods": [
            "health",
            "warmup",
            "model_status",
            "task_submit",
            "task_status",
            "task_cancel",
            "shutdown",
        ],
        "deprecated_methods": ["predict_image"],
        "task_kinds": ["predict_image", "predict_pdf", "install_deps", "switch_cpu_gpu"],
        "task_status": ["queued", "running", "success", "error", "cancelled"],
        "task_terminal_status": ["success", "error", "cancelled"],
    },
}


def _contract_json_path() -> Path:
    # e:\LaTexSnipper\src\backend\rpc_contract.py -> repo root at parents[2]
    return Path(__file__).resolve().parents[2] / "contracts" / "daemon_rpc_contract.v1.json"


def _load_contract() -> dict[str, Any]:
    p = _contract_json_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return dict(_FALLBACK_CONTRACT)


CONTRACT: dict[str, Any] = _load_contract()
CONTRACT_NAME = str(CONTRACT.get("name", "latexsnipper-daemon-rpc"))
CONTRACT_VERSION = str(CONTRACT.get("version", "1.0.0"))

_enums = CONTRACT.get("enums", {}) if isinstance(CONTRACT.get("enums"), dict) else {}

METHOD_HEALTH = "health"
METHOD_WARMUP = "warmup"
METHOD_MODEL_STATUS = "model_status"
METHOD_PREDICT_IMAGE = "predict_image"
METHOD_TASK_SUBMIT = "task_submit"
METHOD_TASK_STATUS = "task_status"
METHOD_TASK_CANCEL = "task_cancel"
METHOD_SHUTDOWN = "shutdown"

TASK_KIND_PREDICT_IMAGE = "predict_image"
TASK_KIND_PREDICT_PDF = "predict_pdf"
TASK_KIND_INSTALL_DEPS = "install_deps"
TASK_KIND_SWITCH_CPU_GPU = "switch_cpu_gpu"

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_SUCCESS = "success"
TASK_STATUS_ERROR = "error"
TASK_STATUS_CANCELLED = "cancelled"

METHODS = tuple(str(x) for x in (_enums.get("methods") or ()))
DEPRECATED_METHODS = tuple(str(x) for x in (_enums.get("deprecated_methods") or ()))
TASK_KINDS = tuple(str(x) for x in (_enums.get("task_kinds") or ()))
TASK_STATUSES = tuple(str(x) for x in (_enums.get("task_status") or ()))
TASK_TERMINAL_STATUSES = tuple(str(x) for x in (_enums.get("task_terminal_status") or ()))


def is_known_method(method: str) -> bool:
    m = str(method or "")
    if METHODS:
        return m in METHODS or m in DEPRECATED_METHODS
    return m in (
        METHOD_HEALTH,
        METHOD_WARMUP,
        METHOD_MODEL_STATUS,
        METHOD_PREDICT_IMAGE,
        METHOD_TASK_SUBMIT,
        METHOD_TASK_STATUS,
        METHOD_TASK_CANCEL,
        METHOD_SHUTDOWN,
    )


def is_supported_task_kind(kind: str) -> bool:
    k = str(kind or "")
    if TASK_KINDS:
        return k in TASK_KINDS
    return k in (
        TASK_KIND_PREDICT_IMAGE,
        TASK_KIND_PREDICT_PDF,
        TASK_KIND_INSTALL_DEPS,
        TASK_KIND_SWITCH_CPU_GPU,
    )


def is_terminal_task_status(status: str) -> bool:
    s = str(status or "")
    if TASK_TERMINAL_STATUSES:
        return s in TASK_TERMINAL_STATUSES
    return s in (TASK_STATUS_SUCCESS, TASK_STATUS_ERROR, TASK_STATUS_CANCELLED)


def method_params_required(method: str) -> tuple[str, ...]:
    methods = CONTRACT.get("methods", {}) if isinstance(CONTRACT.get("methods"), dict) else {}
    spec = methods.get(str(method or ""), {})
    if isinstance(spec, dict):
        vals = spec.get("params_required", []) or []
        return tuple(str(x) for x in vals)
    return tuple()
