# LaTeXSnipper macOS Office 插件需求基线

> 文档状态：需求基线（后续变更必须记录）
> 开发分支：`feature/macos-officejs-addin`
> 初始设计基线 main：`ea3cfde`（2026-07-13）
> 最新同步 main：`fc4849ee077bb5b6636c4acca4f34b3bb524d31f`（2026-07-16）
> 最后更新：2026-07-16

## 1. 项目目标

为 LaTeXSnipper 开发 macOS 端 Microsoft Office 插件。第一阶段以 Word for macOS 为目标，通过 Office.js 提供任务窗格和 Word 文档集成，并复用 LaTeXSnipper macOS App 的 OCR、模型推理、资源管理等重型能力。

用户在 Office 中的主要交互界面是插件任务窗格。LaTeXSnipper App 在后台以无主窗口服务模式运行，正常使用插件时不显示 App 主窗口；只有截图遮罩、macOS 权限提示等确有必要的原生界面可以临时出现。

## 2. 第一性原则

1. 保证原项目现有功能和使用方式不变。
2. 对现有代码做最小、隔离、可回滚的修改。
3. macOS 插件代码放在独立目录，不把 Office.js 逻辑混入 Windows VSTO 插件。
4. Windows Word/PowerPoint 插件、桌面 OCR、截图、导出和安装流程不得因本项目退化。
5. 能复用现有协议、领域模型、测试数据和静态资产时优先复用；不能跨平台复用的宿主实现按相同语义重写。
6. 未经验证的能力不得在文档或 UI 中宣称已经支持。

## 3. Git 与双设备协作要求

### 3.1 分支规则

- 所有开发、文档、测试记录和提交只进入：

  ```text
  feature/macos-officejs-addin
  ```

- 不在 `main` 上开发或提交。
- 不从废弃分支继续开发。
- 不整体 merge 或 cherry-pick `origin/feature/macos-office-addin`；只按文件或函数语义提取可复用内容。

### 3.2 每次行动前对齐 main

每个开发阶段、代码修改批次和提交开始前必须：

1. 执行 `git fetch origin main`。
2. 比较当前分支与 `origin/main` 的提交差异。
3. 在工作区干净且可以安全快进时，优先 `git merge --ff-only origin/main`。
4. 已有开发提交时，先审查 main 的变更范围、冲突和测试影响，再决定 merge/rebase；不得静默覆盖开发成果。
5. 同步 main 后重新运行与受影响模块相称的回归测试。
6. 在状态文档中记录同步到的 main commit、测试结果和未验证项。

### 3.3 必须随分支同步的交接资料

分支应持续维护以下信息，使任一设备拉取分支后可以继续工作：

- 项目总计划和阶段划分。
- 当前完成到的阶段。
- 下一阶段和具体待办。
- 已发现 Bug、风险和复现条件。
- 已执行的测试、测试环境和结果。
- 尚未测试的场景。
- 已作出的技术决策及其原因。
- 当前分支所基于的最新 main commit。

计划建立并持续更新：

```text
office_addin/word-macos/REQUIREMENTS.md
office_addin/word-macos/PROJECT_PLAN.md
office_addin/word-macos/STATUS.md
office_addin/word-macos/ISSUES.md
office_addin/word-macos/TEST_MATRIX.md
office_addin/word-macos/DECISIONS.md
```

本文件是需求基线；其他文档在对应阶段建立。

### 3.4 发布与开发者测试限制

当前项目只允许开发和开发者测试，不进入任何发布流程：

- 不执行 Release build 或发布打包验证。
- 不创建 GitHub Release、Git Tag、正式安装包或公开下载链接。
- 不提交 AppSource、Microsoft Marketplace 或其他应用市场。
- 不发布 GitHub Pages 或其他公网任务窗格页面。
- 不向公开 CI 上传可下载的 App、安装包、manifest bundle 或构建 artifact。
- 不把开发构建产物提交到 Git 分支；分支只保存源码、开发配置、测试和文档。

允许的开发者测试方式：

- 使用本机可信证书和 `https://localhost` 运行任务窗格。
- 使用仅面向开发环境的 sideload manifest。
- 在被 Git 忽略的本地目录生成临时开发产物。
- 在开发分支运行单元测试、静态检查和不产出公开 artifact 的 CI。
- 需要换设备时，从开发分支拉取源码并在目标设备重新生成本地开发产物。

