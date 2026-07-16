# 已知问题、风险与未验证项

> 更新时间：2026-07-16

## 开放风险

| ID | 级别 | 状态 | 内容 | 处理计划 |
|---|---|---|---|---|
| RISK-001 | P0 | 未验证 | Word for Mac 是否稳定接受目标 Flat OPC/OMML，以及 MathML HTML 导入是否形成真实 `m:oMath`。 | M2 真机 Spike；未通过前保持插入按钮禁用。 |
| RISK-002 | P0 | 未验证 | HTTPS taskpane 到 localhost Agent 的 mixed-content、CORS、Private Network 和证书行为。 | M4 分别验证 HTTP loopback、可信 HTTPS、OPTIONS 和 Authorization。 |
| RISK-003 | P0 | 未验证 | Content Control 与 Custom XML Part 在 Undo/Redo、复制和失败回滚时不是原子事务。 | M3 建立补偿事务与一致性测试。 |
| RISK-004 | P1 | 已知限制 | 当前浏览器 renderer 只显式启用 `base`、`ams`、`newcommand`、`bbox`，尚未覆盖 Windows 的 `mhchem`、`physics`、`braket`、`cancel` 等扩展矩阵。 | M2 先建立安全和兼容 fixture，再按白名单加入扩展；不启用 `require`/`autoload`。 |
| RISK-005 | P1 | 未验证 | 当前 CSP、动态模块和 Custom Elements 在最低目标 Word WKWebView 版本的实际兼容性。 | M1 Word 侧载与 M6 最低版本矩阵验证。 |
| RISK-006 | P1 | 未实现 | SMAppService/Login Item 与现有 Python/PyQt/PyInstaller App 的隐藏后台模式尚未设计到代码层。 | M4 独立 Spike，保持正常 Finder 启动不变。 |
| RISK-007 | P1 | 未验证 | Office.js manifest 无法限制只运行于 Mac；validator 同时列出 Word Web/Windows/iPad。 | 运行时只做能力检测，不按平台硬拒绝；后续文档明确首阶段只验收 Mac。 |
| RISK-008 | P0 | 已知阻断 | M1 `FormulaMetadata` 仍是 schema v1，且把 `MathJax-3.2.2` 当作 render engine；已落后于最新 Windows schema v2 契约。 | M2 写入前实现读 v1/写 v2、语义化引擎枚举和未知版本拒绝；当前插入按钮继续禁用。 |
| RISK-009 | P0 | 未实现 | macOS 尚无持久 documentId、跨文档复制/重复 equationId rekey 和 tag/payload 一致性校验。 | M3 由 Custom XML 承担文档身份，并覆盖重开、另存为、复制、重复 ID 和失败回滚。 |
| RISK-010 | P0 | 未实现 | 编辑会话尚无 generation 与捕获 edit target；未来异步提交可能在切换文档或选区后写错对象。 | M3 复用 Windows 语义：generation + `{documentId,equationId}` + 提交前目标重验，command gate 继续保留。 |

## 已修复问题

| ID | 发现方式 | 问题 | 修复与防回归 |
|---|---|---|---|
| BUG-001 | Microsoft manifest validator | manifest `0.2.0.0` 低于 Office 接受的最低 `1.0`。 | 改为 `1.0.0.0`；官方复验显示 manifest valid。 |
| BUG-002 | 本机 Vite 启动检查 | asset 插件在 serve 模式调用 `emitFile()`，开发服务器无法启动。 | 拆分 `apply: serve` 与 `apply: build` 插件；本机服务随后启动成功。 |
| BUG-003 | Development bundle 检查 | Vite 会给 manifest 需要的图标加 hash，未来 Agent 托管 bundle 时固定 URL 会 404。 | 固定 16/32/64/80 图标输出名并复验 Development bundle。 |
| BUG-004 | 共享资产审查 + 真浏览器复现 | `\colorbox` 会转成未打包的 `\bbox`；首次补入扩展后又因过早校验 startup 删除 MathJax 全局。 | 白名单本地 `bbox.js`，等待 `startup.promise` 后校验 API；真浏览器 `\colorbox{yellow}{$x^2$}` 生成 SVG。 |
| BUG-005 | Office API 审查 | Office.js 缺失或初始化超时会被错误显示成“浏览器预览模式”。 | 新增 typed error、错误状态和重连入口；普通浏览器空 host 保持独立，超时有单元测试。 |
| BUG-006 | 安全策略测试审查 | manifest URL 检查漏掉 `DefaultValue` 属性，远程脚本检查漏掉单引号。 | URL 提取同时覆盖资源属性、`AppDomain` 与单双引号脚本；Development bundle 增加独立白名单检查。 |
| BUG-007 | 异步状态审查 | 旧预览或旧 Agent/Office 请求可能覆盖较新的用户输入和连接结果，预览错误恢复后提示不清理。 | 输入时立即废弃旧渲染，三条异步链路只接收最新 generation，预览恢复时清理对应错误。 |

## 当前未测试

- Word for Mac 内真实 HTTPS 侧载、Ribbon 展示和任务窗格恢复。
- `npm run dev` 在第二台设备上的证书首次授权流程。
- Word 原生 inline/display/numbered 插入。
- Content Control、Custom XML、加载、更新、删除和保存重开。
- Word Undo/Redo、复制粘贴、另存为和多公式选区。
- metadata v1 reader/v2 writer、未知 schema 拒绝、语义化 render engine。
- 持久 documentId、重复 ID rekey、跨文档复制和 tag/payload 一致性。
- session generation、陈旧 accept/cancel、切换文档/选区后的 edit target 重验。
- `mhchem`、`physics`、`braket`、`cancel`、复杂颜色、字体和多行完整矩阵。
- 中文输入法在 Word WKWebView 中的实际组合输入。
- Agent session、鉴权、OCR job、取消、崩溃恢复和版本不匹配。
- SMAppService、Dock 隐藏、截图遮罩和 macOS 权限恢复。
- 原项目在 Agent 代码修改后的回归；macOS 插件工作本身没有修改原项目运行时代码，本次仅原样合并最新 main。

当前没有已知、未修复的 M1 自动化或普通浏览器范围功能 Bug。上述风险不得在 UI 或文档中宣称已经支持。
