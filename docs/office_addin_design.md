# Office Add-in 已实现设计

本文只描述当前已经交付的 Word 与 PowerPoint Office.js 行为，不记录未实现的愿景或兼容设想。

## 目标与边界

LaTeXSnipper Office 加载项连接本机 Office Bridge，负责公式输入、LaTeX 转换结果写入 Office、截图识别结果载入以及 Word 中由本加载项拥有的公式生命周期管理。

对于本产品目标，当前实现位于可可靠使用的 Office.js 能力边界：

- Word 维护本加载项创建的带标记 OMML 公式，具备源代码、更新、删除与编号闭环。
- PowerPoint 写入公式 PNG 图像；编号与公式合成为同一张图像。
- 任意 Word 原生公式、缺失元数据的对象和 PowerPoint 图像不被伪装为可编辑 LaTeXSnipper 公式。
- 不实现历史结构修复或猜测式兼容路径。

## 运行结构

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

Ribbon 命令通过共享运行时进入任务窗格调度层；`Editor`、`Insert`、`Screenshot OCR`、编号动作和 `Help` 都执行真实命令，而不是仅打开一个无动作的窗格。

截图识别返回后，任务窗格输入值总会更新；若 `Dialog editor` 正在打开，父窗口通过 Office 对话框消息同时将同一 LaTeX 写入该编辑器。

## 语言

`src/services/i18n.ts` 使用 `Office.context.displayLanguage` 选择 `en-US` 或 `zh-CN`：

- 任务窗格和编辑对话框通过文本键渲染。
- Ribbon 通过两份 manifest 内的 `zh-CN` override 由 Office 本身切换。
- 帮助入口根据当前语言打开 `help.html` 或 `help.zh-cn.html`。

## Word 对象模型

### 公式身份

每个由加载项创建的 Word 公式使用内容控件标记 `latexsnipper-eq-{id}`。文档设置保存其 LaTeX、显示模式、编号模式和编号值。无标记或无元数据的公式不是受管理公式。

### 普通公式

普通公式使用 OMML 内容控件。插入、加载、更新与删除只针对该内容控件；当公式位于用户表格中时，删除操作不会删除用户表格。

### 编号公式

编号公式使用独立的无边框三列表格：中间单元格放公式，右侧单元格放编号，左右空间保证公式居中。每次插入均保留表格后的段落边界，连续插入不会生成共享表格。

### Word 命令

| 命令 | 行为 |
|---|---|
| `Insert Formula` | 创建新的受管理 OMML 公式 |
| `Load Selected` | 仅加载选中的受管理公式 |
| `Update` | 在已加载公式身份下重写内容与元数据 |
| `Delete Selected` | 删除公式；编号公式删除自身布局表格；清理元数据 |
| `Auto Numbered` | 将选中的未编号受管理公式改为自动编号 |
| `Renumber All` | 只重排自动编号公式，保留手动编号 |

插入点若位于任意受管理公式或编号布局内部，适配器返回可读提示并拒绝写入。

## PowerPoint 对象模型

`src/office/powerpointInsert.ts` 通过 `Office.context.document.setSelectedDataAsync` 和 `Office.CoercionType.Image` 写入 Bridge 生成的 PNG。

| 命令 | 行为 |
|---|---|
| `Insert Formula` | 裁剪空白边界后插入一张公式 PNG |
| `Insert Manual #` | 在编辑器填写手动编号后，于 Canvas 中合成公式和编号并插入一张 PNG |
| `Editor` | 编辑待插入的 LaTeX |
| `Screenshot OCR` | 将 OCR 结果载入编辑器 |

PowerPoint 工作流没有 `Load Selected`、`Update`、`Delete Selected`、自动编号或 `Renumber All`。稳定发布路径使用 `Office.CoercionType.Image` 写入图像，该方法不返回可由本插件标记并持续追踪的图片对象。删除后的图片无法可靠参与编号重算，因此不保留只会递增的伪自动编号状态。

## Bridge 与数据

