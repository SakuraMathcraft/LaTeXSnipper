# 🎉 LaTeXSnipper v1.03 Release Notes

## 🇨🇳 中文说明

### ✨ New Features
- 📐 截图选框新增实时尺寸与坐标显示：支持 `宽 x 高` 与左上角 `x,y`，方便精确截取。
- 🎯 截图层新增局部十字准星，便于对齐关键字符与公式区域。
- 🏷️ 统一“公式命名/重命名”弹窗：历史记录与收藏夹使用同一套交互样式。

### 🚀 UX Improvements
- 🌗 截图体验升级为“选区高亮、外围变暗”聚焦模式，选区内容保持原亮度。
- 🪟 编辑窗口去除最小化按钮，保留更清晰的工具窗口行为。
- 📌 重命名窗口固定大小，仅保留必要控制，交互更稳定。
- 🎨 收藏夹选中样式优化为浅蓝高亮，减少黑框干扰。
- 🧹 清空历史记录确认弹窗显示将清理的具体条数。

### 🐛 Bug Fixes
- ✅ 修复收藏夹“添加到历史”出现双重 InfoBar 提示的问题。
- ✅ 修复收藏夹标签名称显示不同步（历史已命名但收藏夹未显示）的问题。
- ✅ 修复历史记录编辑保存后列表未即时刷新的问题。
- ✅ 修复收藏夹导出 SVG 失败（`cannot import name 'latex_to_svg'`）的问题。
- ✅ 精简 CORE 依赖层冗余项，减少与 `pix2tex` 传递依赖的重复硬编码。

---

## 🇺🇸 English

### ✨ New Features
- 📐 Added real-time capture metrics in screenshot selection: `width x height` and top-left `x,y` coordinates.
- 🎯 Added a local crosshair near the cursor for more accurate formula-region alignment.
- 🏷️ Unified formula rename dialog across History and Favorites for consistent behavior.

### 🚀 UX Improvements
- 🌗 Upgraded capture overlay to focused mode: selected area stays bright while outside area is dimmed.
- 🪟 Removed minimize button from formula editor window for cleaner tool-window behavior.
- 📌 Made rename dialog fixed-size with minimal controls to reduce UI noise.
- 🎨 Improved Favorites selected-row style to soft blue highlight.
- 🧹 Clear-history confirmation now shows the exact number of records to be removed.

### 🐛 Bug Fixes
- ✅ Fixed duplicate InfoBar notifications when adding formulas from Favorites to History.
- ✅ Fixed name/tag sync issue where renamed labels did not render correctly in Favorites.
- ✅ Fixed stale UI issue where edited History content was saved but not refreshed immediately.
- ✅ Fixed SVG export failure in Favorites (`cannot import name 'latex_to_svg'`).
- ✅ Reduced redundant CORE dependency declarations and aligned with pip-resolved transitive deps.
