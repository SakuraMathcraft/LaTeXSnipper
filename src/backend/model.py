
try:
    from PyQt6.QtCore import QObject, pyqtSignal
except Exception:
    class _Signal:
        def __init__(self):
            self._handlers = []

        def connect(self, fn):
            if callable(fn) and fn not in self._handlers:
                self._handlers.append(fn)

        def emit(self, *args, **kwargs):
            for fn in list(self._handlers):
                try:
                    fn(*args, **kwargs)
                except Exception:
                    pass

    class _SignalDescriptor:
        def __set_name__(self, _owner, name):
            self._name = f"__sig_{name}"

        def __get__(self, instance, _owner):
            if instance is None:
                return self
            sig = instance.__dict__.get(self._name)
            if sig is None:
                sig = _Signal()
                instance.__dict__[self._name] = sig
            return sig

    def pyqtSignal(*_args, **_kwargs):
        return _SignalDescriptor()

    class QObject:
        def __init__(self, *args, **kwargs):
            super().__init__()

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading

from PIL import Image

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


def _pix2text_runtime_compat_code() -> str:
    return textwrap.dedent(
        r"""
        def _patch_onnxruntime_cpu_only():
            import os
            if os.environ.get("LATEXSNIPPER_FORCE_ORT_CPU", "") != "1":
                return
            try:
                import onnxruntime as _ort
            except Exception:
                return
            try:
                _orig_gap = _ort.get_available_providers
                if not getattr(_orig_gap, "_latexsnipper_force_cpu_patch", False):
                    def _cpu_only_providers():
                        try:
                            providers = list(_orig_gap() or [])
                        except Exception:
                            providers = []
                        if "CPUExecutionProvider" in providers:
                            return ["CPUExecutionProvider"]
                        return providers or ["CPUExecutionProvider"]

                    _cpu_only_providers._latexsnipper_force_cpu_patch = True
                    _ort.get_available_providers = _cpu_only_providers
            except Exception:
                pass
            try:
                _orig_gd = _ort.get_device
                if not getattr(_orig_gd, "_latexsnipper_force_cpu_patch", False):
                    def _cpu_only_device():
                        return "CPU"

                    _cpu_only_device._latexsnipper_force_cpu_patch = True
                    _ort.get_device = _cpu_only_device
            except Exception:
                pass

        def _patch_rapidocr_model_root_dir():
            try:
                from pathlib import Path
                from rapidocr.inference_engine.onnxruntime import main as _rapidocr_ort_main
            except Exception:
                return
            try:
                _orig_init = _rapidocr_ort_main.OrtInferSession.__init__
                if getattr(_orig_init, "_latexsnipper_model_root_dir_patch", False):
                    return
            except Exception:
                return

            def _patched_init(self, cfg):
                try:
                    if cfg.get("model_root_dir") is None:
                        _model_path = cfg.get("model_path")
                        if _model_path:
                            cfg["model_root_dir"] = str(Path(_model_path).expanduser().resolve().parent)
                except Exception:
                    try:
                        _model_path = cfg.get("model_path")
                        if _model_path:
                            cfg["model_root_dir"] = str(Path(_model_path).parent)
                    except Exception:
                        pass
                return _orig_init(self, cfg)

            _patched_init._latexsnipper_model_root_dir_patch = True
            _rapidocr_ort_main.OrtInferSession.__init__ = _patched_init

        _patch_onnxruntime_cpu_only()
        _patch_rapidocr_model_root_dir()
        """
    ).strip()


