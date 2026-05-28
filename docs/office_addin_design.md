# Office.js Add-in 迁移记录

本文记录 `office_addin` 已实现的 Office.js 行为和迁移价值。它不再作为 LaTeXSnipper Office 集成的最终设计文档；最终架构见 `docs/office_plugin_design.md`。

## 结论

Office.js 已经验证了 LaTeXSnipper 与 Word/PowerPoint 集成的核心流程，但它不适合作为最终产品形态：

- 单机安装无法像原生插件一样可靠持久显示 Ribbon；稳定分发依赖企业部署、Office Store 或受信任目录策略。
- Ribbon 图标、manifest、WebView Runtime、localhost HTTPS、证书和 sideload 缓存都属于宿主平台外部约束。
- 无法实现每个公式都是可双击编辑的原生 OLE 对象。
- 无法在 Word/PPT 对象模型底层提供类似 MathType/AxMath 的自绘公式对象、快捷键和对象生命周期控制。

因此，`office_addin` 保留为迁移参考；新增和最终能力进入 Windows 原生 `office_plugin`。

## 已验证能力

```text
Word / PowerPoint Ribbon
  -> Shared runtime task pane
       -> MathLive quick editor
       -> Dialog editor
       -> Local Office bridge
            GET  installed add-in static site over HTTPS in release builds
            POST /convert/latex
            POST /recognize/screenshot
            POST /recognition/status
            GET  /health, /config
```

这些能力可以迁移到原生插件：

- Ribbon 命令模型：编辑器、插入、截图识别、加载、删除、编号、重编号。
- Bridge 协议：LaTeX 转 OMML、截图 OCR、OCR 状态、安装路径发现。
- MathLive 编辑器：公式输入、符号面板、结构模板、中英文 UI。
- Word 公式元数据：公式 ID、LaTeX 源码、显示模式、编号模式和编号值。
- 编号公式规则：每个编号公式独立布局，连续插入不得共享表格或对象容器。
- PowerPoint 图片路径：裁剪公式图像、手动编号合成图像。

## 当前 Word 行为

每个由 Office.js 加载项创建的 Word 公式使用内容控件标记 `latexsnipper-eq-{id}`。文档设置保存其 LaTeX、显示模式、编号模式和编号值。无标记或无元数据的公式不是受管理公式。

| 命令 | 行为 |
|---|---|
| `Insert Formula` | 创建新的受管理 OMML 公式 |
| `Load Selected` | 仅加载选中的受管理公式 |
| `Update` | 在已加载公式身份下重写内容与元数据 |
| `Delete Selected` | 删除公式；编号公式删除自身布局表格；清理元数据 |
| `Auto Numbered` | 将选中的未编号受管理公式改为自动编号 |
| `Renumber All` | 只重排自动编号公式，保留手动编号 |

插入点若位于任意受管理公式或编号布局内部，适配器返回可读提示并拒绝写入。

## 当前 PowerPoint 行为

`src/office/powerpointInsert.ts` 通过 `Office.context.document.setSelectedDataAsync` 和 `Office.CoercionType.Image` 写入 Bridge 生成的 PNG。

| 命令 | 行为 |
|---|---|
| `Insert Formula` | 裁剪空白边界后插入一张公式 PNG |
| `Insert Manual #` | 在编辑器填写手动编号后，于 Canvas 中合成公式和编号并插入一张 PNG |
| `Editor` | 编辑待插入的 LaTeX |
| `Screenshot OCR` | 将 OCR 结果载入编辑器 |

PowerPoint 工作流没有 `Load Selected`、`Update`、`Delete Selected`、自动编号或 `Renumber All`。稳定发布路径使用 `Office.CoercionType.Image` 写入图像，该方法不返回可由本插件标记并持续追踪的图片对象。删除后的图片无法可靠参与编号重算，因此不保留只会递增的伪自动编号状态。

## 不迁移的 Office.js 机制

以下机制只服务于旧实现，不应进入 `office_plugin`：

- manifest sideload 作为持久安装方案。
- 依赖任务窗格保持状态的命令调度。
- 用文档设置弥补对象自身无法持久保存源数据的问题。
- 通过 `localhost` 静态站点承载 Office UI。
- 针对 Office.js 插入失败的 OOXML 字符串修补。
- PowerPoint 中不可追踪图片对象的伪编辑流程。

## 源码边界

| 文件 | 迁移价值 |
|---|---|
| `src/taskpane/App.ts` | 命令编排、状态提示、Bridge 调用顺序 |
| `src/dialog/editorDialog.ts` | 可视化公式编辑器交互 |
| `src/taskpane/mathliveEditor.ts` | MathLive 封装 |
| `src/office/wordInsert.ts` | Word OMML、编号布局和元数据规则 |
| `src/office/powerpointInsert.ts` | PowerPoint 图像裁剪与编号合成 |
| `src/services/i18n.ts` | 中英文术语与错误提示 |
| `../src/integration/office/bridge_server.py` | Bridge API |

## 清理条件

只有在 `office_plugin` 完成以下闭环后，才能删除 `office_addin`：

- Word 原生 Ribbon 稳定加载。
- Word OMML 插入、加载、更新、删除、编号和重编号达到现有能力。
- Word OLE 公式对象可插入、双击编辑、保存源数据并重新渲染。
- PowerPoint 图片插入能力不低于当前 Office.js 实现。
- PowerPoint OLE 公式对象可插入、双击编辑、保存源数据并重新渲染。
- 快捷键和安装器持久注册链路完成。
- 回归测试覆盖对象生命周期、编号、文档保存/重开和卸载清理。
