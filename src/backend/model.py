
from PyQt6.QtCore import QObject, pyqtSignal

import subprocess, sys, json, os, shutil, re, textwrap
from pathlib import Path
os.environ.setdefault("ORT_DISABLE_AZURE", "1")
import threading
from PIL import Image
from backend.torch_runtime import (
    normalize_mode,
    infer_main_python,
    detect_torch_info,
    mode_satisfies,
    build_torch_pip_args,
    inject_shared_torch_env,
)

def get_deps_python() -> str:
    """
    获取用户依赖目录中的 Python 解释器路径。
    - 打包模式：必须使用用户目录的独立 Python
    - 开发模式：如果环境变量设置了则使用，否则使用当前 Python
    """
    # 优先从环境变量获取（由 deps_bootstrap 设置）
    pyexe = os.environ.get("LATEXSNIPPER_PYEXE", "")
    if pyexe and os.path.exists(pyexe):
        return pyexe
    
    # 检查是否是打包模式
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        # 打包模式但没有设置环境变量，这是个问题
        print("[WARN] 打包模式下未找到依赖 Python，请先运行依赖向导")
        return sys.executable  # 回退，但可能不工作
    
    # 开发模式：使用当前 Python
    return sys.executable

def get_unimernet_python() -> str:
    """使用隔离的 UniMERNet Python（若已配置），否则回退到依赖 Python。"""
    pyexe = os.environ.get("UNIMERNET_PYEXE", "")
    if pyexe and os.path.exists(pyexe):
        return pyexe
    return get_deps_python()

def get_pix2text_python() -> str:
    """Return pix2text runtime python, fallback to deps python."""
    pyexe = os.environ.get("PIX2TEXT_PYEXE", "")
    if pyexe and os.path.exists(pyexe):
        return pyexe
    return get_deps_python()

