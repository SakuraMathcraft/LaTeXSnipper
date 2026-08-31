"""MathCraft runtime failure classification and user-facing diagnostics."""

from __future__ import annotations

import sys

from mathcraft_ocr.error_patterns import (
    looks_like_cuda_runtime_error,
    looks_like_gpu_provider_error,
    looks_like_onnxruntime_install_error,
)

def classify_mathcraft_failure(detail: str) -> dict[str, str]:
    raw = str(detail or "").strip()
    lower = raw.lower()

    def _pack(code: str, title: str, user_message: str, log_message: str) -> dict[str, str]:
        return {
            "code": code,
            "title": title,
            "user_message": user_message,
            "log_message": log_message,
        }

    def _cuda_runtime_diagnostics() -> tuple[str, str]:
        try:
            if sys.platform == "linux":
                from .cuda_diagnostics import diagnose_cuda_shared_libraries

                report = diagnose_cuda_shared_libraries()
            else:
                from .cuda_diagnostics import diagnose_cuda_dll_paths

                report = diagnose_cuda_dll_paths()
            return report.format_for_user(), report.format_for_log()
        except Exception:
            return "", ""

    if not raw:
        return _pack(
            "UNKNOWN",
            "模型预热未完成",
            "MathCraft OCR 预热失败，请打开运行日志查看具体原因。",
            "未拿到明确异常文本，需要结合运行日志继续排查。",
        )
    if "no module named" in lower and "mathcraft_ocr" in lower:
        return _pack(
            "MATHCRAFT_MISSING",
            "缺少 MathCraft OCR",
            "未找到 MathCraft OCR 包，请检查程序文件是否完整。",
            "mathcraft_ocr 模块不可导入，当前内置识别链路不可用。",
        )
    if "no module named" in lower and "onnxruntime" in lower:
        return _pack(
            "ONNXRUNTIME_MISSING",
            "缺少 onnxruntime",
            "未安装 onnxruntime 依赖，请重新校验依赖层是否安装完整。",
            "onnxruntime 模块缺失，MathCraft ONNX 后端不可用。",
        )
    if looks_like_onnxruntime_install_error(raw):
        runtime_hint = "onnxruntime 依赖未正确安装或运行时不可用，请通过依赖管理重装当前 MathCraft 后端。"
        if sys.platform == "win32":
            runtime_hint = (
                f"{runtime_hint} 如 CPU 后端仍失败，请安装最新 Microsoft Visual C++ Redistributable x64 后重启。"
            )
        return _pack(
            "ONNXRUNTIME_BROKEN",
            "onnxruntime 依赖异常",
            runtime_hint,
            f"onnxruntime 可导入但运行时接口不完整或 provider 查询失败: {raw[:300]}",
        )
    mathcraft_runtime_modules = (
        "rapidocr",
        "cv2",
        "opencv",
        "numpy",
        "pil",
        "pillow",
        "transformers",
        "tokenizers",
    )
    if "no module named" in lower and any(module in lower for module in mathcraft_runtime_modules):
        return _pack(
            "MATHCRAFT_DEP_MISSING",
            "MathCraft 依赖不完整",
            "当前依赖环境缺少 MathCraft OCR 运行依赖，请通过依赖管理安装 BASIC、CORE 和对应的 MATHCRAFT_CPU/GPU 层。",
            f"MathCraft worker 缺少运行依赖，通常是打包模板 Python 尚未部署完整依赖: {raw[:300]}",
        )
    if "not ready" in lower and "missing" in lower and "missing=[]" not in lower:
        return _pack(
            "MODEL_CACHE_INCOMPLETE",
            "模型缓存不完整",
            "MathCraft OCR 模型缓存不完整，请补齐模型权重后重试。",
            f"MathCraft 模型缓存不完整: {raw[:300]}",
        )
    if "failed to download model" in lower or "no usable download source" in lower:
        return _pack(
            "MODEL_DOWNLOAD_FAILED",
            "模型权重下载失败",
            "MathCraft OCR 模型权重下载失败，请检查网络连接或稍后重试。",
            f"MathCraft 模型权重下载失败: {raw[:300]}",
        )
    if "list index out of range" in lower or ("indexerror" in lower and "rapidocr" in lower):
        return _pack(
            "OCR_VOCAB_MISMATCH",
            "OCR 字典与模型不匹配",
            "MathCraft 文字识别模型与字典不匹配，请更新或重新下载 MathCraft 模型权重。",
            f"RapidOCR 解码越界，通常是 PP-OCR 识别模型与字典文件不匹配: {raw[:300]}",
        )
    if looks_like_cuda_runtime_error(raw):
        user_hint, log_hint = _cuda_runtime_diagnostics()
        user_message = "CUDA 环境异常，GPU 推理不可用。"
        if user_hint:
            user_message = f"{user_message}{user_hint}"
        path_name = "LD_LIBRARY_PATH" if sys.platform == "linux" else "PATH"
        log_message = f"CUDAExecutionProvider 初始化失败，常见原因是 CUDA/cuDNN 版本不匹配或 {path_name} 配置错误。"
        if log_hint:
            log_message = f"{log_message} {log_hint}"
        return _pack(
            "CUDA_RUNTIME_BROKEN",
            "CUDA 环境异常",
            user_message,
            log_message,
        )
    if looks_like_gpu_provider_error(raw):
        return _pack(
            "GPU_PROVIDER_UNAVAILABLE",
            "GPU 推理不可用",
            "当前 GPU 推理后端不可用，请检查依赖层和显卡运行环境。",
            f"请求的 GPU execution provider 未能启用，且未回退到 CPU: {raw[:300]}",
        )
    if "unsupported worker action" in lower or "unsupported warmup profile" in lower:
        return _pack(
            "UNSUPPORTED_MODE",
            "识别模式不支持",
            "当前 MathCraft OCR 版本不支持该识别模式。",
            f"请求了 MathCraft v1 未支持的模式: {raw[:300]}",
        )
    if "timeout" in lower:
        return _pack(
            "WORKER_TIMEOUT",
            "识别进程超时",
            "MathCraft OCR 运行进程响应超时，请稍后重试或检查模型运行环境。",
            "MathCraft OCR 运行进程超时，需要检查模型初始化耗时、图片大小和运行环境。",
        )
    return _pack(
        "UNKNOWN",
        "模型运行异常",
        "MathCraft OCR 运行异常，请打开运行日志查看具体原因。",
        f"未命中已知错误分类，原始错误: {raw[:300]}",
    )
