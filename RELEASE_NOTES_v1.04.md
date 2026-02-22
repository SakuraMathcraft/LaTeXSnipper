# 🎉 LaTeXSnipper v1.04 Release Notes

## 🇨🇳 中文说明

### ✨ 重点更新
- 精简 `BASIC` 层依赖：移除 `PyQt6-WebEngine`、`PyQt6-Fluent-Widgets` 等 UI 侧依赖，`BASIC` 仅保留非 GUI 运行必需项（网络、图像处理、onnxruntime 等）。
- 内置 `python311` 运行时：打包版默认使用内置独立 Python，不再依赖或污染用户本机 Python 环境。
- 共享 Torch 机制升级：新增统一的 `backend/torch_runtime.py` 策略，隔离环境可复用主环境 Torch 能力，减少重复安装与环境漂移。
- 安装体积显著下降：依赖向导下载体积与安装时间明显降低，尤其是首次部署和重装场景。
- 修复 pix2text 安装阶段长时间回溯：固定关键链路版本并调整安装顺序，避免 pip resolver 在冲突依赖间反复回溯。

### ⚙️ 安装与运行策略
- 打包模式首启默认落到内置 `deps/python311`，用户无需先手动选择依赖环境。
- `BASIC` 层不再承担 GUI 运行库安装职责，避免与打包内置运行时重复。
- pix2text 安装流程改为稳定顺序：先卸载 `optimum*`，再固定 `transformers==4.55.4` 和 `tokenizers==0.21.4`，最后安装 `pix2text==1.1.6`。
- 隔离环境 Torch 校验/注入统一走共享逻辑（含 `LATEXSNIPPER_SHARED_TORCH_SITE` 与 `torch/lib` 路径处理）。

### 🚀 体验升级
- 截图层升级为“选区高亮 + 外围变暗”的聚焦模式，框选区域更清晰。
- 十字准星升级为黑白双层样式（外黑内白），在深色/浅色背景下都更显眼。
- 截图时显示实时尺寸与坐标，便于精准截取公式区域。

### 🐛 Bug 修复
- 修复“依赖路径已更改”弹窗点击 `Yes` 后不生效的问题（`sys` 局部变量作用域错误导致保存流程异常）。
- 修复隔离环境中 Torch 校验命令误判问题（可用环境不再被错误提示 `ModuleNotFoundError: torch`）。
- 修复打包模式与隔离环境切换中的若干状态同步问题，提升重检与重装稳定性。
- 优化 pix2text 依赖提示弹窗内容与长度，命令预览更紧凑，复制执行更直接。

---

## 🇺🇸 English

### ✨ Highlights
- Slimmed down the `BASIC` layer by removing UI-side dependencies (e.g. `PyQt6-WebEngine`, `PyQt6-Fluent-Widgets`).
- Bundled `python311` runtime: packaged builds now default to an internal isolated Python and no longer pollute users' system Python.
- Upgraded shared Torch strategy via `backend/torch_runtime.py`, enabling isolated envs to reuse Torch from main runtime.
- Significantly reduced dependency download/install footprint.
- Fixed pip resolver backtracking during pix2text setup by pinning key packages and improving install order.

### ⚙️ Runtime / Installer Policy
- First launch in packaged mode now defaults to bundled `deps/python311` without requiring manual environment selection.
- `BASIC` now focuses on non-GUI runtime dependencies only.
- pix2text setup uses a stable sequence: remove `optimum*`, pin `transformers==4.55.4` + `tokenizers==0.21.4`, then install `pix2text==1.1.6`.
- Shared Torch probing/injection is unified, including `LATEXSNIPPER_SHARED_TORCH_SITE` handling.

### 🚀 UX Improvements
- Capture overlay now uses focused dimming (bright selection + dimmed outside region).
- Crosshair upgraded to a dual-color style (black outer + white inner) for better visibility on both light and dark backgrounds.
- Real-time size/coordinate feedback during capture improves precision.

### 🐛 Bug Fixes
- Fixed restart flow after dependency path change (`Yes` action now works as expected).
- Fixed false-negative Torch checks in isolated environments.
- Improved stability for packaged mode + isolated env switching and re-validation.
- Simplified pix2text dependency tip dialog and command preview.