class ModelWrapper(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, default_model: str | None = None):
        super().__init__()
        self.device = "cpu"
        self.torch = None
        self.pix2tex_model = None
        self.pix2text_model = None
        self._pix2text_import_failed = False
        self._unimernet_import_failed = False
        self._unimernet_subprocess_ready = False
        self._unimernet_worker = None
        self._unimernet_worker_lock = threading.Lock()
        self._pix2text_subprocess_ready = False  # 子进程模式
        self._pix2text_worker = None
        self._pix2text_worker_lock = threading.Lock()
        self._pix2tex_subprocess_ready = False   # pix2tex 也支持子进程模式
        self._pix2tex_worker = None
        self._pix2tex_worker_lock = threading.Lock()
        self._pix2tex_load_error = None          # 记录加载失败的错误信息
        self._providers_logged = False
        self._ort_gpu_available = None
        self._pix2tex_inited = False
        self._pix2tex_init_lock = threading.Lock()
        self._pix2tex_main_route_logged = False
        self._pix2tex_subprocess_route_logged = False
        self._ort_probe_raw = ""
        self._torch_repair_attempted = set()
        self._default_model = (default_model or "pix2text").lower()
        self.last_used_model = None
        if not self._default_model.startswith("pix2text"):
            self._default_model = "pix2text"
        
        # 判断是否是打包模式
        self._is_frozen = getattr(sys, 'frozen', False)
        
        if self._is_frozen:
            # 打包模式：所有 AI 操作都在子进程中运行
            self._emit("[INFO] 打包模式：AI 模型将在子进程中运行")
            self._probe_subprocess_models(probe_pix2text=True)
        else:
            # 开发模式：可以在主进程中加载（如果依赖可用）
            self._init_torch()
            self._probe_onnxruntime()
            self._lazy_load_pix2text()
    
    def _probe_subprocess_models(self, probe_pix2text: bool = False):
        """打包模式探测：仅预加载 pix2text。"""
        self._probe_onnxruntime()
        self._pix2tex_subprocess_ready = False
        self._pix2tex_load_error = None
        if probe_pix2text:
            self._emit("[INFO] 预加载 pix2text（启动阶段）...")
        self._lazy_load_pix2text()

    def _target_torch_mode(self, target: str) -> str:
        """v1.05: 共享 torch 策略收敛到 pix2text 单路径。"""
        _ = target  # keep signature for backward compatibility
        return normalize_mode(os.environ.get("PIX2TEXT_TORCH_MODE", "auto"))

    def _target_shared_torch_site(self, target: str) -> str:
        _ = target  # keep signature for backward compatibility
        for cand in (
            os.environ.get("PIX2TEXT_SHARED_TORCH_SITE", ""),
            os.environ.get("LATEXSNIPPER_SHARED_TORCH_SITE", ""),
        ):
            site = (cand or "").strip()
            if site and os.path.isdir(site):
                return site
        return ""

    def _discover_shared_torch_site(self, target: str) -> str:
        # 1) explicit envs
        site = self._target_shared_torch_site(target)
        if site:
            return site
        # 2) main python inferred by runtime
        try:
            from backend.torch_runtime import python_site_packages
            main_site = python_site_packages(infer_main_python())
            if main_site and (main_site / "torch").exists():
                return str(main_site)
        except Exception:
            pass
        # 3) deps python path
        try:
            from backend.torch_runtime import python_site_packages
            deps_site = python_site_packages(get_deps_python())
            if deps_site and (deps_site / "torch").exists():
                return str(deps_site)
        except Exception:
            pass
        # 4) install base dir hint
        try:
            base = (os.environ.get("LATEXSNIPPER_INSTALL_BASE_DIR", "") or "").strip()
            if base:
                c = Path(base) / "python311" / "Lib" / "site-packages"
                if c.exists() and (c / "torch").exists():
                    return str(c)
        except Exception:
            pass
        # 5) source layout fallback
        try:
            app_dir = Path(__file__).resolve().parent.parent
            c = app_dir / "deps" / "python311" / "Lib" / "site-packages"
            if c.exists() and (c / "torch").exists():
                return str(c)
        except Exception:
            pass
        return ""

    def _build_subprocess_env(self, target: str) -> dict:
        env = os.environ.copy()
        # 隔离子进程：避免主进程 PYTHONPATH/PYTHONHOME 污染隔离环境依赖解析。
        for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE"):
            env.pop(k, None)
        env["PYTHONNOUSERSITE"] = "1"
        # v1.05: target 参数仅为兼容，统一按 pix2text 共享路径构建子进程环境。
        _ = target
        shared_site = self._discover_shared_torch_site("pix2text")
        env = inject_shared_torch_env(env, shared_site)
        if shared_site:
            env["PIX2TEXT_SHARED_TORCH_SITE"] = shared_site
        else:
            env.pop("PIX2TEXT_SHARED_TORCH_SITE", None)
        env.pop("LATEXSNIPPER_SHARED_TORCH_SITE", None)
        env["LATEXSNIPPER_SHARED_TORCH_MODE"] = self._target_torch_mode("pix2text")
        return env

    def _looks_like_torch_issue(self, err_text: str) -> bool:
        t = (err_text or "").lower()
        if not t:
            return False
        keywords = [
            "no module named 'torch'",
            "no module named \"torch\"",
            "torch not found",
            "import failed: no module named 'torch'",
            "cannot import name",
            "torchvision",
            "torchaudio",
            "cudnn",
            "libtorch",
            "c10",
            "worker no output",
        ]
        return any(k in t for k in keywords)

    def _auto_repair_isolated_torch(self, target: str, reason: str = "") -> bool:
        """
        自动回退：当共享 torch 不可用或版本不匹配时，按目标模式在隔离环境补装 torch 三件套。
        """
        # v1.05: 仅保留 pix2text 修复路径；保留 target 形参以兼容旧调用。
        repair_key = "pix2text"
        if repair_key in self._torch_repair_attempted:
            return False
        if reason and not self._looks_like_torch_issue(reason):
            return False

        self._torch_repair_attempted.add(repair_key)
        pyexe = get_pix2text_python()
        if not pyexe or not os.path.exists(pyexe):
            return False

        mode = self._target_torch_mode("pix2text")
        shared_site = self._target_shared_torch_site("pix2text")
        if shared_site:
            shared_info = detect_torch_info(infer_main_python(), timeout_sec=8)
            if mode_satisfies(shared_info, mode):
                # 主环境理论满足目标模式时，默认不落本地安装；
                # 但若已出现明确 torch 导入/加载错误，允许回退到隔离环境本地安装。
                reason_t = (reason or "").lower()
                explicit_torch_fail = any(x in reason_t for x in [
                    "no module named 'torch'",
                    "no module named \"torch\"",
                    "dll load failed",
                    "cudnn",
                    "c10",
                    "libtorch",
                ])
                if not explicit_torch_fail:
                    return False
        if mode == "auto":
            main_info = detect_torch_info(infer_main_python(), timeout_sec=8)
            mode = "gpu" if (main_info.get("mode") == "gpu") else "cpu"

        env = self._build_subprocess_env("pix2text")
        current = detect_torch_info(pyexe, timeout_sec=8, run_env=env)
        if mode_satisfies(current, mode):
            return False

        args, note = build_torch_pip_args(pyexe, mode)
        if not args:
            self._emit(f"[WARN] {target} 自动回退未执行: {note}")
            return False

        self._emit(f"[INFO] {target} 尝试自动回退安装 torch({mode})...")
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                env=env,
            )
            if proc.returncode != 0:
                tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-300:]
                self._emit(f"[WARN] {target} 自动回退安装失败: {tail}")
                return False
            after = detect_torch_info(pyexe, timeout_sec=10, run_env=env)
            if mode_satisfies(after, mode):
                self._emit(f"[INFO] {target} 自动回退成功: 已安装 {mode} 版 torch")
                return True
            self._emit(f"[WARN] {target} 自动回退后仍未满足目标模式({mode})")
            return False
        except Exception as e:
            self._emit(f"[WARN] {target} 自动回退异常: {e}")
            return False

    # -------- 通用日志 --------
    def _emit(self, msg: str):
        # 安全打印：防止 sys.stdout/stderr 丢失导致崩溃
        try:
            if sys.stdout and not getattr(sys.stdout, "closed", False):
                print(msg, flush=True)
        except Exception:
            pass
        try:
            self.status_signal.emit(msg)
        except Exception:
            pass

    # -------- 模型状态查询 --------
    def is_ready(self) -> bool:
        """兼容旧调用：统一返回 pix2text 就绪状态。"""
        return self.is_pix2text_ready()
    
    def is_pix2text_ready(self) -> bool:
        """检查 pix2text 模型是否可用"""
        if self._is_frozen:
            return self._pix2text_subprocess_ready
        # 非打包模式：子进程验证成功或模型已加载才算就绪
        if self._pix2text_subprocess_ready:
            return True
        if self.pix2text_model is not None:
            return True
        # 其它情况都算未就绪（懒加载不算就绪）
        return False
    
    def is_model_ready(self, model_name: str) -> bool:
        """检查指定模型是否可用"""
        return self.is_pix2text_ready() if (model_name or "").startswith("pix2text") else False
    
    def get_error(self) -> str | None:
        """获取加载错误信息，如果没有错误返回 None"""
        if self._pix2text_import_failed:
            return "pix2text not ready"
        return None
    
    def get_status_text(self) -> str:
        """获取模型状态描述文本"""
        if self._pix2text_import_failed:
            return "❌ 模型加载失败: pix2text not ready"
        if self.is_pix2text_ready():
            return f"✅ 模型就绪 (设备: {self.device})"
        return "⏳ 模型未加载"

    # -------- torch 初始化 --------
    def _init_torch(self):
        try:
            import torch
            self.torch = torch
            if torch.cuda.is_available():
                self.device = "cuda"
                self._emit(f"[INFO] 设备: cuda:0 (name={torch.cuda.get_device_name(0)})")
            else:
                self.device = "cpu"
                self._emit("[INFO] 设备: cpu")
        except Exception as e:
            self.device = "cpu"
            self._emit(f"[WARN] 导入 torch 失败, 使用 CPU: {e}")

    # -------- onnxruntime 预探测(子进程) --------
    def _probe_onnxruntime(self):
        probe_code = textwrap.dedent(r"""
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
        """).strip()
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", probe_code],
                capture_output=True, timeout=10, text=True,
                encoding="utf-8", errors="replace"
            )
            raw_out = (proc.stdout or "").strip()
            raw_err = (proc.stderr or "").strip()
            self._ort_probe_raw = f"STDOUT={raw_out} STDERR={raw_err}"
        except Exception as e:
            self._emit(f"[WARN] onnxruntime probe launch failed: {e}")
            return
        m = re.search(r"(\{.*\})", raw_out)
        if not m:
            self._emit(f"[WARN] onnxruntime probe returned no JSON: {self._ort_probe_raw[:300]}")
            return
        try:
            info = json.loads(m.group(1))
        except Exception as e:
            self._emit(f"[WARN] onnxruntime probe JSON parse failed: {e}")
            return
        if not info.get("ok"):
            self._emit(f"[WARN] onnxruntime subprocess error: {info.get('err','<unknown>')}")
            return
        prov = info.get("providers", [])
        self._ort_gpu_available = "CUDAExecutionProvider" in prov
        self._emit(f"[INFO] onnxruntime providers detected: {prov}")
        if not self._ort_gpu_available:
            self._check_and_fix_onnxruntime_conflict()

    def _check_and_fix_onnxruntime_conflict(self):
        """Fix onnxruntime package conflicts in deps python."""
        check_code = textwrap.dedent(r"""
            import json
            try:
                import pkg_resources
                installed = {p.key: p.version for p in pkg_resources.working_set}
                has_ort = 'onnxruntime' in installed
                has_ort_gpu = 'onnxruntime-gpu' in installed
                print(json.dumps({
                    "has_ort": has_ort,
                    "has_ort_gpu": has_ort_gpu,
                    "ort_ver": installed.get('onnxruntime', ''),
                    "ort_gpu_ver": installed.get('onnxruntime-gpu', '')
                }))
            except Exception as e:
                print(json.dumps({"error": str(e)}))
        """).strip()
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", check_code],
                capture_output=True, timeout=10, text=True,
                encoding="utf-8", errors="replace"
            )
            m = re.search(r"\{.*\}", proc.stdout or "")
            if not m:
                return
            info = json.loads(m.group())
            has_ort = info.get("has_ort", False)
            has_ort_gpu = info.get("has_ort_gpu", False)
            if has_ort and has_ort_gpu:
                self._emit(
                    f"[WARN] onnxruntime conflict detected: onnxruntime={info.get('ort_ver')} "
                    f"onnxruntime-gpu={info.get('ort_gpu_ver')}"
                )
                self._emit("[INFO] remove CPU onnxruntime to keep GPU provider chain clean")
                self._fix_onnxruntime_conflict(deps_python)
            elif has_ort_gpu and not self._ort_gpu_available:
                self._emit("[WARN] onnxruntime-gpu installed but CUDAExecutionProvider unavailable")
                self._emit("[HINT] verify CUDA runtime / VC++ runtime / torch dll dependencies")
        except Exception as e:
            self._emit(f"[WARN] onnxruntime conflict probe failed: {e}")

    def _fix_onnxruntime_conflict(self, deps_python: str):
        """修复 onnxruntime 冲突：卸载 CPU 版"""
        try:
            import subprocess
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.CREATE_NO_WINDOW
            
            # 卸载 CPU 版
            self._emit("[INFO] 正在卸载 onnxruntime (CPU 版)...")
            uninstall_cmd = [deps_python, "-m", "pip", "uninstall", "onnxruntime", "-y"]
            proc = subprocess.run(uninstall_cmd, capture_output=True, timeout=60, 
                                  text=True, encoding="utf-8", errors="replace",
                                  creationflags=flags)
            
            if proc.returncode == 0:
                self._emit("[OK] 已卸载冲突的 onnxruntime ✅")
                self._emit("[INFO] 请重启程序以使 onnxruntime-gpu 生效")
                self._ort_gpu_available = None  # 需要重新探测
            else:
                self._emit(f"[WARN] 卸载失败: {proc.stderr[:200]}")
        except Exception as e:
            self._emit(f"[WARN] 修复 onnxruntime 冲突失败: {e}")

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
        # 打包模式：不在主进程加载，使用子进程
        if self._is_frozen:
            return
        
        if self._pix2tex_inited and self.pix2tex_model:
            return
        if self._pix2tex_init_lock.locked():
            with self._pix2tex_init_lock:
                return
        with self._pix2tex_init_lock:
            if self._pix2tex_inited and self.pix2tex_model:
                return
            if not self._pix2tex_main_route_logged:
                self._emit("[INFO] [main] pix2tex 将在主进程加载并推理（开发模式）")
                self._pix2tex_main_route_logged = True
            try:
                self._emit("[INFO] [main] 开始加载 pix2tex (首次启动会安装权重，请耐心等待)...")
                import warnings
                # 已知第三方依赖告警：不影响推理，仅会污染启动日志。
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=r"^Pydantic serializer warnings:",
                        category=UserWarning,
                    )
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
                self._emit(f"[INFO] [main] pix2tex 加载完成 (device={self.device})")
            except ModuleNotFoundError as e:
                self._emit(f"[ERROR] pix2tex 加载失败: {e} ，请重启程序并挂上梯子，因为会重新下载模型权重")
                raise ModuleNotFoundError(f"依赖缺失: {e}") from e
            except Exception as e:
                self._emit(f"[ERROR] pix2tex 加载失败: {e} ，请重启程序并挂上梯子，因为会重新下载模型权重")
                raise
            # 若加载在 CPU 但 GPU 可用 -> 迁移
            if self.device != "cuda" and self.torch and self.torch.cuda.is_available():
                try:
                    self._emit("[INFO] [main] 检测到 GPU 可用, 强制迁移 pix2tex -> cuda")
                    # 恢复原始标准流，防止 CUDA 内部的 C 代码使用损坏的 stderr
                    try:
                        if sys.__stderr__ and not getattr(sys.__stderr__, 'closed', False):
                            sys.stderr = sys.__stderr__
                        if sys.__stdout__ and not getattr(sys.__stdout__, 'closed', False):
                            sys.stdout = sys.__stdout__
                    except Exception:
                        pass
                    # 抑制 CUDA 内部的警告输出
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        self._sync_pix2tex_all_modules("cuda")
                    p = None
                    if hasattr(self.pix2tex_model, "model"):
                        p = next(self.pix2tex_model.model.parameters(), None)
                    if p is not None and p.device.type == "cuda":
                        self.device = "cuda"
                        self._emit("[INFO] [main] pix2tex 迁移到 GPU 成功")
                    else:
                        self._emit("[WARN] [main] pix2tex 迁移后参数仍非 GPU, 保持 CPU")
                except Exception as e:
                    self._emit(f"[WARN] [main] pix2tex 迁移 GPU 失败, 保持 CPU: {e}")

    # -------- pix2tex 递归迁移 --------
    def _sync_pix2tex_all_modules(self, device: str):
        if not self.pix2tex_model or not self.torch:
            return
        torch = self.torch
        target = torch.device(device)
        visited = set()

        def move(obj, parent=None, attr_name=None):
            if obj is None or id(obj) in visited:
                return
            visited.add(id(obj))
            if hasattr(obj, "to") and callable(getattr(obj, "to")):
                try:
                    # 对于 nn.Module，to() 是 in-place 操作（返回 self）
                    # 但为了安全，如果有父对象，尝试重新赋值
                    new_obj = obj.to(target)
                    if parent is not None and attr_name and new_obj is not obj:
                        try:
                            setattr(parent, attr_name, new_obj)
                        except Exception:
                            pass
                except Exception:
                    pass
            # 递归处理子模块
            for name in ("model", "models", "_model", "encoder", "decoder", "backbone", "head", "image_resizer"):
                if hasattr(obj, name):
                    move(getattr(obj, name), obj, name)

        move(self.pix2tex_model)
        
        # 确保 pix2tex 内部的 device 属性也更新
        try:
            self.pix2tex_model.device = target
        except Exception:
            pass
        
        # ⚠️ 关键：更新 pix2tex 的 args.device，因为 __call__ 用它来决定图像转换目标
        if hasattr(self.pix2tex_model, "args"):
            try:
                self.pix2tex_model.args.device = device  # 使用字符串 'cuda' 或 'cpu'
                self._emit(f"[DEBUG] [main] 已更新 pix2tex args.device = {device}")
            except Exception:
                pass
        
        # 额外：确保内部 model 的 device 也更新
        if hasattr(self.pix2tex_model, "model"):
            try:
                self.pix2tex_model.model.device = target
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

    # -------- pix2text  --------
    def _stop_unimernet_worker(self):
        proc = getattr(self, "_unimernet_worker", None)
        self._unimernet_worker = None
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

    def _ensure_unimernet_worker(self) -> bool:
        try:
            proc = self._unimernet_worker
            if proc and proc.poll() is None:
                return True
        except Exception:
            proc = None
        with self._unimernet_worker_lock:
            try:
                proc = self._unimernet_worker
                if proc and proc.poll() is None:
                    return True
            except Exception:
                proc = None
            try:
                import subprocess
                import textwrap
                deps_python = get_unimernet_python()
                subprocess_code = textwrap.dedent(r"""
import sys, json, os
from PIL import Image

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

_bootstrap_shared_torch()


def _normalize(out):
    if isinstance(out, dict):
        for k in ("text", "latex", "result", "pred", "preds", "output"):
            if k in out:
                out = out[k]
                break
    if isinstance(out, (list, tuple)):
        if len(out) == 1:
            out = out[0]
        else:
            out = "\n\n".join(str(x) for x in out)
    return str(out)


def _pick_weight(model_dir):
    if not model_dir:
        return ""
    candidates = [
        os.path.join(model_dir, "pytorch_model.pth"),
        os.path.join(model_dir, "pytorch_model.bin"),
        os.path.join(model_dir, "model.safetensors"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    pths = [p for p in os.listdir(model_dir) if p.lower().endswith(".pth")]
    if pths:
        return os.path.join(model_dir, sorted(pths)[0])
    return ""


def _load_model():
    model_dir = os.environ.get("UNIMERNET_MODEL_PATH", "")
    if not model_dir or not os.path.isdir(model_dir):
        return None, None, None, f"model dir missing: {model_dir or '<empty>'}"
    weight_path = _pick_weight(model_dir)
    if not weight_path:
        return None, None, None, f"weight missing in: {model_dir}"
    try:
        import torch
        import unimernet
        from omegaconf import OmegaConf
        from unimernet.models.unimernet.unimernet import UniMERModel
        from unimernet.processors import load_processor
    except Exception as e:
        return None, None, None, f"import failed: {e}"
    try:
        base_cfg = os.path.join(os.path.dirname(unimernet.__file__), "configs", "models", "unimernet_base.yaml")
        cfg = OmegaConf.load(base_cfg)
        cfg.model.tokenizer_config.path = model_dir
        cfg.model.model_config.model_name = model_dir
        cfg.model.load_pretrained = False
        cfg.model.load_finetuned = True
        cfg.model.finetuned = weight_path
        model = UniMERModel.from_config(cfg.model)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)
        model.eval()
        vis_cfg = None
        try:
            vis_cfg = cfg.preprocess.vis_processor.eval
        except Exception:
            vis_cfg = None
        vis_processor = load_processor("formula_image_eval", vis_cfg)
        return model, vis_processor, device, ""
    except Exception as e:
        return None, None, None, f"infer init failed: {e}"


model, vis_processor, device, load_err = _load_model()
print(json.dumps({"ready": True, "ok": bool(model), "error": load_err}), flush=True)


def _infer(img):
    if not model:
        return None, load_err or "model not loaded"
    try:
        image = vis_processor(img).unsqueeze(0).to(device)
        out = model.generate({"image": image})
        if isinstance(out, dict):
            pred = out.get("pred_str", out.get("preds"))
            if isinstance(pred, (list, tuple)):
                pred = pred[0] if pred else ""
            if pred is not None:
                return _normalize(pred), None
        return _normalize(out), None
    except Exception as e:
        return None, f"infer failed: {e}"


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    if line == "__quit__":
        break
    try:
        req = json.loads(line)
    except Exception:
        req = {"image": line}
    if req.get("ping"):
        print(json.dumps({"ok": True, "ready": True}), flush=True)
        continue
    img_path = req.get("image", "")
    if not img_path:
        print(json.dumps({"ok": False, "error": "image path missing"}), flush=True)
        continue
    try:
        img = Image.open(img_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"open image failed: {e}"}), flush=True)
        continue
    pred, err = _infer(img)
    if pred:
        print(json.dumps({"ok": True, "result": pred}), flush=True)
    else:
        print(json.dumps({"ok": False, "error": err or "infer failed"}), flush=True)
""").strip()
                proc = subprocess.Popen(
                    [deps_python, "-u", "-c", subprocess_code],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=self._build_subprocess_env("unimernet"),
                )
                self._unimernet_worker = proc
                return True
            except Exception as e:
                self._emit(f"[ERROR] UniMERNet worker start failed: {e}")
                self._unimernet_worker = None
                return False

    def _run_unimernet_worker(self, img_path: str) -> str:
        import json
        proc = self._unimernet_worker
        if not proc or proc.poll() is not None:
            raise RuntimeError("unimernet worker not running")
        try:
            payload = json.dumps({"image": img_path})
            proc.stdin.write(payload + "\n")
            proc.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"unimernet worker send failed: {e}")
        for _ in range(200):
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if data.get("ready") and not data.get("result") and not data.get("error"):
                continue
            if data.get("ok"):
                self._unimernet_subprocess_ready = True
                return data.get("result", "")
            raise RuntimeError(data.get("error", "unimernet error"))
        raise RuntimeError("unimernet worker no output")

    def _run_unimernet_subprocess(self, pil_img: Image.Image) -> str:
        """Run UniMERNet inference via subprocess."""
        import tempfile
        import textwrap

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            pil_img.save(tmp, format="PNG")

        try:
            if self._ensure_unimernet_worker():
                result = self._run_unimernet_worker(tmp_path)
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                return result
        except Exception as e:
            self._emit(f"[WARN] UniMERNet worker fallback: {e}")
            self._stop_unimernet_worker()
            try:
                if self._auto_repair_isolated_torch("unimernet", str(e)):
                    if self._ensure_unimernet_worker():
                        result = self._run_unimernet_worker(tmp_path)
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                        return result
            except Exception as e2:
                self._emit(f"[WARN] UniMERNet auto-repair retry failed: {e2}")

        subprocess_code = textwrap.dedent(r"""
import sys, json, io, os, importlib
from PIL import Image

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

_bootstrap_shared_torch()


def _normalize(out):
    if isinstance(out, dict):
        for k in ("text", "latex", "result", "pred", "preds", "output"):
            if k in out:
                out = out[k]
                break
    if isinstance(out, (list, tuple)):
        if len(out) == 1:
            out = out[0]
        else:
            out = "\n\n".join(str(x) for x in out)
    return str(out)


def _pick_weight(model_dir):
    if not model_dir:
        return ""
    candidates = [
        os.path.join(model_dir, "pytorch_model.pth"),
        os.path.join(model_dir, "pytorch_model.bin"),
        os.path.join(model_dir, "model.safetensors"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    pths = [p for p in os.listdir(model_dir) if p.lower().endswith(".pth")]
    if pths:
        return os.path.join(model_dir, sorted(pths)[0])
    return ""


def _run_custom(img):
    model_dir = os.environ.get("UNIMERNET_MODEL_PATH", "")
    if not model_dir or not os.path.isdir(model_dir):
        return None, f"model dir missing: {model_dir or '<empty>'}"
    weight_path = _pick_weight(model_dir)
    if not weight_path:
        return None, f"weight missing in: {model_dir}"
    try:
        import torch
        import unimernet
        from omegaconf import OmegaConf
        from unimernet.models.unimernet.unimernet import UniMERModel
        from unimernet.processors import load_processor
    except Exception as e:
        return None, f"import failed: {e}"
    try:
        base_cfg = os.path.join(os.path.dirname(unimernet.__file__), "configs", "models", "unimernet_base.yaml")
        cfg = OmegaConf.load(base_cfg)
        cfg.model.tokenizer_config.path = model_dir
        cfg.model.model_config.model_name = model_dir
        cfg.model.load_pretrained = False
        cfg.model.load_finetuned = True
        cfg.model.finetuned = weight_path
        model = UniMERModel.from_config(cfg.model)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)
        model.eval()
        vis_cfg = None
        try:
            vis_cfg = cfg.preprocess.vis_processor.eval
        except Exception:
            vis_cfg = None
        vis_processor = load_processor("formula_image_eval", vis_cfg)
        image = vis_processor(img).unsqueeze(0).to(device)
        out = model.generate({"image": image})
        if isinstance(out, dict):
            pred = out.get("pred_str", out.get("preds"))
            if isinstance(pred, (list, tuple)):
                pred = pred[0] if pred else ""
            if pred is not None:
                return _normalize(pred), None
        return _normalize(out), None
    except Exception as e:
        return None, f"infer failed: {e}"


def _try_module(mod, img):
    for fn in ("predict", "infer", "inference", "recognize", "run"):
        f = getattr(mod, fn, None)
        if callable(f):
            return _normalize(f(img))
    for cls_name in ("UniMERModel", "UniMERNet", "UniMERNetModel", "UniMERNetPredictor"):
        cls = getattr(mod, cls_name, None)
        if cls is None:
            continue
        model = None
        try:
            if hasattr(cls, "from_pretrained"):
                model_path = os.environ.get("UNIMERNET_MODEL_PATH", "")
                if model_path:
                    model = cls.from_pretrained(model_path)
                else:
                    model = cls.from_pretrained()
            else:
                model = cls()
        except Exception:
            model = None
        if model is None:
            continue
        for meth in ("predict", "infer", "__call__"):
            m = getattr(model, meth, None)
            if callable(m):
                return _normalize(m(img))
    return None


try:
    img_path = sys.argv[1]
    img = Image.open(img_path)
    pred, err = _run_custom(img)
    if pred:
        print(json.dumps({"ok": True, "result": pred}))
        sys.exit(0)
    tried = []
    for mod_name in ("unimernet.models", "unimernet.models.unimernet.unimernet", "demo", "unimernet"):
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            tried.append(f"{mod_name}: {e}")
            continue
        out = _try_module(mod, img)
        if out:
            print(json.dumps({"ok": True, "result": out}))
            sys.exit(0)
    msg = "No usable UniMERNet entry point."
    if err:
        msg += f" {err}"
    if tried:
        msg += " | " + " | ".join(tried[-3:])
    print(json.dumps({"ok": False, "error": msg}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
""")

        try:
            deps_python = get_unimernet_python()
            proc = subprocess.run(
                [deps_python, "-c", subprocess_code, tmp_path],
                capture_output=True, timeout=120, text=True,
                encoding="utf-8", errors="replace",
                env=self._build_subprocess_env("unimernet"),
            )
            output = (proc.stdout or "").strip()
            if not output:
                raise RuntimeError(f"subprocess no output: stderr={proc.stderr[:200]}")
            m = re.search(r"\{.*\}", output)
            if not m:
                raise RuntimeError(f"subprocess no output: {output[:200]}")
            result = json.loads(m.group())
            if result.get("ok"):
                self._unimernet_subprocess_ready = True
                return result.get("result", "")
            raise RuntimeError(result.get("error", "error"))
        except subprocess.TimeoutExpired:
            raise RuntimeError("UniMERNet error")
        except Exception as e:
            self._emit(f"[ERROR] UniMERNet subprocess error: {e}")
            raise
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _run_pix2text(self, pil_img: Image.Image, mode: str = "formula") -> str:
        """通过子进程运行 pix2text，避免与 pix2tex 依赖冲突
        
        Args:
            pil_img: PIL 图片
            mode: 识别模式
                - "formula": 只识别公式（默认）
                - "text": 只识别文字
                - "text_formula": 混合识别文字+公式
                - "mixed": 通用识别（自动检测）
                - "page": 整页识别（含布局分析）
                - "table": 表格识别
        """
        if not self._pix2text_subprocess_ready:
            raise RuntimeError("Pix2Text 子进程未就绪")
        return self._run_pix2text_subprocess(pil_img, mode)

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
                import subprocess
                import textwrap
                deps_python = get_pix2text_python()
                subprocess_code = textwrap.dedent(r"""
import sys, json
import os
from PIL import Image

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

_bootstrap_shared_torch()

def _pick_device():
    try:
        import torch
        torch_cuda = torch.cuda.is_available()
    except Exception:
        torch_cuda = False
    try:
        import onnxruntime as ort
        ort_cuda = "CUDAExecutionProvider" in (ort.get_available_providers() or [])
    except Exception:
        ort_cuda = False
    return "cuda" if (torch_cuda and ort_cuda) else "cpu"

try:
    from pix2text import Pix2Text
    import warnings
    warnings.filterwarnings("ignore")
    device = _pick_device()

    def _build_p2t(dev, enable_table=False):
        errs = []

        # Prefer deterministic legacy MFR path first to avoid unstable auto-selection branches.
        stable_cfg = {
            "layout": {"model_type": "DocYoloLayoutParser"},
            "text_formula": {
                "formula": {
                    "model_name": "mfr",
                    "model_backend": "onnx",
                }
            },
        }
        try:
            return Pix2Text.from_config(
                total_configs=stable_cfg,
                device=dev,
                enable_table=enable_table,
            )
        except Exception as e:
            errs.append(f"stable(mfr): {e}")

        try:
            return Pix2Text.from_config(device=dev, enable_table=enable_table)
        except Exception as e:
            errs.append(f"from_config: {e}")
        try:
            # fallback: same as manual bootstrap command used by users
            return Pix2Text(device=dev, enable_table=enable_table)
        except Exception as e:
            errs.append(f"Pix2Text(): {e}")
            raise RuntimeError("; ".join(errs))

    p2t = _build_p2t(device, enable_table=False)
    p2t_table = None

    def _get_table_model():
        global p2t_table
        if p2t_table is None:
            p2t_table = _build_p2t(device, enable_table=True)
        return p2t_table

    print(json.dumps({"ready": True, "ok": True, "device": device}), flush=True)
except Exception as e:
    print(json.dumps({"ready": True, "ok": False, "error": str(e)}), flush=True)
    p2t = None
    p2t_table = None


def _do_mode(img, mode):
    if not p2t:
        return None, "pix2text not ready"
    if mode == "formula":
        result = p2t.recognize_formula(img)
    elif mode == "text":
        result = p2t.recognize_text(img)
    elif mode == "text_formula":
        out = p2t.recognize_text_formula(img)
        parts = []
        for item in out:
            if isinstance(item, dict):
                t = item.get("type", "")
                txt = item.get("text", "")
                if t == "isolated" or t == "embedding":
                    parts.append(f"$${txt}$$" if t == "isolated" else f"${txt}$")
                else:
                    parts.append(txt)
            else:
                parts.append(str(item))
        result = " ".join(parts)
    elif mode == "mixed":
        out = p2t.recognize(img)
        if isinstance(out, str):
            result = out
        elif isinstance(out, list):
            parts = []
            for item in out:
                if isinstance(item, dict):
                    parts.append(item.get("text", str(item)))
                else:
                    parts.append(str(item))
            result = " ".join(parts)
        else:
            result = str(out)
    elif mode == "page":
        out = p2t.recognize_page(img)
        if isinstance(out, dict):
            result = out.get("text", str(out))
        else:
            result = str(out)
    elif mode == "table":
        p2t_for_table = p2t
        try:
            p2t_for_table = _get_table_model()
        except Exception:
            p2t_for_table = p2t
        table_ocr = getattr(p2t_for_table, "table_ocr", None)
        if callable(table_ocr):
            result = table_ocr(img)
        elif hasattr(table_ocr, 'recognize') and callable(table_ocr.recognize):
            result = table_ocr.recognize(img)
        elif hasattr(table_ocr, '__call__'):
            result = table_ocr.__call__(img)
        else:
            if hasattr(table_ocr, 'ocr'):
                result = table_ocr.ocr(img)
            else:
                result = p2t_for_table.recognize(img)
        if isinstance(result, dict):
            result = result.get("html", result.get("text", str(result)))
    else:
        result = p2t.recognize_formula(img)

    if not isinstance(result, str):
        result = str(result)
    return result.strip(), None


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
    try:
        img = Image.open(img_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"open image failed: {e}"}), flush=True)
        continue
    result, err = _do_mode(img, mode)
    if result is not None:
        print(json.dumps({"ok": True, "result": result}), flush=True)
    else:
        print(json.dumps({"ok": False, "error": err or "pix2text error"}), flush=True)
""").strip()
                proc = subprocess.Popen(
                    [deps_python, "-u", "-c", subprocess_code],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=self._build_subprocess_env("pix2text"),
                )
                self._pix2text_worker = proc
                return True
            except Exception as e:
                self._emit(f"[ERROR] pix2text worker start failed: {e}")
                self._pix2text_worker = None
                return False

    def _run_pix2text_worker(self, img_path: str, mode: str) -> str:
        import json
        proc = self._pix2text_worker
        if not proc or proc.poll() is not None:
            raise RuntimeError("pix2text worker not running")
        try:
            payload = json.dumps({"image": img_path, "mode": mode})
            proc.stdin.write(payload + "\n")
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
            try:
                data = json.loads(line)
            except Exception:
                continue
            if data.get("ready") and not data.get("result") and not data.get("error"):
                continue
            if data.get("ok"):
                self._pix2text_subprocess_ready = True
                return data.get("result", "")
            raise RuntimeError(data.get("error", "pix2text error"))
        raise RuntimeError("pix2text worker no output")

    def _run_pix2text_subprocess(self, pil_img: Image.Image, mode: str = "formula") -> str:
        """Run pix2text inference via subprocess."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            pil_img.save(tmp, format="PNG")

        # table 模式优先使用一次性子进程（带超时），避免 worker 长时间无输出造成界面“识别中”卡死。
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
                try:
                    if self._auto_repair_isolated_torch("pix2text", str(e)):
                        if self._ensure_pix2text_worker():
                            result = self._run_pix2text_worker(tmp_path, mode)
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                            return result
                except Exception as e2:
                    self._emit(f"[WARN] pix2text auto-repair retry failed: {e2}")
        else:
            try:
                print("[INFO] pix2text table mode: use one-shot subprocess (timeout protected)", flush=True)
            except Exception:
                pass

        subprocess_code = textwrap.dedent(r"""
            import sys, json
            import os
            from PIL import Image
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
            _bootstrap_shared_torch()
            def _pick_device():
                try:
                    import torch
                    torch_cuda = torch.cuda.is_available()
                except Exception:
                    torch_cuda = False
                try:
                    import onnxruntime as ort
                    ort_cuda = "CUDAExecutionProvider" in (ort.get_available_providers() or [])
                except Exception:
                    ort_cuda = False
                return "cuda" if (torch_cuda and ort_cuda) else "cpu"
            try:
                from pix2text import Pix2Text
                import warnings
                warnings.filterwarnings("ignore")

                img_path = sys.argv[1]
                mode = sys.argv[2] if len(sys.argv) > 2 else "formula"
                device = _pick_device()
                enable_table = (mode == "table")
                stable_cfg = {
                    "layout": {"model_type": "DocYoloLayoutParser"},
                    "text_formula": {
                        "formula": {
                            "model_name": "mfr",
                            "model_backend": "onnx",
                        }
                    },
                }
                try:
                    p2t = Pix2Text.from_config(
                        total_configs=stable_cfg,
                        device=device,
                        enable_table=enable_table,
                    )
                except Exception:
                    try:
                        p2t = Pix2Text.from_config(device=device, enable_table=enable_table)
                    except Exception:
                        # fallback for first-run bootstrap in isolated env
                        p2t = Pix2Text(device=device, enable_table=enable_table)
                img = Image.open(img_path)

                if mode == "formula":
                    result = p2t.recognize_formula(img)
                elif mode == "text":
                    result = p2t.recognize_text(img)
                elif mode == "text_formula":
                    out = p2t.recognize_text_formula(img)
                    parts = []
                    for item in out:
                        if isinstance(item, dict):
                            t = item.get("type", "")
                            txt = item.get("text", "")
                            if t == "isolated" or t == "embedding":
                                parts.append(f"$${txt}$$" if t == "isolated" else f"${txt}$")
                            else:
                                parts.append(txt)
                        else:
                            parts.append(str(item))
                    result = " ".join(parts)
                elif mode == "mixed":
                    out = p2t.recognize(img)
                    if isinstance(out, str):
                        result = out
                    elif isinstance(out, list):
                        parts = []
                        for item in out:
                            if isinstance(item, dict):
                                parts.append(item.get("text", str(item)))
                            else:
                                parts.append(str(item))
                        result = " ".join(parts)
                    else:
                        result = str(out)
                elif mode == "page":
                    out = p2t.recognize_page(img)
                    if isinstance(out, dict):
                        result = out.get("text", str(out))
                    else:
                        result = str(out)
                elif mode == "table":
                    table_ocr = p2t.table_ocr
                    if callable(table_ocr):
                        result = table_ocr(img)
                    elif hasattr(table_ocr, 'recognize') and callable(table_ocr.recognize):
                        result = table_ocr.recognize(img)
                    elif hasattr(table_ocr, '__call__'):
                        result = table_ocr.__call__(img)
                    else:
                        if hasattr(table_ocr, 'ocr'):
                            result = table_ocr.ocr(img)
                        else:
                            result = p2t.recognize(img)
                    if isinstance(result, dict):
                        result = result.get("html", result.get("text", str(result)))
                else:
                    result = p2t.recognize_formula(img)

                if not isinstance(result, str):
                    result = str(result)
                result = result.strip()
                print(json.dumps({"ok": True, "result": result}))
            except Exception as e:
                import traceback
                print(json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()}))
        """).strip()

        try:
            deps_python = get_pix2text_python()
            timeout = 300 if mode in ("page", "table") else 120
            proc = subprocess.run(
                [deps_python, "-c", subprocess_code, tmp_path, mode],
                capture_output=True, timeout=timeout, text=True,
                encoding="utf-8", errors="replace",
                env=self._build_subprocess_env("pix2text"),
            )
            output = (proc.stdout or "").strip()
            if not output:
                raise RuntimeError(f"subprocess no output: stderr={proc.stderr[:200]}")
            m = re.search(r"\{.*\}", output)
            if not m:
                raise RuntimeError(f"subprocess no output: {output[:200]}")
            result = json.loads(m.group())
            if result.get("ok"):
                return result.get("result", "")
            raise RuntimeError(result.get("error", "error"))
        except subprocess.TimeoutExpired:
            raise RuntimeError("pix2text error")
        except Exception as e:
            self._emit(f"[ERROR] pix2text subprocess error: {e}")
            raise
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _lazy_load_pix2text(self):
        if self._pix2text_subprocess_ready or self._pix2text_import_failed:
            return self._pix2text_subprocess_ready
        try:
            _dbg_env = self._build_subprocess_env("pix2text")
            _dbg_site = (_dbg_env.get("PIX2TEXT_SHARED_TORCH_SITE", "") or _dbg_env.get("LATEXSNIPPER_SHARED_TORCH_SITE", "") or "").strip()
            self._emit(f"[DEBUG] pix2text shared torch site: {_dbg_site or '<empty>'}")
            _dbg_pp = (_dbg_env.get("PYTHONPATH", "") or "").strip()
            if _dbg_pp:
                self._emit(f"[DEBUG] pix2text subprocess PYTHONPATH: {_dbg_pp}")
        except Exception:
            pass

        def _extract_json(text: str):
            txt = (text or "").strip()
            if not txt:
                return None
            for line in reversed(txt.splitlines()):
                s = line.strip()
                if not s:
                    continue
                if s.startswith("{") and s.endswith("}"):
                    try:
                        return json.loads(s)
                    except Exception:
                        pass
            m = re.search(r"\{.*\}", txt, re.S)
            if not m:
                return None
            try:
                return json.loads(m.group())
            except Exception:
                return None

        def _emit_pix2text_stack_hint(err_text: str):
            t = (err_text or "").strip()
            if not t:
                return
            if "_SENTENCE_TRANSFORMERS_TASKS_TO_MODEL_LOADERS" in t:
                self._emit(
                    "[HINT] 检测到 optimum/transformers 兼容异常，"
                    "请在依赖向导重新安装 CORE（会升级 optimum 并复验）。"
                )
            if "cannot import name 'GenerationMixin' from 'transformers.generation'" in t:
                self._emit(
                    "[HINT] transformers 未识别到可用 torch（常见于 torch metadata 缺失）。"
                    "请在依赖向导重装 HEAVY 层以修复 torch/torchvision/torchaudio 元数据。"
                )

        def _run_bootstrap(pyexe: str) -> bool:
            bootstrap_code = textwrap.dedent(r"""
                import json
                import os, sys
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
                _bootstrap_shared_torch()
                try:
                    from pix2text import Pix2Text
                    import warnings
                    warnings.filterwarnings("ignore")
                    stable_cfg = {
                        "layout": {"model_type": "DocYoloLayoutParser"},
                        "text_formula": {
                            "formula": {
                                "model_name": "mfr",
                                "model_backend": "onnx",
                            }
                        },
                    }
                    try:
                        Pix2Text.from_config(
                            total_configs=stable_cfg,
                            device="cpu",
                            enable_table=False,
                        )
                    except Exception:
                        Pix2Text.from_config(device="cpu", enable_table=False)
                    print(json.dumps({"ok": True}))
                except Exception as e:
                    print(json.dumps({"ok": False, "error": str(e)}))
            """).strip()
            try:
                proc = subprocess.run(
                    [pyexe, "-c", bootstrap_code],
                    capture_output=True,
                    timeout=900,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._build_subprocess_env("pix2text"),
                )
            except subprocess.TimeoutExpired:
                self._emit("[WARN] pix2text bootstrap timeout (>900s)")
                return False
            boot_out = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
            boot_result = _extract_json(boot_out)
            if boot_result and boot_result.get("ok"):
                self._emit("[INFO] pix2text bootstrap success")
                return True
            err = (boot_result or {}).get("error") or (boot_out[:200] if boot_out else "unknown")
            self._emit(f"[WARN] pix2text bootstrap failed: {err}")
            _emit_pix2text_stack_hint(err)
            return False

        try:
            deps_python = get_pix2text_python()
            probe_code = textwrap.dedent(r"""
                import json
                import os, sys
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
                _bootstrap_shared_torch()
                try:
                    import pix2text
                    from pix2text import Pix2Text
                    ver = getattr(pix2text, "__version__", "")
                    try:
                        if not isinstance(ver, str):
                            ver = getattr(ver, "__version__", None) or str(ver)
                    except Exception:
                        ver = ""
                    stable_cfg = {
                        "layout": {"model_type": "DocYoloLayoutParser"},
                        "text_formula": {
                            "formula": {
                                "model_name": "mfr",
                                "model_backend": "onnx",
                            }
                        },
                    }
                    try:
                        Pix2Text.from_config(
                            total_configs=stable_cfg,
                            device="cpu",
                            enable_table=False,
                        )
                    except Exception as init_e:
                        print(json.dumps({"ok": False, "ver": ver, "error": f"probe_init: {init_e}"}))
                    else:
                        print(json.dumps({"ok": True, "ver": ver}))
                except Exception as e:
                    print(json.dumps({"ok": False, "error": str(e)}))
            """).strip()
            probe_timed_out = False
            try:
                proc = subprocess.run(
                    [deps_python, "-c", probe_code],
                    capture_output=True,
                    timeout=120,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._build_subprocess_env("pix2text"),
                )
                output = "\n".join([(proc.stdout or ""), (proc.stderr or "")]).strip()
                result = _extract_json(output)
            except subprocess.TimeoutExpired:
                probe_timed_out = True
                result = None
                self._emit("[WARN] pix2text probe timeout (>120s), fallback to bootstrap init")

            if probe_timed_out or not (result and result.get("ok")):
                self._emit("[WARN] pix2text probe failed, trying bootstrap init...")
                if not _run_bootstrap(deps_python):
                    repair_reason = ""
                    try:
                        repair_reason = (result or {}).get("error", "") or output
                    except Exception:
                        repair_reason = ""
                    if self._auto_repair_isolated_torch("pix2text", repair_reason):
                        self._emit("[INFO] pix2text 已执行自动回退，重试 bootstrap...")
                        if not _run_bootstrap(deps_python):
                            self._pix2text_import_failed = True
                            return False
                    else:
                        self._pix2text_import_failed = True
                        return False
            else:
                ver = (result or {}).get("ver", "") or "unknown"
                self._emit(f"[INFO] pix2text probe ok (ver={ver})")

            worker_ready = False
            try:
                worker_ready = bool(self._ensure_pix2text_worker())
            except Exception as e:
                self._emit(f"[WARN] pix2text worker start skipped: {e}")
            if not worker_ready:
                self._emit("[WARN] pix2text worker not ready after probe/bootstrap")
                self._pix2text_subprocess_ready = False
                return False

            self._pix2text_subprocess_ready = True
            self._pix2text_import_failed = False
            return True
        except Exception as e:
            self._emit(f"[WARN] pix2text lazy load exception: {e}")
            self._pix2text_import_failed = True
            return False

    def _lazy_load_unimernet(self):
        if self._unimernet_subprocess_ready or self._unimernet_import_failed:
            return self._unimernet_subprocess_ready
        if not os.environ.get("UNIMERNET_PYEXE") and not os.environ.get("UNIMERNET_MODEL_PATH"):
            self._emit("[DEBUG] unimernet preheat skipped: env not configured")
            return False
        try:
            self._emit("[INFO] 预加载 unimernet（启动阶段）...")
            try:
                _dbg_env = self._build_subprocess_env("unimernet")
                _dbg_site = (_dbg_env.get("PIX2TEXT_SHARED_TORCH_SITE", "") or _dbg_env.get("LATEXSNIPPER_SHARED_TORCH_SITE", "") or "").strip()
                self._emit(f"[DEBUG] unimernet shared torch site: {_dbg_site or '<empty>'}")
            except Exception:
                pass
            deps_python = get_unimernet_python()
            probe_code = textwrap.dedent(r"""
                import json, importlib.util, os
                ok = False
                try:
                    ok = importlib.util.find_spec("unimernet") is not None
                except Exception:
                    ok = False
                model_dir = os.environ.get("UNIMERNET_MODEL_PATH", "")
                weight_ok = False
                if model_dir and os.path.isdir(model_dir):
                    for n in os.listdir(model_dir):
                        if n.lower().endswith(('.pth', '.bin', '.safetensors')):
                            weight_ok = True
                            break
                print(json.dumps({"ok": ok, "model_ok": weight_ok}))
            """).strip()
            proc = subprocess.run(
                [deps_python, "-c", probe_code],
                capture_output=True, timeout=20, text=True,
                encoding="utf-8", errors="replace",
                env=self._build_subprocess_env("unimernet"),
            )
            output = (proc.stdout or "").strip()
            m = re.search(r"\{.*\}", output)
            if not m:
                err_preview = ((proc.stderr or "").strip() or output or "no output")[:200]
                self._emit(f"[WARN] unimernet probe no JSON output: {err_preview}")
                self._unimernet_import_failed = True
                return False
            result = json.loads(m.group())
            if result.get("ok") and result.get("model_ok"):
                self._emit("[INFO] unimernet probe ok (pkg=ok, weight=ok)")
                self._emit("[INFO] unimernet preheat: starting worker and warmup inference...")
                if not self._ensure_unimernet_worker():
                    self._emit("[WARN] unimernet worker start failed during preheat")
                    self._unimernet_import_failed = True
                    self._unimernet_subprocess_ready = False
                    return False
                warmup_ok = False
                warmup_err = ""
                warmup_path = ""
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        warmup_path = tmp.name
                    # 触发一次最小推理，确保首次识别前完成模型/设备热身
                    Image.new("RGB", (32, 32), (255, 255, 255)).save(warmup_path, format="PNG")
                    _ = self._run_unimernet_worker(warmup_path)
                    warmup_ok = True
                except Exception as e:
                    warmup_err = str(e)
                finally:
                    if warmup_path:
                        try:
                            os.unlink(warmup_path)
                        except Exception:
                            pass

                if not warmup_ok:
                    self._emit(f"[WARN] unimernet warmup inference failed: {warmup_err}")
                    self._stop_unimernet_worker()
                    self._unimernet_import_failed = True
                    self._unimernet_subprocess_ready = False
                    return False

                self._unimernet_subprocess_ready = True
                self._unimernet_import_failed = False
                self._emit("[INFO] unimernet worker preheat ok")
                return True
            self._emit(
                f"[WARN] unimernet probe failed (pkg_ok={bool(result.get('ok'))}, "
                f"model_ok={bool(result.get('model_ok'))})"
            )
            self._unimernet_import_failed = True
            return False
        except Exception as e:
            self._emit(f"[WARN] unimernet preheat exception: {e}")
            self._unimernet_import_failed = True
            return False

    def _run_pix2tex(self, pil_img: Image.Image) -> str:
        if self._is_frozen:
            if not self._pix2tex_subprocess_route_logged:
                self._emit("[INFO] [subprocess] pix2tex 将在子进程执行推理（打包模式）")
                self._pix2tex_subprocess_route_logged = True
            return self._run_pix2tex_subprocess(pil_img)
        self._ensure_pix2tex()
        self._ensure_pix2tex_device()
        if not self.pix2tex_model:
            raise RuntimeError("pix2tex not ready")
        try:
            return self.pix2tex_model(pil_img)
        except Exception as e:
            self._emit(f"[ERROR] pix2tex error: {e}")
            raise

    def _stop_pix2tex_worker(self):
        proc = getattr(self, "_pix2tex_worker", None)
        self._pix2tex_worker = None
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

    def _ensure_pix2tex_worker(self) -> bool:
        try:
            proc = self._pix2tex_worker
            if proc and proc.poll() is None:
                return True
        except Exception:
            proc = None
        with self._pix2tex_worker_lock:
            try:
                proc = self._pix2tex_worker
                if proc and proc.poll() is None:
                    return True
            except Exception:
                proc = None
            try:
                import subprocess
                import textwrap
                deps_python = get_deps_python()
                subprocess_code = textwrap.dedent(r"""
