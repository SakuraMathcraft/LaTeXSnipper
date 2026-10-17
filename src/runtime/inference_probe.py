"""Child-process checks for an isolated inference component."""

import inspect

from mathcraft_ocr.native_libraries import audit_private_gpu_libraries

PROBE_CODE = (
    "from pathlib import Path\n"
    + inspect.getsource(audit_private_gpu_libraries)
    + r"""
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
gpu = sys.argv[2] == 'gpu'
if not Path(sys.prefix).resolve().is_relative_to(root):
    raise RuntimeError('Python prefix is outside the inference component')
handles = []
native = root / 'native'
if gpu and os.name == 'nt':
    handles.append(os.add_dll_directory(str(native)))

import numpy as np
import cv2
import rapidocr
import tokenizers
import transformers
import onnxruntime as ort

if gpu:
    ort.preload_dlls(directory=str(native))
provider = 'CUDAExecutionProvider' if gpu else 'CPUExecutionProvider'

def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)

def integer(field, value):
    return varint(field << 3) + varint(value)

def message(field, value):
    return varint((field << 3) | 2) + varint(len(value)) + value

def string(field, value):
    return message(field, value.encode('utf-8'))

def info(name, shape):
    dimensions = b''.join(message(1, integer(1, value)) for value in shape)
    tensor = integer(1, 1) + message(2, dimensions)
    return string(1, name) + message(2, message(1, tensor))

def check(operation, left, right, expected):
    node = string(1, 'x') + string(1, 'w') + string(2, 'y') + string(4, operation)
    graph = message(1, node) + string(2, 'probe')
    graph += message(11, info('x', left.shape)) + message(11, info('w', right.shape)) + message(12, info('y', expected.shape))
    model = integer(1, 8) + string(2, 'latexsnipper') + message(7, graph) + message(8, integer(2, 13))
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    if gpu:
        options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
    session = ort.InferenceSession(model, sess_options=options, providers=[provider], enable_fallback=False)
    session.disable_fallback()
    if provider not in session.get_providers():
        raise RuntimeError('Requested execution provider did not initialize')
    actual = session.run(None, {'x': left, 'w': right})[0]
    if not np.allclose(actual, expected, rtol=1e-5, atol=1e-5):
        raise RuntimeError(operation + ' result mismatch')

left = np.array([[1, 2], [3, 4]], dtype=np.float32)
right = np.array([[4, 3], [2, 1]], dtype=np.float32)
check('MatMul', left, right, left @ right)
left = np.arange(1, 10, dtype=np.float32).reshape(1, 1, 3, 3)
right = np.ones((1, 1, 2, 2), dtype=np.float32)
expected = np.array([[[[12, 16], [24, 28]]]], dtype=np.float32)
check('Conv', left, right, expected)
native_modules = audit_private_gpu_libraries(native) if gpu else {}
print(json.dumps({'python': sys.version.split()[0], 'ort': ort.__version__, 'provider': provider,
                  'gpu_inference': gpu, 'checks': ['imports', 'MatMul', 'Conv'], 'native_modules': native_modules}))
"""
)
