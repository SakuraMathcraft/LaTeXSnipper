import threading
import urllib.request
import os
import sys
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtCore import QTimer
from utils import resource_path

subprocess_lock = threading.Lock()

# 需要监控的模块列表（如果这些模块已加载，pip 安装可能会因文件占用失败）
CONFLICT_MODULES = {
    # torch 系列
    "torch", "torchvision", "torchaudio",
    # pix2tex/pix2text 系列
    "pix2tex", "pix2text",
    # onnxruntime
    "onnxruntime", "onnxruntime_gpu",
    # OCR 相关
    "cnocr", "cnstd", "rapidocr", "easyocr",
    # 其他常见冲突模块
    "transformers", "timm", "cv2", "numpy", "scipy",
}

def get_loaded_conflict_modules() -> list[str]:
    """
    检测当前进程中已加载的可能导致安装冲突的模块
    返回已加载的冲突模块名列表
    """
    loaded = []
    for mod_name in CONFLICT_MODULES:
        if mod_name in sys.modules:
            loaded.append(mod_name)
    return loaded

def needs_restart_for_install() -> tuple[bool, list[str]]:
    """
    检查是否需要重启程序才能安全安装依赖
    返回 (need_restart, loaded_modules)
    """
    loaded = get_loaded_conflict_modules()
    return (len(loaded) > 0, loaded)


def safe_run(cmd, cwd=None, shell=False, timeout=None, **popen_kwargs):
    """
    启动子进程并返回 Popen 对象，不预先读取/关闭 stdout。
    透传一切 Popen 参数（如 stdout/stderr/text/encoding/env/bufsize/creationflags 等），
    让调用方（例如 _pip_install）自己控制读取和等待。
    """
    print(f"[RUN] {' '.join(cmd)}")
    # 默认按行读取：如果调用方没指定，给个合理的默认
    popen_kwargs.setdefault("stdout", subprocess.PIPE)
    popen_kwargs.setdefault("stderr", subprocess.STDOUT)
    popen_kwargs.setdefault("text", True)

    # 直接 Popen，剩下的读取/等待由调用方处理
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=shell,
        **popen_kwargs
    )
    return proc

def get_base_dir():
    """
    获取程序运行的基础目录（兼容 PyInstaller 打包）
    - 开发模式：返回源代码目录
    - 打包模式：返回 _MEIPASS 临时解压目录
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 打包后的运行环境
        return Path(sys._MEIPASS)
    else:
        # 源代码运行环境
        return Path(__file__).parent

BASE_DIR = get_base_dir()
print(f"[DEBUG] 程序运行目录: {BASE_DIR}")

class InstallWorker(QThread):
    log_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    done = pyqtSignal(bool)  # True=全部成功

    def __init__(self, pyexe, pkgs, stop_event, pause_event, state_lock, state, state_path, chosen_layers, log_q, mirror=False):
        super().__init__()
        self.mirror = mirror
        self._done_emitted = False
        self.proc = None
        self.pyexe = pyexe
        self.pkgs = pkgs
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.state_lock = state_lock
        self.state = state
        self.state_path = state_path
        self.chosen_layers = chosen_layers
        self.log_q = log_q  # 新增

    def _emit_done_safe(self, ok: bool):
        if not self._done_emitted:
            self._done_emitted = True
            try:
                self.done.emit(ok)
            except RuntimeError:
                pass

    def stop(self):
        """用于从UI触发中断下载"""
        self.stop_event.set()
        if hasattr(self, "proc") and self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            finally:
                self.proc = None

    def run(self):
        """依赖安装线程主函数（稳定版）"""
        try:
            self.log_updated.emit(f"[INFO] 开始检查 {len(self.pkgs)} 个包...")
            self.log_updated.emit(f"[DEBUG] 使用 Python: {self.pyexe}")
            installed_before = _current_installed(self.pyexe)
            self.log_updated.emit(f"[INFO] 当前已安装 {len(installed_before)} 个包")

            # 需要 GPU 版 PyTorch 的层列表
            GPU_LAYERS = ["HEAVY_GPU", "PIX2TEXT_GPU"]
            chosen_layers = self.chosen_layers or []
            needs_gpu = any(layer in chosen_layers for layer in GPU_LAYERS)
            
            # ⚠️ 若安装任何 GPU 层，检查并处理 CPU/GPU 版本冲突
            if needs_gpu:
                # 1. 卸载冲突的 onnxruntime（CPU 版）—— 即使 onnxruntime-gpu 已安装也要卸载
                #    因为两者同时存在时，CPU 版会覆盖 GPU 版的 providers
                if "onnxruntime" in installed_before:
                    self.log_updated.emit("[INFO] 检测到 onnxruntime（CPU），将先卸载以避免与 onnxruntime-gpu 冲突...")
                    self.log_updated.emit("[INFO] 注意：onnxruntime 和 onnxruntime-gpu 不能同时存在！")
                    try:
                        uninstall_cmd = [str(self.pyexe), "-m", "pip", "uninstall", "onnxruntime", "-y"]
                        subprocess.run(uninstall_cmd, timeout=120, creationflags=flags)
                        self.log_updated.emit("[OK] 已卸载冲突的 onnxruntime ✅")
                        installed_before.pop("onnxruntime", None)
                    except Exception as e:
                        self.log_updated.emit(f"[WARN] 卸载 onnxruntime 失败（继续安装）: {e}")
                
                # 2. 检查 PyTorch 是否是 CPU 版本（会导致 DLL 冲突）
                torch_version = installed_before.get("torch", "")
                torchaudio_version = installed_before.get("torchaudio", "")
                # CPU 版本特征：带 +cpu 后缀，或者没有 +cu 后缀（从 PyPI 安装的默认是 CPU 版）
                is_cpu_torch = (
                    "+cpu" in torch_version or 
                    "+cpu" in torchaudio_version or
                    (torch_version and "+cu" not in torch_version and "torch" in installed_before)
                )
                if is_cpu_torch:
                    self.log_updated.emit(f"[WARN] 检测到 CPU 版本 PyTorch ({torch_version})")
                    self.log_updated.emit("[INFO] CPU 与 CUDA 版本混装会导致 DLL 初始化失败，正在卸载...")
                    try:
                        for pkg in ["torch", "torchvision", "torchaudio"]:
                            if pkg in installed_before:
                                uninstall_cmd = [str(self.pyexe), "-m", "pip", "uninstall", pkg, "-y"]
                                subprocess.run(uninstall_cmd, timeout=120, creationflags=flags)
                                installed_before.pop(pkg, None)
                        self.log_updated.emit("[OK] 已卸载 CPU 版本 PyTorch，将重新安装 CUDA 版本 ✅")
                    except Exception as e:
                        self.log_updated.emit(f"[WARN] 卸载 PyTorch 失败: {e}")

            # ⚠️ 反向检测：若安装 HEAVY_CPU，检查是否存在 CUDA 版本 PyTorch
            if "HEAVY_CPU" in chosen_layers and "HEAVY_GPU" not in chosen_layers:
                torch_version = installed_before.get("torch", "")
                # CUDA 版本特征：带 +cu 后缀
                is_cuda_torch = "+cu" in torch_version
                if is_cuda_torch:
                    self.log_updated.emit(f"[WARN] 检测到 CUDA 版本 PyTorch ({torch_version})")
                    self.log_updated.emit("[INFO] 将卸载 CUDA 版本，安装 CPU 版本以节省空间...")
                    try:
                        for pkg in ["torch", "torchvision", "torchaudio"]:
                            if pkg in installed_before:
                                uninstall_cmd = [str(self.pyexe), "-m", "pip", "uninstall", pkg, "-y"]
                                subprocess.run(uninstall_cmd, timeout=120, creationflags=flags)
                                installed_before.pop(pkg, None)
                        self.log_updated.emit("[OK] 已卸载 CUDA 版本 PyTorch ✅")
                    except Exception as e:
                        self.log_updated.emit(f"[WARN] 卸载 PyTorch 失败: {e}")

            # 检查哪些包需要安装
            pending = []
            skipped = []
            for p in self.pkgs:
                pkg_name = re.split(r'[<>=!~ ]', p, 1)[0].lower()
                if pkg_name in installed_before:
                    skipped.append(f"{pkg_name} ({installed_before[pkg_name]})")
                else:
                    pending.append(p)
            
            if skipped:
                self.log_updated.emit(f"[INFO] 跳过已安装: {', '.join(skipped[:10])}{'...' if len(skipped) > 10 else ''}")
            
            if not pending:
                self.log_updated.emit("[INFO] 所有依赖已安装，无需下载。")
                self.progress_updated.emit(100)
                self._emit_done_safe(True)
                return
            
            self.log_updated.emit(f"[INFO] 需要安装 {len(pending)} 个包（跳过 {len(skipped)} 个已安装）")

            total = len(pending)
            done_count = 0
            fail_count = 0
            failed_pkgs = []  # 记录失败的包
            # 判断 torch 安装源策略
            # - 选择 HEAVY_GPU：自动检测 CUDA 版本，使用对应的 CUDA 源
            # - 选择 HEAVY_CPU 或自动补充：使用 CPU 源
            want_gpu_torch = "HEAVY_GPU" in (self.chosen_layers or [])
            want_cpu_torch = not want_gpu_torch and ("CORE" in (self.chosen_layers or []) or "HEAVY_CPU" in (self.chosen_layers or []))
            
            # 获取 CUDA 信息（自动检测）
            cuda_info = get_cuda_info()
            detected_torch_url = cuda_info.get("torch_url")  # 基于检测到的 CUDA 版本
            
            if want_gpu_torch:
                if detected_torch_url:
                    self.log_updated.emit(f"[INFO] 检测到 CUDA {cuda_info.get('version')}，将使用 {cuda_info.get('torch_tag')} 版本 PyTorch")
                else:
                    self.log_updated.emit("[WARN] 未检测到 CUDA，GPU 层将使用默认源（可能是 CPU 版本）")
            
            for i, pkg in enumerate(pending, start=1):
                while not self.pause_event.is_set():
                    if self.stop_event.is_set():
                        self.log_updated.emit("[CANCEL] 用户取消安装。")
                        break
                    time.sleep(0.1)
                if self.stop_event.is_set():
                    self.log_updated.emit("[CANCEL] 用户取消安装。")
                    break

                torch_url = None
                root = re.split(r'[<>=!~ ]', pkg, 1)[0].strip().lower()
                if root in TORCH_NAMES:
                    if want_gpu_torch and detected_torch_url:
                        # 使用自动检测的 CUDA 对应 URL
                        torch_url = detected_torch_url
                    elif want_gpu_torch:
                        # 有 GPU 但未检测到 CUDA，回退到 cu118
                        torch_url = "https://download.pytorch.org/whl/cu118"
                    elif want_cpu_torch:
                        torch_url = "https://download.pytorch.org/whl/cpu"

                try:
                    ok = _pip_install(
                        self.pyexe, pkg, self.stop_event, self.log_q,
                        use_mirror=self.mirror, flags=flags, pause_event=self.pause_event,
                        torch_url=torch_url
                    )
                except Exception as e:
                    ok = False
                    tb = traceback.format_exc()
                    self.log_updated.emit(f"[FATAL] 安装 {pkg} 时发生异常: {e}\n{tb}")
                done_count += 1
                percent = int(done_count / total * 100)
                self.progress_updated.emit(percent)
                if ok:
                    self.log_updated.emit(f"[OK] {pkg} 安装成功 ✅")
                else:
                    self.log_updated.emit(f"[ERR] {pkg} 安装失败 ❌")
                    fail_count += 1
                    failed_pkgs.append(pkg)

            all_ok = (fail_count == 0)
            
            # 无论成功与否，都尝试修复关键版本
            # 这是必要的，因为 pix2text 和 pix2tex 有依赖冲突
            _fix_critical_versions(self.pyexe, self.log_updated.emit)
            
            # 如果安装了 PIX2TEXT_GPU，提示用户关于冲突的信息
            if "PIX2TEXT_GPU" in (self.chosen_layers or []):
                self.log_updated.emit("")
                self.log_updated.emit("[INFO] ⚠️ pix2tex 和 pix2text 存在依赖冲突：")
                self.log_updated.emit("  - pix2text 需要 pydantic-core>=2.41")
                self.log_updated.emit("  - pix2tex 需要 pydantic-core==2.23")
                self.log_updated.emit("  - 已自动修复为兼容版本，两者均通过子进程隔离运行")
                self.log_updated.emit("  - 如遇问题，可只使用其中一个模型")
                self.log_updated.emit("")
            
            if all_ok:
                self.log_updated.emit("[OK] 所有依赖安装成功 ✅")
            else:
                self.log_updated.emit(f"[WARN] 部分安装失败，共 {fail_count}/{total} 个 ❌")
                self.log_updated.emit("")
                self.log_updated.emit("=" * 70)
                self.log_updated.emit("📋 失败包汇总 - 可在终端中手动安装:")
                self.log_updated.emit("")
                for pkg in failed_pkgs:
                    self.log_updated.emit(f'  pip install "{pkg}" --upgrade --user')
                self.log_updated.emit("")
                self.log_updated.emit("=" * 70)
                self.log_updated.emit("")
                self.log_updated.emit("🔍 常见失败原因及解决方案:")
                self.log_updated.emit("")
                self.log_updated.emit("  1. 🔒 程序占用文件：关闭本程序后再手动安装")
                self.log_updated.emit("  2. 🔐 权限不足：以管理员身份运行终端")
                self.log_updated.emit("  3. 🌐 网络问题：尝试使用镜像源或 VPN")
                self.log_updated.emit("  4. ⚠️ 依赖冲突：查看上方 [DIAG] 诊断信息")
                self.log_updated.emit("")
                self.log_updated.emit("💡 推荐操作:")
                self.log_updated.emit("  1. 关闭本程序")
                self.log_updated.emit("  2. 打开 CMD 终端（以管理员身份）")
                self.log_updated.emit("  3. 执行上述 pip install 命令")
                self.log_updated.emit("  4. 重新启动程序")
                self.log_updated.emit("=" * 70)

            self.progress_updated.emit(100)
            self._emit_done_safe(all_ok)
        except Exception as e:
            tb = traceback.format_exc()
            self.log_updated.emit(f"[FATAL] 安装线程未捕获异常: {e}\n{tb}")

import os, sys, json, subprocess, threading, queue, urllib.request, re
from pathlib import Path

from PyQt6.QtGui import QIcon

os.environ["PYTHONUTF8"] = "1"

flags = 0
if sys.platform == "win32":
    flags = subprocess.CREATE_NO_WINDOW
_repair_in_progress = False
CONFIG_FILE = "LaTeXSnipper_config.json"
STATE_FILE = ".deps_state.json"

# 需要特殊处理的包
TORCH_NAMES = {"torch", "torchvision", "torchaudio"}
QT_PKGS = {"pyqt6", "pyqt6-qt6", "pyqt6-webengine", "pyqt6-webengine-qt6"}

# 关键版本约束（防止 pip 自动升级导致兼容性问题）
CRITICAL_VERSIONS = {
    "numpy": "numpy>=1.26.4,<2",
    "protobuf": "protobuf>=3.20,<5",
    # pydantic 和 pydantic-core 必须版本匹配
    "pydantic": "pydantic==2.9.2",
    "pydantic-core": "pydantic-core==2.23.4",
}

def _fix_critical_versions(pyexe: str, log_fn=None):
    """
    安装完成后强制修复关键依赖版本。
    
    背景：pix2text 和 pix2tex 有依赖冲突：
    - pix2text 依赖链需要 pydantic-core>=2.41.4
    - pix2tex 需要 pydantic-core==2.23.4
    
    pip 会自动选择新版本满足 pix2text，但这会破坏 pix2tex。
    我们在安装后强制降级到兼容版本，让两者都能在子进程中工作。
    """
    import subprocess
    
    if log_fn:
        log_fn("[INFO] 正在修复关键依赖版本（解决 pix2tex/pix2text 冲突）...")
    
    for pkg, spec in CRITICAL_VERSIONS.items():
        try:
            # 使用 --no-deps 避免触发依赖解析
            cmd = [pyexe, "-m", "pip", "install", spec, "--no-deps", "--force-reinstall"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if log_fn:
                if result.returncode == 0:
                    log_fn(f"  [OK] 已修复 {pkg} → {spec.split('==')[-1] if '==' in spec else spec}")
                else:
                    log_fn(f"  [WARN] 修复 {pkg} 失败: {result.stderr[:100]}")
        except Exception as e:
            if log_fn:
                log_fn(f"  [WARN] 修复 {pkg} 异常: {e}")
    
    if log_fn:
        log_fn("[INFO] 关键版本修复完成")

# 各功能层的运行时验证测试代码
# 每个层需要验证的核心导入，确保包不仅安装了，还能真正工作
LAYER_VERIFY_CODE = {
    "BASIC": """
