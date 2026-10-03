# Office 共享公式编辑器

此目录是共享源码编辑器的可复现构建和测试入口，不随应用运行，也不要求用户安装 Node.js。

- `source-editor.js` 封装 CodeMirror 6：文档、事务、撤销、选择、补全、光标处 Tab 插入与结构诊断；选中多行时仍可整体缩进。
- `template-fields.js` 在源码事务中保存占位符位置，支持 Tab / Shift-Tab、选区包裹和独立撤销；用户源码不经过 snippet 字符串转义或模板重解析。
- `EditorAssets/editor-layout.mjs` 与 `editor.css` 是两个宿主唯一的布局与样式入口；宿主 HTML 只加载共享资源。顶部工具栏、左侧符号库、公式 / 源码分隔线和提交栏共用实现。
- `EditorAssets/symbol-library.mjs` 只保留公式模板，不包含用英文说明凑成的磁贴；`template-catalog.mjs` 统一分类、别名、快捷键、模板与补全目录。新增条目只修改目录数据；矩阵尺寸由 `matrix-templates.mjs` 生成。
- `EditorAssets/symbol-panel.mjs` 提供一个跨分类搜索、纵向分类导航与磁贴滚动、键盘导航和折叠。“常用”初始为空，右键磁贴或工具栏星标可加入或移除，本地保存选择；在“常用”视图不显示矩阵行列控件。只渲染可见磁贴，按实际公式和标题宽度测量并重新排布，同一公式在各分类宽度一致。缓存上限 256 项，不创建额外 MathLive 编辑器。矩阵模板保留在“结构”组。
- `EditorAssets/template-insertion.mjs` 记录活动编辑器与可视化选区，通过同一入口插入模板。源码补全、磁贴及 MathLive 原有 Ctrl+F/R/H/L/J 快捷键共用目录；源码区 Ctrl+F/H 继续用于查找 / 替换。
- `EditorAssets/source-sync.mjs` 协调源码和 MathLive；源码是唯一文档状态。异步预览核对修订号，仅明确的可视化修改才回写，中文组合输入期间延迟同步。源码移除旧的多行容器时重建 MathLive 控件，避免旧结构滞留。可无损往返的公式打开时直接聚焦可视化区。
- `EditorAssets/typography-panel.mjs` 使用原生宿主提供的字体目录与样式快照；全局设置和编辑器共用 17 项字形选项。数字字体显示全部系统字体，汉字字体使用从等线到幼圆的 23 项固定列表，以中文名称显示、不探测字形。下拉列表顺序固定，选择不会重排选项；列表外的当前字体显示选择提示，不作为可选字体追加。`font-size-picker.mjs` 从共享字号表生成可键盘操作的中文字号 / pt 菜单，并允许输入自定义 pt。`draft-preview.mjs` 用会话与修订筛选最终预览，处理合并、取消、组合输入和提交锁定。原生桥接复用 `IFormulaRenderer`，预览与提交使用当前草稿。
- Word / PowerPoint 设置页共用 `settings.css`、`settings-typography.mjs` 和 `cjk-font-picker.mjs`，字体选项由同一实现生成；宿主脚本维护各自的偏好状态和保存桥接。分段选择使用滑块动画，并遵循系统的减少动画偏好。
- Word / PowerPoint 设置页分别保存全局公式默认字体、字号、样式和颜色，并提供 JSON 导入、导出；导出文件名即预设名称。编辑器内字体调整只应用于当前公式。`TypographySettingsStore` 遇到不兼容的用户配置会删除并以当前默认值重建，不做迁移。
- `EditorAssets/latex-structure.mjs` 提供括号 / 环境诊断及保守的往返判定，不代替 TeX 渲染器。普通 `align` 在 MathLive 保留结构时可直接编辑；注释、MathML、结构错误、无法识别的命令，或 `\displaylines` 外含其他内容且被 MathLive 重组时，保留源码并限制可视化编辑。用户可点击提示中的“用上方结果替换源码（可撤销）”明确采用 MathLive 的表示，再继续可视化编辑。
- 编辑器 WebView2 关闭默认右键菜单和浏览器专属快捷键；可视化区保留 MathLive 右键菜单中的局部上色、剪切、粘贴和全选，隐藏键盘与菜单图标。全局颜色由源码外层 `\textcolor` 表示，并同步工具栏、可视化区、提交属性和最终预览；局部上色立即写回内层源码。 MathLive 仅解析全局颜色包裹内的公式，显示颜色从同一源码读取，以支持顶层多行环境；可视化写回恢复源码外层颜色包裹，状态窗格共享该逻辑。源码查找、复制粘贴、撤销，以及 MathLive 的模板快捷键照常由编辑器处理。顶部撤销、重做和符号库开关为带可访问名称的图标按钮。
- 构建结果 `source-editor.bundle.js`、许可证和共享 CSS 随 `EditorSharedAssets` 发布，Word/PPT 共用。依赖版本由 `package-lock.json` 固定。

在本目录运行：

```powershell
npm ci
npm run build
npm test
npm run test:browser
```

构建仅含运行时依赖，当前 JS 约 392 KB，依赖许可证由实际打包模块生成。修改源文件后重新生成 bundle；修改共享模块后运行对应回归。Node 通过当前环境的 `PATH` 查找，不依赖固定安装盘符。

浏览器测试使用已安装的 Edge、Playwright 和本地文件路由，模拟 WebView2 的虚拟主机映射，不访问在线脚本。覆盖两个宿主页面、系统深色模式下固定浅色外观、桌面与紧凑窗口、复杂源码、可视化编辑、撤销重做、过期通知、组合输入事件、补全、缩进、查找替换及提交。符号库回归覆盖空白常用、右键收藏、跨分类搜索后保留选区、模板填写、矩阵尺寸、键盘导航、纵向滚动、缓存复用、折叠恢复焦点、MathLive 公式预览和大小自适应。浏览器测试验证网页事件；WebView2 设置由托管构建及安装后实测确认。

截图与 Playwright 运行输出位于系统临时目录。组合输入测试验证事件生命周期，真实 Windows 输入法及 Office 内完整交互仍在安装包验收时检查。

参考：[CodeMirror API](https://codemirror.net/docs/ref/)、[MathLive 输入事件与静默更新](https://mathlive.io/mathfield/guides/interacting/)。

字体回归覆盖字体 / 字号 / 颜色、预览和提交快照一致、失效响应、取消、新会话、渲染错误、提交失败恢复及面板小窗口布局。浏览器测试使用模拟桥接；真实宿主渲染使用 `office_plugin/tools/Test-OfficeTypographyE2E.ps1` 验证，参数与环境要求见 [Office 插件说明](../../office_plugin/README.md)。

MathLive 与源码均可用 Escape 后再按 Tab 离开编辑器；预览往返在源码未改动时恢复原编辑目标与选区。字号组合输入纳入编辑保护。字体面板在外部点击或 Escape 时关闭，避免原生字体下拉列表因短暂失焦而无法选中；真实输入法与 Office 内下拉交互仍待宿主验收。

常用中的完整公式在空白编辑器中直接通过源码同步加载；外层全局颜色投影同样用于磁贴预览，避免 MathLive 将带颜色的多行环境插入为不可见的嵌套数组。