开发产物原则上只能由项目所有者在自己的设备上获得。不得依赖公开仓库分支、公开 Actions artifact 或公开链接传递可安装构建。如果未来需要把测试包交付给其他人员或启用发布流程，必须由项目所有者另行明确授权。

## 4. 产品形态

### 4.1 用户可见部分

Word 任务窗格是 Office 场景下的主要操作页面，至少承载：

- LaTeX 输入和公式编辑。
- 公式预览。
- 行内、行间和带编号公式模式。
- 插入、加载、更新和删除。
- OCR、模型和后台服务状态。
- 重任务进度、取消和错误恢复。
- 必要的插件设置。

### 4.2 后台部分

macOS App 增加独立的 Office 后台服务模式：

- 无主窗口。
- 正常后台运行时不显示 Dock 主界面。
- 不在启动时预加载模型，保持低内存和低 CPU 占用。
- 收到重任务后再按需加载模型和运行时。
- App 被用户正常从 Finder 启动时，仍显示原来的完整界面并保持原功能。
- 截图 OCR 时允许临时显示截图遮罩；任务完成后继续隐藏。

### 4.3 后台启动方式

目标方案是使用 macOS `SMAppService` 注册用户级 Login Item 或 LaunchAgent，由 `launchd` 管理后台服务：

- 用户首次安装/启用时完成一次系统授权。
- 授权后后台服务可自动启动，并在异常退出时恢复。
- Office.js 不负责绕过系统授权静默启动任意原生 App。
- 如果用户禁用了后台项目，插件必须显示清晰的修复入口，而不是空白或无限等待。
- 自定义 URL Scheme 只作为显式用户操作下的恢复或启动备用方案，不作为核心静默启动机制。

## 5. 组件职责边界

### 5.1 Word Office.js 插件负责

- Ribbon/任务窗格入口和 Office 内 UI。
- Word 选区、Range、Content Control 和文档事件。
- 公式对象插入、定位、加载、替换和删除。
- Word 原生 OMML/OOXML 写入。
- 公式编号、引用和文档内布局。
- 插件侧状态展示、操作锁和错误提示。
- 文档内公式短标识和元数据关联。

Word 文档对象只能由 Office.js 操作，后台 App 不直接控制 Word DOM。

### 5.2 macOS 后台 App 负责

- 截图与 macOS 系统权限。
- OCR 和本地/外部模型推理。
- 模型下载、校验、缓存和运行时管理。
- PDF、图像预处理及其他计算密集任务。
- 长任务队列、进度、取消和结果缓存。
- 本地服务生命周期、版本和能力报告。
- 后续经验证需要放到本地后端的重型公式转换能力。

### 5.3 插件内保留的轻量能力

- 基础 UI 和输入校验。
- MathLive 编辑能力。
- 轻量公式预览。
- Word 文档操作所需的轻量格式组装。

插件页面在后台服务不可用时仍应能够加载，并显示安装、启用或恢复指引；不得因为本地服务离线而出现空白任务窗格。

## 6. Windows 端复用与兼容要求

Windows 当前采用 VSTO/COM/OLE：公式编辑、MathJax 渲染、OMML/OLE 插入、元数据、编号和引用在插件内部完成，桌面 Bridge 只负责截图 OCR。

macOS 端：

- 复用 Windows 的领域语义和 JSON 字段。
- 复用本地 MathLive、MathJax、字体、许可证和公式测试样例。
- 复用 Bridge 的业务含义，但升级为适合浏览器客户端的安全、版本化协议。
- 不复用 VSTO、COM、OLE、WebView2、Windows 注册表、原生 DLL 和 Inno Setup。
- 不以修改 Windows 插件为 macOS MVP 的前置条件。

### 6.1 公式元数据语义

目标字段保持与 Windows 一致：

```text
schemaVersion
documentId
equationId
latex
displayMode
numberingMode
numberText
renderEngine
fontScale
```

Windows 完整元数据位于 `Document.Variables`，Office.js 不提供同等访问接口。因此 macOS 首版计划使用：

- Content Control：保存短 ID/revision 标签。
- Custom XML Part：保存完整、带 namespace 的公式元数据。

