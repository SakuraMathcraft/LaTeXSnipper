
from PyQt6.QtCore import QObject, pyqtSignal

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
from pathlib import Path

from PIL import Image

from backend.torch_runtime import infer_main_python, inject_shared_torch_env, python_site_packages

os.environ.setdefault("ORT_DISABLE_AZURE", "1")


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def get_deps_python() -> str:
    pyexe = os.environ.get("LATEXSNIPPER_PYEXE", "")
    if pyexe and os.path.exists(pyexe):
        return pyexe
    if getattr(sys, "frozen", False):
        print("[WARN] packaged mode: deps python not configured, fallback to current runtime")
    return sys.executable


def get_pix2text_python() -> str:
    pyexe = os.environ.get("PIX2TEXT_PYEXE", "")
    if pyexe and os.path.exists(pyexe):
        return pyexe
    return get_deps_python()


def _extract_json(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    for line in reversed(raw.splitlines()):
        s = line.strip()
        if not s:
            continue
        if s.startswith("{") and s.endswith("}"):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


class ModelWrapper(QObject):
    """v1.05: pix2text-only model wrapper."""

    status_signal = pyqtSignal(str)

    def __init__(self, default_model: str | None = None):
        super().__init__()
        self.device = "cpu"
        self.torch = None

        self._default_model = (default_model or "pix2text").lower()
        if not self._default_model.startswith("pix2text"):
            self._default_model = "pix2text"

        self._is_frozen = bool(getattr(sys, "frozen", False))
        self._pix2text_import_failed = False
        self._pix2text_subprocess_ready = False
        self._pix2text_worker = None
        self._pix2text_worker_lock = threading.Lock()

        self._ort_gpu_available = None
        self._ort_probe_raw = ""
        self.last_used_model = None

        if self._is_frozen:
            self._emit("[INFO] packaged mode: pix2text runs in subprocess")
        else:
            self._init_torch()

        self._probe_onnxruntime()
        self._lazy_load_pix2text()

    def _emit(self, msg: str) -> None:
        try:
            print(msg)
        except Exception:
            pass
        try:
            self.status_signal.emit(msg)
        except Exception:
            pass

    def _discover_shared_torch_site(self) -> str:
        for cand in (
            os.environ.get("PIX2TEXT_SHARED_TORCH_SITE", ""),
            os.environ.get("LATEXSNIPPER_SHARED_TORCH_SITE", ""),
        ):
            site = (cand or "").strip()
            if site and os.path.isdir(site):
                return site

        try:
            main_site = python_site_packages(infer_main_python())
            if main_site and (main_site / "torch").exists():
                return str(main_site)
        except Exception:
            pass

        try:
            deps_site = python_site_packages(get_deps_python())
            if deps_site and (deps_site / "torch").exists():
                return str(deps_site)
        except Exception:
            pass

        try:
            base = (os.environ.get("LATEXSNIPPER_INSTALL_BASE_DIR", "") or "").strip()
            if base:
                c = Path(base) / "python311" / "Lib" / "site-packages"
                if c.exists() and (c / "torch").exists():
                    return str(c)
        except Exception:
            pass

        try:
            app_dir = Path(__file__).resolve().parent.parent
            c = app_dir / "deps" / "python311" / "Lib" / "site-packages"
            if c.exists() and (c / "torch").exists():
                return str(c)
        except Exception:
            pass

        return ""

    def _build_subprocess_env(self) -> dict:
        env = os.environ.copy()
        for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE"):
            env.pop(k, None)
        env["PYTHONNOUSERSITE"] = "1"

        shared_site = self._discover_shared_torch_site()
        env = inject_shared_torch_env(env, shared_site)
        if shared_site:
            env["PIX2TEXT_SHARED_TORCH_SITE"] = shared_site
        else:
            env.pop("PIX2TEXT_SHARED_TORCH_SITE", None)
        env.pop("LATEXSNIPPER_SHARED_TORCH_SITE", None)
        return env

    def is_ready(self) -> bool:
        return self.is_pix2text_ready()

    def is_pix2text_ready(self) -> bool:
        return bool(self._pix2text_subprocess_ready)

    def is_model_ready(self, model_name: str) -> bool:
        return self.is_pix2text_ready() if (model_name or "").startswith("pix2text") else False

    def get_error(self) -> str | None:
        if self._pix2text_import_failed:
            return "pix2text not ready"
        return None

    def get_status_text(self) -> str:
        if self._pix2text_import_failed:
            return "model load failed: pix2text not ready"
        if self._pix2text_subprocess_ready:
            return f"model ready (device={self.device})"
        return "model not loaded"

    def _init_torch(self) -> None:
        try:
            import torch

            self.torch = torch
            if torch.cuda.is_available():
                self.device = "cuda"
                self._emit(f"[INFO] device: cuda:0 (name={torch.cuda.get_device_name(0)})")
            else:
                self.device = "cpu"
                self._emit("[INFO] device: cpu")
        except Exception as e:
            self.device = "cpu"
            self._emit(f"[WARN] torch import failed, fallback cpu: {e}")

    def _probe_onnxruntime(self) -> None:
        probe_code = textwrap.dedent(
            r"""
            import json
            out = {"ok": False}
            try:
                import onnxruntime as ort
                out["ok"] = True
                out["providers"] = ort.get_available_providers()
                out["ver"] = ort.__version__
            except Exception as e:
                out["err"] = f"{e.__class__.__name__}: {e}"
            print(json.dumps(out))
            """
        ).strip()
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", probe_code],
                capture_output=True,
                timeout=10,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_subprocess_creationflags(),
            )
            raw_out = (proc.stdout or "").strip()
            raw_err = (proc.stderr or "").strip()
            self._ort_probe_raw = f"STDOUT={raw_out} STDERR={raw_err}"
        except Exception as e:
            self._emit(f"[WARN] onnxruntime probe launch failed: {e}")
            return

        info = _extract_json(raw_out)
        if not info:
            self._emit(f"[WARN] onnxruntime probe returned no JSON: {self._ort_probe_raw[:300]}")
            return
        if not info.get("ok"):
            self._emit(f"[WARN] onnxruntime probe failed: {info.get('err', '<unknown>')}")
            return

        providers = info.get("providers", [])
        self._ort_gpu_available = "CUDAExecutionProvider" in providers
        self._emit(f"[INFO] onnxruntime providers detected: {providers}")

    def _stop_pix2text_worker(self):
        proc = getattr(self, "_pix2text_worker", None)
        self._pix2text_worker = None
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.write("__quit__\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
    def _pix2text_worker_code(self) -> str:
        return textwrap.dedent(
            r"""
            import json
            import os
            import sys
            from PIL import Image

            def _bootstrap_shared_torch():
                _shared_site = (
                    os.environ.get("PIX2TEXT_SHARED_TORCH_SITE", "")
                    or os.environ.get("LATEXSNIPPER_SHARED_TORCH_SITE", "")
                    or ""
                ).strip()
                if not (_shared_site and os.path.isdir(_shared_site)):
                    return
                _added = False
                try:
                    if _shared_site not in sys.path:
                        sys.path.insert(0, _shared_site)
                        _added = True
                except Exception:
                    pass
                try:
                    _torch_lib = os.path.join(_shared_site, "torch", "lib")
                    if os.path.isdir(_torch_lib):
                        if hasattr(os, "add_dll_directory"):
                            os.add_dll_directory(_torch_lib)
                        os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass
                try:
                    try:
                        import torch  # noqa: F401
                    except Exception:
                        pass
                    try:
                        import torchvision  # noqa: F401
                    except Exception:
                        pass
                    try:
                        import torchaudio  # noqa: F401
                    except Exception:
                        pass
                except Exception:
                    pass
                finally:
                    if _added:
                        try:
                            sys.path.remove(_shared_site)
                        except Exception:
                            pass

            def _pick_device():
                try:
                    import torch
                    torch_cuda = bool(torch.cuda.is_available())
                except Exception:
                    torch_cuda = False
                try:
                    import onnxruntime as ort
                    ort_cuda = "CUDAExecutionProvider" in (ort.get_available_providers() or [])
                except Exception:
                    ort_cuda = False
                return "cuda" if (torch_cuda and ort_cuda) else "cpu"

            def _build_p2t(dev, enable_table=False):
                from pix2text import Pix2Text
                stable_cfg = {
                    "layout": {"model_type": "DocYoloLayoutParser"},
                    "text_formula": {
                        "formula": {"model_name": "mfr", "model_backend": "onnx"}
                    },
                }
                try:
                    return Pix2Text.from_config(total_configs=stable_cfg, device=dev, enable_table=enable_table)
                except Exception:
                    try:
                        return Pix2Text.from_config(device=dev, enable_table=enable_table)
                    except Exception:
                        return Pix2Text(device=dev, enable_table=enable_table)

            def _as_text(obj):
                if isinstance(obj, str):
                    return obj.strip()
                if isinstance(obj, dict):
                    return str(obj.get("html") or obj.get("text") or obj)
                if isinstance(obj, list):
                    out = []
                    for item in obj:
                        if isinstance(item, dict):
                            out.append(str(item.get("text", item)))
                        else:
                            out.append(str(item))
                    return " ".join(x.strip() for x in out if str(x).strip())
                return str(obj)

            def _run_mode(model_main, model_table, img, mode):
                if mode == "formula":
                    return _as_text(model_main.recognize_formula(img))
                if mode == "text":
                    return _as_text(model_main.recognize_text(img))
                if mode == "mixed":
                    return _as_text(model_main.recognize(img))
                if mode == "page":
                    return _as_text(model_main.recognize_page(img))
                if mode == "table":
                    m = model_table if model_table is not None else model_main
                    table_ocr = getattr(m, "table_ocr", None)
                    if callable(table_ocr):
                        return _as_text(table_ocr(img))
                    if hasattr(table_ocr, "recognize") and callable(table_ocr.recognize):
                        return _as_text(table_ocr.recognize(img))
                    if hasattr(table_ocr, "ocr") and callable(table_ocr.ocr):
                        return _as_text(table_ocr.ocr(img))
                    return _as_text(m.recognize(img))
                return _as_text(model_main.recognize_formula(img))

            _bootstrap_shared_torch()

            model = None
            model_table = None
            try:
                import warnings
                warnings.filterwarnings("ignore")
                device = _pick_device()
                model = _build_p2t(device, enable_table=False)
                print(json.dumps({"ready": True, "ok": True, "device": device}), flush=True)
            except Exception as e:
                print(json.dumps({"ready": True, "ok": False, "error": str(e)}), flush=True)

            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                if line == "__quit__":
                    break

                try:
                    req = json.loads(line)
                except Exception:
                    req = {"image": line, "mode": "formula"}

                if req.get("ping"):
                    print(json.dumps({"ok": True, "ready": True}), flush=True)
                    continue

                img_path = req.get("image", "")
                mode = req.get("mode", "formula")
                if not img_path:
                    print(json.dumps({"ok": False, "error": "image path missing"}), flush=True)
                    continue
                if model is None:
                    print(json.dumps({"ok": False, "error": "pix2text not ready"}), flush=True)
                    continue

                try:
                    img = Image.open(img_path)
                except Exception as e:
                    print(json.dumps({"ok": False, "error": f"open image failed: {e}"}), flush=True)
                    continue

                try:
                    if mode == "table" and model_table is None:
                        model_table = _build_p2t(_pick_device(), enable_table=True)
                    result = _run_mode(model, model_table, img, mode)
                    print(json.dumps({"ok": True, "result": result}), flush=True)
                except Exception as e:
                    print(json.dumps({"ok": False, "error": str(e)}), flush=True)
            """
        ).strip()

    def _ensure_pix2text_worker(self) -> bool:
        try:
            proc = self._pix2text_worker
            if proc and proc.poll() is None:
                return True
        except Exception:
            proc = None

        with self._pix2text_worker_lock:
            try:
                proc = self._pix2text_worker
                if proc and proc.poll() is None:
                    return True
            except Exception:
                proc = None

            try:
                deps_python = get_pix2text_python()
                proc = subprocess.Popen(
                    [deps_python, "-u", "-c", self._pix2text_worker_code()],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=self._build_subprocess_env(),
                    creationflags=_subprocess_creationflags(),
                )
                self._pix2text_worker = proc
                return True
            except Exception as e:
                self._emit(f"[ERROR] pix2text worker start failed: {e}")
                self._pix2text_worker = None
                return False

    def _run_pix2text_worker(self, img_path: str, mode: str) -> str:
        proc = self._pix2text_worker
        if not proc or proc.poll() is not None:
            raise RuntimeError("pix2text worker not running")

        try:
            proc.stdin.write(json.dumps({"image": img_path, "mode": mode}) + "\n")
            proc.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"pix2text worker send failed: {e}")

        for _ in range(300):
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            data = _extract_json(line)
            if not data:
                continue
            if data.get("ready") and not data.get("result") and not data.get("error"):
                continue
            if data.get("ok"):
                self._pix2text_subprocess_ready = True
                return str(data.get("result", ""))
            raise RuntimeError(data.get("error", "pix2text error"))

        raise RuntimeError("pix2text worker no output")
    def _pix2text_oneshot_code(self) -> str:
        return textwrap.dedent(
            r"""
            import json
            import os
            import sys
            from PIL import Image

            def _bootstrap_shared_torch():
                _shared_site = (
                    os.environ.get("PIX2TEXT_SHARED_TORCH_SITE", "")
                    or os.environ.get("LATEXSNIPPER_SHARED_TORCH_SITE", "")
                    or ""
                ).strip()
                if not (_shared_site and os.path.isdir(_shared_site)):
                    return
                _added = False
                try:
                    if _shared_site not in sys.path:
                        sys.path.insert(0, _shared_site)
                        _added = True
                except Exception:
                    pass
                try:
                    _torch_lib = os.path.join(_shared_site, "torch", "lib")
                    if os.path.isdir(_torch_lib):
                        if hasattr(os, "add_dll_directory"):
                            os.add_dll_directory(_torch_lib)
                        os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass
                try:
                    try:
                        import torch  # noqa: F401
                    except Exception:
                        pass
                    try:
                        import torchvision  # noqa: F401
                    except Exception:
                        pass
                    try:
                        import torchaudio  # noqa: F401
                    except Exception:
                        pass
                except Exception:
                    pass
                finally:
                    if _added:
                        try:
                            sys.path.remove(_shared_site)
                        except Exception:
                            pass

            def _pick_device():
                try:
                    import torch
                    torch_cuda = bool(torch.cuda.is_available())
                except Exception:
                    torch_cuda = False
                try:
                    import onnxruntime as ort
                    ort_cuda = "CUDAExecutionProvider" in (ort.get_available_providers() or [])
                except Exception:
                    ort_cuda = False
                return "cuda" if (torch_cuda and ort_cuda) else "cpu"

            def _build_p2t(dev, enable_table=False):
                from pix2text import Pix2Text
                stable_cfg = {
                    "layout": {"model_type": "DocYoloLayoutParser"},
                    "text_formula": {
                        "formula": {"model_name": "mfr", "model_backend": "onnx"}
                    },
                }
                try:
                    return Pix2Text.from_config(total_configs=stable_cfg, device=dev, enable_table=enable_table)
                except Exception:
                    try:
                        return Pix2Text.from_config(device=dev, enable_table=enable_table)
                    except Exception:
                        return Pix2Text(device=dev, enable_table=enable_table)

            def _as_text(obj):
                if isinstance(obj, str):
                    return obj.strip()
                if isinstance(obj, dict):
                    return str(obj.get("html") or obj.get("text") or obj)
                if isinstance(obj, list):
                    out = []
                    for item in obj:
                        if isinstance(item, dict):
                            out.append(str(item.get("text", item)))
                        else:
                            out.append(str(item))
                    return " ".join(x.strip() for x in out if str(x).strip())
                return str(obj)

            _bootstrap_shared_torch()

            img_path = sys.argv[1]
            mode = sys.argv[2] if len(sys.argv) > 2 else "formula"
            try:
                import warnings
                warnings.filterwarnings("ignore")
                dev = _pick_device()
                p2t = _build_p2t(dev, enable_table=(mode == "table"))
                img = Image.open(img_path)

                if mode == "formula":
                    result = p2t.recognize_formula(img)
                elif mode == "text":
                    result = p2t.recognize_text(img)
                elif mode == "mixed":
                    result = p2t.recognize(img)
                elif mode == "page":
                    result = p2t.recognize_page(img)
                elif mode == "table":
                    table_ocr = getattr(p2t, "table_ocr", None)
                    if callable(table_ocr):
                        result = table_ocr(img)
                    elif hasattr(table_ocr, "recognize") and callable(table_ocr.recognize):
                        result = table_ocr.recognize(img)
                    elif hasattr(table_ocr, "ocr") and callable(table_ocr.ocr):
                        result = table_ocr.ocr(img)
                    else:
                        result = p2t.recognize(img)
                else:
                    result = p2t.recognize_formula(img)

                print(json.dumps({"ok": True, "result": _as_text(result)}))
            except Exception as e:
                print(json.dumps({"ok": False, "error": str(e)}))
            """
        ).strip()

    def _run_pix2text_subprocess(self, pil_img: Image.Image, mode: str = "formula") -> str:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            pil_img.save(tmp, format="PNG")

        worker_enabled = mode not in ("table",)
        if worker_enabled:
            try:
                if self._ensure_pix2text_worker():
                    result = self._run_pix2text_worker(tmp_path, mode)
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
                    return result
            except Exception as e:
                self._emit(f"[WARN] pix2text worker fallback: {e}")
                self._stop_pix2text_worker()
        else:
            try:
                print("[INFO] pix2text table mode: use one-shot subprocess (timeout protected)", flush=True)
            except Exception:
                pass

        try:
            deps_python = get_pix2text_python()
            timeout = 300 if mode in ("page", "table") else 120
            proc = subprocess.run(
                [deps_python, "-c", self._pix2text_oneshot_code(), tmp_path, mode],
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_subprocess_env(),
                creationflags=_subprocess_creationflags(),
            )
            output = (proc.stdout or "").strip()
            if not output:
                raise RuntimeError(f"subprocess no output: stderr={(proc.stderr or '')[:200]}")
            result = _extract_json(output)
            if result and result.get("ok"):
                self._pix2text_subprocess_ready = True
                return str(result.get("result", ""))
            if result:
                raise RuntimeError(result.get("error", "pix2text error"))
            raise RuntimeError(f"subprocess no json: {output[:200]}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("pix2text timeout")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _is_missing_onnx_pair_error(self, msg: str) -> bool:
        s = (msg or "").strip().lower()
        if not s:
            return False
        if "could not find any onnx model file" not in s:
            return False
        if ".onnx" not in s:
            return False
        return ("encoder" in s) or ("decoder" in s)

    def _cleanup_broken_pix2text_onnx_cache(self, deps_python: str) -> tuple[bool, str, int, str]:
        cleanup_code = textwrap.dedent(
            r"""
            import json
            import shutil
            from pathlib import Path
            out = {"ok": False, "root": "", "removed": []}
            try:
                from pix2text.utils import data_dir
                from pix2text.consts import MODEL_VERSION
                root = Path(data_dir()) / str(MODEL_VERSION)
                out["root"] = str(root)
                if root.exists():
                    for d in root.iterdir():
                        if not d.is_dir():
                            continue
                        name = d.name.lower()
                        if ("mfr" not in name) or ("onnx" not in name):
                            continue
                        enc = d / "encoder_model.onnx"
                        dec = d / "decoder_model.onnx"
                        if enc.exists() ^ dec.exists():
                            shutil.rmtree(d, ignore_errors=True)
                            out["removed"].append(str(d))
                out["ok"] = True
            except Exception as e:
                out["error"] = str(e)
            print(json.dumps(out, ensure_ascii=False))
            """
        ).strip()
        try:
            proc = subprocess.run(
                [deps_python, "-c", cleanup_code],
                capture_output=True,
                timeout=120,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_subprocess_env(),
                creationflags=_subprocess_creationflags(),
            )
            raw = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
            obj = _extract_json(raw) or {}
            ok = bool(obj.get("ok"))
            root = str(obj.get("root", "") or "")
            removed = int(len(obj.get("removed") or []))
            err = str(obj.get("error", "") or "").strip()
            if not ok and not err and raw:
                err = raw[:260]
            return ok, root, removed, err
        except Exception as e:
            return False, "", 0, str(e)

    def _probe_and_bootstrap_pix2text(
        self, deps_python: str, probe_code: str, bootstrap_code: str
    ) -> tuple[bool, str, str]:
        probe_result = None
        probe_output = ""
        try:
            proc = subprocess.run(
                [deps_python, "-c", probe_code],
                capture_output=True,
                timeout=120,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_subprocess_env(),
                creationflags=_subprocess_creationflags(),
            )
            probe_output = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
            probe_result = _extract_json(probe_output)
        except subprocess.TimeoutExpired:
            self._emit("[WARN] pix2text probe timeout (>120s), fallback to bootstrap")

        if probe_result and probe_result.get("ok"):
            ver = (probe_result or {}).get("ver", "") or "unknown"
            self._emit(f"[INFO] pix2text probe ok (ver={ver})")
            return True, str(ver), ""

        probe_err = ""
        if isinstance(probe_result, dict):
            probe_err = str(probe_result.get("error", "") or "").strip()
        if not probe_err and probe_output:
            probe_err = probe_output[:220]
        if probe_err:
            self._emit(f"[WARN] pix2text probe failed detail: {probe_err}")
        self._emit("[WARN] pix2text probe failed, trying bootstrap init...")

        proc = subprocess.run(
            [deps_python, "-c", bootstrap_code],
            capture_output=True,
            timeout=900,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self._build_subprocess_env(),
            creationflags=_subprocess_creationflags(),
        )
        boot_out = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
        boot_result = _extract_json(boot_out)
        if not (boot_result and boot_result.get("ok")):
            err = (boot_result or {}).get("error") or (boot_out[:220] if boot_out else "unknown")
            self._emit(f"[WARN] pix2text bootstrap failed: {err}")
            return False, "", str(err)

        ver = (boot_result or {}).get("ver", "") or "unknown"
        self._emit(f"[INFO] pix2text bootstrap success (ver={ver})")
        return True, str(ver), str(probe_err or "")

    def _lazy_load_pix2text(self):
        if self._pix2text_subprocess_ready or self._pix2text_import_failed:
            return self._pix2text_subprocess_ready

        try:
            dbg_env = self._build_subprocess_env()
            dbg_site = (
                dbg_env.get("PIX2TEXT_SHARED_TORCH_SITE", "")
                or dbg_env.get("LATEXSNIPPER_SHARED_TORCH_SITE", "")
                or ""
            ).strip()
            self._emit(f"[DEBUG] pix2text shared torch site: {dbg_site or '<empty>'}")
        except Exception:
            pass

        deps_python = get_pix2text_python()
        probe_code = textwrap.dedent(
            r"""
            import json, os, sys
            from importlib import metadata as _md
            def _bootstrap_shared_torch():
                _shared_site = (os.environ.get("PIX2TEXT_SHARED_TORCH_SITE", "") or os.environ.get("LATEXSNIPPER_SHARED_TORCH_SITE", "") or "").strip()
                if not (_shared_site and os.path.isdir(_shared_site)):
                    return
                _added = False
                try:
                    if _shared_site not in sys.path:
                        sys.path.insert(0, _shared_site)
                        _added = True
                except Exception:
                    pass
                try:
                    _torch_lib = os.path.join(_shared_site, "torch", "lib")
                    if os.path.isdir(_torch_lib):
                        if hasattr(os, "add_dll_directory"):
                            os.add_dll_directory(_torch_lib)
                        os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass
                try:
                    import torch, torchvision  # noqa: F401
                except Exception:
                    pass
                finally:
                    if _added:
                        try:
                            sys.path.remove(_shared_site)
                        except Exception:
                            pass
            _bootstrap_shared_torch()
            try:
                import pix2text
                from pix2text import Pix2Text
                try:
                    ver = _md.version("pix2text")
                except Exception:
                    ver = str(getattr(pix2text, "__version__", ""))
                stable_cfg = {"layout": {"model_type": "DocYoloLayoutParser"}, "text_formula": {"formula": {"model_name": "mfr", "model_backend": "onnx"}}}
                Pix2Text.from_config(total_configs=stable_cfg, device="cpu", enable_table=False)
                print(json.dumps({"ok": True, "ver": ver}))
            except Exception as e:
                print(json.dumps({"ok": False, "error": str(e)}))
            """
        ).strip()

        bootstrap_code = textwrap.dedent(
            r"""
            import json
            from importlib import metadata as _md
            import pix2text
            from pix2text import Pix2Text
            stable_cfg = {"layout": {"model_type": "DocYoloLayoutParser"}, "text_formula": {"formula": {"model_name": "mfr", "model_backend": "onnx"}}}
            try:
                try:
                    ver = _md.version("pix2text")
                except Exception:
                    ver = str(getattr(pix2text, "__version__", ""))
                Pix2Text.from_config(total_configs=stable_cfg, device="cpu", enable_table=False)
                print(json.dumps({"ok": True, "ver": ver}))
            except Exception as e:
                print(json.dumps({"ok": False, "error": str(e)}))
            """
        ).strip()

        try:
            ok, ver, fail_detail = self._probe_and_bootstrap_pix2text(
                deps_python, probe_code, bootstrap_code
            )

            if (not ok) and self._is_missing_onnx_pair_error(fail_detail):
                self._emit(
                    "[WARN] pix2text ONNX cache looks broken (missing encoder/decoder), "
                    "auto-clean and retry once..."
                )
                c_ok, c_root, c_removed, c_err = self._cleanup_broken_pix2text_onnx_cache(deps_python)
                if c_ok:
                    if c_removed > 0:
                        self._emit(
                            f"[INFO] pix2text cache cleanup removed {c_removed} broken dir(s)"
                            f"{f' under {c_root}' if c_root else ''}"
                        )
                    else:
                        self._emit(
                            f"[WARN] pix2text cache cleanup finished but no broken dir found"
                            f"{f' under {c_root}' if c_root else ''}"
                        )
                    ok, ver, fail_detail = self._probe_and_bootstrap_pix2text(
                        deps_python, probe_code, bootstrap_code
                    )
                else:
                    self._emit(f"[WARN] pix2text cache cleanup failed: {c_err or 'unknown'}")

            if not ok:
                self._pix2text_import_failed = True
                return False

            worker_ready = bool(self._ensure_pix2text_worker())
            if not worker_ready:
                self._emit("[WARN] pix2text worker not ready after probe/bootstrap")
                self._pix2text_subprocess_ready = False
                self._pix2text_import_failed = True
                return False
            try:
                worker_pid = getattr(getattr(self, "_pix2text_worker", None), "pid", None)
                self._emit(
                    f"[INFO] pix2text resident worker ready"
                    f"{f' (pid={worker_pid})' if worker_pid else ''}"
                )
            except Exception:
                self._emit("[INFO] pix2text resident worker ready")

            self._pix2text_subprocess_ready = True
            self._pix2text_import_failed = False
            return True
        except Exception as e:
            self._emit(f"[WARN] pix2text lazy load exception: {e}")
            self._pix2text_import_failed = True
            return False

    def predict(self, pil_img: Image.Image, model_name: str = "pix2text") -> str:
        model = (model_name or "pix2text").lower()
        mode_map = {
            "pix2text": "formula",
            "pix2text_text": "text",
            "pix2text_mixed": "mixed",
            "pix2text_page": "page",
            "pix2text_table": "table",
        }
        if not model.startswith("pix2text"):
            model = "pix2text"
        mode = mode_map.get(model, "formula")

        if not self._pix2text_subprocess_ready:
            self._lazy_load_pix2text()
        if not self._pix2text_subprocess_ready:
            raise RuntimeError("pix2text not ready")

        self.last_used_model = model
        return self._run_pix2text_subprocess(pil_img, mode=mode)
