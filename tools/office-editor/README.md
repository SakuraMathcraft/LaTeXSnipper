# Office 共享公式编辑器

此目录是共享源码编辑器的可复现构建和测试入口，不随应用运行，也不要求用户安装 Node.js。

- `source-editor.js` 封装 CodeMirror 6：文档、事务、撤销、选择、补全、缩进与结构诊断。
- `template-fields.js` 在源码事务中保存占位符位置，支持 Tab / Shift-Tab、选区包裹和独立撤销；用户源码不经过 snippet 字符串转义或模板重解析。
- `EditorAssets/editor-layout.mjs` 与 `editor.css` 是两个宿主唯一的布局与样式入口；宿主 HTML 只加载共享资源。顶部撤销 / 重做、公式 / 源码分隔线、底部两行磁贴和提交栏共用实现。
- `EditorAssets/symbol-library.mjs` 保留现有条目，`template-catalog.mjs` 统一分类、别名、快捷键、模板与补全目录。新增条目只修改目录数据；矩阵尺寸由 `matrix-templates.mjs` 生成。
- `EditorAssets/symbol-panel.mjs` 提供统一搜索、分类、横向滚动、键盘导航和折叠。静态公式仅在磁贴可见时渲染，缓存上限 128 项，不创建额外 MathLive 编辑器，不随草稿字体变化重建。
- `EditorAssets/template-insertion.mjs` 记录活动编辑器与可视化选区，通过同一入口插入模板。源码补全、磁贴及 MathLive 原有 Ctrl+F/R/H/L/J 快捷键共用目录；源码区 Ctrl+F/H 继续用于查找 / 替换。
- `EditorAssets/source-sync.mjs` 协调源码和 MathLive；源码是唯一文档状态。异步预览核对修订号，仅明确的可视化修改才回写，中文组合输入期间延迟同步。
- `EditorAssets/typography-panel.mjs` 使用原生宿主提供的字体目录、字号表和样式快照；`draft-preview.mjs` 用会话与修订筛选最终预览，处理合并、取消、组合输入和提交锁定。原生桥接复用 `IFormulaRenderer`，预览与提交使用当前草稿。
- `EditorAssets/latex-structure.mjs` 提供括号 / 环境诊断及保守的往返判定，不代替 TeX 渲染器。
- 构建结果 `source-editor.bundle.js`、许可证和共享 CSS 随 `EditorSharedAssets` 发布，Word/PPT 共用。依赖版本由 `package-lock.json` 固定。

在本目录运行：

```powershell
npm ci
npm run build
npm test
npm run test:browser
```

构建仅含运行时依赖，当前 JS 约 392 KB，依赖许可证由实际打包模块生成。修改源文件后重新生成 bundle；修改共享模块后运行对应回归。Node 通过当前环境的 `PATH` 查找，不依赖固定安装盘符。

浏览器测试使用已安装的 Edge、Playwright 和本地文件路由，模拟 WebView2 的虚拟主机映射，不访问在线脚本。覆盖两个宿主页面、明暗主题、1180×780、980×680 与 640×480 窗口、复杂源码、可视化编辑、撤销重做、过期通知、组合输入事件、补全、缩进、查找替换及提交。6A 回归另覆盖搜索后保留选区、两种编辑目标的模板填写、矩阵尺寸、转义源码、模板命令边界、键盘磁贴导航、滚轮区域隔离、翻页、缓存复用、折叠恢复焦点和延迟预览期间的提交锁定。

截图与 Playwright 运行输出位于系统临时目录。组合输入测试验证事件生命周期，真实 Windows 输入法及 Office 内完整交互仍在安装包验收时检查。

参考：[CodeMirror API](https://codemirror.net/docs/ref/)、[MathLive 输入事件与静默更新](https://mathlive.io/mathfield/guides/interacting/)。

6B 回归覆盖字体 / 字号 / 颜色、预览和提交快照一致、失效响应、取消、新会话、渲染错误、提交失败恢复及面板小窗口布局。浏览器测试使用模拟桥接；真实渲染需另外执行 `office_plugin/tests/LaTeXSnipper.OfficePlugin.Rendering.Smoke` 的 `--typography` 检查。
