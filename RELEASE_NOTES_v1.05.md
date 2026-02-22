# 🎉 LaTeXSnipper v1.05 Release Notes

## 🇨🇳 中文说明

### ✨ 重点更新
- 🧩 **模型架构精简为 pix2text-only**：移除 `pix2tex` / `UniMERNet` 全链路逻辑（含分支、fallback、多模型入口），统一到 `pix2text` 模型族。
- 🧠 **默认策略调整**：默认识别模型改为 `pix2text` 公式识别；PDF 场景默认推荐 `mixed`（混合识别）。
- 🧰 **依赖向导单模型化**：CPU/GPU 仅切换 `torch + onnxruntime` 互斥组合，固定 `pix2text==1.1.6` + `transformers==4.55.4` + `tokenizers==0.21.4`，并保留 `pymupdf` 以保障 PDF 能力。

### 🚀 稳定性与体积优化
- 🪶 **进一步轻量化**：清理旧模型链及冗余路径，降低打包体积膨胀风险。
- 🔁 **安装顺序固化**：保持 pix2text 稳定安装顺序，减少 pip resolver 长时间回溯。
- 🧭 **配置迁移增强**：历史配置中 `pix2tex/unimernet` 自动映射到 `pix2text`，升级后可直接运行。

### 🖥️ 启动与日志体验
- 🪟 新增启动阶段显示控制台选项（默认关闭），并持续修复打包模式下多余终端闪现问题。
- 📋 调试终端可用性优化：恢复鼠标滚轮查看与文本复制能力。
- 🏷️ 日志窗口标题调整为 **“初始化与运行日志”**，语义更准确。
- 🚀 Splash 状态文案细化（如“加载主窗口”“预热模型中”），降低“卡住”误判。

### 🐛 关键修复
- ✅ 修复多处子进程窗口策略导致的空白终端常驻/频繁闪现。
- ✅ 修复设置项“启动时显示终端”相关崩溃与状态不同步问题。
- ✅ 修复部分误导性日志文案，区分“探测失败/回退成功”与“真实不可用”。
- ✅ 统一模型预热与 worker 就绪判定，减少“显示已就绪但首次识别慢”的体验落差。

---

## 🇺🇸 English

### ✨ Highlights
- 🧩 **pix2text-only architecture**: removed the full `pix2tex` / `UniMERNet` pipeline (branches, fallback paths, and multi-model entrypoints), unified on `pix2text`.
- 🧠 **Default policy update**: default model is now `pix2text` formula OCR; PDF flow now recommends `mixed` mode by default.
- 🧰 **Single-model dependency wizard**: CPU/GPU now only switches mutually exclusive `torch + onnxruntime` stacks, with pinned `pix2text==1.1.6`, `transformers==4.55.4`, `tokenizers==0.21.4`, and `pymupdf` retained for PDF.

### 🚀 Stability and Size
- 🪶 **Lean package path**: cleaned legacy model chains and redundant paths to reduce package bloat risk.
- 🔁 **Stable install sequencing**: preserved deterministic pix2text install order to avoid long pip backtracking.
- 🧭 **Config migration**: legacy `pix2tex/unimernet` values are auto-mapped to `pix2text` on startup.

### 🖥️ Startup & Logging UX
- 🪟 Added startup-console preference (default off), with continued fixes for unwanted terminal flashing in packaged mode.
- 📋 Improved debug console usability: mouse-wheel scrolling and text copy are available again.
- 🏷️ Console title renamed to **“Initialization & Runtime Log”** (CN UI: “初始化与运行日志”).
- 🚀 Splash messaging refined (e.g., "Loading main window", "Model preheating") to reduce perceived startup stalls.

### 🐛 Fixes
- ✅ Fixed multiple subprocess window-policy issues causing persistent/blank flashing terminals.
- ✅ Fixed crashes and state-sync issues around the “show console on startup” setting.
- ✅ Adjusted misleading log texts to distinguish probe fallback from real model failures.
- ✅ Aligned model preheat/worker readiness checks to improve first-inference behavior.