Bridge URL 与会话 token 由文档设置保存。Word 额外保存公式来源和自动编号状态；PowerPoint 插入结果不写入虚假的可编辑公式元数据。

本机安装包将构建后的 Office 站点、manifest 和 `localhost` TLS 配置安装到本机。启用 Office 功能后的桌面端发现这些资源后，以 `https://localhost:8765` 同时提供站点和 Bridge API：

- Windows Inno 包为当前用户安装站点与证书，将实际所选安装目录写入产品注册表供 Bridge 发现，并将 Word/PPT manifest 写入 `WEF\Developer` 本机 sideload 注册。不写入需要 UNC 共享目录的 `TrustedCatalogs`。
- macOS `.pkg` 安装站点与证书，并将 Word/PPT manifest 放入 Microsoft 文档指定的 `wef` 本机 sideload 目录。
- GitHub Release workflow 额外产出 `OfficeDeploymentManifests-<version>.zip`，供管理员通过 Microsoft 365 Integrated apps 统一部署；Windows 本机安装程序纳入 SignPath 签名路径。

本机 sideload 适用于单机安装和测试，不等同于 Microsoft 支持的组织级生产分发。组织内持续分配 Ribbon 插件由 Microsoft 365 Integrated apps 部署实现；Marketplace 上架仍不属于仓库可自动完成的发布步骤。

## Requirement Sets

| 宿主 | Manifest 声明 | 支持目标 |
|---|---|---|
| Word | `WordApi 1.3`, `SharedRuntime 1.1` | Windows: Microsoft 365 Word Version 2205 (Build 15202.10000) 或 Word 2024；Mac: Word 16.61 |
| PowerPoint | `ImageCoercion 1.1`, `SharedRuntime 1.1` | Windows: Microsoft 365 PowerPoint Version 2102 (Build 13722.10000) 或 PowerPoint 2021/2024；Mac: PowerPoint 16.46 |

本机 Bridge 和桌面截图是产品依赖，因此不把 Office Web 或移动版列为交付目标。

## 源码边界

| 文件 | 责任 |
|---|---|
| `src/taskpane/App.ts` | 宿主工作流与命令调度 |
| `src/dialog/editorDialog.ts` | 可视化公式编辑 |
| `src/taskpane/mathliveEditor.ts` | MathLive 封装 |
| `src/office/wordInsert.ts` | Word 受管理公式适配器 |
| `src/office/powerpointInsert.ts` | PowerPoint 图像适配器 |
| `src/services/i18n.ts` | 中英文字符串与错误显示 |
| `src/services/equationSession.ts` | 文档设置持久化 |
| `src/services/ribbonCommands.ts` | Ribbon 与共享运行时队列 |
| `../src/integration/office/addin_runtime.py` | 正式安装站点及 TLS 文件发现 |
| `../scripts/build_office_addin_installer.ps1` | Windows Office 加载项安装包构建 |
| `../scripts/build_office_addin_macos.sh` | macOS Office 加载项安装包构建 |

## 官方依据

- [Word JavaScript API requirement sets](https://learn.microsoft.com/javascript/api/requirement-sets/word/word-api-requirement-sets)
- [Shared runtime requirement sets](https://learn.microsoft.com/javascript/api/requirement-sets/common/shared-runtime-requirement-sets)
- [Image coercion requirement sets](https://learn.microsoft.com/javascript/api/requirement-sets/common/image-coercion-requirement-sets)
- [Localize Office Add-ins](https://learn.microsoft.com/office/dev/add-ins/develop/localization)
- [Sideload Office Add-ins from a network share on Windows](https://learn.microsoft.com/office/dev/add-ins/testing/create-a-network-shared-folder-catalog-for-task-pane-and-content-add-ins)
- [Sideload Office Add-ins on Mac](https://learn.microsoft.com/office/dev/add-ins/testing/sideload-an-office-add-in-on-mac)
- [Deploy add-ins through Integrated apps](https://learn.microsoft.com/microsoft-365/admin/manage/test-and-deploy-microsoft-365-apps)