import sys, json, base64, io
from PIL import Image

try:
    import torch
    import warnings
    warnings.filterwarnings(
        "ignore",
        message=r"^Pydantic serializer warnings:",
        category=UserWarning,
    )
    from pix2tex.cli import LatexOCR
    ocr = LatexOCR()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(json.dumps({"ready": True, "ok": True, "device": dev}), flush=True)
except Exception as e:
    print(json.dumps({"ready": True, "ok": False, "error": str(e)}), flush=True)
    ocr = None

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    if line == "__quit__":
        break
    try:
        req = json.loads(line)
    except Exception:
        req = {"image_b64": line}
    if req.get("ping"):
        print(json.dumps({"ok": True, "ready": True}), flush=True)
        continue
    img_b64 = req.get("image_b64", "")
    if not img_b64:
        print(json.dumps({"ok": False, "error": "image data missing"}), flush=True)
        continue
    if not ocr:
        print(json.dumps({"ok": False, "error": "pix2tex not ready"}), flush=True)
        continue
    try:
        img_data = base64.b64decode(img_b64)
        img = Image.open(io.BytesIO(img_data))
        result = ocr(img)
        if not isinstance(result, str):
            result = str(result)
        result = result.strip()
        print(json.dumps({"ok": True, "result": result}), flush=True)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), flush=True)
