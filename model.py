
from PyQt6.QtCore import QObject, pyqtSignal

import subprocess, sys, json, os, shutil, re
os.environ.setdefault("ORT_DISABLE_AZURE", "1")
import threading
from PIL import Image

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

class ModelWrapper(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.device = "cpu"
        self.torch = None
        self.pix2tex_model = None
        self.pix2text_model = None
        self._pix2text_import_failed = False
        self._pix2text_subprocess_ready = False  # 子进程模式
        self._pix2tex_subprocess_ready = False   # pix2tex 也支持子进程模式
        self._pix2tex_load_error = None          # 记录加载失败的错误信息
        self._providers_logged = False
        self._ort_gpu_available = None
        self._pix2tex_inited = False
        self._pix2tex_init_lock = threading.Lock()
        self._ort_probe_raw = ""
        
        # 判断是否是打包模式
        self._is_frozen = getattr(sys, 'frozen', False)
        
        if self._is_frozen:
            # 打包模式：所有 AI 操作都在子进程中运行
            self._emit("[INFO] 打包模式：AI 模型将在子进程中运行")
            self._probe_subprocess_models()
        else:
            # 开发模式：可以在主进程中加载（如果依赖可用）
            self._init_torch()
            self._probe_onnxruntime()
            # 尝试加载 pix2tex，但失败不阻塞程序启动
            try:
                self._ensure_pix2tex()
            except Exception as e:
                self._pix2tex_load_error = str(e)
                self._emit(f"[WARN] pix2tex 初始化失败，程序将继续启动: {e}")
                self._emit("[HINT] 可在【设置】→【依赖管理向导】中修复依赖")
    
    def _probe_subprocess_models(self):
        """打包模式下，通过子进程探测可用的模型"""
        self._probe_onnxruntime()
        
        # 探测 pix2tex
        self._emit("[INFO] 正在探测 pix2tex (子进程模式)...")
        probe_code = '''
import json, sys
try:
    import torch
    from pix2tex.cli import LatexOCR
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(json.dumps({"ok": True, "device": device}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
'''
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", probe_code],
                capture_output=True, timeout=30, text=True
            )
            output = proc.stdout.strip()
            m = re.search(r'\{.*\}', output)
            if m:
                result = json.loads(m.group())
                if result.get("ok"):
                    self._pix2tex_subprocess_ready = True
                    self.device = result.get("device", "cpu")
                    self._emit(f"[INFO] pix2tex 子进程可用 (device={self.device})")
                else:
                    error_msg = result.get('error', '未知错误')
                    self._pix2tex_load_error = error_msg  # 记录错误
                    self._emit(f"[WARN] pix2tex 不可用: {error_msg}")
            else:
                # 无法解析 JSON，可能有错误输出
                stderr_msg = proc.stderr.strip() if proc.stderr else "无输出"
                self._pix2tex_load_error = stderr_msg[:200]
                self._emit(f"[WARN] pix2tex 探测失败: {stderr_msg[:200]}")
        except Exception as e:
            self._pix2tex_load_error = str(e)
            self._emit(f"[WARN] pix2tex 探测失败: {e}")
        
        # 探测 pix2text
        self._lazy_load_pix2text()

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
        """检查 pix2tex 模型是否可用"""
        if self._is_frozen:
            return self._pix2tex_subprocess_ready
        return self._pix2tex_inited and self.pix2tex_model is not None
    
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
        if model_name.startswith("pix2text"):
            return self.is_pix2text_ready()
        else:
            return self.is_ready()
    
    def get_error(self) -> str | None:
        """获取加载错误信息，如果没有错误返回 None"""
        return self._pix2tex_load_error
    
    def get_status_text(self) -> str:
        """获取模型状态描述文本"""
        if self._pix2tex_load_error:
            return f"❌ 模型加载失败: {self._pix2tex_load_error[:50]}..."
        if self.is_ready():
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
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", probe_code],
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
        
        # ⚠️ 检测 onnxruntime 冲突：如果安装了 GPU 版但没有 CUDA provider
        if not self._ort_gpu_available:
            self._check_and_fix_onnxruntime_conflict()

    def _check_and_fix_onnxruntime_conflict(self):
        """检测并尝试修复 onnxruntime / onnxruntime-gpu 冲突"""
        # 检查是否同时安装了两个版本
        check_code = r"""
import json
try:
    import pkg_resources
    installed = {p.key: p.version for p in pkg_resources.working_set}
    has_ort = 'onnxruntime' in installed
    has_ort_gpu = 'onnxruntime-gpu' in installed
    print(json.dumps({"has_ort": has_ort, "has_ort_gpu": has_ort_gpu, 
                      "ort_ver": installed.get('onnxruntime', ''), 
                      "ort_gpu_ver": installed.get('onnxruntime-gpu', '')}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
"""
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", check_code],
                capture_output=True, timeout=10, text=True
            )
            m = re.search(r'\{.*\}', proc.stdout or "")
            if not m:
                return
            info = json.loads(m.group())
            
            has_ort = info.get("has_ort", False)
            has_ort_gpu = info.get("has_ort_gpu", False)
            
            if has_ort and has_ort_gpu:
                # 冲突！两者同时存在
                self._emit(f"[WARN] 检测到 onnxruntime 冲突: onnxruntime={info.get('ort_ver')} 与 onnxruntime-gpu={info.get('ort_gpu_ver')} 同时存在")
                self._emit("[INFO] CPU 版会覆盖 GPU 版的 providers，正在自动修复...")
                self._fix_onnxruntime_conflict(deps_python)
            elif has_ort_gpu and not self._ort_gpu_available:
                # 只有 GPU 版但没有 CUDA provider，可能是 DLL 问题
                self._emit("[WARN] onnxruntime-gpu 已安装但 CUDA provider 不可用")
                self._emit("[HINT] 可能原因：CUDA 版本不匹配或缺少 Visual C++ 运行库")
        except Exception as e:
            self._emit(f"[WARN] onnxruntime 冲突检测失败: {e}")

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
                                  text=True, creationflags=flags)
            
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
            try:
                self._emit("[INFO] 开始加载 pix2tex (首次启动会安装权重，请耐心等待)...")
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
            except ModuleNotFoundError as e:
                self._emit(f"[ERROR] pix2tex 加载失败: {e} ，请重启程序并挂上梯子，因为会重新下载模型权重")
                raise ModuleNotFoundError(f"依赖缺失: {e}") from e
            except Exception as e:
                self._emit(f"[ERROR] pix2tex 加载失败: {e} ，请重启程序并挂上梯子，因为会重新下载模型权重")
                raise
            # 若加载在 CPU 但 GPU 可用 -> 迁移
            if self.device != "cuda" and self.torch and self.torch.cuda.is_available():
                try:
                    self._emit("[INFO] 检测到 GPU 可用, 强制迁移 pix2tex -> cuda")
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
                self._emit(f"[DEBUG] 已更新 pix2tex args.device = {device}")
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
        """检查 pix2text 是否可用（子进程隔离模式）"""
        if self._pix2text_import_failed:
            return None
        if self._pix2text_subprocess_ready:
            return True  # 已验证可用
        
        self._emit("[INFO] 验证 Pix2Text 可用性 (子进程隔离模式)...")
        
        # 使用子进程检测 pix2text 是否可导入
        probe_code = '''
import json
try:
    from pix2text import Pix2Text
    # 只检查能否导入，不实际加载模型（太慢）
    print(json.dumps({"ok": True}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
'''
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", probe_code],
                capture_output=True, timeout=30, text=True
            )
            output = proc.stdout.strip()
            m = re.search(r'\{.*\}', output)
            if m:
                result = json.loads(m.group())
                if result.get("ok"):
                    self._pix2text_subprocess_ready = True
                    self._emit("[INFO] Pix2Text 子进程验证成功")
                    return True
                else:
                    err = result.get("error", "未知错误")
                    self._emit(f"[WARN] Pix2Text 不可用: {err}")
            else:
                self._emit(f"[WARN] Pix2Text 检测输出异常: {output[:200]}")
        except subprocess.TimeoutExpired:
            self._emit("[WARN] Pix2Text 检测超时")
        except Exception as e:
            self._emit(f"[WARN] Pix2Text 检测失败: {e}")
        
        self._pix2text_import_failed = True
        return None

    # -------- 对外预测接口 --------
    def predict(self, pil_img: Image.Image, model_name: str = "pix2tex") -> str:
        """
        识别图片中的内容
        
        Args:
            pil_img: PIL 图片
            model_name: 模型/模式名称
                - "pix2tex": 使用 pix2tex 识别公式（默认）
                - "pix2text": 使用 pix2text 识别公式
                - "pix2text_text": 使用 pix2text 识别纯文字
                - "pix2text_mixed": 使用 pix2text 混合识别（文字+公式）
                - "pix2text_page": 使用 pix2text 整页识别
                - "pix2text_table": 使用 pix2text 表格识别
        """
        # 检查是否有加载错误
        if self._pix2tex_load_error and not self._pix2tex_inited:
            error_msg = f"模型未加载: {self._pix2tex_load_error}\n请在【设置】→【依赖管理向导】中修复依赖"
            self._emit(f"[ERROR] {error_msg}")
            return ""
        
        name = (model_name or "pix2tex").lower()
        
        # pix2text 系列模式
        if name.startswith("pix2text"):
            if self._lazy_load_pix2text():
                # 解析模式
                if name == "pix2text":
                    mode = "formula"
                elif name == "pix2text_text":
                    mode = "text"
                elif name == "pix2text_mixed":
                    mode = "text_formula"
                elif name == "pix2text_page":
                    mode = "page"
                elif name == "pix2text_table":
                    mode = "table"
                else:
                    mode = "formula"
                
                try:
                    return self._run_pix2text(pil_img, mode)
                except Exception as e:
                    self._emit(f"[WARN] Pix2Text ({mode}) 推理失败, 回退 pix2tex: {e}")
        
        # pix2tex 推理
        try:
            return self._run_pix2tex(pil_img)
        except Exception as e:
            self._emit(f"[ERROR] pix2tex 推理失败: {e}")
            return ""

    # -------- pix2tex 推理 --------
    def _run_pix2tex(self, pil_img: Image.Image) -> str:
        # 打包模式：使用子进程
        if self._is_frozen:
            if not self._pix2tex_subprocess_ready:
                raise RuntimeError("pix2tex 子进程未就绪，请先安装依赖")
            return self._run_pix2tex_subprocess(pil_img)
        
        # 开发模式：检查加载错误
        if self._pix2tex_load_error:
            raise RuntimeError(f"模型加载失败: {self._pix2tex_load_error}")
        
        # 开发模式：使用主进程
        self._ensure_pix2tex()
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
                    self._emit(f"[ERROR] 回退 CPU 仍失败: {e3}，你这辈子有了啊")
                    return ""
            self._emit(f"[ERROR] pix2tex 推理失败: {e}")
            return ""

    def _run_pix2tex_subprocess(self, pil_img: Image.Image) -> str:
        """在隔离的子进程中运行 pix2tex"""
        import base64
        import io
        
        # 将图片编码为 base64
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        
        # 子进程代码
        subprocess_code = '''
import sys, json, base64, io
from PIL import Image
try:
    from pix2tex.cli import LatexOCR
    model = LatexOCR()
    img_data = base64.b64decode(sys.argv[1])
    img = Image.open(io.BytesIO(img_data))
    result = model(img).strip()
    print(json.dumps({"ok": True, "result": result}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
'''
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", subprocess_code, img_b64],
                capture_output=True, timeout=60, text=True
            )
            output = proc.stdout.strip()
            if not output:
                raise RuntimeError(f"子进程无输出: stderr={proc.stderr[:200]}")
            
            # 提取 JSON
            m = re.search(r'\{.*\}', output)
            if not m:
                raise RuntimeError(f"无法解析输出: {output[:200]}")
            
            result = json.loads(m.group())
            if result.get("ok"):
                return result.get("result", "")
            else:
                raise RuntimeError(result.get("error", "未知错误"))
        except subprocess.TimeoutExpired:
            raise RuntimeError("pix2tex 推理超时")
        except Exception as e:
            self._emit(f"[ERROR] pix2tex 子进程失败: {e}")
            raise

    # -------- pix2text 推理 --------
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

    def _run_pix2text_subprocess(self, pil_img: Image.Image, mode: str = "formula") -> str:
        """在隔离的子进程中运行 pix2text"""
        import base64
        import io
        import tempfile
        
        # 将图片保存为临时文件（避免命令行参数过长）
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            pil_img.save(tmp, format="PNG")
        
        # 子进程代码 - 支持多种识别模式，从临时文件读取图片
        subprocess_code = '''
import sys, json
from PIL import Image
try:
    from pix2text import Pix2Text
    import warnings
    warnings.filterwarnings("ignore")
    
    p2t = Pix2Text.from_config()
    img_path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "formula"
    img = Image.open(img_path)
    
    if mode == "formula":
        # 只识别公式
        result = p2t.recognize_formula(img)
    elif mode == "text":
        # 只识别文字
        result = p2t.recognize_text(img)
    elif mode == "text_formula":
        # 混合识别文字+公式，返回格式化结果
        out = p2t.recognize_text_formula(img)
        # out 是列表，每个元素有 type 和 text
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
        # 通用识别
        out = p2t.recognize(img)
        # 格式化输出
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
        # 整页识别
        out = p2t.recognize_page(img)
        # 提取文本内容
        if isinstance(out, dict):
            result = out.get("text", str(out))
        else:
            result = str(out)
    elif mode == "table":
        # 表格识别 - 需要正确调用 table_ocr 方法
        table_ocr = p2t.table_ocr
        if callable(table_ocr):
            result = table_ocr(img)
        elif hasattr(table_ocr, 'recognize') and callable(table_ocr.recognize):
            result = table_ocr.recognize(img)
        elif hasattr(table_ocr, '__call__'):
            result = table_ocr.__call__(img)
        else:
            # 如果 table_ocr 是对象，尝试通过 recognize 或 ocr 方法调用
            if hasattr(table_ocr, 'ocr'):
                result = table_ocr.ocr(img)
            else:
                # 回退到 recognize 方法
                result = p2t.recognize(img)
        if isinstance(result, dict):
            result = result.get("html", result.get("text", str(result)))
    else:
        result = p2t.recognize_formula(img)
    
    # 确保 result 是字符串
    if not isinstance(result, str):
        result = str(result)
    result = result.strip()
    print(json.dumps({"ok": True, "result": result}))
except Exception as e:
    import traceback
    print(json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()}))
'''
        try:
            deps_python = get_deps_python()
            proc = subprocess.run(
                [deps_python, "-c", subprocess_code, tmp_path, mode],
                capture_output=True, timeout=120, text=True  # 增加超时时间，page 模式较慢
            )
            output = proc.stdout.strip()
            if not output:
                raise RuntimeError(f"子进程无输出: stderr={proc.stderr[:200]}")
            
            # 提取 JSON
            m = re.search(r'\{.*\}', output)
            if not m:
                raise RuntimeError(f"无法解析输出: {output[:200]}")
            
            result = json.loads(m.group())
            if result.get("ok"):
                return result.get("result", "")
            else:
                raise RuntimeError(result.get("error", "未知错误"))
        except subprocess.TimeoutExpired:
            raise RuntimeError("pix2text 推理超时")
        except Exception as e:
            self._emit(f"[ERROR] pix2text 子进程失败: {e}")
            raise
        finally:
            # 清理临时文件
            try:
                import os
                os.unlink(tmp_path)
            except Exception:
                pass