import numpy as np
import PIL
import requests
import lxml
import PyQt6
# onnxruntime 可能是 CPU 版本或 GPU 版本，都可以
try:
    import onnxruntime
except ImportError:
    try:
        import onnxruntime_gpu as onnxruntime
    except ImportError:
        raise ImportError("onnxruntime (CPU 或 GPU 版本) 未安装")
print("BASIC OK")
""",
    "CORE": """
import pix2tex
from pix2tex.cli import LatexOCR
import latex2mathml.converter
import sympy
import matplotlib
import matplotlib.mathtext
print("CORE OK")
""",
    "HEAVY_CPU": """
import torch
print("torch version:", torch.__version__)
print("HEAVY_CPU OK")
""",
    "HEAVY_GPU": """
import torch
if not torch.cuda.is_available():
    raise RuntimeError("CUDA not available")
print("CUDA device:", torch.cuda.get_device_name(0))
print("HEAVY_GPU OK")
""",
    "PIX2TEXT_GPU": """
from pix2text import Pix2Text
print("PIX2TEXT_GPU OK")
""",
    "OCR": """
import rapidocr
print("OCR OK")
""",
    "OPTIONAL": """
import pandas
print("OPTIONAL OK")
""",
}

def _verify_layer_runtime(pyexe: str, layer: str, timeout: int = 60) -> tuple:
    """
    验证某个功能层是否能在运行时正常工作。
    
    返回: (success: bool, error_msg: str)
    """
    import subprocess
    
    if layer not in LAYER_VERIFY_CODE:
        # 没有验证代码的层，默认通过
        return True, ""
    
    code = LAYER_VERIFY_CODE[layer]
    try:
        result = subprocess.run(
            [pyexe, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if result.returncode == 0:
            return True, ""
        else:
            # 提取关键错误信息
            err = result.stderr.strip()
            # 截取最后几行，通常是最有用的
            err_lines = err.split('\n')[-5:]
            return False, '\n'.join(err_lines)
    except subprocess.TimeoutExpired:
        return False, "验证超时"
    except Exception as e:
        return False, str(e)

def _verify_installed_layers(pyexe: str, claimed_layers: list, log_fn=None) -> list:
    """
    验证声称已安装的层是否真正可用。
    
    返回: 真正可用的层列表
    """
    verified = []
    for layer in claimed_layers:
        ok, err = _verify_layer_runtime(pyexe, layer)
        if ok:
            verified.append(layer)
            if log_fn:
                log_fn(f"[OK] {layer} 层验证通过")
        else:
            if log_fn:
                log_fn(f"[WARN] {layer} 层验证失败: {err[:200]}")
    return verified

# 分层依赖（保持原始规格；含 +cu 与 ~= 的组合后续会自动规范化）
LAYER_MAP = {
    "BASIC": [
        "simsimd~=6.0.5","lxml~=4.9.3","PyQt6-WebEngine~=6.9.0",
        "pillow~=11.0.0", "pyperclip~=1.11.0", "packaging~=25.0",
        "requests~=2.32.5", "tqdm~=4.67.1",
        "numpy>=1.26.4,<2.0.0", "filelock~=3.13.1",
        "pydantic~=2.9.2", "regex~=2024.9.11",
        "safetensors~=0.6.2", "sentencepiece~=0.1.99",
        "certifi~=2024.2.2", "idna~=3.6", "urllib3~=2.5.0",
        "colorama~=0.4.6", "psutil~=7.1.0",
        "typing_extensions>=4.12.2",
        "onnxruntime~=1.19.2",
        "PyQt6-Fluent-Widgets~=1.9.2",
    ],
    # ❗ CORE 现在只负责 pix2tex + Web 预览 + 数学库 + SVG 导出
    "CORE": [
        "pix2tex~=0.1.4",
        "protobuf>=3.20,<5",  # wandb 需要旧版 protobuf，6.x 会导致 Result 属性缺失
        "sympy~=1.13.3", "mpmath~=1.3.0",
        "networkx~=3.2.1",
        "humanfriendly~=10.0",
        "onnx~=1.15.0",
        "latex2mathml>=2.0.0",  # LaTeX 转 MathML 的支持
        "matplotlib~=3.8.4",  # LaTeX 公式转 SVG 的支持
    ],
    # ✅ 新增：pix2text GPU 模型层（只在用户选中时安装）
    "PIX2TEXT_GPU": [
        "pix2text~=1.1.4",
        "tokenizers~=0.22.1",
        "transformers~=4.57.0",
        "timm~=0.5.4",
        "einops~=0.8.1",
        "entmax~=1.3",
        "omegaconf~=2.3.0",
        "munch~=4.0.0",
        "fsspec~=2023.10.0",
        # 如 pix2text 额外需要其他包，可补充在这里
    ],
    # HEAVY_CPU: PyTorch CPU 版，用于无 GPU 但需要深度学习推理的场景
    "HEAVY_CPU": [
        "torch==2.7.1",
        "torchvision==0.22.1",
        "torchaudio==2.7.1",
        "optimum~=1.16.2",
    ],
    # HEAVY_GPU: PyTorch GPU 版（CUDA 11.8），用于有 NVIDIA GPU 的加速推理场景
    "HEAVY_GPU": [
        "torch==2.7.1",
        "torchvision==0.22.1",
        "torchaudio==2.7.1",
        "onnxruntime-gpu~=1.18.1",  # 1.18.x 支持 CUDA 11.8，1.19+ 需要 CUDA 12.x
    ],
    "OCR": [
        "rapidocr~=3.2.0", "cnocr~=2.3.2.1", "cnstd~=1.2.6.1", "easyocr~=1.7.1",
        "opencv-python~=4.9.0.80", "pyclipper~=1.3.0.post5", "shapely~=2.0.2",
        "scipy~=1.13.1", "scikit-image~=0.22.0", "imageio~=2.34.0",
        "tifffile~=2024.2.12",
        "albumentations~=1.4.21", "albucore~=0.0.20",
        "ultralytics~=8.2.32", "thop~=0.1.1-2209072238"
    ],
    "OPTIONAL": [
        "datasets~=2.17.0", "evaluate~=0.4.1",
        "pandas~=2.3.3", "polars~=1.34.0",
        "seaborn~=0.13.2",
        "wandb~=0.16.3", "responses~=0.18.0",
        "coloredlogs~=15.0.1", "platformdirs~=4.4.0",
        "appdirs~=1.4.4", "xxhash~=3.4.1",
        "multiprocess~=0.70.16", "pyarrow~=15.0.0",
        "unidecode~=1.3.8",
        "tzdata~=2024.1",
        "jinja2~=3.1.3", "markupsafe~=2.1.5",
        "pyparsing~=3.1.1",
        "fonttools~=4.49.0", "cycler~=0.12.1",
        "kiwisolver~=1.4.5", "contourpy~=1.2.0",
    ]
}

SKIP_PREFIX = {"pip","setuptools","wheel","python","openssl","zlib","ninja"}

# ---------------- 基础工具 ----------------
def _load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def _save_json(p: Path, data, log_q=None):
    try:
        from pathlib import Path
        Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        msg = f"[Deps] 写文件失败: {e}"
        print(msg)
        if log_q:
            log_q.put(msg)

def _site_packages_root(pyexe: Path):
    """
    传入的是 python.exe 路径：
      - 独立版: <deps_dir>/python311/python.exe -> <deps_dir>/python311/Lib/site-packages
      - venv 版: <deps_dir>/venv/Scripts/python.exe -> <deps_dir>/venv/Lib/site-packages
    """
    py_dir = pyexe.parent
    # 支持 .venv/Scripts/python.exe 结构，向上查找 Lib/site-packages
    candidates = [
        py_dir / "Lib" / "site-packages",
        py_dir.parent / "Lib" / "site-packages",  # 兼容 .venv/Scripts/python.exe
        py_dir.parent.parent / "Lib" / "site-packages"  # 兼容更深层嵌套
    ]
    for sp in candidates:
        if sp.exists():
            return sp
    return None

def _inject_private_python_paths(pyexe: Path):
    """
    仅在开发模式下注入私有 site-packages 路径。
    打包后的程序：AI 模型在子进程中运行，无需注入。
    """
    import sys, os
    
    # 打包模式下不注入，避免与内置包冲突
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        print("[INFO] 打包模式：跳过路径注入，AI 模型将在子进程中使用独立 Python")
        return
    
    sp = _site_packages_root(pyexe)
    if not sp:
        return

    # 1) 剔除 venv/项目 site-packages，避免环境混用
    bad_markers = [
        os.sep + ".venv" + os.sep,
        os.sep + "env" + os.sep,
        os.sep + "venv" + os.sep,
    ]
    sys.path[:] = [p for p in sys.path if not any(m in p for m in bad_markers)]
    # 2) 把私有 site-packages 放到最前
    if str(sp) not in sys.path:
        sys.path.insert(0, str(sp))

    # 3) Windows: 显式加入 DLL 搜索目录，优先保证 torch 能找到其依赖
    if os.name == "nt":
        try:
            import os as _os
            from ctypes import windll  # noqa: F401  触发加载机制
            torch_lib = sp / "torch" / "lib"
            dlls_dir = pyexe.parent / "DLLs"
            if torch_lib.exists():
                _os.add_dll_directory(str(torch_lib))
            if dlls_dir.exists():
                _os.add_dll_directory(str(dlls_dir))
        except Exception:
            pass

def _ensure_pip(main_python: Path) -> bool:
    """
    确保专用 Python(python311/python.exe) 内 pip 可用并升级。
    不再创建/使用 venv。
    """
    import urllib.request, subprocess

    if not main_python.exists():
        raise RuntimeError(f"[ERR] 主 Python 不存在: {main_python}")

    # 修复 embedded/_pth 情况
    try:
        pth_candidates = list(main_python.parent.glob("python*.pth")) + list(main_python.parent.glob("python*._pth"))
        for pth_file in pth_candidates:
            content = pth_file.read_text(encoding="utf-8")
            if "#import site" in content:
                from pathlib import Path
                Path(pth_file).write_text(content.replace("#import site", "import site"), encoding="utf-8")
    except Exception:
        pass

    # 检测 pip
    try:
        subprocess.check_call([str(main_python), "-m", "pip", "--version"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        pip_ready_event.set()
        return True
    except Exception:
        pass

    # 安装 pip
    gp_url = "https://bootstrap.pypa.io/get-pip.py"
    gp_path = main_python.parent / "get-pip.py"
    urllib.request.urlretrieve(gp_url, gp_path)
    subprocess.check_call([str(main_python), str(gp_path)], timeout=180, creationflags=flags)

    # 升级三件套
    cmd = [str(main_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "--no-cache-dir"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
    ok = res.returncode == 0
    if ok:
        pip_ready_event.set()
    return ok

def _current_installed(pyexe):
    """获取当前环境已安装的包列表"""
    try:
        with subprocess_lock:
            subprocess.check_call([str(pyexe), "-m", "pip", "--version"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except Exception as e:
        print(f"[WARN] pip 不可用: {e}")
        return {}
    try:
        with subprocess_lock:
            out = subprocess.check_output(
                [str(pyexe), "-m", "pip", "list", "--format=json"],
                text=True, creationflags=flags)
        data = json.loads(out)
        result = {d["name"].lower(): d["version"] for d in data}
        print(f"[DEBUG] 已安装包数量: {len(result)}")
        return result
    except Exception as e:
        print(f"[WARN] 获取已安装包列表失败: {e}")
        return {}

def _filter_packages(pkgs):
    res = []
    for spec in pkgs:
        name = re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
        if any(name.startswith(p) for p in SKIP_PREFIX):
            continue
        res.append(spec)
    return res

def _gpu_available():
    try:
        r = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2, creationflags=flags)
        return r.returncode == 0
    except Exception:
        return False

def _detect_cuda_version() -> tuple:
    """
    检测系统安装的 CUDA Toolkit 版本。
    
    返回: (major, minor, full_version_str) 或 (None, None, None) 如果未检测到
    
    检测顺序（重要：优先检测实际安装的 CUDA Toolkit，而非驱动支持版本）：
    1. nvcc --version（CUDA Toolkit 实际安装版本 - 最重要）
    2. 环境变量 CUDA_PATH（从安装路径提取版本）
    3. nvidia-smi 输出（驱动支持的最高版本 - 作为回退）
    
    注意：nvidia-smi 显示的是驱动支持的最高 CUDA 版本，不是实际安装的版本！
    PyTorch 需要匹配实际安装的 CUDA Toolkit 版本。
    """
    import re
    
    # 方法1: 通过 nvcc 检测（CUDA Toolkit 实际版本 - 最可靠）
    try:
        r = subprocess.run(
            ["nvcc", "--version"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            timeout=5, 
            creationflags=flags,
            text=True
        )
        if r.returncode == 0:
            # 匹配 "release 11.8" 或 "V11.8.89"
            match = re.search(r'release\s*(\d+)\.(\d+)|V(\d+)\.(\d+)', r.stdout)
            if match:
                if match.group(1):
                    major, minor = int(match.group(1)), int(match.group(2))
                else:
                    major, minor = int(match.group(3)), int(match.group(4))
                print(f"[INFO] 通过 nvcc 检测到 CUDA Toolkit {major}.{minor}")
                return (major, minor, f"{major}.{minor}")
    except Exception:
        pass
    
    # 方法2: 通过环境变量检测
    cuda_path = os.environ.get("CUDA_PATH", "")
    if cuda_path:
        # 从路径中提取版本，如 "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8"
        match = re.search(r'v?(\d+)\.(\d+)', cuda_path)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            print(f"[INFO] 通过 CUDA_PATH 检测到 CUDA {major}.{minor}")
            return (major, minor, f"{major}.{minor}")
    
    # 方法3: 通过 nvidia-smi 检测（驱动支持的最高版本 - 回退方案）
    # 注意：这不是实际安装的 CUDA 版本！
    try:
        r = subprocess.run(
            ["nvidia-smi"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            timeout=5, 
            creationflags=flags,
            text=True
        )
        if r.returncode == 0:
            # 匹配 "CUDA Version: 13.1" 或类似格式
            match = re.search(r'CUDA Version:\s*(\d+)\.(\d+)', r.stdout)
            if match:
                major, minor = int(match.group(1)), int(match.group(2))
                print(f"[WARN] 未找到 nvcc，使用驱动支持版本 CUDA {major}.{minor}（可能不准确）")
                # 如果驱动版本很高但没有安装 CUDA Toolkit，建议使用较保守的版本
                # 回退到 cu118 作为安全选择
                return (11, 8, "11.8 (推断)")
    except Exception:
        pass
    
    return (None, None, None)

def _get_torch_index_url(cuda_version: tuple) -> str:
    """
    根据 CUDA 版本返回对应的 PyTorch 下载 URL。
    
    PyTorch 官方支持的 CUDA 版本（截至 2.7.x）：
    - cu118: CUDA 11.8
    - cu121: CUDA 12.1
    - cu124: CUDA 12.4
    - cu126: CUDA 12.6 (最新稳定)
    
    注意：CUDA 向后兼容，所以 CUDA 13.x 驱动可以运行 CUDA 12.x 编译的程序。
    
    返回: index-url 字符串，如果没有 CUDA 则返回 None（使用 CPU 版本）
    """
    major, minor, _ = cuda_version
    
    if major is None:
        return None  # 无 CUDA，使用 CPU 版本
    
    # PyTorch 官方 CUDA 轮子版本映射
    # 格式: (major, minor): (cu_tag, url)
    cuda_urls = [
        ((11, 8), ("cu118", "https://download.pytorch.org/whl/cu118")),
        ((12, 1), ("cu121", "https://download.pytorch.org/whl/cu121")),
        ((12, 4), ("cu124", "https://download.pytorch.org/whl/cu124")),
        ((12, 6), ("cu126", "https://download.pytorch.org/whl/cu126")),
    ]
    
    # 将用户 CUDA 版本转换为可比较的数值
    user_cuda = major * 100 + minor
    
    # 找到最高的兼容版本（不超过用户版本，或用户版本更高时使用最新的）
    best_match = None
    best_cuda_num = 0
    
    for (cmaj, cmin), (tag, url) in cuda_urls:
        cuda_num = cmaj * 100 + cmin
        # 如果用户 CUDA >= 此版本，则可以使用
        if cuda_num <= user_cuda and cuda_num > best_cuda_num:
            best_cuda_num = cuda_num
            best_match = (tag, url)
    
    # 如果用户 CUDA 比所有支持的都高（如 CUDA 13.x），使用最新的可用版本
    if best_match is None and user_cuda > 0:
        # 使用最高的可用版本（cu126）
        best_match = cuda_urls[-1][1]
        print(f"[INFO] CUDA {major}.{minor} 高于 PyTorch 支持的最高版本，将使用 {best_match[0]}")
    
    if best_match:
        return best_match[1]
    
    return None

# 全局缓存检测到的 CUDA 信息
_cached_cuda_info = None

def get_cuda_info() -> dict:
    """
    获取 CUDA 环境信息（带缓存）。
    
    返回: {
        "available": bool,
        "version": str or None,  # 如 "12.4"
        "major": int or None,
        "minor": int or None,
        "torch_url": str or None,  # PyTorch 下载 URL
        "torch_tag": str,  # 如 "cu124" 或 "cpu"
    }
    """
    global _cached_cuda_info
    if _cached_cuda_info is not None:
        return _cached_cuda_info
    
    major, minor, version_str = _detect_cuda_version()
    torch_url = _get_torch_index_url((major, minor, version_str)) if major else None
    
    # 确定 torch tag
    if torch_url:
        # 从 URL 中提取 tag
        if "cu118" in torch_url:
            torch_tag = "cu118"
        elif "cu121" in torch_url:
            torch_tag = "cu121"
        elif "cu124" in torch_url:
            torch_tag = "cu124"
        elif "cu126" in torch_url:
            torch_tag = "cu126"
        else:
            torch_tag = "cuda"
    else:
        torch_tag = "cpu"
    
    _cached_cuda_info = {
        "available": major is not None,
        "version": version_str,
        "major": major,
        "minor": minor,
        "torch_url": torch_url,
        "torch_tag": torch_tag,
    }
    
    print(f"[INFO] CUDA 检测结果: {_cached_cuda_info}")
    return _cached_cuda_info

# --------------- 规格处理与安装策略 ---------------
_pat_local_tilde = re.compile(r'^([A-Za-z0-9_\-]+)~=(\d+(?:\.\d+)+)\+([A-Za-z0-9_.-]+)$')

import os, time, traceback
pip_ready_event = threading.Event()

def _diagnose_install_failure(output: str, returncode: int) -> str:
    """
    分析 pip 安装失败的输出，诊断具体原因
    """
    output_lower = output.lower()
    
    # 1. 文件/进程占用（最常见的权限问题）
    if any(x in output_lower for x in [
        "permission denied",
        "access is denied",
        "being used by another process",
        "permissionerror",
        "winerror 5",
        "winerror 32",  # 文件被另一进程使用
        "errno 13",
    ]):
        return "🔒 文件被占用或权限不足 - 请关闭程序后重试，或以管理员身份运行"
    
    # 2. 依赖冲突
    if any(x in output_lower for x in [
        "conflicting dependencies",
        "incompatible",
        "no matching distribution",
        "could not find a version",
        "resolutionimpossible",
        "package requires",
    ]):
        return "⚠️ 依赖版本冲突 - 某些包的版本要求互相矛盾"
    
    # 3. 网络问题
    if any(x in output_lower for x in [
        "connection refused",
        "connection timed out",
        "could not fetch url",
        "network is unreachable",
        "name or service not known",
        "getaddrinfo failed",
        "ssl: certificate",
        "readtimeouterror",
        "connectionerror",
    ]):
        return "🌐 网络连接失败 - 请检查网络或尝试使用镜像源"
    
    # 4. 磁盘空间
    if any(x in output_lower for x in [
        "no space left",
        "disk full",
        "not enough space",
        "oserror: [errno 28]",
    ]):
        return "💾 磁盘空间不足 - 请清理磁盘后重试"
    
    # 5. 编译失败（C扩展）
    if any(x in output_lower for x in [
        "building wheel",
        "failed building",
        "error: command",
        "microsoft visual c++",
        "vcvarsall.bat",
        "cl.exe",
    ]):
        return "🔧 编译失败 - 可能缺少 Visual C++ Build Tools"
    
    # 6. Python 版本不兼容
    if any(x in output_lower for x in [
        "requires python",
        "python_requires",
        "not supported",
    ]):
        return "🐍 Python 版本不兼容 - 该包不支持当前 Python 版本"
    
    # 7. pip 本身的问题
    if any(x in output_lower for x in [
        "pip._internal",
        "attributeerror",
        "modulenotfounderror: no module named 'pip'",
    ]):
        return "📦 pip 损坏或版本过低 - 请先升级 pip"
    
    # 8. CUDA/GPU 相关
    if any(x in output_lower for x in [
        "cuda",
        "cudnn",
        "nvidia",
        "gpu",
    ]) and "error" in output_lower:
        return "🎮 CUDA/GPU 相关错误 - 请检查 CUDA 版本是否匹配"
    
    # 默认
    if returncode == 1:
        return f"❓ 一般错误 (code={returncode}) - 请查看上方日志获取详情"
    elif returncode == 2:
        return f"❓ 命令行语法错误 (code={returncode})"
    else:
        return f"❓ 未知错误 (code={returncode}) - 请查看上方日志获取详情"

#  扩展 _pip_install：为 torch 系列包支持专用 index-url（cu118），，并支持 pause_event
def _pip_install(pyexe, pkg, stop_event, log_q, use_mirror=False, flags=0, torch_url=None, pause_event=None):
    """
    安装单个依赖包，支持实时日志、镜像切换、重试与防阻塞。
    新增: 当 pkg 属于 TORCH_NAMES 且 torch_url 非空时，使用 --index-url= torch_url，
         并忽略 -i 镜像参数，保证拉取到 CUDA 轮子。
    """
    import subprocess, os, time, traceback, re
    from pathlib import Path

    max_retries = 2
    retry = 0
    proc = None

    def _root_name(spec: str) -> str:
        return re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
    # Fallback 修复：防止传入错误 pyexe
    if not Path(pyexe).exists():
        pyexe = Path(sys.executable)
        log_q.put(f"[WARN] 传入 Python 不存在，自动切换为 {pyexe}")

    if not pip_ready_event.wait(timeout=60):
        log_q.put(f"[ERR] pip 未初始化完成，跳过 {pkg}")
        return False

    env = os.environ.copy()
    main_site = Path(pyexe).parent / "Lib" / "site-packages"
    if main_site.exists():
        env["PYTHONPATH"] = f"{main_site};{env.get('PYTHONPATH', '')}"
    env["PYTHONUNBUFFERED"] = "1"
    # 补丁：自动应用依赖目录下的 constraints.txt
    try:
        py_path = Path(pyexe) if not isinstance(pyexe, Path) else pyexe
        cfile = py_path.parent.parent / "constraints.txt"  # <deps_dir>/constraints.txt
        if cfile.exists():
            env["PIP_CONSTRAINT"] = str(cfile)
    except Exception:
        pass

    name = _root_name(pkg)
    use_torch_repo = (torch_url is not None) and (name in TORCH_NAMES)

    while retry <= max_retries:
        if stop_event.is_set():
            log_q.put("[INFO] 检测到停止信号，中断安装任务。")
            return False
        # 若处于暂停状态，则等待继续
        if pause_event is not None and not pause_event.is_set():
            log_q.put("[INFO] 已暂停，等待继续 ...")
            while not pause_event.is_set():

                if stop_event.is_set():
                    log_q.put("[CANCEL] 用户取消安装。")
                    return False
                time.sleep(0.1)
        try:
            args = [
                str(pyexe), "-m", "pip", "install",
                pkg, "--upgrade"
            ]
            # 安装策略优化：
            # 1. Qt 家族：禁止强制重装，避免卸载已加载的 DLL
            # 2. Torch 家族：不用 force-reinstall，因为 index-url 已指定正确源
            # 3. 其他大型包：不用 force-reinstall，避免重装所有依赖（太慢）
            # 4. 只对关键版本修复包使用 force-reinstall
            
            # 需要强制重装的包（版本冲突敏感）
            force_reinstall_pkgs = {"numpy", "protobuf", "pydantic", "pydantic-core"}
            
            if name in force_reinstall_pkgs:
                args.append("--force-reinstall")
            elif name in QT_PKGS:
                # Qt 包：禁止重装
                pass
            elif name in TORCH_NAMES:
                # Torch 包：不强制重装，依赖 index-url 选择正确版本
                pass
            else:
                # 其他包：普通升级即可，不强制重装依赖
                pass
            
            # Qt 顶层包禁依赖以防触发 PyQt6-Qt6 重装
            if name in {"pyqt6", "pyqt6-webengine"}:
                args.append("--no-deps")

            # numpy 兜底
            if name == "numpy":
                args[-3:-3] = ["numpy<2.0.0"]
            # 索引源策略：torch 走 --index-url，其它走 -i（官方或清华）
            if use_torch_repo:
                args += ["--index-url", torch_url]
                if retry == 0:
                    log_q.put(f"[Source] Torch 使用 {torch_url} 🔧")
            else:
                if use_mirror:
                    args += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
                    if retry == 0:
                        log_q.put("[Source] 使用清华源 📦")
                else:
                    args += ["-i", "https://pypi.org/simple"]
                    if retry == 0:
                        log_q.put("[Source] 使用官方源 🌐")

            log_q.put(f"[CMD] {' '.join(args)}")
            with subprocess_lock:
                proc = safe_run(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    env=env,
                    creationflags=flags
                )

            # 收集输出用于错误诊断
            output_lines = []
            for line in proc.stdout:
                # 运行中支持暂停/继续
                if pause_event is not None:
                    while not pause_event.is_set():
                        if stop_event.is_set():
                            try:
                                proc.terminate()
                            except Exception:
                                pass
                            return False
                        time.sleep(0.1)
                log_q.put(line.rstrip())
                output_lines.append(line.rstrip())
            proc.communicate(timeout=1200)

            if proc.returncode == 0:
                log_q.put(f"[OK] {pkg} 安装成功 ✅")
                return True
            else:
                # 分析失败原因
                full_output = "\n".join(output_lines[-50:])  # 最后50行
                failure_reason = _diagnose_install_failure(full_output, proc.returncode)
                
                log_q.put(f"[WARN] {pkg} 安装失败 (returncode={proc.returncode})")
                log_q.put(f"[DIAG] 可能原因: {failure_reason}")
                
                retry += 1
                if retry <= max_retries:
                    log_q.put(f"[INFO] 第 {retry} 次重试中... ⏳")
                else:
                    # 所有重试都失败，提供手动安装命令
                    log_q.put(f"[ERR] {pkg} 安装失败 ❌")
                    log_q.put(f"[ERR] 失败原因: {failure_reason}")
                    log_q.put("")
                    log_q.put("=" * 60)
                    log_q.put("💡 手动安装提示（请在终端中执行以下命令）：")
                    log_q.put("")
                    manual_cmd = f'"{pyexe}" -m pip install {pkg} --upgrade --user'
                    log_q.put(f"  {manual_cmd}")
                    log_q.put("")
                    log_q.put("如遇权限问题，可尝试：")
                    log_q.put(f'  1. 关闭程序后以管理员身份运行终端')
                    log_q.put(f'  2. 或使用 --user 选项安装到用户目录')
                    log_q.put(f'  3. 或在设置中点击"打开环境终端"执行上述命令')
                    log_q.put("=" * 60)
                    log_q.put("")
                    return False
             # 重试前也响应暂停/取消
                if pause_event is not None:
                    while not pause_event.is_set():
                        if stop_event.is_set():
                            return False
                        time.sleep(0.1)
                time.sleep(3)
                continue

        except subprocess.TimeoutExpired:
            log_q.put(f"[ERR] {pkg} 安装超时，正在重试...")
            retry += 1
            continue
        except Exception as e:
            tb = traceback.format_exc()
            log_q.put(f"[FATAL] {pkg} 安装异常: {e}\n{tb}")
            return False

    # 检查 pip 可用
    try:
        subprocess.check_call(
            [str(pyexe), "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
        )
    except Exception:
        log_q.put(f"[ERR] pip 不可用，跳过 {pkg}")
        return False
    # 防御式返回（正常流程不会走到这里）
    return False

# GPU 切换专用线程（保留供将来手动 GPU 切换功能使用）
# 当前版本中 GPU 选择已通过 HEAVY_GPU 层直接在向导中完成，此类暂未使用
class GpuSwitchWorker(QThread):
    log_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    done = pyqtSignal(bool)  # True=成功

    def __init__(self, pyexe, state_path, stop_event, log_q, mirror=False, torch_url="https://download.pytorch.org/whl/cu118"):
        super().__init__()
        self.pyexe = str(pyexe)
        self.state_path = Path(state_path)
        self.stop_event = stop_event
        self.log_q = log_q
        self.mirror = mirror
        self.torch_url = torch_url
        self.proc = None

    def stop(self):
        self.stop_event.set()
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass
    def _run_cmd(self, args: list[str], timeout: int | None = None) -> int:
        self.log_q.put(f"[CMD] {' '.join(args)}")
        with subprocess_lock:
            self.proc = safe_run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                creationflags=flags
            )
        for line in self.proc.stdout:
            self.log_q.put(line.rstrip())
        self.proc.communicate(timeout=timeout)
        rc = self.proc.returncode or 0
        self.proc = None
        return rc
    def _uninstall_cpu_stack(self) -> bool:
        self.log_q.put("[STEP] 卸载 CPU 版 PyTorch 栈 ...")
        pkgs = ["torch", "torchvision", "torchaudio",
                "onnxruntime", "onnxruntime-cpu", "onnxruntime-gpu"]
        args = [self.pyexe, "-m", "pip", "uninstall", "-y", *pkgs]
        rc = self._run_cmd(args, timeout=600)
        if rc == 0:
            self.log_q.put("[OK] 已卸载 CPU 版依赖。")
            return True
        self.log_q.put(f"[WARN] 卸载出现返回码 {rc}，将继续尝试安装 GPU 版。")
        return True  # 卸载失败不阻断（可能部分未安装）

    def _install_gpu_stack(self) -> bool:
        self.log_q.put("[STEP] 安装 GPU 版 PyTorch 栈 ...")
        pkgs = [
            "torch==2.7.1",
            "torchvision==0.22.1",
            "torchaudio==2.7.1",
            "onnxruntime-gpu~=1.19.2"
        ]
        total = len(pkgs)
        ok_all = True
        for i, p in enumerate(pkgs, 1):
            if self.stop_event.is_set():
                self.log_q.put("[CANCEL] 用户取消。")
                return False
            # torch 三件套走 cu118 源；onnxruntime-gpu 走 PyPI/镜像
            is_torch = re.split(r'[<>=!~ ]', p, 1)[0].strip().lower() in TORCH_NAMES
            ok = _pip_install(
                self.pyexe, p, self.stop_event, self.log_q,
                use_mirror=(self.mirror and not is_torch),
                flags=flags,
                torch_url=(self.torch_url if is_torch else None)
            )
            self.progress_updated.emit(10 + int(70 * i / total))
            ok_all = ok_all and ok
        return ok_all

    def _verify_gpu(self):
        self.log_q.put("[STEP] 运行 GPU 环境自检 ...")
        code = r"""
