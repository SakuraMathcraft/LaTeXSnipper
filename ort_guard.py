# 文件: src/backend/ort_guard.py
import os
import importlib
from functools import lru_cache

MIN_IR_FOR_RUNTIME = 10  # 你的 OCR 模型当前使用的 IR 版本
MIN_RUNTIME_FOR_IR10 = (1, 20)  # 经验阈值: 1.20.x 可正常加载 IR>=10 的常见模型

os.environ.setdefault("ORT_DISABLE_AZURE", "1")
os.environ.setdefault("ONNXRUNTIME_DISABLE_TELEMETRY", "1")

def _parse_ver(v: str):
    parts = v.split(".")
    return tuple(int(p) for p in parts[:2])

@lru_cache
def ort_environment_ok(model_path: str | None = None) -> bool:
    try:
        import numpy as np
        import onnxruntime as ort
    except Exception as e:
        print(f"[ORTGuard] 导入失败: {e}")
        return False

    ort_ver = _parse_ver(ort.__version__)
    np_major = int(np.__version__.split(".")[0])

    if np_major >= 2 and ort_ver < (1, 20):
        print(f"[ORTGuard] 不推荐组合: onnxruntime={ort.__version__} 与 numpy={np.__version__} (建议升级 onnxruntime≥1.20.*)")
        return False

    if model_path:
        try:
            import onnx  # 仅在需要时加载
            m = onnx.load(model_path)
            ir = getattr(m, "ir_version", None)
            if ir and ir >= MIN_IR_FOR_RUNTIME and ort_ver < MIN_RUNTIME_FOR_IR10:
                print(f"[ORTGuard] 模型 IR={ir} 需要更高 onnxruntime (当前 {ort.__version__})")
                return False
        except Exception as e:
            # 非致命，继续尝试运行
            print(f"[ORTGuard] 模型 IR 预检忽略: {e}")

    return True

def create_cpu_session(model_path: str):
    """创建仅 CPU Provider 的 InferenceSession"""
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    providers = [p for p in ort.get_available_providers() if p == "CPUExecutionProvider"]
    if not providers:
        raise RuntimeError("[ORTGuard] 未发现 CPUExecutionProvider")
    return ort.InferenceSession(model_path, sess_options=so, providers=providers)
