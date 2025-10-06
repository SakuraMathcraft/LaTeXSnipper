
from PyQt6.QtCore import QObject, pyqtSignal
import subprocess, sys, json, os, shutil, re
os.environ.setdefault("ORT_DISABLE_AZURE", "1")
import threading
from PIL import Image


class ModelWrapper(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.device = "cpu"
        self.torch = None
        self.pix2tex_model = None
        self.pix2text_model = None
        self._pix2text_import_failed = False
        self._providers_logged = False
        self._ort_gpu_available = None
        self._pix2tex_inited = False
        self._pix2tex_init_lock = threading.Lock()
        self._ort_probe_raw = ""
        self._init_torch()
        self._probe_onnxruntime()

    # -------- 通用日志 --------
    def _emit(self, msg: str):
        print(msg, flush=True)
        self.status_signal.emit(msg)

    # -------- torch 初始化 --------
    def _init_torch(self):
        try:
            import torch
            self.torch = torch
            if torch.cuda.is_available():
                self.device = "cuda"
                self._emit(f"[INFO] 设备: cuda:0 (name={torch.cuda.get_device_name(0)})")
                self._emit("[INFO] 设备: cuda")
            else:
                self.device = "cpu"
                self._emit("[INFO] 设备: cpu")
        except Exception as e:
            self.device = "cpu"
            self._emit(f"[WARN] 导入 torch 失败, 使用 CPU: {e}")

    # -------- onnxruntime 预探测(子进程) --------
    def _probe_onnxruntime(self):
        probe_code = r"""
import json, sys
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
        try:
            proc = subprocess.run(
                [sys.executable, "-c", probe_code],
                capture_output=True, timeout=10, text=True
            )
            raw_out = (proc.stdout or "").strip()
            raw_err = (proc.stderr or "").strip()
            self._ort_probe_raw = f"STDOUT={raw_out} STDERR={raw_err}"
        except Exception as e:
            self._emit(f"[WARN] onnxruntime 预探测子进程失败: {e}")
            return
        m = re.search(r"(\{.*\})", raw_out)
        if not m:
            self._emit(f"[WARN] onnxruntime 预探测输出无 JSON, 原始: {self._ort_probe_raw[:300]}")
            return
        try:
            info = json.loads(m.group(1))
        except Exception as e:
            self._emit(f"[WARN] onnxruntime 预探测 JSON 解析失败: {e}")
            return
        if not info.get("ok"):
            self._emit(f"[WARN] onnxruntime 预探测失败: {info.get('err','<空错误>')}")
            return
        prov = info.get("providers", [])
        self._ort_gpu_available = "CUDAExecutionProvider" in prov
        self._emit(f"[INFO] 预探测 onnxruntime providers: {prov}")

    # -------- onnxruntime 主进程兜底 --------
    def _direct_probe_onnxruntime(self):
        if self._ort_gpu_available is not None:
            return
        try:
            import onnxruntime as ort
            prov = ort.get_available_providers()
            self._ort_gpu_available = "CUDAExecutionProvider" in prov
            self._emit(f"[INFO] 直接探测 onnxruntime providers: {prov}")
        except Exception as e:
            self._ort_gpu_available = False
            self._emit(f"[WARN] 直接导入 onnxruntime 失败(继续以 CPU 假定): {e}")

    # -------- pix2tex 懒加载 --------
    def _ensure_pix2tex(self):
        if self._pix2tex_inited and self.pix2tex_model:
            return
        if self._pix2tex_init_lock.locked():
            with self._pix2tex_init_lock:
                return
        with self._pix2tex_init_lock:
            if self._pix2tex_inited and self.pix2tex_model:
                return
            try:
                self._emit("[INFO] 开始加载 pix2tex (懒加载)...")
                from pix2tex.cli import LatexOCR
                self.pix2tex_model = LatexOCR()  # 不传 device
                real_dev = getattr(self.pix2tex_model, "device", None)
                if real_dev is None and hasattr(self.pix2tex_model, "model"):
                    try:
                        p = next(self.pix2tex_model.model.parameters(), None)
                        if p is not None:
                            real_dev = p.device
                    except Exception:
                        pass
                if real_dev is not None:
                    self.device = str(real_dev)
                self._pix2tex_inited = True
                self._emit(f"[INFO] pix2tex 加载完成 (device={self.device})")
            except Exception as e:
                self._emit(f"[ERROR] pix2tex 加载失败: {e}")
                raise
            # 若加载在 CPU 但 GPU 可用 -> 迁移
            if self.device != "cuda" and self.torch and self.torch.cuda.is_available():
                try:
                    self._emit("[INFO] 检测到 GPU 可用, 强制迁移 pix2tex -> cuda")
                    self._sync_pix2tex_all_modules("cuda")
                    p = None
                    if hasattr(self.pix2tex_model, "model"):
                        p = next(self.pix2tex_model.model.parameters(), None)
                    if p is not None and p.device.type == "cuda":
                        self.device = "cuda"
                        self._emit("[INFO] pix2tex 迁移到 GPU 成功")
                    else:
                        self._emit("[WARN] pix2tex 迁移后参数仍非 GPU, 保持 CPU")
                except Exception as e:
                    self._emit(f"[WARN] pix2tex 迁移 GPU 失败, 保持 CPU: {e}")

    # -------- pix2tex 递归迁移 --------
    def _sync_pix2tex_all_modules(self, device: str):
        if not self.pix2tex_model or not self.torch:
            return
        torch = self.torch
        target = torch.device(device)
        visited = set()

        def move(obj):
            if obj is None or id(obj) in visited:
                return
            visited.add(id(obj))
            if hasattr(obj, "to"):
                try:
                    obj.to(target)
                except Exception:
                    pass
            for name in ("model", "models", "_model", "encoder", "decoder"):
                if hasattr(obj, name):
                    move(getattr(obj, name))

        move(self.pix2tex_model)
        try:
            self.pix2tex_model.device = target
        except Exception:
            pass

    def _ensure_pix2tex_device(self):
        if not self.pix2tex_model:
            return
        cur = getattr(self.pix2tex_model, "device", None)
        if cur is not None:
            cur_s = str(cur)
            if cur_s != self.device:
                self.device = cur_s

    # -------- pix2text 支持 --------
    def _clear_pix2text_cache(self):
        home = os.path.expanduser("~")
        targets = set()
        for p in (
            os.path.join(home, ".pix2text"),
            os.path.join(os.environ.get("APPDATA", "") or "", "pix2text")
        ):
            if p and os.path.exists(p):
                targets.add(p)
        hf_root = os.path.join(home, ".cache", "huggingface", "hub", "models")
        if os.path.isdir(hf_root):
            for n in os.listdir(hf_root):
                if "pix2text" in n.lower():
                    targets.add(os.path.join(hf_root, n))
        removed = []
        for d in list(targets):
            try:
                shutil.rmtree(d)
                removed.append(d)
            except Exception as e:
                self._emit(f"[WARN] 清理缓存失败: {d} -> {e}")
        if removed:
            self._emit(f"[INFO] 已清理 pix2text 缓存: {removed}")
        else:
            self._emit("[INFO] 未发现需要清理的 pix2text 缓存目录")

    def _need_retry(self, err: str) -> bool:
        e = err.lower()
        keys = (
            "untagged enum modelwrapper",
            "safetensors",
            "eof while",
            "unexpected end",
            "failed to deserialize",
            "error while deserializing"
        )
        return any(k in e for k in keys)

    def _log_ort_providers(self):
        if self._providers_logged:
            return
        try:
            import onnxruntime as ort
            self._emit(f"[INFO] onnxruntime providers: {ort.get_available_providers()}")
        except Exception as e:
            self._emit(f"[WARN] 获取 onnxruntime providers 失败: {e}")
        self._providers_logged = True

    def _lazy_load_pix2text(self):
        if self._pix2text_import_failed:
            return None
        if self.pix2text_model:
            return self.pix2text_model
        if self._ort_gpu_available is None:
            self._emit("[INFO] onnxruntime 状态未知, 尝试主进程直接探测...")
            self._direct_probe_onnxruntime()
        if self._ort_gpu_available is False:
            os.environ.setdefault("ORT_DISABLE_GRAPH_OPT", "1")
        from importlib import import_module

        def _do_load(first: bool):
            self._emit(f"[INFO] 加载 Pix2Text 模型...(retry={not first})")
            mod = import_module("pix2text")
            Pix2Text = getattr(mod, "Pix2Text")
            self._log_ort_providers()
            self.pix2text_model = Pix2Text.from_config()
            self._emit(f"[INFO] Pix2Text 加载成功(retry={not first}, gpu={self._ort_gpu_available})")
            return self.pix2text_model

        try:
            return _do_load(True)
        except Exception as e:
            msg = str(e)
            self._emit(f"[WARN] Pix2Text 首次加载失败: {msg}")
            if self._need_retry(msg):
                self._emit("[INFO] 检测到疑似损坏权重, 清理缓存后重试...")
                self._clear_pix2text_cache()
                try:
                    return _do_load(False)
                except Exception as e2:
                    self._emit(f"[WARN] Pix2Text 重试仍失败: {e2}")
            self._emit("[WARN] Pix2Text 已禁用，回退 pix2tex")
            self._pix2text_import_failed = True
            self.pix2text_model = None
            return None

    # -------- 对外预测接口 --------
    def predict(self, pil_img: Image.Image, model_name: str = "pix2tex") -> str:
        name = (model_name or "pix2tex").lower()
        if name == "pix2text":
            if self._lazy_load_pix2text():
                try:
                    return self._run_pix2text(pil_img)
                except Exception as e:
                    self._emit(f"[WARN] Pix2Text 推理失败, 回退 pix2tex: {e}")
        self._ensure_pix2tex()
        try:
            return self._run_pix2tex(pil_img)
        except Exception as e:
            self._emit(f"[ERROR] pix2tex 推理失败: {e}")
            return ""

    # -------- pix2tex 推理 --------
    def _run_pix2tex(self, pil_img: Image.Image) -> str:
        if not self.pix2tex_model:
            raise RuntimeError("pix2tex 未初始化")
        self._ensure_pix2tex_device()
        if self.device == "cuda":
            try:
                p = None
                if hasattr(self.pix2tex_model, "model"):
                    p = next(self.pix2tex_model.model.parameters(), None)
                if p is not None and p.device.type != "cuda":
                    self._emit("[INFO] 再次尝试迁移 pix2tex -> cuda (推理前校验)")
                    self._sync_pix2tex_all_modules("cuda")
            except Exception as e:
                self._emit(f"[WARN] 推理前迁移 GPU 失败(忽略继续): {e}")
        try:
            return self.pix2tex_model(pil_img).strip()
        except Exception as e:
            msg = str(e)
            if ("FloatTensor" in msg and "cuda.FloatTensor" in msg) or "device type" in msg:
                self._emit(f"[WARN] 捕获设备不匹配, 尝试强制同步后重试: {msg}")
                try:
                    tgt = "cuda" if (self.torch and self.torch.cuda.is_available()) else "cpu"
                    self._sync_pix2tex_all_modules(tgt)
                    self.device = tgt
                    return self.pix2tex_model(pil_img).strip()
                except Exception as e2:
                    self._emit(f"[WARN] 同步重试失败: {e2}")
            if self.device == "cuda":
                self._emit(f"[WARN] pix2tex GPU 失败, 切 CPU: {e}")
                self.device = "cpu"
                self._sync_pix2tex_all_modules("cpu")
                try:
                    return self.pix2tex_model(pil_img).strip()
                except Exception as e3:
                    self._emit(f"[ERROR] 回退 CPU 仍失败: {e3}")
                    return ""
            self._emit(f"[ERROR] pix2tex 推理失败: {e}")
            return ""

    # -------- pix2text 推理 --------
    def _run_pix2text(self, pil_img: Image.Image) -> str:
        if not self.pix2text_model:
            raise RuntimeError("Pix2Text 未加载")
        try:
            return self.pix2text_model.recognize_formula(pil_img).strip()
        except Exception as e:
            self._emit(f"[WARN] Pix2Text 推理异常: {e}")
            raise