import torch
print("cuda.is_available:", torch.cuda.is_available())
print("torch version:", torch.__version__)
print("torch.version.cuda:", torch.version.cuda)
try:
    print("cudnn version:", torch.backends.cudnn.version())
except Exception as e:
    print("cudnn version: <error>", e)
if torch.cuda.is_available():
    print("device 0:", torch.cuda.get_device_name(0))
import numpy as np
print(np.__version__)
"""
        args = [self.pyexe, "-c", code]
        rc = self._run_cmd(args, timeout=180)
        return rc == 0

    def _mark_layer_installed(self):
        try:
            state = _load_json(self.state_path, {"installed_layers": []})
            cur = set(state.get("installed_layers", []))
            cur.add("HEAVY_GPU")
            _save_json(self.state_path, {"installed_layers": sorted(list(cur))})
            self.log_q.put("[OK] 已写入 HEAVY_GPU 到状态文件。")
        except Exception as e:
            self.log_q.put(f"[WARN] 写状态文件失败: {e}")
    def run(self):
        try:
            self.progress_updated.emit(5)
            if not self._uninstall_cpu_stack():
                self.done.emit(False); return
            self.progress_updated.emit(15)
            if not self._install_gpu_stack():
                self.done.emit(False); return
            self.progress_updated.emit(90)
            ver_ok = self._verify_gpu()
            self.progress_updated.emit(98)
            if ver_ok:
                self._mark_layer_installed()
            self.progress_updated.emit(100)
            self.done.emit(ver_ok)
        except Exception as e:
            tb = traceback.format_exc()
            self.log_q.put(f"[FATAL] GPU 切换线程异常: {e}\n{tb}")
            self.done.emit(False)
# --------------- UI ---------------
def _build_layers_ui(pyexe, deps_dir, installed_layers, default_select, chosen, state_path, from_settings=False):
    import sys
    # 使用外部传入的 installed_layers；不覆盖
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QLabel,
                                 QHBoxLayout, QComboBox, QFileDialog, QLineEdit, QMessageBox)
    from qfluentwidgets import PushButton, FluentIcon
    dlg = QDialog()
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))
    dlg.setWindowTitle("依赖环境选择")
    lay = QVBoxLayout(dlg)

    def _force_quit():
        # 可选：通知后台停止任务
        try:
            global stop_event
            if 'stop_event' in globals():
                stop_event.set()
        except Exception:
            pass
        # 立即退出（不弹确认）
        QTimer.singleShot(0, lambda: QApplication.instance().quit())
        QTimer.singleShot(20, lambda: sys.exit(0))

    def _on_close(evt):
        evt.accept()
        _force_quit()

    # 新增：读取已安装层
    state_file = os.path.join(deps_dir, ".deps_state.json")
    claimed_layers = []
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                claimed_layers = state.get("installed_layers", [])
        except Exception:
            pass

    # ====== 运行时验证：检查声称已安装的层是否真正可用 ======
    # 新增：如果不是设置页面重启且已安装 basic 和 core，则跳过验证
    # 直接使用 from_settings 参数
    failed_layers = []
    verified_layers = []
    skip_verify = not from_settings and "BASIC" in claimed_layers and "CORE" in claimed_layers
    if skip_verify:
        installed_layers["layers"] = claimed_layers
    else:
        verified_layers = []
        failed_layers = []
        if claimed_layers and pyexe and os.path.exists(pyexe):
            print("[INFO] 正在验证已安装的功能层...")
            for layer in claimed_layers:
                ok, err = _verify_layer_runtime(pyexe, layer, timeout=30)
                if ok:
                    verified_layers.append(layer)
                    print(f"  [OK] {layer} 验证通过")
                else:
                    failed_layers.append((layer, err))
                    print(f"  [FAIL] {layer} 验证失败: {err[:100]}")
            # 如果有验证失败的层，更新状态文件
            if failed_layers:
                installed_layers["layers"] = verified_layers
                try:
                    _save_json(state_file, {"installed_layers": verified_layers})
                    print(f"[INFO] 已更新状态文件，移除失败的层: {[l for l,_ in failed_layers]}")
                except Exception as e:
                    print(f"[WARN] 更新状态文件失败: {e}")
            else:
                installed_layers["layers"] = verified_layers
        else:
            installed_layers["layers"] = claimed_layers
    # ====== 验证结束 ======

    # 判断是否缺少关键层（BASIC 或 CORE）
    missing_layers = []
    if "BASIC" not in installed_layers["layers"]:
        missing_layers.append("BASIC")
    if "CORE" not in installed_layers["layers"]:
        missing_layers.append("CORE")

    lack_critical = bool(missing_layers)

    # 新增：显示当前依赖环境和已安装层（根据状态显示不同信息）
    # 如果有验证失败的层，显示警告
    if failed_layers:
        failed_names = [l for l, _ in failed_layers]
        status_text = f"当前依赖环境：{deps_dir}\n⚠️ 以下功能层安装但无法使用: {', '.join(failed_names)}\n可用功能层: {', '.join(verified_layers) if verified_layers else '(无)'}"
        status_color = "#c62828"  # 红色警告
    elif installed_layers["layers"]:
        if lack_critical:
            status_text = f"检测到当前环境{deps_dir}的功能层不完整\n已完整安装的功能层：{', '.join(installed_layers['layers'])}"
            status_color = "#555"
        else:
            status_text = f"当前依赖环境：{deps_dir}\n已完整安装的功能层：{', '.join(installed_layers['layers'])}"
            status_color = "#2e7d32"  # 绿色表示完整
    else:
        status_text = f"当前依赖环境：{deps_dir}\n已安装层：(无)"
        status_color = "#c62828"  # 红色表示未安装
    
    env_info = QLabel(status_text)
    env_info.setStyleSheet(f"color:{status_color};font-size:12px;margin-bottom:6px;")
    lay.addWidget(env_info)
    lay.addWidget(QLabel("选择需要安装的功能层:"))

    # 获取验证失败的层名列表
    failed_layer_names = [l for l, _ in failed_layers] if failed_layers else []

    checks = {}
    # 遍历所有功能层
    for layer in LAYER_MAP.keys():
        row = QHBoxLayout()
        cb = QCheckBox(layer)
        del_btn = None
        if layer in failed_layer_names:
            cb.setChecked(True)
            cb.setEnabled(True)
            cb.setText(f"{layer}（需要修复）")
            cb.setStyleSheet("color: #c62828;")
        elif layer in installed_layers["layers"]:
            cb.setChecked(False)
            cb.setEnabled(False)
            cb.setText(f"{layer}（已安装）")
            # 新增删除按钮，使用 FluentIcon.DELETE（垃圾筐图标）
            del_btn = PushButton(FluentIcon.DELETE, "")
            del_btn.setFixedSize(32, 32)
            del_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 4px;
                    color: #666666;
                }
                QPushButton:hover {
                    background: #ffebee;
                    color: #d32f2f;
                    border: 1px solid #ffcdd2;
                }
                QPushButton:pressed {
                    background: #ffcdd2;
                    color: #c62828;
                    border: 1px solid #ef5350;
                }
            """)
            import subprocess
            def make_del_func(layer_name):
                def _del():
                    reply = QMessageBox.warning(
                        dlg, "删除确认",
                        f"确定要删除层 [{layer_name}] 及其所有依赖包吗？此操作不可恢复！",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        # 卸载该层所有包
                        pkgs = [p for p in LAYER_MAP.get(layer_name, []) if not p.startswith('__stdlib__')]
                        for pkg in pkgs:
                            pkg_name = pkg.split('~')[0].split('=')[0].split('>')[0].split('<')[0]
                            try:
                                subprocess.run([str(pyexe), "-m", "pip", "uninstall", "-y", pkg_name], check=False)
                            except Exception as e:
                                print(f"[WARN] 卸载包 {pkg_name} 失败: {e}")
                        # 更新状态文件
                        if layer_name in installed_layers["layers"]:
                            installed_layers["layers"].remove(layer_name)
                            _save_json(state_file, {"installed_layers": installed_layers["layers"]})
                        QMessageBox.information(dlg, "删除成功", f"已删除层: {layer_name} 及其依赖包，请重启依赖向导以刷新。")
                        dlg.close()
                return _del
            del_btn.clicked.connect(make_del_func(layer))
        else:
            cb.setEnabled(True)
            cb.setChecked(layer in default_select)
            cb.setText(layer)
        checks[layer] = cb
        row.addWidget(cb)
        if del_btn:
            row.addWidget(del_btn)
        lay.addLayout(row)

    # ---------- HEAVY_CPU / HEAVY_GPU 互斥逻辑 ----------
    def on_heavy_cpu_changed(state):
        if state and checks.get("HEAVY_GPU") and checks["HEAVY_GPU"].isEnabled():
            checks["HEAVY_GPU"].setChecked(False)
        # PIX2TEXT_GPU 需要 HEAVY_GPU，如果选了 CPU 则禁用提示
        if state and checks.get("PIX2TEXT_GPU"):
            if checks["PIX2TEXT_GPU"].isEnabled() and checks["PIX2TEXT_GPU"].isChecked():
                checks["PIX2TEXT_GPU"].setChecked(False)
    
    def on_heavy_gpu_changed(state):
        if state and checks.get("HEAVY_CPU") and checks["HEAVY_CPU"].isEnabled():
            checks["HEAVY_CPU"].setChecked(False)
    
    if "HEAVY_CPU" in checks and checks["HEAVY_CPU"].isEnabled():
        checks["HEAVY_CPU"].stateChanged.connect(on_heavy_cpu_changed)
    if "HEAVY_GPU" in checks and checks["HEAVY_GPU"].isEnabled():
        checks["HEAVY_GPU"].stateChanged.connect(on_heavy_gpu_changed)

    # ---------- GPU 加速提示（含 CUDA 版本检测）----------
    gpu_info_label = QLabel()
    has_gpu = _gpu_available()
    cuda_info = get_cuda_info()
    
    if has_gpu and cuda_info.get("available"):
        cuda_ver = cuda_info.get("version", "未知")
        torch_tag = cuda_info.get("torch_tag", "cuda")
        gpu_info_label.setText(f"✅ 检测到 NVIDIA GPU (CUDA {cuda_ver})，将使用 {torch_tag} 版本 PyTorch")
        gpu_info_label.setStyleSheet("color:#28a745;font-size:12px;margin:4px 0;")
    elif has_gpu:
        gpu_info_label.setText("⚠️ 检测到 GPU 但未找到 CUDA，将尝试使用 cu118 版本")
        gpu_info_label.setStyleSheet("color:#856404;font-size:12px;margin:4px 0;")
    else:
        gpu_info_label.setText("⚠️ 未检测到 NVIDIA GPU，建议安装 HEAVY_CPU 层")
        gpu_info_label.setStyleSheet("color:#856404;font-size:12px;margin:4px 0;")
    lay.addWidget(gpu_info_label)
    # 路径显示与更改
    path_row = QHBoxLayout()
    path_edit = QLineEdit(deps_dir)
    path_edit.setReadOnly(True)
    btn_path = PushButton(FluentIcon.FOLDER, "更改安装(依赖加载)路径")
    btn_path.setFixedHeight(36)
    btn_path.setToolTip("更改后需要重启程序才能生效")
    path_row.addWidget(QLabel("依赖安装/加载路径:"))
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(btn_path)
    lay.addLayout(path_row)
    # 镜像选择
    mirror_box = QComboBox()
    mirror_box.addItem("官方 PyPI", "off")
    mirror_box.addItem("清华镜像", "tuna")
    lay.addWidget(mirror_box)

    # ---------- 按钮布局 ----------
    btn_row = QHBoxLayout()

    btn_download = PushButton(FluentIcon.DOWNLOAD, "下载")
    btn_download.setFixedHeight(36)
    btn_enter = PushButton(FluentIcon.PLAY, "进入")
    btn_enter.setFixedHeight(36)
    btn_enter.setDefault(True)
    btn_cancel = PushButton(FluentIcon.CLOSE, "退出程序")
    btn_cancel.setFixedHeight(36)
    btn_row.addWidget(btn_download)
    btn_row.addWidget(btn_enter)
    btn_row.addWidget(btn_cancel)
    lay.addLayout(btn_row)

    # 警告 label
    warn = QLabel("缺少关键依赖层，部分功能将不可用！")
    warn.setStyleSheet("color:red;")
    lay.addWidget(warn)


    # 说明 label
    desc = QLabel(
        "📦 层级说明：\n"
        "• BASIC：基础依赖层（UI、网络、图像处理、onnxruntime 等），必须安装。\n"
        "• CORE：核心识别层（pix2tex、LaTeX 转换、SVG/MathML 导出），必须安装。\n"
        "• HEAVY_CPU：PyTorch CPU 版（无 GPU 设备时选择）。\n"
        "• HEAVY_GPU：PyTorch GPU 版 + CUDA（有 NVIDIA GPU 时选择）。\n"
        "• PIX2TEXT_GPU：高级模型 pix2text（需先安装 HEAVY_GPU）。\n"
        "• OCR：OCR 文字识别层（rapidocr、cnocr、easyocr 等）。\n"
        "• OPTIONAL：可视化与增强功能（pandas 等）。\n"
        "⚠️ 重要提示：\n"
        "• HEAVY_CPU 和 HEAVY_GPU 互斥，只能选择其一！\n"
        "• onnxruntime 和 onnxruntime-gpu 互斥，会自动卸载冲突版本。\n"
        "• 有 NVIDIA GPU → 选 HEAVY_GPU + PIX2TEXT_GPU（推荐）\n"
        "• 无 GPU / 仅 CPU → 选 HEAVY_CPU（不能选 PIX2TEXT_GPU）"
    )
    desc.setStyleSheet("color:#555;font-size:11px;")
    lay.addWidget(desc)
    chosen = {"layers": None, "mirror": False, "deps_path": deps_dir, "force_enter": False}
    # 动态更新按钮和警告
    def update_ui():
        required = {"BASIC", "CORE"}
        missing = [l for l in required if l not in installed_layers["layers"]]
        is_lack_critical = bool(missing)
        btn_enter.setText("强制进入" if is_lack_critical else "进入")
        warn.setVisible(is_lack_critical)

    update_ui()

    def choose_path():
        import os
        d = QFileDialog.getExistingDirectory(dlg, "选择依赖安装/加载目录", deps_dir)
        if d:
            path_edit.setText(d)
            state_file = os.path.join(d, ".deps_state.json")
            installed_layers["layers"] = []
            if os.path.exists(state_file):
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                        installed_layers["layers"] = state.get("installed_layers", [])
                except Exception:
                    pass
            env_info.setText(
                f"当前依赖环境：{d}\n已安装层：{', '.join(installed_layers['layers']) if installed_layers['layers'] else '(无)'}"
            )
            for layer, cb in checks.items():
                if layer in installed_layers["layers"]:
                    cb.setChecked(False)
                    cb.setEnabled(False)
                    cb.setText(f"{layer}（已安装）")
                else:
                    cb.setEnabled(True)
                    cb.setChecked(layer in default_select)
                    cb.setText(layer)
            # 移除与 venv/调试相关输出，避免策略混用
            update_ui()
            # 保存新路径到配置
            config_path = os.path.join(os.path.expanduser("~"), CONFIG_FILE)
            cfg = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            cfg["install_base_dir"] = d
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                # 提示用户需要重启
                msg = f"依赖路径已更改为：\n{d}\n\n是否立即重启程序以应用新路径？\n\n选择\"是\"将关闭程序，请手动重新启动。"
                reply = QMessageBox.question(
                    dlg, "路径已更改", msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # 自动重启程序并传递参数
                    import sys
                    import os
                    import subprocess
                    exe = sys.executable
                    args = sys.argv.copy()
                    # 避免重复添加参数
                    if '--force-deps-check' not in args:
                        args.append('--force-deps-check')
                    # Windows下用Popen启动新进程
                    try:
                        subprocess.Popen([exe] + args, close_fds=True)
                    except Exception as e:
                        print(f"[ERR] 自动重启失败: {e}")
                    dlg.reject()
                    QApplication.instance().quit()
                    sys.exit(0)
            except Exception as e:
                print(f"[ERR] 保存配置失败: {e}")

    btn_path.clicked.connect(choose_path)

    def enter():
        """进入按钮：环境完整则直接进入，否则强制进入"""
        sel = [L for L, c in checks.items() if c.isChecked()]
        chosen["layers"] = sel
        chosen["mirror"] = (mirror_box.currentData() == "tuna")
        chosen["deps_path"] = path_edit.text()
        
        print(f"[DEBUG] Selected layers: {sel}")
        required = {"BASIC", "CORE"}
        missing = [l for l in required if l not in installed_layers["layers"]]
        
        # 环境完整时直接进入
        if not missing:
            chosen["force_enter"] = False
            dlg.accept()
            return
        
        # 缺少关键层但用户未选择任何层 → 强制进入
        if not sel:
            chosen["force_enter"] = True
            dlg.done(1)  # done(1) 表示强制进入
            return
        
        # 缺少关键层且用户选择了层 → 进行下载
        chosen["force_enter"] = False
        dlg.accept()

    btn_enter.clicked.connect(enter)

    def download():
        sel = [L for L, c in checks.items() if c.isChecked()]
        if not sel:
            custom_warning_dialog("提示", "请至少选择一个依赖层进行下载。", dlg)
            return
        chosen["layers"] = sel
        chosen["mirror"] = (mirror_box.currentData() == "tuna")
        chosen["deps_path"] = path_edit.text()
        chosen["force_enter"] = False
        dlg.accept()

    btn_download.clicked.connect(download)

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox
    import sys

    # ---------- 安全退出逻辑 ----------
    def safe_exit():
        """安全退出程序"""
        try:
            global stop_event
            if 'stop_event' in globals():
                stop_event.set()
        except Exception:
            pass

        reply = QMessageBox.question(
            dlg, "退出确认",
            "确定要退出安装向导并关闭程序吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            QTimer.singleShot(100, lambda: QApplication.instance().quit())
            QTimer.singleShot(2000, lambda: sys.exit(0))

    # ---------- UI 刷新函数 ----------
    def refresh_ui():
        """在安装完成后刷新依赖状态"""
        try:
            new_state = _load_json(state_path, {"installed_layers": []})
            installed_layers["layers"] = new_state.get("installed_layers", [])

            # 更新警告与按钮文本
            if "BASIC" in installed_layers["layers"] and "CORE" in installed_layers["layers"]:
                warn.setVisible(False)
                btn_enter.setText("进入")
            else:
                warn.setVisible(True)
                btn_enter.setText("强制进入")

            # 更新复选框
            for layer, cb in checks.items():
                if layer in installed_layers["layers"]:
                    cb.setChecked(False)
                    cb.setEnabled(False)
                    cb.setText(f"{layer}（已安装）")
                else:
                    cb.setEnabled(True)
                    cb.setChecked(layer in default_select)
                    cb.setText(layer)

            env_info.setText(
                f"当前依赖环境：{deps_dir}\n已安装层：{', '.join(installed_layers['layers']) if installed_layers['layers'] else '(无)'}"
            )
            print("[OK] 依赖状态刷新成功 ✅")
        except Exception as e:
            print(f"[WARN] UI 刷新失败: {e}")

    # ✅ 暴露给外部调用
    dlg.refresh_ui = refresh_ui

    # ---------- 退出按钮逻辑：直接退出程序 ----------
    def _exit_app():
        """退出按钮：先确认，然后直接退出程序"""
        reply = QMessageBox.question(
            dlg, "退出确认",
            "确定要退出安装向导并关闭程序吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            dlg.reject()  # 先关闭对话框
            QTimer.singleShot(50, lambda: QApplication.instance().quit())
            QTimer.singleShot(500, lambda: sys.exit(0))

    btn_cancel.clicked.connect(_exit_app)

    # 右上角关闭事件：与退出按钮一致
    def _on_close(evt):
        _exit_app()
        evt.ignore()  # 由 _exit_app 控制退出
    dlg.closeEvent = _on_close

    return dlg, chosen

def _progress_dialog():
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QProgressBar, QHBoxLayout
    from qfluentwidgets import PushButton, FluentIcon
    dlg = QDialog(); dlg.setWindowTitle("安装进度"); dlg.resize(680,440)
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))
    lay = QVBoxLayout(dlg)
    info = QLabel("正在遍历寻找缺失的库，完成后将自动下载，请不要关闭此窗口(๑•̀ㅂ•́)و✧)...")
    logw = QTextEdit(); logw.setReadOnly(True)
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setFixedHeight(20)  # 增加高度
    progress.setMinimumWidth(400)  # 增加宽度
    progress.setStyleSheet("""
        QProgressBar {
            border: 2px solid #ddd;
            border-radius: 10px;
            text-align: center;
            background-color: #f0f0f0;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 #4CAF50, stop:1 #66BB6A);
            border-radius: 8px;
        }
    """)

    btn_cancel = PushButton(FluentIcon.CLOSE, "退出下载")
    btn_cancel.setFixedHeight(32)
    btn_pause = PushButton(FluentIcon.PAUSE, "暂停下载")
    btn_pause.setFixedHeight(32)
    btn_row = QHBoxLayout()
    btn_row.addWidget(btn_pause)
    btn_row.addWidget(btn_cancel)
    lay.addWidget(info); lay.addWidget(logw,1); lay.addWidget(progress); lay.addLayout(btn_row)
    return dlg, info, logw, btn_cancel, btn_pause, progress

def custom_warning_dialog(title, message, parent=None):
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout
    from qfluentwidgets import PushButton, FluentIcon
    from PyQt6.QtGui import QIcon

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    # 添加图标
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))

    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(message))

    btn_row = QHBoxLayout()
    ok_btn = PushButton(FluentIcon.ACCEPT, "确定")
    ok_btn.setFixedHeight(32)
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addStretch()
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)

    return dlg.exec() == QDialog.DialogCode.Accepted

