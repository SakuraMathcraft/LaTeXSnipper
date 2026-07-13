# 当前开发状态

> 更新时间：2026-07-13
> 当前分支：`feature/macos-officejs-addin`
> 对齐的 origin/main：`ea3cfde215f3d53639ebf1835b6c8ba1de459036`
> 发布状态：仅 Development，本项目未发布

## 当前阶段

M1“任务窗格与本地渲染基础”已完成代码、自动化和普通浏览器验收。Word for Mac 内的可信 HTTPS 侧载尚未执行，因此 M1 的真机验收仍是未测试状态。

## 本阶段已完成

- 独立 `package.json`、`package-lock.json`、TypeScript、Vite 和 Vitest 配置。
- Development manifest：WordApi 1.3、Home Ribbon `ShowTaskpane`、localhost HTTPS。
- Microsoft 官方 manifest 验证通过；版本由无效的 `0.2.0.0` 修正为 `1.0.0.0`。
- 原生 HTML/CSS 任务窗格和浅色/深色、320px 窄窗布局。
- MathLive 0.110.0 可视化编辑器，不引入 Compute Engine。
- MathJax 3.2.2 懒加载、显式 `base/ams/newcommand/bbox` 白名单、SVG 预览、MathML 校验和活动 SVG 内容清理。
- `\colorbox` 与外层 `$` 的 Windows 渲染预处理语义。
- Word host capability、Word OOXML 写入端口和 Agent `/v1/health` 客户端边界。
- 后台不可用时不阻塞页面；UI 明确区分浏览器、Word 和 Agent 状态。
- Office.js 缺失/超时不会伪装成浏览器模式；错误状态提供 Word 重连入口。
- 预览、Agent 检测和 Office 初始化均只接受最新一轮异步结果。
- “插入公式”保持禁用，防止未经 Word 真机验证的 MathML/OMML 写入文档。
- `.dev/`、证书、local env 和 coverage 均被 Git 忽略。

## 当前验证摘要

- Node `v26.5.0`，npm `11.17.0`。
- npm 安装审计：140 个开发包，0 个已知漏洞。
- TypeScript：通过。
- Vitest：8 个测试文件、26 项测试通过，详见 `TEST_MATRIX.md`。
- Development bundle：36 个文件通过固定资产、Compute Engine 排除和远程脚本白名单检查；只生成到 `.dev/taskpane/`，未提交。
- Microsoft 官方 manifest validator：有效。
- 本机普通浏览器：MathLive、MathJax、`\colorbox → \bbox`、状态降级、编号切换、清空和 320px 布局通过。
- 原项目 Python 回归：环境阻塞，0 项收集；本机 Python 3.9.6 低于项目要求且缺少 pytest/PyQt，临时 Python 3.11 下载因网络受限失败，不能记为通过或失败。
- Release build/发布：按要求未执行。

## 下一阶段

M2“Word 原生公式 P0 Spike”：

1. 行动前再次 fetch 和检查最新 main。
2. 添加已知正确的 Flat OPC/OMML fixture 和结构快照测试。
3. 在 Word for Mac 侧载当前 Development manifest。
4. 验证 `insertOoxml`，再验证 MathML `insertHtml` 后的 `getOoxml()`。
5. 检查 inline/display、Content Control、Undo/Redo、保存重开。
6. 根据真机结果决定转换主路径；未通过前不启用插入按钮。

## 换设备后的接手步骤

```bash
git fetch origin main
git switch feature/macos-officejs-addin
git pull --ff-only origin feature/macos-officejs-addin
git rev-list --left-right --count HEAD...origin/main
cd office_addin/word-macos
npm ci
npm run check
```

首次侧载前再运行 `npm run cert:install`，由 macOS 在该设备本地授权证书。不要复制另一台设备的私钥，不要从公开 artifact 获取开发包。

## 当前禁止事项

- 不在或不向 `main` 提交、推送本项目变更。
- 不运行 Release build 或发布打包测试。
- 不创建 Release、Tag、Pages、公开 artifact、AppSource 提交或公开下载链接。
- 不提交 `.dev/`、`node_modules/`、证书或 sideload 生成物。
