# LaTeXSnipper Word for macOS（Development）

这是 LaTeXSnipper 的 macOS Word Office.js 插件子项目。当前只用于项目所有者在自己的设备上开发和侧载测试，不包含 Release、公开部署或应用市场流程。

## 当前能力

- Word add-in-only XML manifest，最低能力基线为 WordApi 1.3。
- 原生 TypeScript、HTML 和 CSS 任务窗格。
- 复用仓库内 MathLive 0.110.0，提供可视化公式编辑。
- 复用仓库内 MathJax 3.2.2，懒加载生成 SVG 预览和 MathML。
- Word、后台 Agent、编辑器和预览的独立状态展示。
- 后台不可用时，编辑与预览仍能正常使用。
- Office.js 和 Word 文档操作通过窄适配器隔离。

Word 原生公式写入、Content Control、Custom XML、截图 OCR 和后台服务尚未启用。任务窗格里的“插入公式”按钮会保持禁用，直到 Word for Mac 真机 Spike 证明转换结果是实际 OMML，而不是图片或文本。

## 两台设备的开发准备

每台设备都从同一个开发分支开始：

```bash
git fetch origin main
git switch feature/macos-officejs-addin
git pull --ff-only origin feature/macos-officejs-addin
git rev-list --left-right --count HEAD...origin/main
```

不得切换到 `main` 进行本项目开发，也不得把本目录的提交推送到 `main`。

安装隔离在本子项目内的开发依赖：

```bash
cd office_addin/word-macos
npm ci
```

本子项目要求 Node.js `22.12.0+`。依赖和工具版本已锁定在 `package-lock.json`，不要在另一台设备上跳过 `npm ci`。

首次在一台 Mac 上开发时，手工安装并信任该设备自己的 localhost 开发证书：

```bash
npm run cert:install
```

该命令需要 macOS 授权。证书和私钥不会提交到 Git。随后启动受信任的 HTTPS 开发服务：

```bash
npm run dev
```

任务窗格地址固定为：

```text
https://localhost:3000/taskpane.html
```

在 Word for Mac 中只侧载：

```text
office_addin/word-macos/manifest/word-dev.xml
```

侧载方法随 Word 版本可能变化，应使用 Microsoft 的 Word for Mac sideload 开发文档。`word-dev.xml` 源码只随本开发分支同步；不要把它与 Development bundle、证书或侧载包制成公开下载 artifact。

## 开发检查

```bash
npm run check
npm run manifest:validate
npm run build:dev
```

- `check`：TypeScript 静态检查和单元测试，可离线运行。
- `manifest:validate`：调用 Microsoft 官方校验服务；它是 schema 验证，不是 AppSource 提交或发布。
- `build:dev`：只生成未压缩、有 source map 的本地 Development bundle，输出在被 Git 忽略的 `.dev/`；随后检查固定资源、Compute Engine 排除和远程脚本白名单。

不存在 `build`、`release`、`publish` 或 `deploy` 命令。不得把 `.dev/`、证书、安装包或其他生成物提交到分支。

## 目录边界

```text
manifest/                 本机侧载 manifest
scripts/                  HTTPS 开发服务入口
src/backend/              本机 Agent 客户端边界
src/domain/               公式领域模型
src/editor/               MathLive 适配器
src/office/               Office.js / Word 适配器
src/rendering/            MathJax 预览与 MathML
src/state/                任务窗格状态
test/                     自动化测试
```

共享 MathLive、MathJax 和图标的源文件仍位于仓库原来的 `src/assets/`。开发构建只按白名单取所需文件，不提交第二份 vendor 资源，也不会复制 Compute Engine 或整个 MathJax 目录。

## 交接资料

- [需求基线](./REQUIREMENTS.md)
- [项目计划](./PROJECT_PLAN.md)
- [当前状态](./STATUS.md)
- [问题与风险](./ISSUES.md)
- [测试矩阵](./TEST_MATRIX.md)
- [技术决策](./DECISIONS.md)