""").strip()
                proc = subprocess.Popen(
                    [deps_python, "-u", "-c", subprocess_code],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                self._pix2tex_worker = proc
                return True
            except Exception as e:
                self._emit(f"[ERROR] pix2tex worker start failed: {e}")
                self._pix2tex_worker = None
                return False

    def _run_pix2tex_worker(self, img_b64: str | None = None, ping: bool = False) -> str:
        import json
        proc = self._pix2tex_worker
        if not proc or proc.poll() is not None:
            raise RuntimeError("pix2tex worker not running")
        try:
            if ping:
                payload_obj = {"ping": True}
            else:
                payload_obj = {"image_b64": img_b64 or ""}
            payload = json.dumps(payload_obj)
            proc.stdin.write(payload + "\n")
            proc.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"pix2tex worker send failed: {e}")

        for _ in range(300):
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if data.get("ready") and not data.get("result") and not data.get("error"):
                if ping and data.get("ok"):
                    self._pix2tex_subprocess_ready = True
                    self._pix2tex_load_error = None
                    return ""
                continue
            if data.get("ok"):
                self._pix2tex_subprocess_ready = True
                self._pix2tex_load_error = None
                return data.get("result", "")
            raise RuntimeError(data.get("error", "pix2tex error"))
        raise RuntimeError("pix2tex worker no output")

    def _warmup_pix2tex_worker(self) -> bool:
        try:
            if not self._ensure_pix2tex_worker():
                return False
        except Exception as e:
            return False

        # 先做 ping，确认 worker 进程就绪；这是是否“可用”的硬条件。
        try:
            self._run_pix2tex_worker(ping=True)
        except Exception:
            try:
                self._stop_pix2tex_worker()
            except Exception:
                pass
            return False

        warmup_b64 = ""
        try:
            import io, base64
            from PIL import ImageDraw
            buf = io.BytesIO()
            # 使用带简单前景内容的小图预热，避免“纯白空图”触发第三方库边界错误。
            warmup_img = Image.new("RGB", (160, 56), (255, 255, 255))
            draw = ImageDraw.Draw(warmup_img)
            draw.text((12, 14), "x+1=2", fill=(0, 0, 0))
            warmup_img.save(buf, format="PNG")
            warmup_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            _ = self._run_pix2tex_worker(warmup_b64)
            return True
        except Exception as e:
            # 预热推理失败不视为模型不可用；首次真实识别仍会正常重试。
            self._emit(f"[WARN] [subprocess] pix2tex warmup inference skipped: {e}")
            self._pix2tex_subprocess_ready = True
            self._pix2tex_load_error = None
            return True

    def _run_pix2tex_subprocess(self, pil_img: Image.Image) -> str:
        import io, base64
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        try:
            if self._ensure_pix2tex_worker():
                return self._run_pix2tex_worker(img_b64)
        except Exception as e:
            self._emit(f"[WARN] pix2tex worker fallback: {e}")
            self._stop_pix2tex_worker()
        subprocess_code = textwrap.dedent(r"""
            import sys, json, base64, io
            from PIL import Image
            try:
                import warnings
                warnings.filterwarnings(
                    "ignore",
                    message=r"^Pydantic serializer warnings:",
                    category=UserWarning,
                )
                from pix2tex.cli import LatexOCR
                img_data = base64.b64decode(sys.argv[1])
                img = Image.open(io.BytesIO(img_data))
                model = LatexOCR()
                result = model(img)
                if not isinstance(result, str):
                    result = str(result)
                print(json.dumps({"ok": True, "result": result}))
            except Exception as e:
                print(json.dumps({"ok": False, "error": str(e)}))
        """).strip()
        deps_python = get_deps_python()
        proc = subprocess.run(
            [deps_python, "-c", subprocess_code, img_b64],
            capture_output=True, timeout=120, text=True,
            encoding="utf-8", errors="replace"
        )
        output = (proc.stdout or "").strip()
        m = re.search(r"\{.*\}", output)
        if not m:
            raise RuntimeError(f"subprocess no output: {proc.stderr[:200]}")
        result = json.loads(m.group())
        if result.get("ok"):
            self._pix2tex_subprocess_ready = True
            self._pix2tex_load_error = None
            return result.get("result", "")
        raise RuntimeError(result.get("error", "pix2tex subprocess error"))

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