在 Windows 尚未实现 Custom XML fallback/双读写以前，macOS 不复用 Windows 的 `latexsnipper-eq-` 前缀，暂用独立前缀，例如：

```text
latexsnipper-js-eq-
```

避免 Windows 插件误识别公式后因找不到 `Document.Variables` 而报错。跨 Windows/macOS 互编辑属于后续兼容阶段。

最新 main 的 Windows metadata 已升级为 schema v2。macOS 在启用任何受管公式写入前必须满足：

- 读取兼容 schema v1，写入只使用 schema v2；未知版本、缺少身份字段或字段不一致时明确失败。
- `renderEngine` 使用跨端语义值 `Omml`、`Image` 或 `MathJaxSvg`，渲染器版本另存，不能再把 `MathJax-3.2.2` 当作引擎枚举。
- Custom XML 同时保存持久 `documentId`；Content Control tag 的 `equationId` 必须与 payload 一致。
- 文档重开保持身份；跨文档复制、另存为或重复 `equationId` 时按当前文档重新分配身份。
- 当前 M1 中硬编码的 macOS schema v1 仅是尚未落盘的领域草案，不得直接用于 M2/M3 文档写入。

### 6.2 编辑会话与目标身份

最新 Windows 稳定基线使用显式加载编辑，而不是把实验性的双击/OLE 激活视为已交付能力。macOS 编辑生命周期必须复用以下语义：

- 每次打开编辑器分配单调递增的 session generation；过期 accept/cancel 不得完成新会话。
- 打开时捕获 `{documentId, equationId}` 和原公式目标，提交前重新验证文档、公式身份与唯一性。
- 用户切换文档、选区或目标已被删除时安全拒绝，不得把结果写到当前活动文档中的同名对象。
- command gate 与 session generation 同时保留，分别防止重复命令和陈旧异步回调。
- metadata 校验或双写失败时回滚，不静默修补身份不一致。

## 7. Office.js 技术基线

- 第一阶段宿主：Word for macOS。
- Manifest：XML add-in-only manifest。
- 基础 API：建议以 `WordApi 1.3` 为正式最低能力基线。
- Ribbon：通过 `VersionOverrides` 使用 Add-in Commands；base manifest 保留任务窗格回退入口。
- 前端：TypeScript、原生 HTML/CSS、轻量 DOM 状态管理。
- 构建：隔离在 `office_addin/word-macos/` 内，不修改根项目依赖。
- 生产资源必须使用 HTTPS。
- MathLive、MathJax 和字体使用仓库内固定版本，不运行未锁定 CDN 脚本。
- 不在首版引入 React/Vue 等大型 UI 框架。

## 8. 公式功能要求

### 8.1 第一阶段目标

- 手工输入和编辑 LaTeX。
- 行内公式。
- 行间公式。
- 手动或自动编号公式的基础模型。
- Word 原生可编辑公式作为主路径。
- 插入、加载、更新、删除受管公式。
- 文档保存、关闭和重开后仍可恢复完整 LaTeX。

### 8.2 插入格式

- 主路径：OMML/OOXML。
- SVG/图片只作为明确提示用户的兼容降级路径。
- 纯 LaTeX 文本不得在无提示的情况下冒充插入成功的公式。
- macOS 不实现 OLE。

### 8.3 必须先验证的转换链路

Windows 依赖 Office 安装目录中的 `MML2OMML.XSL`，macOS Office.js 无法直接复用。必须按顺序做真机 Spike：

1. 插入已知正确 OMML/Flat OPC。
2. 验证 inline/display 和 Content Control 包装。
3. 用本地 MathJax 生成 MathML。
4. 验证 Word for Mac 的 MathML HTML 导入是否转换为真实 `m:oMath`。
5. 若失败，再评估许可证明确、覆盖充分的 MathML → OMML 转换方案。

不得用只覆盖少量公式的手写转换器宣称完整支持 Word 原生公式。

## 9. 插件与后台 App 通信要求

### 9.1 基本原则

- 仅绑定 loopback 地址。
- 使用版本化 API，例如 `/v1/...`。
- 插件加载时执行 health、版本和 capability 协商。
- 后台版本不兼容时给出可理解的升级提示。
- 所有重任务使用异步 Job，不维持数分钟的单个 HTTP 长请求。
- 支持查询进度、取消、超时和失败重试。