def classify_pix2text_failure(detail: str) -> dict[str, str]:
    raw = str(detail or "").strip()
    lower = raw.lower()

    def _pack(code: str, title: str, user_message: str, log_message: str) -> dict[str, str]:
        return {
            "code": code,
            "title": title,
            "user_message": user_message,
            "log_message": log_message,
        }

    if not raw:
        return _pack(
            "UNKNOWN",
            "模型预热未完成",
            "pix2text 预热失败，请打开运行日志查看具体原因。",
            "未拿到明确异常文本，需结合上游日志继续排查。",
        )

    if "no module named" in lower and "pix2text" in lower:
        return _pack(
            "PIX2TEXT_MISSING",
            "缺少 pix2text",
            "未安装 pix2text 依赖，请先完成依赖向导中的 BASIC/CORE 安装。",
            "pix2text 模块未安装，当前环境无法启动识别模型。",
        )

    if "no module named" in lower and "onnxruntime" in lower:
        return _pack(
            "ONNXRUNTIME_MISSING",
            "缺少 onnxruntime",
            "未安装 onnxruntime 依赖，请重新校验依赖层是否安装完整。",
            "onnxruntime 模块缺失，pix2text 的 ONNX 后端不可用。",
        )

    if "no module named" in lower and "torch" in lower:
        return _pack(
            "TORCH_MISSING",
            "缺少 torch",
            "未安装 torch 依赖，请重新校验依赖层是否安装完整。",
            "torch 模块缺失，pix2text 无法初始化运行时。",
        )

    if "no module named" in lower and "cv2" in lower:
        return _pack(
            "OPENCV_MISSING",
            "缺少 opencv-python",
            "未安装 opencv-python 依赖，请在依赖向导中修复 CORE 层。",
            "cv2 模块缺失，pix2text/rapidocr 的图像预处理依赖不完整。",
        )

    if "onnxruntime_pybind11_state" in lower and ("拒绝访问" in raw or "access is denied" in lower):
        return _pack(
            "ORT_ACCESS_DENIED",
            "onnxruntime 被拦截",
            "onnxruntime DLL 被系统拒绝访问，疑似被杀毒软件/Defender 拦截或目录权限受限。",
            "onnxruntime DLL 加载被拒绝访问，优先检查杀毒软件隔离、Defender 和目录权限。",
        )

    if "cuda_path is set but cuda wasn't able to be loaded" in lower or "createexecutionproviderinstance" in lower:
        return _pack(
            "CUDA_RUNTIME_BROKEN",
            "CUDA 环境异常",
            "检测到 CUDA/cuDNN 环境异常，当前 GPU 推理不可用，请修复 CUDA 环境或改用 CPU。",
            "CUDAExecutionProvider 初始化失败，常见原因是 CUDA/cuDNN 版本不匹配或 PATH 配置错误。",
        )

    if ("c10.dll" in lower or "\\torch\\lib\\" in lower or "/torch/lib/" in lower) and (
        "winerror 1114" in lower or "dll load failed" in lower or "error loading" in lower
    ):
        return _pack(
            "TORCH_DLL_LOAD_FAILED",
            "Torch 运行库加载失败",
            "Torch 运行库加载失败，常见原因是 VC++ 运行库缺失、杀毒软件拦截或依赖安装不完整。",
            "torch DLL 加载失败，优先检查 Microsoft Visual C++ 2015-2022 x64、杀毒软件拦截和损坏安装。",
        )

    if "expected str, bytes or os.pathlike object, not nonetype" in lower:
        return _pack(
            "BROKEN_DEP_PATH",
            "依赖环境异常",
            "依赖环境路径异常或安装不完整，请重新校验依赖层，必要时删除损坏依赖后重装。",
            "运行时拿到了空路径对象，通常表示依赖环境不完整、路径注入失败或安装目录损坏。",
        )

    if "missing encoder" in lower or "missing decoder" in lower:
        return _pack(
            "BROKEN_ONNX_CACHE",
            "模型缓存损坏",
            "检测到 pix2text 模型缓存不完整，请重新下载模型或清理损坏缓存后重试。",
            "pix2text ONNX 缓存缺少 encoder/decoder 文件，属于不完整模型缓存。",
        )

    if "can not find available file in" in lower and "pix2text" in lower:
        return _pack(
            "BROKEN_MODEL_CACHE",
            "模型缓存不完整",
            "检测到 pix2text 模型目录不完整，请重新下载模型或清理损坏缓存后重试。",
            "pix2text 模型目录存在但缺少可用权重文件，通常由首次下载中断导致。",
        )

    if (
        ("does not exists" in lower or "can not find model file" in lower)
        and any(token in lower for token in ("rapidocr", "cnocr", "cnstd", "pp-ocr", "densenet_lite_136-gru"))
    ) or (
        "appdata" in lower
        and any(token in lower for token in ("\\cnocr\\", "\\cnstd\\", "/cnocr/", "/cnstd/"))
    ):
        return _pack(
            "BROKEN_OCR_MODEL_CACHE",
            "OCR 模型缓存不完整",
            "检测到 cnocr/cnstd/rapidocr 的模型目录不完整，请清理损坏缓存后重试。",
            "cnocr/cnstd/rapidocr 模型目录存在但缺少可用 ONNX 权重，通常由首次下载中断或文件被隔离导致。",
        )

    if ("table-rec" in lower or "pix2text-table-rec" in lower) and any(
        token in lower
        for token in (
            "config.json",
            "preprocessor_config.json",
            "model.safetensors",
            "pytorch_model.bin",
            "does not exist",
            "does not appear to have",
        )
    ):
        return _pack(
            "BROKEN_TABLE_MODEL_CACHE",
            "表格模型缓存不完整",
            "检测到表格识别模型目录不完整，请清理损坏缓存后重试。",
            "table-rec 模型目录存在但缺少可用配置或权重文件，通常由首次下载中断导致。",
        )

    if "timeout" in lower:
        return _pack(
            "WARMUP_TIMEOUT",
            "模型预热超时",
            "pix2text 首次预热超时，可能是网络过慢、模型下载未完成或环境响应异常。",
            "预热阶段超时，需继续排查网络、模型下载和运行时初始化耗时。",
        )

    return _pack(
        "UNKNOWN",
        "模型预热未完成",
        "pix2text 预热失败，请打开运行日志查看具体依赖错误。",
        f"未命中已知错误分类，原始错误: {raw[:300]}",
    )