def show_dependency_wizard(always_show_ui: bool = True) -> bool:
    """
    当环境损坏或依赖缺失时，强制打开依赖修复窗口（仅尝试一次）。
    仅在已有 QApplication 实例时工作；不再自行创建实例。
    """
    from PyQt6.QtWidgets import QApplication, QMessageBox

    global _repair_in_progress
    if _repair_in_progress:
        print("[WARN] 已在修复流程中，跳过重复调用。")
        return False
    _repair_in_progress = True

    app = QApplication.instance()
    if app is None:
        print("[WARN] show_dependency_wizard 需要已有 QApplication 实例。请在主程序创建后再调用。")
        _repair_in_progress = False
        return False
    QMessageBox.warning(
        None,
        "依赖修复",
        "检测到依赖环境损坏或缺失，请在接下来的窗口中重新选择安装目录或修复依赖。"
    )

    try:
        ok = ensure_deps(always_show_ui=always_show_ui)
        if not ok:
            QMessageBox.critical(None, "修复失败", "依赖修复未成功，请退出程序后重新运行。")
        else:
            QMessageBox.information(None, "修复完成", "依赖环境修复成功，请重新启动程序。")
        return ok
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[FATAL] show_dependency_wizard 失败: {e}\n{tb}")
        QMessageBox.critical(None, "严重错误", f"依赖修复失败：{e}")
        return False
    finally:
        _repair_in_progress = False