建议的初始协议表面：

```text
GET    /v1/health
POST   /v1/sessions
GET    /v1/capabilities
GET    /v1/settings
PATCH  /v1/settings
GET    /v1/models
POST   /v1/models/{id}/install
POST   /v1/jobs/screenshot-ocr
GET    /v1/jobs/{id}
DELETE /v1/jobs/{id}
```

### 9.2 安全要求

- 精确校验允许的 Office 插件 Origin。
- 开发与生产 Origin 分开配置。
- 使用短期会话 Token；受保护接口必须鉴权。
- 不照搬当前 Windows `/config` 无鉴权直接返回长期 Token 的方式。
- CORS 不是鉴权，服务端必须同时验证 Origin 和会话。
- 添加正确的 `Vary: Origin` 和 no-store 响应头。
- 不监听局域网或公网地址。
- 敏感配置和长期秘密使用 macOS Keychain 或等价安全存储。

### 9.3 必须先验证的网络链路

Word for Mac 使用 WebView，正式任务窗格是 HTTPS 页面。必须真机测试：

- HTTPS taskpane → HTTP `localhost`。
- HTTPS taskpane → HTTP `127.0.0.1`。
- HTTPS taskpane → 可信本地 HTTPS 服务。
- OPTIONS preflight、Authorization 和 JSON POST。
- App 启动、关闭、崩溃恢复和版本不匹配。

如果 WKWebView 阻止 HTTPS → HTTP，则新增 macOS 可选 TLS Bridge；不得直接替换 Windows 当前 HTTP Bridge。

## 10. 非功能要求

- 后台空闲时保持低 CPU、低内存和零模型预加载。
- 插件操作必须有并发锁，防止双击和快捷键重复插入。
- 兼容中文输入法组合态，不在 `event.isComposing` 时触发提交。
- 预览更新需要 debounce。
- 支持浅色/深色模式和窄任务窗格。
- 关键状态使用无障碍语义和 `aria-live`。
- 所有用户可见错误需要区分：服务未安装、服务未启用、权限不足、网络失败、模型缺失、转换失败、Word API 不支持。
- 日志不得记录完整鉴权 Token、API Key 或不必要的文档正文。
- 插件和后台服务均需提供版本与诊断信息。

## 11. 测试与验收要求

### 11.1 原项目回归

每次涉及现有目录的修改必须运行对应回归测试，至少覆盖：

- Office Bridge。
- Office 插件结构与契约。
- macOS 应用生命周期和清理。
- OCR/截图相关受影响路径。
- 现有公式导出与 OMML 测试。

### 11.2 插件自动化测试

- LaTeX 输入标准化和领域模型。
- Manifest schema、Requirements、Ribbon 和 URL。
- Office.js adapter mock。
- OOXML/OMML 快照和 XML 结构校验。
- Content Control 与 metadata 生命周期。
- Bridge client 的 health/session/job、超时、取消和错误分类。
- 并发提交、IME、快捷键和重复点击。
- 构建输出中不得包含远程未锁定脚本。
- CI 只能报告测试结果，不上传可安装或可运行的构建 artifact。

### 11.3 开发者侧载测试

- 只生成 Development 配置，不生成 Release 配置。
- 任务窗格只由本机可信的 `https://localhost` 服务提供。
- 开发 manifest 不得引用公网部署地址。
- 本地产物必须位于 `.gitignore` 覆盖的目录。
- 测试完成后不得创建 Release、Tag、Pages 部署或公开附件。

### 11.4 Word for Mac 真机测试

- 侧载、首次打开和任务窗格恢复。
- inline/display/numbered 公式。
- 保存、关闭、重开、另存为。
- 加载、更新、删除。
- Undo/Redo。
- 同文档和跨文档复制粘贴。
- Custom XML metadata 的孤儿清理和失败补偿。
- 中文输入法、深色模式、窄任务窗格。
- 后台 App 未安装、未授权、关闭、崩溃和版本不匹配。
- 截图权限首次申请、拒绝后恢复、OCR 取消和超时。
- 离线状态、模型未安装及模型下载失败。

## 12. 当前已知风险与未验证项

以下项目在完成真机 Spike 前均视为未验证：

