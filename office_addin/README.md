# LaTeXSnipper Office.js 加载项

`office_addin` 是当前已实现的 Office.js 加载项，也是迁移到 Windows 原生 Office 插件前的参考实现。它会暂时保留，用来复用 UI、Bridge 协议、OMML 转换、截图识别联动和 Word 编号公式处理经验；迁移完成后再安全删除。

它不是 LaTeXSnipper Office 集成的最终方向。没有 Microsoft 365 企业部署、Office Store 或受信任共享目录时，Office.js 不能稳定提供类似 MathType、AxMath 的持久 Ribbon、原生对象、双击编辑和底层快捷键体验。

## 当前定位

| 项目 | 定位 |
|---|---|
| `office_addin` | Office.js 迁移参考和临时可用实现 |
| `office_plugin` | 计划中的 Windows 原生 Office 插件主线 |
| 桌面端 Bridge | 继续作为 OCR、LaTeX 转换、OMML/图片生成和本地渲染服务 |

后续新增 Office 能力默认进入 `office_plugin`，不再把 Office.js 作为最终产品架构扩展。

## 已实现能力

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

## Office.js 边界

本目录的实现只承认 Office.js 能可靠交付的范围：

- Word 只编辑和维护本加载项创建且仍具备元数据的 OMML 公式。
- PowerPoint 只交付稳定的公式图像插入。
- 不猜测任意 Word 原生公式的 LaTeX 来源。
- 不把 PowerPoint 图片伪装成可再次编辑的公式对象。
- 不保留损坏对象、历史结构或外来对象的兼容兜底逻辑。

无法用 Office.js 可靠解决的需求已经转入原生插件设计：

- 安装后长期稳定显示 Ribbon，无需企业账号或 Office 管理中心部署。
- Word/PPT 中的每个公式都是可识别、可双击编辑、可持久保存源数据的原生对象。
- 支持 OLE 公式对象、原生自绘渲染和快捷键。
- 支持类似 MathType/AxMath 的 Windows 桌面插件体验。

## 支持要求

| 宿主 | 要求 |
|---|---|
| Word 桌面版 | `WordApi 1.3`、`SharedRuntime 1.1`；Windows 目标为 Microsoft 365 Word Version 2205 (Build 15202.10000) 或 Word 2024，Mac 要求 Word 16.61 |
| PowerPoint 桌面版 | `ImageCoercion 1.1`、`SharedRuntime 1.1`；Windows 目标为 Microsoft 365 PowerPoint Version 2102 (Build 13722.10000) 或 PowerPoint 2021/2024，Mac 要求 PowerPoint 16.46 |

本地 Bridge 与桌面截图依赖使 Web 和移动版 Office 不属于当前支持范围。

## 开发启动

首次使用前安装依赖并信任开发证书：

```powershell
cd office_addin
npm install
.\scripts\trust_vite_dev_cert.ps1 -OpenInstaller
```

启动 Word 加载项：

```powershell
cd office_addin
npm run dev:word
```

启动 PowerPoint 加载项：

```powershell
cd office_addin
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

## 原生插件迁移原则

- 不把 Office.js 的 sideload、manifest、WebView 限制带入 `office_plugin`。
- 保留 Bridge 的能力边界：OCR、转换、渲染、模型状态由桌面端负责。
- Word 最终支持 OMML 公式和 LaTeXSnipper OLE 公式对象两种表示。
- PowerPoint 最终支持当前 OMML 图片插入和 LaTeXSnipper OLE 公式对象两种表示。
- 公式源数据、渲染参数、编号信息必须随对象持久保存，而不是依赖临时任务窗格状态。

详细目标架构见 `../docs/office_plugin_design.md`。