def clear_deps_state():
    """
    清空依赖状态文件，用于当依赖目录损坏或首次初始化异常时自动修复。
    """
    import json, os
    from pathlib import Path

    try:
        # 确定配置文件路径
        home_config = os.path.join(os.path.expanduser("~"), "LaTeXSnipper_config.json")
        print(f"[DEBUG] 清理状态文件：{home_config}")

        if not os.path.exists(home_config):
            print("[WARN] 配置文件不存在，无需清理。")
            return

        with open(home_config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        deps_dir = cfg.get("install_base_dir")

        if not deps_dir or not os.path.exists(deps_dir):
            print(f"[ERR] 无法找到依赖目录：{deps_dir}")
            return

        # 删除旧状态文件
        state_path = Path(deps_dir) / ".deps_state.json"
        if state_path.exists():
            state_path.unlink()
            print(f"[OK] 已删除旧状态文件：{state_path}")

        # 重建空状态文件
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"installed_layers": []}, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已重新生成空状态文件：{state_path}")

    except Exception as e:
        print(f"[ERR] 清除依赖状态文件失败: {e}")

from pathlib import Path


def _load_config_path():
    return Path.home() / "LaTeXSnipper_config.json"

def _read_config_install_dir(cfg_path: Path) -> str | None:
    if cfg_path.exists():
        try:
            import json
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            v = data.get("install_base_dir")
            if isinstance(v, str) and v.strip():
                return v
        except Exception:
            pass
    return None
