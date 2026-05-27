# LaTeXSnipper Office 加载项

该加载项通过本机 LaTeXSnipper Office Bridge 为 Word 和 PowerPoint 提供公式输入与截图识别。任务窗格、编辑器和 Ribbon 文本会按 Office 显示语言在中文与英文之间自动切换。

## 当前功能

### Word

Word 使用带 `latexsnipper-eq-{id}` 标记的内容控件保存 OMML 公式，并在文档设置中保存对应 LaTeX 和编号信息。

| 功能 | 实际行为 |
|---|---|
| `Editor` | 打开 MathLive 编辑器和符号/结构面板 |
| `Insert Formula` | 在光标处插入新的可编辑 LaTeXSnipper 公式 |
| `Load Selected` | 加载选中的 LaTeXSnipper 公式进行编辑 |
| `Delete Selected` | 删除选中公式及其元数据；编号公式同时删除自身表格 |
| `Auto Numbered` | 为选中的未编号公式添加自动编号 |
| `Renumber All` | 按文档顺序重排所有自动编号公式 |
| `Screenshot OCR` | 将下一次桌面端截图识别结果载入任务窗格，并同步到已打开的编辑器窗口 |

编号公式以独立的无边框三列表格布局；连续插入不会合并到同一表格。处于已有公式或编号布局内部的插入请求会直接提示不可插入。

### PowerPoint

PowerPoint 通过 `Office.CoercionType.Image` 插入 PNG 图像：

| 功能 | 实际行为 |
|---|---|
| `Editor` | 打开公式编辑器 |
| `Insert Formula` | 向当前幻灯片插入按公式实际边界裁剪过的图像 |
| `Insert Manual #` | 打开编辑器填写编号后，插入一张包含公式和该编号的合成图像 |
| `Screenshot OCR` | 将识别结果载入任务窗格，并同步到已打开的编辑器窗口后再插入 |

PowerPoint 不提供已插入公式图像的 `Load`、`Update`、`Delete Selected`、`Auto Numbered` 或 `Renumber All`。正式可用的 `Office.CoercionType.Image` 写入路径不会返回可由插件持续跟踪的图片对象；删除图像后无法可靠识别哪些编号仍存在，因此 PPT 不生成伪自动编号。

## Office.js 能力边界

本实现已经覆盖当前目标中 Office.js 可可靠交付的边界：

- Word 只编辑和维护本加载项创建且仍具备元数据的公式，不猜测任意原生 Word 公式的 LaTeX 来源。
- PowerPoint 只交付稳定的公式图像插入，不宣称提供原生可编辑公式对象。
- 不保留损坏对象、历史结构或外来对象的兼容兜底逻辑。

## 支持要求

| 宿主 | 要求 |
|---|---|
| Word 桌面版 | `WordApi 1.3`、`SharedRuntime 1.1`；Windows 目标为 Microsoft 365 Word Version 2205 (Build 15202.10000) 或 Word 2024，Mac 要求 Word 16.61 |
| PowerPoint 桌面版 | `ImageCoercion 1.1`、`SharedRuntime 1.1`；Windows 目标为 Microsoft 365 PowerPoint Version 2102 (Build 13722.10000) 或 PowerPoint 2021/2024，Mac 要求 PowerPoint 16.46 |

本地 Bridge 与桌面截图依赖使 Web 和移动版 Office 不属于当前支持范围。

## 正式安装与分发

发布流水线生成本机运行时安装包以及持久部署 manifest 包：

| 平台 | 产物 | 实际行为 |
|---|---|---|
| Windows | `LaTeXSnipperOfficeAddinSetup-<version>.exe` | 通过 Inno 安装已构建站点，并生成、信任仅用于 `localhost` 的 TLS 证书 |
| macOS | `LaTeXSnipperOfficeAddin-<version>.pkg` | 安装已构建站点，并生成、信任 `localhost` TLS 证书 |
| Microsoft 365 部署 | `LaTeXSnipperOfficeDeploymentManifests-<version>.zip` | 包含 Word/PPT 生产 manifest，由管理员在 Microsoft 365 管理中心的 Integrated apps 中部署 |

Windows 安装包同时将 manifest 注册为受信目录，用户在 Office 中通过 **插入 → 加载项 → 共享文件夹** 添加一次后即持久驻留 Ribbon。企业管理员也可通过 Integrated apps 统一部署。

## 开发启动

首次使用前安装依赖并信任开发证书：

```powershell
cd E:\LaTexSnipper\office_addin
npm install
.\scripts\trust_vite_dev_cert.ps1 -OpenInstaller
```

启动 Word 加载项：

```powershell
cd E:\LaTexSnipper\office_addin
npm run dev:word
```

启动 PowerPoint 加载项：

```powershell
cd E:\LaTexSnipper\office_addin
npm run dev:powerpoint
```

两个命令复用 `scripts/start_office_dev.ps1`，启动 HTTPS Vite 服务、检查本机 Bridge，并向对应 Office 宿主旁加载 manifest。

## 模块

| 模块 | 责任 |
|---|---|
| `src/taskpane/App.ts` | 宿主 UI、Ribbon 指令调度、Bridge 与对话框编排 |
| `src/dialog/editorDialog.ts` | MathLive 编辑器、符号和结构输入 |
| `src/office/wordInsert.ts` | Word OMML 插入、加载、更新、删除与编号 |
| `src/office/powerpointInsert.ts` | PowerPoint PNG 与编号合成图像插入 |
| `src/services/i18n.ts` | 按 Office 显示语言切换文本 |
| `src/services/equationSession.ts` | Word 文档设置和编号状态 |
| `../src/integration/office/addin_runtime.py` | 发现正式安装的站点与本机 TLS 配置 |

官方依据：
[Word requirement sets](https://learn.microsoft.com/javascript/api/requirement-sets/word/word-api-requirement-sets)；
[Shared runtime requirement sets](https://learn.microsoft.com/javascript/api/requirement-sets/common/shared-runtime-requirement-sets)；
[Image coercion requirement sets](https://learn.microsoft.com/javascript/api/requirement-sets/common/image-coercion-requirement-sets)；
[Shared folder catalog sideloading on Windows](https://learn.microsoft.com/office/dev/add-ins/testing/create-a-network-shared-folder-catalog-for-task-pane-and-content-add-ins)；
[Sideloading on Mac](https://learn.microsoft.com/office/dev/add-ins/testing/sideload-an-office-add-in-on-mac)。