class ModelWrapper(QObject):
    """v1.05: pix2text-only model wrapper."""

    status_signal = pyqtSignal(str)

    def __init__(self, default_model: str | None = None, auto_warmup: bool = True):
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
        self._last_pix2text_error = ""
        self._last_pix2text_error_code = ""
        self._force_ort_cpu_only = False

        if self._is_frozen:
            self._emit("[INFO] packaged mode: pix2text runs in subprocess")
        else:
            self._emit("[INFO] dev mode: pix2text runs in subprocess")

        self._probe_onnxruntime()
        if auto_warmup:
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

    def _build_subprocess_env(self) -> dict:
        env = os.environ.copy()
        for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE"):
            env.pop(k, None)
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PIX2TEXT_SHARED_TORCH_SITE", None)
        env.pop("LATEXSNIPPER_SHARED_TORCH_SITE", None)
        if self._force_ort_cpu_only:
            env["LATEXSNIPPER_FORCE_ORT_CPU"] = "1"
        else:
            env.pop("LATEXSNIPPER_FORCE_ORT_CPU", None)
        return env

    def is_ready(self) -> bool:
        return self.is_pix2text_ready()

    def is_pix2text_ready(self) -> bool:
        return bool(self._pix2text_subprocess_ready)

    def is_model_ready(self, model_name: str) -> bool:
        return self.is_pix2text_ready() if (model_name or "").startswith("pix2text") else False

    def get_error(self) -> str | None:
        if self._pix2text_import_failed:
            return self._last_pix2text_error or "pix2text not ready"
        return None

    def get_status_text(self) -> str:
        if self._pix2text_import_failed:
            return "model load failed: pix2text not ready"
        if self._pix2text_subprocess_ready:
            return f"model ready (device={self.device})"
        return "model not loaded"

    def _set_pix2text_error(self, detail: str) -> dict[str, str]:
        info = classify_pix2text_failure(detail)
        self._last_pix2text_error = str(info.get("user_message", "") or "").strip()
        self._last_pix2text_error_code = str(info.get("code", "") or "").strip()
        return info

    def _clear_pix2text_error(self) -> None:
        self._last_pix2text_error = ""
        self._last_pix2text_error_code = ""

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
            raw_err = str(info.get("err", "<unknown>") or "<unknown>")
            diag = classify_pix2text_failure(raw_err)
            self._emit(f"[WARN] onnxruntime probe failed [{diag['code']}]: {raw_err}")
            self._emit(f"[DIAG] {diag['log_message']}")
            return

        providers = info.get("providers", [])
        self._ort_gpu_available = "CUDAExecutionProvider" in providers
        self.device = "cuda" if self._ort_gpu_available else "cpu"
        self._emit(f"[INFO] device: {self.device}")
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
        return (
            textwrap.dedent(
                r"""
                import json
                import os
                import sys
                from PIL import Image

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

                """
            ).strip()
            + "\n\n"
            + _pix2text_runtime_compat_code()
            + "\n\n"
            + textwrap.dedent(
                r"""
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
        )

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
        return (
            textwrap.dedent(
                r"""
                import json
                import os
                import sys
                from PIL import Image

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

                """
            ).strip()
            + "\n\n"
            + _pix2text_runtime_compat_code()
            + "\n\n"
            + textwrap.dedent(
                r"""
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
        )

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
            if mode == "table":
                if not self._ensure_table_mode_runtime(deps_python):
                    raise RuntimeError("pix2text table model not ready")
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

    def _is_incomplete_pix2text_cache_error(self, msg: str) -> bool:
        s = (msg or "").strip().lower()
        if not s:
            return False
        if self._is_missing_onnx_pair_error(s):
            return True
        return "can not find available file in" in s

    def _is_incomplete_ocr_model_cache_error(self, msg: str) -> bool:
        info = classify_pix2text_failure(msg)
        return info.get("code") == "BROKEN_OCR_MODEL_CACHE"

    def _is_cuda_runtime_broken_error(self, msg: str) -> bool:
        info = classify_pix2text_failure(msg)
        return info.get("code") == "CUDA_RUNTIME_BROKEN"

    def _inspect_pix2text_model_cache(self, deps_python: str) -> dict[str, object]:
        inspect_code = textwrap.dedent(
            r"""
            import json
            from pathlib import Path
            out = {"ok": False, "root": "", "ready": False, "incomplete": False}
            try:
                from pix2text.utils import data_dir
                from pix2text.consts import MODEL_VERSION
                root = Path(data_dir()) / str(MODEL_VERSION)
                out["root"] = str(root)
                if not root.exists():
                    out["ok"] = True
                    print(json.dumps(out, ensure_ascii=False))
                    raise SystemExit

                mfr_dir = next((d for d in root.iterdir() if d.is_dir() and "mfr" in d.name.lower() and "onnx" in d.name.lower()), None)
                mfd_dir = next((d for d in root.iterdir() if d.is_dir() and "mfd" in d.name.lower() and "onnx" in d.name.lower()), None)
                layout_dir = next((d for d in root.iterdir() if d.is_dir() and "layout-docyolo" in d.name.lower()), None)

                mfr_ready = bool(
                    mfr_dir
                    and (mfr_dir / "encoder_model.onnx").exists()
                    and (mfr_dir / "decoder_model.onnx").exists()
                )
                mfd_ready = bool(mfd_dir and any((not p.is_dir()) and p.suffix.lower() == ".onnx" for p in mfd_dir.rglob("*")))
                layout_ready = bool(layout_dir and any((not p.is_dir()) and p.suffix.lower() == ".pt" for p in layout_dir.rglob("*")))

                dirs_present = bool(mfr_dir or mfd_dir or layout_dir)
                out["ready"] = bool(mfr_ready and mfd_ready and layout_ready)
                out["incomplete"] = bool(dirs_present and not out["ready"])
                out["ok"] = True
            except SystemExit:
                raise
            except Exception as e:
                out["error"] = str(e)
            print(json.dumps(out, ensure_ascii=False))
            """
        ).strip()
        try:
            proc = subprocess.run(
                [deps_python, "-c", inspect_code],
                capture_output=True,
                timeout=60,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_subprocess_env(),
                creationflags=_subprocess_creationflags(),
            )
            raw = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
            obj = _extract_json(raw) or {}
            if not obj:
                return {"ok": False, "root": "", "ready": False, "incomplete": False, "error": raw[:260]}
            obj.setdefault("root", "")
            obj.setdefault("ready", False)
            obj.setdefault("incomplete", False)
            return obj
        except Exception as e:
            return {"ok": False, "root": "", "ready": False, "incomplete": False, "error": str(e)}

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
                        remove = False
                        if ("mfr" in name) and ("onnx" in name):
                            enc = d / "encoder_model.onnx"
                            dec = d / "decoder_model.onnx"
                            remove = not (enc.exists() and dec.exists())
                        elif ("mfd" in name) and ("onnx" in name):
                            remove = not any((not p.is_dir()) and p.suffix.lower() == ".onnx" for p in d.rglob("*"))
                        elif "layout-docyolo" in name:
                            remove = not any((not p.is_dir()) and p.suffix.lower() == ".pt" for p in d.rglob("*"))
                        if remove:
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

    def _inspect_ocr_model_cache(self, deps_python: str) -> dict[str, object]:
        inspect_code = textwrap.dedent(
            r"""
            import json
            from pathlib import Path
            out = {"ok": False, "ready": True, "incomplete": False, "targets": []}
            try:
                from cnstd.utils import data_dir as cnstd_data_dir
                from cnstd.consts import MODEL_VERSION as CNSTD_MODEL_VERSION
                from cnocr.utils import data_dir as cnocr_data_dir
                from cnocr.consts import MODEL_VERSION as CNOCR_MODEL_VERSION

                targets = [
                    {
                        "name": "cnstd-det",
                        "root": str(Path(cnstd_data_dir()) / str(CNSTD_MODEL_VERSION) / "ppocr" / "ch_PP-OCRv5_det"),
                    },
                    {
                        "name": "cnocr-rec",
                        "root": str(Path(cnocr_data_dir()) / str(CNOCR_MODEL_VERSION) / "densenet_lite_136-gru"),
                    },
                ]

                def _has_onnx(root: Path) -> bool:
                    return any((not p.is_dir()) and p.suffix.lower() == ".onnx" for p in root.rglob("*"))

                results = []
                ready = True
                incomplete = False
                for item in targets:
                    root = Path(item["root"])
                    exists = root.exists()
                    has_onnx = _has_onnx(root) if exists else False
                    item["exists"] = exists
                    item["has_onnx"] = has_onnx
                    item["incomplete"] = bool(exists and not has_onnx)
                    results.append(item)
                    if item["incomplete"]:
                        incomplete = True
                        ready = False
                out["targets"] = results
                out["ready"] = ready
                out["incomplete"] = incomplete
                out["ok"] = True
            except Exception as e:
                out["error"] = str(e)
            print(json.dumps(out, ensure_ascii=False))
            """
        ).strip()
        try:
            proc = subprocess.run(
                [deps_python, "-c", inspect_code],
                capture_output=True,
                timeout=60,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_subprocess_env(),
                creationflags=_subprocess_creationflags(),
            )
            raw = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
            obj = _extract_json(raw) or {}
            if not obj:
                return {"ok": False, "ready": False, "incomplete": False, "targets": [], "error": raw[:260]}
            obj.setdefault("ready", False)
            obj.setdefault("incomplete", False)
            obj.setdefault("targets", [])
            return obj
        except Exception as e:
            return {"ok": False, "ready": False, "incomplete": False, "targets": [], "error": str(e)}

    def _cleanup_broken_ocr_model_cache(self, deps_python: str) -> tuple[bool, int, str]:
        cleanup_code = textwrap.dedent(
            r"""
            import json
            import shutil
            from pathlib import Path
            out = {"ok": False, "removed": []}
            try:
                from cnstd.utils import data_dir as cnstd_data_dir
                from cnstd.consts import MODEL_VERSION as CNSTD_MODEL_VERSION
                from cnocr.utils import data_dir as cnocr_data_dir
                from cnocr.consts import MODEL_VERSION as CNOCR_MODEL_VERSION

                targets = [
                    Path(cnstd_data_dir()) / str(CNSTD_MODEL_VERSION) / "ppocr" / "ch_PP-OCRv5_det",
                    Path(cnocr_data_dir()) / str(CNOCR_MODEL_VERSION) / "densenet_lite_136-gru",
                ]

                for root in targets:
                    if not root.exists():
                        continue
                    has_onnx = any((not p.is_dir()) and p.suffix.lower() == ".onnx" for p in root.rglob("*"))
                    if not has_onnx:
                        shutil.rmtree(root, ignore_errors=True)
                        out["removed"].append(str(root))
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
            removed = int(len(obj.get("removed") or []))
            err = str(obj.get("error", "") or "").strip()
            if not ok and not err and raw:
                err = raw[:260]
            return ok, removed, err
        except Exception as e:
            return False, 0, str(e)

    def _inspect_table_model_cache(self, deps_python: str) -> dict[str, object]:
        inspect_code = textwrap.dedent(
            r"""
            import json
            from pathlib import Path
            out = {"ok": False, "root": "", "ready": False, "incomplete": False}
            try:
                from pix2text.utils import data_dir
                from pix2text.consts import MODEL_VERSION
                root = Path(data_dir()) / str(MODEL_VERSION) / "table-rec"
                out["root"] = str(root)
                if not root.exists():
                    out["ok"] = True
                    print(json.dumps(out, ensure_ascii=False))
                    raise SystemExit

                has_config = (root / "config.json").exists()
                has_preprocessor = (root / "preprocessor_config.json").exists()
                has_weights = any(
                    (not p.is_dir()) and p.name.lower() in {"model.safetensors", "pytorch_model.bin"}
                    for p in root.rglob("*")
                ) or any((not p.is_dir()) and p.suffix.lower() in {".safetensors", ".bin"} for p in root.rglob("*"))
                out["ready"] = bool(has_config and has_preprocessor and has_weights)
                out["incomplete"] = bool(root.exists() and not out["ready"])
                out["ok"] = True
            except SystemExit:
                raise
            except Exception as e:
                out["error"] = str(e)
            print(json.dumps(out, ensure_ascii=False))
            """
        ).strip()
        try:
            proc = subprocess.run(
                [deps_python, "-c", inspect_code],
                capture_output=True,
                timeout=60,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_subprocess_env(),
                creationflags=_subprocess_creationflags(),
            )
            raw = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
            obj = _extract_json(raw) or {}
            if not obj:
                return {"ok": False, "root": "", "ready": False, "incomplete": False, "error": raw[:260]}
            obj.setdefault("root", "")
            obj.setdefault("ready", False)
            obj.setdefault("incomplete", False)
            return obj
        except Exception as e:
            return {"ok": False, "root": "", "ready": False, "incomplete": False, "error": str(e)}

    def _cleanup_broken_table_model_cache(self, deps_python: str) -> tuple[bool, str, int, str]:
        cleanup_code = textwrap.dedent(
            r"""
            import json
            import shutil
            from pathlib import Path
            out = {"ok": False, "root": "", "removed": []}
            try:
                from pix2text.utils import data_dir
                from pix2text.consts import MODEL_VERSION
                root = Path(data_dir()) / str(MODEL_VERSION) / "table-rec"
                out["root"] = str(root)
                if root.exists():
                    has_config = (root / "config.json").exists()
                    has_preprocessor = (root / "preprocessor_config.json").exists()
                    has_weights = any(
                        (not p.is_dir()) and p.name.lower() in {"model.safetensors", "pytorch_model.bin"}
                        for p in root.rglob("*")
                    ) or any((not p.is_dir()) and p.suffix.lower() in {".safetensors", ".bin"} for p in root.rglob("*"))
                    if not (has_config and has_preprocessor and has_weights):
                        shutil.rmtree(root, ignore_errors=True)
                        out["removed"].append(str(root))
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

    def _ensure_table_mode_runtime(self, deps_python: str) -> bool:
        table_code = (
            textwrap.dedent(
                r"""
                import json
                from importlib import metadata as _md
                """
            ).strip()
            + "\n\n"
            + _pix2text_runtime_compat_code()
            + "\n\n"
            + textwrap.dedent(
                r"""
                import pix2text
                from pix2text import Pix2Text
                stable_cfg = {"layout": {"model_type": "DocYoloLayoutParser"}, "text_formula": {"formula": {"model_name": "mfr", "model_backend": "onnx"}}}
                try:
                    try:
                        _md.version("pix2text")
                    except Exception:
                        str(getattr(pix2text, "__version__", ""))
                    Pix2Text.from_config(total_configs=stable_cfg, device="cpu", enable_table=True)
                    print(json.dumps({"ok": True}))
                except Exception as e:
                    print(json.dumps({"ok": False, "error": str(e)}))
                """
            ).strip()
        )

        table_cache = self._inspect_table_model_cache(deps_python)
        table_ready = bool(table_cache.get("ready"))
        table_incomplete = bool(table_cache.get("incomplete"))
        table_root = str(table_cache.get("root", "") or "")

        if table_incomplete:
            self._emit(
                "[WARN] table-rec cache looks incomplete before first table warmup, "
                "cleaning broken cache and retrying full bootstrap..."
            )
            c_ok, c_root, c_removed, c_err = self._cleanup_broken_table_model_cache(deps_python)
            if c_ok and c_removed > 0:
                self._emit(
                    f"[INFO] table-rec cache cleanup removed {c_removed} broken dir(s)"
                    f"{f' under {c_root}' if c_root else ''}"
                )
            elif not c_ok:
                self._emit(f"[WARN] table-rec cache cleanup failed: {c_err or 'unknown'}")

        if table_ready:
            return True

        self._emit(
            "[INFO] table-rec model is not fully cached yet"
            f"{f' under {table_root}' if table_root else ''}, "
            "running first table warmup without short timeout."
        )
        ok, _, fail_detail = self._probe_and_bootstrap_pix2text(
            deps_python,
            table_code,
            table_code,
            run_probe=False,
            probe_timeout=None,
            bootstrap_timeout=None,
        )
        if ok:
            return True

        retry_cache = self._inspect_table_model_cache(deps_python)
        retry_incomplete = bool(retry_cache.get("incomplete")) or classify_pix2text_failure(fail_detail).get("code") == "BROKEN_TABLE_MODEL_CACHE"
        if retry_incomplete:
            self._emit(
                "[WARN] table-rec cache looks broken or incomplete, "
                "auto-clean and retry once..."
            )
            c_ok, c_root, c_removed, c_err = self._cleanup_broken_table_model_cache(deps_python)
            if c_ok:
                if c_removed > 0:
                    self._emit(
                        f"[INFO] table-rec cache cleanup removed {c_removed} broken dir(s)"
                        f"{f' under {c_root}' if c_root else ''}"
                    )
                else:
                    self._emit(
                        f"[WARN] table-rec cache cleanup finished but no broken dir found"
                        f"{f' under {c_root}' if c_root else ''}"
                    )
                ok, _, fail_detail = self._probe_and_bootstrap_pix2text(
                    deps_python,
                    table_code,
                    table_code,
                    run_probe=False,
                    probe_timeout=None,
                    bootstrap_timeout=None,
                )
                if ok:
                    return True
            else:
                self._emit(f"[WARN] table-rec cache cleanup failed: {c_err or 'unknown'}")

        info = self._set_pix2text_error(fail_detail or "table-rec 模型未部署或加载失败。")
        self._emit(f"[WARN] table-rec warmup classified as [{info['code']}]")
        self._emit(f"[DIAG] {info['log_message']}")
        return False

    def _probe_and_bootstrap_pix2text(
        self,
        deps_python: str,
        probe_code: str,
        bootstrap_code: str,
        *,
        run_probe: bool = True,
        probe_timeout: int | None = 120,
        bootstrap_timeout: int | None = 900,
    ) -> tuple[bool, str, str]:
        probe_result = None
        probe_output = ""
        if run_probe:
            try:
                proc = subprocess.run(
                    [deps_python, "-c", probe_code],
                    capture_output=True,
                    timeout=probe_timeout,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._build_subprocess_env(),
                    creationflags=_subprocess_creationflags(),
                )
                probe_output = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
                probe_result = _extract_json(probe_output)
            except subprocess.TimeoutExpired:
                if probe_timeout:
                    self._emit(f"[WARN] pix2text probe timeout (>{probe_timeout}s), fallback to bootstrap")
                else:
                    self._emit("[WARN] pix2text probe timeout, fallback to bootstrap")

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
            diag = classify_pix2text_failure(probe_err)
            self._emit(f"[WARN] pix2text probe failed detail [{diag['code']}]: {probe_err}")
            self._emit(f"[DIAG] {diag['log_message']}")
        if run_probe:
            self._emit("[WARN] pix2text probe failed, trying bootstrap init...")
        else:
            self._emit("[INFO] pix2text first-time warmup: running bootstrap init without short probe timeout...")

        proc = subprocess.run(
            [deps_python, "-c", bootstrap_code],
            capture_output=True,
            timeout=bootstrap_timeout,
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
            diag = classify_pix2text_failure(str(err))
            self._emit(f"[WARN] pix2text bootstrap failed [{diag['code']}]: {err}")
            self._emit(f"[DIAG] {diag['log_message']}")
            return False, "", str(err)

        ver = (boot_result or {}).get("ver", "") or "unknown"
        self._emit(f"[INFO] pix2text bootstrap success (ver={ver})")
        return True, str(ver), str(probe_err or "")

    def _retry_pix2text_with_cpu_ort(
        self,
        deps_python: str,
        probe_code: str,
        bootstrap_code: str,
        fail_detail: str,
    ) -> tuple[bool, str]:
        if self._force_ort_cpu_only or (not self._is_cuda_runtime_broken_error(fail_detail)):
            return False, fail_detail
        self._emit(
            "[WARN] CUDAExecutionProvider runtime looks broken, "
            "retrying pix2text warmup with CPUExecutionProvider only..."
        )
        self._force_ort_cpu_only = True
        self._ort_gpu_available = False
        self.device = "cpu"
        ok, _, retry_fail = self._probe_and_bootstrap_pix2text(
            deps_python,
            probe_code,
            bootstrap_code,
            run_probe=False,
            probe_timeout=None,
            bootstrap_timeout=900,
        )
        if ok:
            self._emit("[INFO] pix2text warmup fallback success with CPUExecutionProvider only")
            return True, ""
        self._emit("[WARN] pix2text CPUExecutionProvider-only fallback failed")
        return False, (retry_fail or fail_detail)

    def _lazy_load_pix2text(self):
        if self._pix2text_subprocess_ready or self._pix2text_import_failed:
            return self._pix2text_subprocess_ready

        deps_python = get_pix2text_python()
        probe_code = (
            textwrap.dedent(
                r"""
                import json, os, sys
                from importlib import metadata as _md
                """
            ).strip()
            + "\n\n"
            + _pix2text_runtime_compat_code()
            + "\n\n"
            + textwrap.dedent(
                r"""
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
        )

        bootstrap_code = (
            textwrap.dedent(
                r"""
                import json
                from importlib import metadata as _md
                """
            ).strip()
            + "\n\n"
            + _pix2text_runtime_compat_code()
            + "\n\n"
            + textwrap.dedent(
                r"""
                import pix2text
                from pix2text import Pix2Text
                stable_cfg = {"layout": {"model_type": "DocYoloLayoutParser"}, "text_formula": {"formula": {"model_name": "mfr", "model_backend": "onnx"}}}
                try:
                    try:
                        _md.version("pix2text")
                    except Exception:
                        str(getattr(pix2text, "__version__", ""))
                    Pix2Text.from_config(total_configs=stable_cfg, device="cpu", enable_table=False)
                    print(json.dumps({"ok": True}))
                except Exception as e:
                    print(json.dumps({"ok": False, "error": str(e)}))
                """
            ).strip()
        )

        try:
            cache_state = self._inspect_pix2text_model_cache(deps_python)
            cache_ready = bool(cache_state.get("ready"))
            cache_incomplete = bool(cache_state.get("incomplete"))
            cache_root = str(cache_state.get("root", "") or "")
            ocr_cache_state = self._inspect_ocr_model_cache(deps_python)
            ocr_cache_incomplete = bool(ocr_cache_state.get("incomplete"))

            if cache_incomplete:
                self._emit(
                    "[WARN] pix2text cache looks incomplete before first warmup, "
                    "cleaning broken cache and retrying full bootstrap..."
                )
                c_ok, c_root, c_removed, c_err = self._cleanup_broken_pix2text_onnx_cache(deps_python)
                if c_ok and c_removed > 0:
                    self._emit(
                        f"[INFO] pix2text cache cleanup removed {c_removed} broken dir(s)"
                        f"{f' under {c_root}' if c_root else ''}"
                    )
                elif not c_ok:
                    self._emit(f"[WARN] pix2text cache cleanup failed: {c_err or 'unknown'}")

            if ocr_cache_incomplete:
                self._emit(
                    "[WARN] OCR model cache looks incomplete before first warmup, "
                    "cleaning broken cnocr/cnstd cache and retrying full bootstrap..."
                )
                c_ok, c_removed, c_err = self._cleanup_broken_ocr_model_cache(deps_python)
                if c_ok and c_removed > 0:
                    self._emit(f"[INFO] OCR cache cleanup removed {c_removed} broken dir(s)")
                elif not c_ok:
                    self._emit(f"[WARN] OCR cache cleanup failed: {c_err or 'unknown'}")

            if cache_ready:
                ok, _, fail_detail = self._probe_and_bootstrap_pix2text(
                    deps_python,
                    probe_code,
                    bootstrap_code,
                    run_probe=True,
                    probe_timeout=120,
                    bootstrap_timeout=900,
                )
            else:
                self._emit(
                    "[INFO] pix2text models are not fully cached yet"
                    f"{f' under {cache_root}' if cache_root else ''}, "
                    "skipping short probe timeout for first warmup."
                )
                ok, _, fail_detail = self._probe_and_bootstrap_pix2text(
                    deps_python,
                    probe_code,
                    bootstrap_code,
                    run_probe=False,
                    probe_timeout=None,
                    bootstrap_timeout=None,
                )

            if (not ok) and self._is_incomplete_pix2text_cache_error(fail_detail):
                self._emit(
                    "[WARN] pix2text cache looks broken or incomplete, "
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
                    retry_cache_state = self._inspect_pix2text_model_cache(deps_python)
                    retry_cache_ready = bool(retry_cache_state.get("ready"))
                    ok, _, fail_detail = self._probe_and_bootstrap_pix2text(
                        deps_python,
                        probe_code,
                        bootstrap_code,
                        run_probe=retry_cache_ready,
                        probe_timeout=120 if retry_cache_ready else None,
                        bootstrap_timeout=900 if retry_cache_ready else None,
                    )
                else:
                    self._emit(f"[WARN] pix2text cache cleanup failed: {c_err or 'unknown'}")

            if (not ok) and self._is_incomplete_ocr_model_cache_error(fail_detail):
                self._emit(
                    "[WARN] OCR model cache looks broken or incomplete, "
                    "auto-clean and retry once..."
                )
                c_ok, c_removed, c_err = self._cleanup_broken_ocr_model_cache(deps_python)
                if c_ok:
                    if c_removed > 0:
                        self._emit(f"[INFO] OCR cache cleanup removed {c_removed} broken dir(s)")
                    else:
                        self._emit("[WARN] OCR cache cleanup finished but no broken dir found")
                    retry_cache_state = self._inspect_pix2text_model_cache(deps_python)
                    retry_cache_ready = bool(retry_cache_state.get("ready"))
                    ok, _, fail_detail = self._probe_and_bootstrap_pix2text(
                        deps_python,
                        probe_code,
                        bootstrap_code,
                        run_probe=retry_cache_ready,
                        probe_timeout=120 if retry_cache_ready else None,
                        bootstrap_timeout=900 if retry_cache_ready else None,
                    )
                else:
                    self._emit(f"[WARN] OCR cache cleanup failed: {c_err or 'unknown'}")

            if not ok:
                cpu_ok, fail_detail = self._retry_pix2text_with_cpu_ort(
                    deps_python,
                    probe_code,
                    bootstrap_code,
                    fail_detail,
                )
                if cpu_ok:
                    ok = True

            if not ok:
                info = self._set_pix2text_error(fail_detail or "pix2text 模型未部署或加载失败。")
                self._emit(f"[WARN] pix2text warmup classified as [{info['code']}]")
                self._emit(f"[DIAG] {info['log_message']}")
                self._pix2text_import_failed = True
                return False

            worker_ready = bool(self._ensure_pix2text_worker())
            if not worker_ready:
                self._emit("[WARN] pix2text worker not ready after probe/bootstrap")
                info = self._set_pix2text_error("pix2text worker 启动失败，依赖环境可能不完整或被系统拦截。")
                self._emit(f"[DIAG] {info['log_message']}")
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
            self._clear_pix2text_error()
            return True
        except Exception as e:
            info = self._set_pix2text_error(str(e))
            self._emit(f"[WARN] pix2text lazy load exception [{info['code']}]: {e}")
            self._emit(f"[DIAG] {info['log_message']}")
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
