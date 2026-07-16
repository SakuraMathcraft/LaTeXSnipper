# 测试矩阵

> 更新时间：2026-07-16
> 环境：macOS，Node v26.5.0，npm 11.17.0

状态说明：通过、失败、未测试、不适用。

## 自动化与构建检查

| 范围 | 方法 | 状态 | 结果 |
|---|---|---|---|
| TypeScript | `npm run typecheck` | 通过 | strict、Bundler resolution、Office.js 类型通过。 |
| 单元测试 | `npm test` | 通过 | 8 个测试文件、26 项测试；领域模型、状态、debounce、Agent、Office host、Word port、MathJax 和开发策略。 |
| 最新 main 同步 | merge `origin/main@fc4849e` 后复验 | 通过 | 与 macOS 插件目录无路径重叠；TypeScript、26 项测试和 Development bundle 复验通过。 |
| npm 审计 | `npm install` | 通过 | 140 packages，0 vulnerabilities。 |
| Development bundle | `npm run build:dev` | 通过 | 36 个文件；固定资源、`bbox`、Compute Engine 排除和远程脚本白名单通过；输出目录被忽略。 |
| Manifest schema | `npm run manifest:validate` | 通过 | Microsoft 官方服务确认 XML schema、HTTPS URL 配置、Word host 和版本有效；本地测试另验图标文件。 |
| Release build | 无 | 不适用 | 按项目要求不执行。 |
| 发布/部署 | 无 | 不适用 | 不存在 release/publish/deploy 脚本。 |

## 单元测试覆盖

| 模块 | 已覆盖 | 尚未覆盖 |
|---|---|---|
| Formula domain | trim、换行、mode fallback、空/过长、M1 未落盘 metadata 草案 | schema v1 reader/v2 writer、语义化 render engine、未知 schema 拒绝 |
| State/debounce | 订阅、不可变更新、重复输入合并、flush/cancel | 大量状态事件压力 |
| Agent client | `/v1/health`、no-store、omit credentials、v1、畸形响应 | session、token、job、取消、真实 CORS |
| Office host | Office.js 缺失、正常浏览器空 host、超时、Word、其他 host、WordApi 1.3 | 真机 Office.js 初始化时序与重连 |
| Word document port | `Word.run → selection → insertOoxml → sync`、空输入、错误脱敏 | 真实 OOXML、返回 Range、Content Control |
| MathJax | `$`、`\colorbox → \bbox`、MathML namespace、SVG script/event/external href/url 清理 | 完整扩展矩阵、超长/恶意 TeX、最低 WKWebView |
| Policy | localhost HTTPS、唯一远程 Office.js、单双引号 URL、无发布脚本、源资产和生成 bundle 白名单 | 最低 WKWebView 对 CSP 的实际执行 |

## 本机普通浏览器验收

本项使用临时 `127.0.0.1` HTTP Vite 页面，只验证网页运行时，不等同于 Word HTTPS 侧载。

| 场景 | 状态 | 结果 |
|---|---|---|
| MathLive 加载 | 通过 | 页面出现 1 个可视化 `math-field`，无 console error/warning。 |
| LaTeX 源码输入 | 通过 | 输入二次公式后可视化编辑区同步显示。 |
| MathJax SVG/MathML | 通过 | 180ms debounce 后出现 1 个 SVG，状态为“本地预览已更新”。 |
| `\colorbox` 本地扩展 | 通过 | `\colorbox{yellow}{$x^2$}` 动态加载本地 `bbox.js`，出现 1 个 SVG；修正后的加载没有新 console error/warning。 |
| Agent 离线降级 | 通过 | `/v1/health` 404 显示“后台未连接”，编辑/预览正常。 |
| 浏览器模式 | 通过 | Office.js 正常返回空 host 时显示“浏览器预览模式”；Office.js 缺失或超时会显示连接失败。 |
| 320px 窄窗 | 通过 | viewport 320，body scroll width 305，无页面级横向溢出。 |
| 编号模式 | 通过 | 选择“编号”后编号输入显示。 |
| 清空 | 通过 | 源码清空、SVG 移除、预览回到 idle、按钮禁用。 |
| 插入防护 | 通过 | “插入公式”始终禁用，未修改任何文档。 |

## Word for Mac 真机矩阵

以下全部未测试，进入 M2/M3 后逐项填写 Word 版本、macOS 版本、结果和复现资料：

- manifest 侧载、Ribbon、首次打开、重开任务窗格。
- 已知 Flat OPC/OMML 的 inline/display 插入。
- MathML import 后 `getOoxml()` 是否包含 `m:oMath`/`m:oMathPara`。
- Content Control 包装、tag/title 和 Range 定位。
- metadata schema v1 读取、v2 写入、未知版本与缺字段拒绝。
- 持久 documentId、tag/payload 一致性、跨文档复制和重复 equationId rekey。
- session generation、陈旧 accept/cancel、切换文档或选区后的 edit target 重验。
- 保存、关闭、重开、另存为、Undo/Redo。
- 加载、更新、删除、复制粘贴和 metadata 补偿。
- 中文输入法、深色模式、320px/更窄任务窗格。
- Agent 未安装、未授权、关闭、崩溃、版本不匹配。

## 原项目回归

macOS 插件自身新增运行时代码都位于 `office_addin/word-macos/`。本次仅原样合并最新 main 的 Windows Office 插件更新，没有在 macOS 插件工作中另行修改桌面 App、Bridge 或 Windows Office 插件。

| 范围 | 状态 | 结果 |
|---|---|---|
| Office Bridge/结构/文档三件套 | 未测试 | 2026-07-16 尝试 `test_office_plugin_structure.py`，系统 Python 缺少 pytest，exit 1，0 collected。 |
| 临时 Python 3.11 环境 | 未完成 | `uv` 下载 Python 时 DNS 受限，exit 2，11.94s；pytest 0 collected / 0 passed / 0 failed。 |
| 全量 pytest | 未测试 | 必须先有 Python 3.11+ 和项目完整依赖。 |

最小保护子集应在环境完整的设备执行：

```bash
python -m pytest \
  test/test_office_bridge.py \
  test/test_office_plugin_docs.py \
  test/test_office_plugin_structure.py \
  -q -p no:cacheprovider
```

随后执行 macOS CI 对应的全量测试：

```bash
QT_QPA_PLATFORM=offscreen \
QT_OPENGL=software \
QTWEBENGINE_DISABLE_SANDBOX=1 \
python -m pytest -q -p no:cacheprovider
```

环境阻塞不是测试失败，也不能记成测试通过。未来一旦修改 `src/` 或 `office_plugin/` 现有代码，必须运行对应回归并在此记录。
