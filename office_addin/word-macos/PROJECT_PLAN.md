# macOS Word 插件项目计划

> 开发分支：`feature/macos-officejs-addin`
> 当前对齐 main：`ea3cfde215f3d53639ebf1835b6c8ba1de459036`
> 最后更新：2026-07-13

## 总目标

在不改变 LaTeXSnipper 原有桌面功能和 Windows Office 插件行为的前提下，为 Word for macOS 增加 Office.js 任务窗格。任务窗格是 Office 场景的主要 UI；macOS App 后续以隐藏后台 Agent 提供 OCR、模型和长任务。

所有代码、测试和交接文档只提交到开发分支。整个计划不包含 Release build、公开托管、GitHub Release、Tag、Pages、公开 artifact 或 AppSource 发布。

## 里程碑

### M0：需求、旧分支和技术基线

状态：已完成。

- 固化第一性原则、Git 规则、开发者测试和不发布约束。
- 审计 Windows 插件、桌面 Bridge 和废弃 macOS 原型。
- 选定 Office.js、WordApi 1.3、Content Control + Custom XML、OMML 主路径。
- 明确任务窗格与隐藏后台 Agent 的职责边界。

退出条件：需求基线已提交；当前分支基于最新 main；废弃分支只作素材参考。

### M1：任务窗格与本地渲染基础

状态：代码和自动化测试已完成，Word 内 HTTPS 侧载验收未执行。

- 建立隔离的 TypeScript/Vite 工程和锁文件。
- 添加仅 localhost HTTPS 的 Development manifest 与 Ribbon 入口。
- 实现 MathLive 可视化编辑和 LaTeX 源码双向同步。
- 懒加载本地 MathJax，生成经过校验的 SVG 预览和 MathML。
- 实现状态机、180ms debounce、IME 防护、浅色/深色和窄窗布局。
- 建立 Word/Agent 适配器边界；后台离线时页面仍可用。
- 固定本地资产白名单、CSP 和许可证输出。

退出条件：静态检查、单元测试、官方 manifest 校验和本机浏览器检查通过；Word 内侧载结果记录到测试矩阵。

### M2：Word 原生公式 P0 Spike

状态：下一阶段。

1. 建立已知正确的 inline/display Flat OPC + OMML fixture。
2. 使用 `Range.insertOoxml` 在 Word for Mac 插入并读取 `getOoxml()` 验证。
3. 测试 MathJax MathML 经 `insertHtml` 后是否产生 `m:oMath`/`m:oMathPara`。
4. 验证返回 Range、Content Control 包装、替换、Undo/Redo、保存和重开。
5. 对转换失败实施显式错误和回滚，不静默降级成图片或纯文本。
6. 只有主链路通过后才启用任务窗格“插入公式”。

退出条件：至少一条覆盖目标公式矩阵的原生 OMML 路径在 Word for Mac 真机通过；失败路径和平台限制有测试与文档。

### M3：受管公式生命周期与元数据

状态：待开始。

- 使用 `latexsnipper-js-eq-` Content Control 短标签。
- 使用带 namespace 的 Custom XML Part 存完整 metadata。
- 实现插入、定位、加载、更新、删除和 orphan 清理。
- 处理复制粘贴、另存为、Undo/Redo 和双写失败补偿。
- 保证 Windows 插件不会误识别 macOS 首版公式。

退出条件：保存/关闭/重开后 LaTeX 可恢复，异常时内容与 metadata 不出现静默不一致。

### M4：macOS 隐藏后台 Agent 与安全协议

状态：待开始。

- 为原 App 增加隔离的 Office 后台模式，不改变 Finder 正常启动行为。
- 使用 SMAppService/Login Item 或经验证的 LaunchAgent 集成。
- 同源或可信 localhost HTTPS 提供 `/v1/health`、session 和 capability 协商。
- 精确 Origin、短期 session token、no-store、`Vary: Origin`、loopback-only。
- 空闲不加载模型；Agent 故障不阻塞 taskpane 静态页面。

退出条件：登录启动、禁用恢复、崩溃恢复、版本不匹配和空闲资源占用在真机有结果。

### M5：OCR、模型与长任务

状态：待开始。

- 截图 OCR job 创建、进度、取消、超时和结果回填。
- 截图遮罩作为唯一允许短暂显示的原生界面之一。
- 模型状态、按需安装、校验和失败恢复。
- 公式必须回到编辑器由用户确认后再写入 Word。

退出条件：权限首次申请、拒绝恢复、取消、模型缺失和离线场景均有可理解状态。

### M6：兼容性与私有开发验收

状态：待开始。

- 完成最低目标 Word/macOS 版本矩阵。
- 运行原项目受影响回归和 Word 真机矩阵。
- 收敛性能、无障碍、深色模式和诊断信息。
- 清理已知问题，确保两台设备仅凭分支即可继续开发。

退出条件：Development 目标完成，所有未验证项明确。此里程碑仍不包含 Release 或发布。

## 每个阶段的固定动作

1. `git fetch origin main` 并记录 `HEAD...origin/main`。
2. 确认当前分支不是 `main`，检查工作区和 main 变更影响。
3. 实施最小、隔离的代码修改。
4. 运行与变更相称的插件测试和原项目回归。
5. 更新 `STATUS.md`、`ISSUES.md` 和 `TEST_MATRIX.md`。
6. 只在 `feature/macos-officejs-addin` 提交和推送。