def _write_config_install_dir(cfg_path: Path, deps_dir: str) -> None:
    try:
        import json
        data = {}
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        data["install_base_dir"] = deps_dir
        from pathlib import Path
        Path(cfg_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
from pathlib import Path
import urllib.request, subprocess, tempfile

# --- 新增：固定下载 Python 3.11.0 安装器并静默安装 ---
def _download_python311_installer(dest_dir: Path) -> Path:
    """
    下载 Windows x64 的 Python 3.11.0 安装器到 dest_dir。
    固定版本：3.11.0（用户要求的指定版本）。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    # 优先使用根目录下的安装器
    root_installer = Path(__file__).parent.parent / "python-3.11.0-amd64.exe"
    if root_installer.exists():
        print(f"[INFO] 使用本地安装器: {root_installer}")
        return root_installer
    # 否则下载
    url = "https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe"
    installer = dest_dir / "python-3.11.0-amd64.exe"
    if not installer.exists():
        print(f"[INFO] 正在下载 Python 安装器: {url}")
        urllib.request.urlretrieve(url, installer)
    return installer

def _silent_install_python311(installer: Path, target_dir: Path, timeout: int = 900) -> bool:
    """
    使用官方安装器静默安装到 target_dir（用户态，无需管理员）。
    说明：不使用`SimpleInstall`以避免与`TargetDir`冲突。
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(installer),
        "/quiet",
        "InstallAllUsers=0",
        f"TargetDir={str(target_dir)}",
        "PrependPath=0",
        "Include_pip=1",
        "Include_test=0",
        "Include_doc=0",
        "Include_launcher=0",
    ]
    print(f"[INFO] 正在静默安装 Python 3.11.0 到: {target_dir}")
    r = subprocess.run(args, timeout=timeout, creationflags=flags)
    if r.returncode != 0:
        print(f"[WARN] 静默安装返回码: {r.returncode}")
        return False
    return (target_dir / "python.exe").exists()

