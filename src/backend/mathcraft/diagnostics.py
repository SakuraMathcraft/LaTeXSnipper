"""MathCraft runtime failure classification and user-facing diagnostics."""

from __future__ import annotations

import re

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

    if not raw:
        return _pack(
            "UNKNOWN",
            "模型预热未完成",
            "MathCraft OCR 预热失败，请打开运行日志查看具体原因。",
            "未拿到明确异常文本，需要结合运行日志继续排查。",
        )
    # Match the missing import itself, never incidental module names in stack paths.
    missing_imports = re.findall(r"No module named ['\"]([^'\"]+)['\"]", raw, re.IGNORECASE)
    missing_module = missing_imports[-1] if missing_imports else ""
    if missing_module == "mathcraft_ocr":
        return _pack(
            "MATHCRAFT_MISSING",
            "缺少 MathCraft OCR",
            "未找到 MathCraft OCR 包，请检查程序文件是否完整。",
            "mathcraft_ocr 模块不可导入，当前内置识别链路不可用。",
        )
    if missing_module == "onnxruntime":
        return _pack(
            "ONNXRUNTIME_MISSING",
            "缺少 onnxruntime",
            "推理组件缺少 onnxruntime，请检查并修复安装资源。",
            "onnxruntime 模块缺失，MathCraft ONNX 后端不可用。",
        )
    if missing_module.startswith("onnxruntime.") or looks_like_onnxruntime_install_error(raw):
        runtime_hint = "onnxruntime 运行资源损坏或不可用，请检查并修复推理组件。"
        return _pack(
            "ONNXRUNTIME_BROKEN",
            "onnxruntime 依赖异常",
            runtime_hint,
            f"onnxruntime 安装不完整、原生库加载失败或 provider 查询失败: {raw[:300]}",
        )
    if missing_module:
        return _pack(
            "MATHCRAFT_DEP_BROKEN" if "." in missing_module else "MATHCRAFT_DEP_MISSING",
            "MathCraft 依赖不完整",
            "MathCraft OCR 运行资源缺失或不完整，请检查并修复安装资源。",
            f"无法导入模块 {missing_module!r}。"
            + ("请检查所属包的安装完整性与版本兼容性。" if "." in missing_module else "推理组件无法找到该模块。"),
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
    if looks_like_cuda_runtime_error(raw):
        return _pack(
            "CUDA_RUNTIME_BROKEN",
            "GPU 运行资源异常",
            "GPU 推理不可用，请检查 NVIDIA 显卡、驱动及推理组件完整性。",
            f"私有 CUDA/cuDNN 初始化失败: {raw[:1000]}",
        )
    if looks_like_gpu_provider_error(raw):
        return _pack(
            "GPU_PROVIDER_UNAVAILABLE",
            "GPU 推理不可用",
            "当前 GPU 推理不可用，请检查显卡、驱动和安装资源。更换发行类型需使用对应安装包。",
            f"请求的 GPU execution provider 未能启用，且未回退到 CPU: {raw[:300]}",
        )
    if "unsupported worker action" in lower or "unsupported warmup profile" in lower:
        return _pack(
            "UNSUPPORTED_MODE",
            "识别模式不支持",
            "当前 MathCraft OCR 版本不支持该识别模式。",
            f"请求了 MathCraft v1 未支持的模式: {raw[:300]}",
        )
    if "timeout" in lower or "运行进程超时" in raw:
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