1. Word for Mac 是否稳定接受目标 Flat OPC/OMML。
2. MathML 经 Office.js/Word HTML parser 后是否得到真实 OMML。
3. HTTPS 任务窗格访问 loopback 服务的 mixed-content、CORS 和 Private Network 限制。
4. `SMAppService` 与当前 Python/PyQt/PyInstaller macOS 打包流程的集成方式。
5. 后台模式隐藏 Dock/主窗口，同时临时显示截图遮罩的行为。
6. Content Control + Custom XML Part 在 Undo/Redo、复制粘贴和异常回滚时的一致性。
7. macOS 与 Windows 公式元数据的最终双向兼容方案。
8. AppSource/组织部署对本地后台服务和 loopback 通信的审核要求。

发现问题后必须同步更新 `ISSUES.md` 和 `TEST_MATRIX.md`，不得只保留在聊天或本地笔记中。

## 13. 废弃分支的处理要求

`origin/feature/macos-office-addin` 仅作为原型素材库：

可参考：

- 任务窗格布局和 macOS 风格 CSS。
- LaTeX 输入标准化纯函数。
- inline/display/numbered 模式建模。
- Office API test-double 和依赖注入测试思路。
- 无障碍 HTML 结构。

必须重写或丢弃：

- HTTP manifest 和自制 HTTP 开发服务器。
- CDN MathJax。
- SVG/HTML 图片作为主要插入路径。
- GitHub Pages 个人地址和双份生成目录。
- 无持久元数据的随机公式 ID。
- 未处理并发、IME 和快捷键冲突的 taskpane 逻辑。

## 14. 第一阶段明确不做

- macOS OLE/COM/VSTO。
- macOS PowerPoint 插件。
- 立即实现完整 Windows/macOS 跨平台互编辑。
- Release build、发布打包及 Release 构建测试。
- GitHub Release、Git Tag、GitHub Pages 或公开 CI artifact。
- AppSource、Microsoft Marketplace 或其他应用市场发布。
- 大范围重构原桌面 App。
- 为了共享代码而强行引入影响根项目的运行时或构建系统。

## 15. 完成定义

一个阶段只有同时满足以下条件才能标记完成：

1. 功能代码、自动化测试和必要文档已提交到开发分支。
2. 分支已检查并记录与最新 `origin/main` 的关系。
3. 原项目受影响回归测试通过。
4. 对应的 Word for Mac 真机验收项有结果，或明确记录为未测试及原因。
5. 已知 Bug、限制和风险已进入分支文档。
6. 下一阶段目标和接手步骤清晰。

## 16. 待确认的产品决策

以下事项不阻塞需求文档建立，但在对应实现前需要确认或通过 Spike 定案：

- 首发最低 macOS 与 Word for Mac 版本。
- 后台服务选择登录常驻，还是后续实现真正的按需 socket activation。
- 后台 App 不可用时，是否要求手工 LaTeX 插入仍可完全离线工作。
- 首版是否在任务窗格提供模型选择、下载和完整设置，还是只提供当前模型状态。
- Windows/macOS 公式互编辑进入哪个里程碑。

发布方式不属于当前阶段的待确认事项。除非项目所有者未来另行授权，否则始终维持“仅本地开发者测试、不发布”的约束。

## 17. 参考边界

- 当前 Windows 插件：`office_plugin/`
- 当前桌面 Bridge：`src/integration/office/`
- 当前 Bridge 生命周期：`src/ui/office_bridge_controller.py`
- 本地 MathLive：`src/assets/mathlive/`
- 本地 MathJax：`src/assets/MathJax-3.2.2/`
- 废弃 macOS 原型：`origin/feature/macos-office-addin`

官方技术依据：

- Apple Service Management：<https://developer.apple.com/documentation/servicemanagement/>
- Office Add-ins manifest：<https://learn.microsoft.com/en-us/office/dev/add-ins/develop/xml-manifest-overview>
- Word JavaScript requirement sets：<https://learn.microsoft.com/en-us/javascript/api/requirement-sets/word/word-api-requirement-sets>
- Word OOXML：<https://learn.microsoft.com/en-us/office/dev/add-ins/word/create-better-add-ins-for-word-with-office-open-xml>
- Office Add-in same-origin policy：<https://learn.microsoft.com/en-us/office/dev/add-ins/develop/addressing-same-origin-policy-limitations>
