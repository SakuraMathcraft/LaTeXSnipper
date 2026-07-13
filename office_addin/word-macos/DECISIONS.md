# 技术决策记录

> 更新时间：2026-07-13

## ADR-001：只在独立开发分支工作

决定：所有源码、测试和交接资料只进入 `feature/macos-officejs-addin`。每个修改批次和提交前同步检查 `origin/main`，不在 `main` 开发或提交。

原因：保证原项目功能不变，让 macOS 插件可以独立审查、回滚和在两台设备间继续。

## ADR-002：原生 TypeScript + HTML/CSS，不引入 React/Vue

决定：任务窗格使用 TypeScript、语义 HTML、CSS variables 和小型状态容器。

原因：当前 UI 边界清晰，原生实现能减少依赖、启动成本和攻击面，也更符合最小修改原则。若未来 UI 复杂度确实超过现有结构，再以测量结果重新评估。

## ADR-003：任务窗格是 UI，macOS App 是隐藏后台

决定：Office 用户主要在 taskpane 操作。Word 文档对象只由 Office.js 管理；OCR、模型、PDF/图像和长任务由隐藏 Agent 负责。

原因：符合用户确认的产品形态，也避免后台原生 App 与 taskpane 维护两套可见 UI。Agent 失败时静态 taskpane 仍必须加载。

## ADR-004：同源 localhost HTTPS

决定：Development manifest 固定 `https://localhost:3000`。目标集成形态由轻量 Agent 同源提供 taskpane 资源和 `/v1` API；Vite 开发时可把 `/v1` 代理到受信任的 localhost Agent。

原因：减少 WKWebView mixed-content 和 CORS 变量，同时保留精确 Origin 与 session 鉴权。当前 Windows HTTP Bridge 不直接替换或复用。

## ADR-005：复用固定本地 MathLive/MathJax，但按白名单取资产

决定：复用仓库内 MathLive 0.110.0 和 MathJax 3.2.2；不使用 jsDelivr/CDN，不复制整个共享资产目录，不引入 Compute Engine。字体和 MathJax 路径保持固定文件名与原目录层级，许可证随 Development bundle 输出。

原因：复用现有稳定资源并避免供应链漂移。MathLive 字体和 MathJax loader 依赖固定路径，普通 Vite hash 会破坏运行时加载。

## ADR-006：显式限制首批 MathJax package

决定：当前 renderer 只声明 `base`、`ams`、`newcommand` 和为兼容既有 `\colorbox` 预处理所需的 `bbox`。`bbox` 扩展按固定本地路径单独白名单加载；不沿用 Windows 的 `[+]` 配置，也不启用 `require`、`autoload`、`html` 或 `setoptions`。

原因：Windows `[+]` 会保留默认 `require`/`autoload`，与安全预期不一致。扩展包要在安全和公式兼容矩阵通过后逐个加入。

## ADR-007：XML add-in-only manifest + WordApi 1.3

决定：使用 add-in-only XML manifest、base taskpane 和 `VersionOverridesV1_0` 的普通 `ShowTaskpane` Ribbon，不加入 shared runtime、FunctionFile、TaskpaneId 或 auto-open。复用废弃原型的 dev UUID，manifest 版本为 validator 接受的 `1.0.0.0`。

原因：覆盖较老 Word for Mac，同时避免 Unified manifest 当前兼容边界和不必要的命令运行时。复用 UUID 可避免两台设备及旧侧载出现两个同名开发插件。

## ADR-008：OMML 是主路径，验证前禁用插入

决定：SVG 只用于 taskpane 预览，不作为默认 Word 插入格式。Word 写入通过窄 `WordDocumentPort` 隔离，按钮在真机证明 OMML 前保持禁用。

原因：旧原型把 SVG 图片当成公式，无法原生编辑和恢复 metadata。不能把“API 调用成功”误当作“真实 Word 公式成功”。

## ADR-009：Content Control + Custom XML，使用独立前缀

决定：后续公式短 ID 放 Content Control，完整 metadata 放 Custom XML Part；首版 tag 使用 `latexsnipper-js-eq-`，暂不复用 Windows 的 `latexsnipper-eq-`。

原因：Office.js 无法读取 Windows 使用的 `Document.Variables`。复用前缀会让 Windows 插件误识别并报 metadata 缺失。

## ADR-010：开发产物按设备生成，不通过仓库传递

决定：提交源码和 `package-lock.json`；`.dev/`、`node_modules/`、证书和 local env 全部忽略。每台设备用 `npm ci` 和本机证书重新生成 Development 环境。

原因：满足只有项目所有者取得开发构建的要求，也避免证书私钥和可运行 artifact 进入 Git。

## ADR-011：manifest 官方校验独立于离线 check

决定：`npm run check` 只运行离线静态检查和单元测试；`npm run manifest:validate` 单独调用 Microsoft 官方服务。

原因：官方校验器在网络不可用时会打印错误但可能仍返回成功退出码，不能把它混入离线 check 后误判。每次 manifest 修改都要单独查看校验文本是否明确显示 `The manifest is valid.`。
