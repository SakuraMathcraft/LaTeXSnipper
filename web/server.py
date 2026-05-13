# coding: utf-8
"""
LaTeXSnipper / MathCraft OCR Web Server
========================================
FastAPI-based web service exposing math OCR as REST endpoints.
Deployable on any server with Python 3.10+.

Usage:
    # Install deps
    pip install -r web/requirements.txt
    pip install -e .              # install mathcraft_ocr in editable mode

    # Run server (port defaults to 8000, or use PORT env / --port flag)
    python web/server.py
    python web/server.py --port 8080
    PORT=9000 python web/server.py

    # Or with uvicorn directly
    python -m uvicorn web.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Ensure the project root is on sys.path for mathcraft_ocr imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mathcraft_ocr.runtime import MathCraftRuntime
from mathcraft_ocr.serialization import (
    doctor_report_to_json,
    formula_result_to_json,
    mixed_result_to_json,
    warmup_plan_to_json,
)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MathCraft OCR Server",
    description="REST API for math OCR: formula / text / mixed recognition",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for the web frontend
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# Global runtime (lazy init + warmup)
# ---------------------------------------------------------------------------

_runtime: Optional[MathCraftRuntime] = None


def _get_runtime() -> MathCraftRuntime:
    global _runtime
    if _runtime is None:
        _runtime = MathCraftRuntime(provider_preference="cpu")
    return _runtime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _read_image_bytes(upload: UploadFile) -> bytes:
    """Read uploaded image into raw bytes."""
    contents = await upload.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty upload")
    return contents


def _image_to_data_uri(image_bytes: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the web frontend."""
    index_path = _STATIC_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>MathCraft OCR Server</h1><p>Frontend not found.</p>")


# ---------------------------------------------------------------------------
# Health / diagnostics
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Lightweight health check."""
    return {"status": "ok"}


@app.get("/api/doctor")
async def doctor():
    """Full diagnostic report (models, providers, cache status)."""
    runtime = _get_runtime()
    report = runtime.doctor()
    return JSONResponse(doctor_report_to_json(report))


# ---------------------------------------------------------------------------
# Warmup (pre-load models)
# ---------------------------------------------------------------------------

@app.post("/api/warmup")
async def warmup(profile: str = "mixed"):
    """Pre-load and validate models for a given profile."""
    runtime = _get_runtime()
    try:
        plan = runtime.warmup(profile=profile)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(warmup_plan_to_json(plan))


# ---------------------------------------------------------------------------
# OCR endpoints
# ---------------------------------------------------------------------------

@app.post("/api/ocr/formula")
async def ocr_formula(
    image: UploadFile = File(...),
    max_new_tokens: int = 256,
):
    """Recognize a single formula from an image."""
    runtime = _get_runtime()
    image_bytes = await _read_image_bytes(image)
    try:
        result = runtime.recognize_formula(image_bytes, max_new_tokens=max_new_tokens)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(formula_result_to_json(result))


@app.post("/api/ocr/text")
async def ocr_text(
    image: UploadFile = File(...),
    min_text_score: float = 0.45,
):
    """Recognize plain text (lines + blocks) from an image."""
    runtime = _get_runtime()
    image_bytes = await _read_image_bytes(image)
    try:
        result = runtime.recognize_text(image_bytes, min_text_score=min_text_score)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(mixed_result_to_json(result))


@app.post("/api/ocr/mixed")
async def ocr_mixed(
    image: UploadFile = File(...),
    min_text_score: float = 0.45,
):
    """Recognize mixed formula + text content from an image."""
    runtime = _get_runtime()
    image_bytes = await _read_image_bytes(image)
    try:
        result = runtime.recognize_mixed(image_bytes, min_text_score=min_text_score)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(mixed_result_to_json(result))


# ---------------------------------------------------------------------------
# Convenience: single endpoint that auto-detects (delegates to mixed)
# ---------------------------------------------------------------------------

@app.post("/api/ocr")
async def ocr_auto(
    image: UploadFile = File(...),
    min_text_score: float = 0.45,
):
    """Auto-detect and recognize (formula + text) from an image."""
    return await ocr_mixed(image, min_text_score=min_text_score)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import os
    import uvicorn

    parser = argparse.ArgumentParser(description="MathCraft OCR Web Server")
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("PORT", 8000)),
        help="Port to listen on (default: 8000, or $PORT env var)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host to bind (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    uvicorn.run(
        "web.server:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