# --------------- 主入口 ---------------
def ensure_deps(prompt_ui=True, require_layers=("BASIC", "CORE"), force_enter=False, always_show_ui=False,
                deps_dir=None, from_settings=False):
    from PyQt6.QtWidgets import QApplication, QFileDialog
    app = QApplication.instance()
    if app is None:
        print("[WARN] ensure_deps 需要 GUI，但当前未创建 QApplication。请在主程序创建 QApplication 后再调用。")
        return False

    # 2) 先读配置，再决定是否弹目录选择框
    cfg_path = _load_config_path()
    if not deps_dir:
        deps_dir = _read_config_install_dir(cfg_path)

    if not deps_dir:
        parent = app.activeWindow()  # 没有也可为 None
        chosen = QFileDialog.getExistingDirectory(parent, "选择依赖安装/加载目录", str(Path.home()))
        if not chosen:
            # 用户取消，安全返回，避免后续对 None/省略号做路径拼接
            return False
        deps_dir = chosen
        _write_config_install_dir(cfg_path, deps_dir)

    deps_path = Path(deps_dir)
    deps_path.mkdir(parents=True, exist_ok=True)

    # 重复的目录选择与保存逻辑移除（前面已处理）
    from PyQt6.QtWidgets import QMessageBox, QDialog
    need_install = False
    if force_enter:
        try:
            custom_warning_dialog("警告", "缺失依赖，程序将强制进入，部分功能可能不可用。")
        except Exception:
            print("[WARN] 缺失依赖，程序将强制进入，部分功能可能不可用。")
        print("[Deps] 强制进入主程序，跳过依赖检查")
        return True

    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        # 打包模式下，彻底屏蔽外部 python311，始终用 sys.executable
        print(f"[INFO] 打包模式：直接使用 PyInstaller 内置解释器，无需独立 Python。")
        pyexe = Path(sys.executable)
        use_bundled_python = False
    else:
        # 开发模式：支持依赖隔离和私有解释器
        py_root = Path(deps_dir) / "python311"
        pyexe = py_root / "python.exe"
        current_pyexe = Path(sys.executable)
        current_site = _site_packages_root(current_pyexe)
        deps_dir_resolved = str(Path(deps_dir).resolve())
        mismatch_reason = ""
        
        # 检查是否打包模式
        is_packaged = hasattr(sys, '_MEIPASS') or '_internal' in str(Path(__file__).parent)
        mode_str = "打包模式" if is_packaged else "开发模式"
        
        if current_site and deps_dir and str(current_site).startswith(deps_dir_resolved):
            print(f"[INFO] {mode_str}：当前 Python 环境与依赖目录一致: {current_pyexe}")
            print(f"[DIAG] 当前 site-packages 路径: {current_site}")
            print(f"[DIAG] 依赖目录路径: {deps_dir_resolved}")
            pyexe = current_pyexe
            use_bundled_python = False
        else:
            use_bundled_python = True
            print(f"[INFO] {mode_str}：当前 Python 与依赖目录不一致，将使用独立 Python: {pyexe}")
            print(f"[DIAG] 当前 Python 解释器: {current_pyexe}")
            print(f"[DIAG] 当前 site-packages 路径: {current_site if current_site else '(未找到)'}")
            print(f"[DIAG] 依赖目录路径: {deps_dir_resolved}")
            if not current_site:
                mismatch_reason = "未能定位当前 Python 的 site-packages 路径。"
            elif not str(current_site).startswith(deps_dir_resolved):
                mismatch_reason = "当前 Python 的 site-packages 不在依赖目录下。"
            else:
                mismatch_reason = "未知原因导致环境不一致。"
            print(f"[DIAG] 环境不一致原因: {mismatch_reason}")
        # 只有开发模式下才自动安装 python311
        if use_bundled_python and not pyexe.exists():
            try:
                print("[INFO] 未找到私有 Python，将自动下载并安装 Python 3.11.0 ...")
                tmp_dir = Path(tempfile.mkdtemp(prefix="py311_dl_"))
                installer = _download_python311_installer(tmp_dir)
                ok = _silent_install_python311(installer, py_root)
                if not ok or not pyexe.exists():
                    QMessageBox.critical(None, "安装失败", "Python 3.11.0 静默安装失败，请检查网络或权限后重试。")
                    return False
                print(f"[OK] 已安装私有 Python: {pyexe}")
            except Exception as e:
                print(f"[ERR] 自动安装 Python 失败: {e}")
                QMessageBox.critical(None, "安装失败", f"自动安装 Python 失败：{e}")
                return False

    # 初始化 pip（无 venv）
    try:
        _ensure_pip(pyexe)
        state_path = Path(deps_dir) / STATE_FILE
        if not state_path.exists():
            _save_json(state_path, {"installed_layers": []})
        pip_ready_event.set()
    except Exception as e:
        print(f"[Deps] 预初始化 pip 失败: {e}")
        pip_ready_event.set()

    import platform
    print("【依赖目录选择后环境信息】")
    print("当前 Python 解释器:", pyexe)
    print("当前平台:", platform.platform())
    print("当前 sys.path:", sys.path)

    sp = _site_packages_root(pyexe)
    # 只有在非 BOOTSTRAPPED 模式下才注入私有路径，避免混合不同 Python 版本的包
    if os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") != "1":
        _inject_private_python_paths(pyexe)
    os.environ["LATEX_SNIPPER_SITE"] = str(sp or "")
    os.environ["LATEXSNIPPER_PYEXE"] = str(pyexe)

    state_path = deps_path / STATE_FILE
    state = _load_json(state_path, {"installed_layers": []})
    installed = {"layers": state.get("installed_layers", [])}

    state_path = deps_path / STATE_FILE

    needed = set(require_layers)
    missing_layers = [L for L in needed if L not in installed["layers"]]

    while True:
        if (missing_layers and prompt_ui) or always_show_ui:
            stop_event = threading.Event()
            # 默认选中的依赖层（首次启动时）
            default_select = ["BASIC", "CORE"]

            chosen = []
            dlg, chosen = _build_layers_ui(pyexe, deps_dir, installed, default_select, chosen, state_path, from_settings=from_settings)
            result = dlg.exec()
            if result != dlg.DialogCode.Accepted:
                # 用户在依赖选择窗口点“退出程序”
                return False

            # 检查是否强制进入（缺少关键层但用户选择直接进入）
            if chosen.get("force_enter", False):
                print("[INFO] 用户选择强制进入，跳过依赖安装")
                return True
            if chosen["layers"]:
                already_have = all(
                    l in state.get("installed_layers", []) for l in chosen["layers"]
                )
                if already_have:
                    print("[INFO] 所选层已存在，跳过下载。")
                    return True

            chosen_layers = chosen.get("layers", [])
            use_mirror = chosen.get("mirror", False)
            deps_dir = chosen.get("deps_path", deps_dir)
            deps_path = Path(deps_dir)
            state_path = deps_path / STATE_FILE
            state = _load_json(state_path, {"installed_layers": []})
            installed["layers"] = state.get("installed_layers", [])
            # 安装后复核关键层，必要时再次弹向导
            missing_layers = [L for L in set(require_layers) if L not in installed["layers"]]
            need_install = bool(chosen_layers) and bool(missing_layers)
            if not chosen_layers and needed.issubset(installed["layers"]):
                return True
            need_install = bool(chosen_layers)

        if need_install:
            if chosen_layers:
                if "HEAVY_GPU" in chosen_layers and not _gpu_available():
                    r = QMessageBox.question(None, "GPU 未检测",
                                             "未检测到 NVIDIA GPU，继续安装 CUDA 轮子可能失败，是否继续？",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if r != QMessageBox.StandardButton.Yes:
                        chosen_layers = [c for c in chosen_layers if c != "HEAVY_GPU"]

                pkgs = []
                for layer in chosen_layers:
                    pkgs.extend(LAYER_MAP[layer])
                # 核心层需要 torch：如果用户既没选 HEAVY_CPU 也没选 HEAVY_GPU，自动添加 HEAVY_CPU
                if "CORE" in chosen_layers and "HEAVY_CPU" not in chosen_layers and "HEAVY_GPU" not in chosen_layers:
                    pkgs.extend(LAYER_MAP.get("HEAVY_CPU", []))

                # ⚠️ 选择 HEAVY_GPU 时，排除 BASIC 层的 onnxruntime（避免与 onnxruntime-gpu 冲突）
                if "HEAVY_GPU" in chosen_layers:
                    # 移除 CPU 版 onnxruntime，保留 onnxruntime-gpu
                    pkgs = [p for p in pkgs if not (p.lower().startswith("onnxruntime") and "gpu" not in p.lower())]

                pkgs = _filter_packages(pkgs)
                log_q = queue.Queue()
                error_box = {"err": None}
                stop_event = threading.Event()
                pause_event = threading.Event()
                state_lock = threading.Lock()

                dlg, info, logw, btn_cancel, btn_pause, progress = _progress_dialog()
                btn_cancel.clicked.connect(lambda: (stop_event.set(), dlg.reject()))
                paused = False
                pause_event = threading.Event()
                def toggle_pause():
                    nonlocal paused
                    paused = not paused
                    if paused:
                        pause_event.clear()
                        btn_pause.setText("继续下载")
                    else:
                        pause_event.set()
                        btn_pause.setText("暂停下载")

                btn_pause.clicked.connect(toggle_pause)
                pause_event.set()

                # === 创建 InstallWorker ===
                worker = InstallWorker(pyexe, pkgs, stop_event, pause_event, state_lock, state, state_path,
                                       chosen_layers, log_q, mirror=use_mirror)
                # === 绑定信号 ===
                worker.log_updated.connect(logw.append)
                worker.progress_updated.connect(progress.setValue)

                def on_install_done(success: bool):
                    if success:
                        logw.append("\n[OK] 所有依赖安装完成 ✅")
                        logw.append("[INFO] 正在验证安装的功能层...")
                        
                        # 安装后进行运行时验证
                        verify_ok_layers = []
                        verify_fail_layers = []
                        for lyr in chosen_layers:
                            v_ok, v_err = _verify_layer_runtime(pyexe, lyr, timeout=60)
                            if v_ok:
                                verify_ok_layers.append(lyr)
                                logw.append(f"  [OK] {lyr} 验证通过")
                            else:
                                verify_fail_layers.append(lyr)
                                logw.append(f"  [FAIL] {lyr} 验证失败: {v_err[:100]}")
                        
                        # 只写入验证通过的层
                        try:
                            state = _load_json(state_path, {"installed_layers": []})
                            current_layers = set(state.get("installed_layers", []))
                            current_layers.update(verify_ok_layers)
                            _save_json(state_path, {"installed_layers": sorted(list(current_layers))})
                        except Exception as e:
                            print(f"[WARN] 无法写入 .deps_state.json: {e}")
                        
                        if verify_fail_layers:
                            logw.append(f"\n[WARN] 以下层安装但验证失败: {', '.join(verify_fail_layers)}")
                            QMessageBox.warning(dlg, "部分验证失败", 
                                f"以下功能层安装但无法正常工作:\n{', '.join(verify_fail_layers)}\n\n请查看日志或使用【打开环境终端】手动修复。")
                        else:
                            QMessageBox.information(dlg, "安装完成", "所有依赖已安装并验证通过！点击完成返回依赖向导。")
                    else:
                        logw.append("\n[ERR] 安装存在失败，请查看日志 ❌")
                        QMessageBox.warning(dlg, "安装不完整", "有依赖安装失败，请查看日志并重试。")
                    progress.setValue(progress.maximum())
                    # 统一改“完成”，返回向导
                    btn_cancel.setText("完成")
                    btn_pause.setEnabled(False)
                    try:
                        btn_cancel.clicked.disconnect()
                    except Exception:
                        pass
                    btn_cancel.clicked.connect(lambda: dlg.close())
                    # 刷新向导 UI
                    try:
                        if hasattr(dlg, "refresh_ui"):
                            dlg.refresh_ui()
                    except Exception as e:
                        print(f"[WARN] 无法调用刷新函数: {e}")

                worker.done.connect(on_install_done)

                # === UI线程日志轮询（防阻塞/防信号风暴）===
                timer = QTimer(dlg)
                timer.setInterval(50)

                def drain_log_queue():
                    drained = 0
                    lines_to_emit = []
                    while drained < 50:
                        try:
                            line = log_q.get_nowait()
                        except queue.Empty:
                            break
                        else:
                            lines_to_emit.append(line)
                            drained += 1
                    if lines_to_emit:
                        worker.log_updated.emit("\n".join(lines_to_emit))

                timer.timeout.connect(drain_log_queue)
                timer.start()

                def on_close_event(event):
                    try:
                        timer.stop()
                        worker.stop()
                        worker.wait(5)  # 等待最长 5 秒
                    except Exception as e:
                        print(f"[WARN] 关闭事件清理异常: {e}")
                    finally:
                        event.accept()

                dlg.closeEvent = on_close_event

                worker.start()
                result = dlg.exec()
                if worker.isRunning():
                    worker.stop()
                    worker.wait(1)

                if result != QDialog.DialogCode.Accepted:
                    # 用户在进度窗口点“退出下载”，回到依赖选择窗口
                    continue
        break
    return True

