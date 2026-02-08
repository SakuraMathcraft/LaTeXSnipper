# 🎉 LaTeXSnipper v1.02 Release Notes

## 🇨🇳 中文说明

### ✨ What Changed
- 🔧 GPU 依赖安装策略升级为 CUDA 版本矩阵自动适配，不再固定 `cu118`。
- 🧭 `HEAVY_GPU` 层改为动态解析版本：`torch/torchvision/torchaudio` 与 `onnxruntime-gpu` 按检测结果自动匹配。
- 🖥️ 设置页“打开环境终端”提示改为动态命令展示（PyTorch/ONNX 根据当前 CUDA 自动给出）。
- 📦 pix2text 安装提示调整为安装最新版：`pip install -U pix2text`（不再固定版本号）。
- 🪟 PDF 识别结果窗口改为更稳定的独立窗口交互模式，避免特殊模态行为带来的主窗口阻塞。

### 🐛 What Fixed
- ✅ 修复大页数 PDF 识别后关闭结果窗口导致主窗口卡死、假关闭、系统提示音持续的问题。
- ✅ 修复 PDF 结果窗口关闭后可能触发的阻塞链路与闪退风险。
- ✅ 修复“终端提示命令”与“实际安装逻辑”版本不一致问题（包括 ONNX Runtime 提示）。
- ✅ 修复 CUDA 版本检测覆盖不足问题，支持 `cu118/cu121/cu124/cu126/cu128/cu129/cu130` 自动映射。
- ✅ 修复 `HEAVY_GPU` 层中硬编码版本导致的策略偏差，统一到动态矩阵策略。

---

## 🇺🇸 English

### ✨ What Changed
- 🔧 Upgraded GPU dependency strategy to CUDA matrix-based auto matching instead of fixed `cu118`.
- 🧭 `HEAVY_GPU` now resolves versions dynamically: `torch/torchvision/torchaudio` and `onnxruntime-gpu` are selected from detected CUDA.
- 🖥️ Environment terminal tips in Settings are now generated dynamically (PyTorch/ONNX commands match current CUDA).
- 📦 pix2text setup now installs latest version via `pip install -U pix2text` (no pinned version).
- 🪟 PDF recognition result window was refactored to a more stable standalone interaction model.

### 🐛 What Fixed
- ✅ Fixed main-window freeze, pseudo-close behavior, and persistent Windows warning sounds after closing PDF result window on large documents.
- ✅ Fixed potential crash paths triggered after PDF result window close.
- ✅ Fixed version mismatch between terminal helper commands and actual installer behavior (including ONNX Runtime hints).
- ✅ Expanded CUDA detection coverage with automatic mapping for `cu118/cu121/cu124/cu126/cu128/cu129/cu130`.
- ✅ Removed hardcoded-version drift in `HEAVY_GPU` and unified behavior under one dynamic matrix strategy.

