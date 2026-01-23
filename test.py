
import torch

# 是否可用 GPU
print("cuda.is_available:", torch.cuda.is_available())

# Torch 版本
print("torch version:", torch.__version__)

# CUDA 运行时版本 (可能为 None 如果是 CPU 构建)
print("torch.version.cuda:", torch.version.cuda)

# cuDNN 版本 (若未启用返回 None 或触发 AttributeError)
print("cudnn version:", torch.backends.cudnn.version())

# 设备名称(仅在有 GPU 时)
if torch.cuda.is_available():
    print("device 0:", torch.cuda.get_device_name(0))
import numpy
print(numpy.__version__)
