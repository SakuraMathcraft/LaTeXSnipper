# LaTeXSnipper ✨

<div align="center">

> 跨平台数学 OCR 工作区与自动化服务，覆盖 **截图 -> 识别 -> 手写 -> 编辑 -> 集成**

<img width="1919" height="1021" alt="LaTeXSnipper v3.0.0" src="docs/latexsnipper-3.0.0.png" />

![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Stars&color=FFD700)
![Forks](https://img.shields.io/github/forks/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Forks&color=1f6feb)
![Issues](https://img.shields.io/github/issues/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Issues&color=d1481e)
![License](https://img.shields.io/badge/license-GPLv3-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-orange?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11-blue?style=flat-square)

[![GitHub Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![Last Commit](https://img.shields.io/github/last-commit/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Activity)](https://github.com/SakuraMathcraft/LaTeXSnipper/graphs/commit-activity)

[常见问题](docs/faq.md) · [版本发布](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) · [LINUX DO 社区](https://linux.do/)

[English](readme.md) · 简体中文

</div>

---

## 核心功能

| 功能 | 说明 |
|---|---|
| 📸 公式识别 | MathCraft OCR 或已配置的本地/线上外部模型支持公式、文本和图文混排识别 |
| 📄 PDF 识别 | 按页识别 PDF，输出 Markdown/LaTeX，并支持 DPI 控制 |
| ✍️ 手写识别 | 独立手写窗口，支持自动识别和实时预览 |
| 🔌 Automation API | 支持本机脚本、批量任务、编辑器工具及安全授权的远程设备 |
| 🧩 应用集成 | 官方 Word/PowerPoint 客户端，以及 AutoKey、AutoHotkey、Hammerspoon、ShareX 和移动端工作流 |
| ⌨️ 公式编辑 | 集成 `MathLive math-field` 和虚拟数学键盘 |
| 🔄 多格式导出 | 覆盖 LaTeX、Markdown、MathML、HTML、OMML、SVG、Word、ODT、PowerPoint、EPUB、PDF、Typst、纯文本等 20 种导出格式 |
| 🧮 数学工作台 | 独立工作区，支持编辑、计算和写回 |
| 📐 核心计算 | 支持计算、化简、数值化、展开、因式分解和求解 |
| 🌙 主题支持 | 主窗口、工具窗口和对话框适配亮色/暗色主题 |
| 🔐 本地优先 | 识别和计算可在本地运行，适合隐私敏感场景 |

MathCraft OCR 基准结果：[表格与对比图](https://github.com/SakuraMathcraft/MathCraft-Models/tree/main/benchmarks) · [复现套件](benchmarks/mathcraft_ocr/README.md)

---

## Automation API

Automation API 通过受控的 `mathcraft` 与 `external` backend 同时开放常驻 MathCraft 模型和桌面端已配置的外部模型。MathCraft 与外部调用分别使用有界、单并发执行器，因此较慢的 Ollama、MinerU 或线上请求不会阻塞 MathCraft；客户端不能读取或覆盖上游地址、模型名、凭据及提示词。

图片输入支持八种常用扩展名：PNG、JPG、JPEG、BMP、GIF、TIF、TIFF、WEBP，对应六种实际编码。最有价值的实际组合是：

- **Snipaste + AutoHotkey/AutoKey/Hammerspoon**：截图后识别并写回剪贴板。
- **ShareX + Automation API**：截图完成后直接上传识别。
- **VS Code/TeXstudio/Obsidian 插件**：识别后直接插入编辑位置。
- **iOS Shortcuts/Android Tasker + Tailscale**：手机调用家中电脑常驻的 MathCraft。
- **Python/curl + 批量接口**：自行批量识别整个图片目录。

接口**默认关闭**，默认仅监听本机 `127.0.0.1:28765`。本机客户端通过私有的 `automation-api.json` 连接文件发现实际地址和每次启动重新生成的 Bearer token。AutoKey、AutoHotkey、Hammerspoon、ShareX、编辑器插件和官方 Office 插件都可以使用这一方式。上传图片串行解码，规范化图片在识别完成前共用同一内存预算，避免并发大图成倍放大内存占用。

远程访问必须由用户显式开启，并使用独立远程密钥以及 Tailscale/WireGuard/SSH 等加密隧道或 HTTPS；不支持直接暴露到公网的明文 HTTP。远程外部模型权限默认关闭，因为它可能消耗第三方额度或本地资源。自动化客户端不会打开桌面截图界面，只能提交已有图片；官方 Office 客户端可在本机等待用户主动执行的下一次桌面识别结果副本。

读取连接文件中的 `base_url` 和 `token` 后，最小本机调用如下：

```bash
curl "$BASE_URL/api/v1/recognition/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Prefer: wait=30" \
  -F backend=mathcraft \
  -F mode=formula \
  -F "images=@formula.png"
```

安全远程调用使用相同路径，但 `BASE_URL` 必须是 HTTPS 或加密隧道地址，并改用独立生成的远程密钥。详见 [完整 API 文档](docs/automation_api.md) 与 [客户端示例](examples/automation/)。

---

## Microsoft Office 插件

LaTeXSnipper 提供 Windows 桌面版 Microsoft Word 和 PowerPoint 插件：

- Word OLE 和原生 OMML 公式插入
- PowerPoint OLE 和 PNG 公式插入
- 共享 MathLive 编辑器和完整符号/公式库
- 公式加载、更新、删除、自动编号和重编号
- 持久化完整 LaTeX 源码、渲染选项、编号数据和公式身份信息
- OLE 公式本地矢量渲染
- 作为官方 Automation API 客户端调用截图识别

请从 [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) 下载 `OfficePluginSetup-<version>.exe`。插件支持 Windows 桌面版 Office 2019、2021、2024、LTSC 2021/2024 和 Microsoft 365 Apps，覆盖 32 位与 64 位 Office。

安装要求和发布构建说明见 [Office 插件文档](office_plugin/README.md)。

---

## 导出格式

LaTeXSnipper 在主窗口和收藏夹窗口中提供共享导出菜单。桌面端当前提供 20 种导出格式。

内置公式导出格式：

- LaTeX inline、display、equation
- Markdown 行内公式和块公式
- MathML 标准形式、`.mml`、`<m>` 和属性形式
- HTML、Word OMML、SVG 代码

在依赖管理中安装 `PANDOC` 层后，可启用可选 Pandoc 导出格式：

- Word `.docx`、ODT `.odt`、PowerPoint `.pptx`、EPUB `.epub`
- PDF `.pdf`（需要 Pandoc 和 XeLaTeX、LuaLaTeX 或 pdfLaTeX 等 LaTeX PDF 引擎）
- 独立 HTML `.html`、Typst `.typ`、纯文本 `.txt`

---

## 平台支持

| 平台 | 状态 | 说明 |
|---|---|---|
| Windows | 主要发布平台 | 原生全局快捷键、Qt 截图、GitHub/Inno 打包 |
| Linux | 通过 provider 层支持 | `pynput` 全局快捷键、Qt 优先截图，可选 Wayland/X11 命令行或 portal 回退 |
| macOS | 通过 provider 层支持 | 原生全局快捷键、Qt 截图和 `screencapture` 回退，截图可能需要屏幕录制权限 |

Linux 和 macOS 会在用户状态目录中创建可选运行时依赖环境，因此需要系统中有可用的 Python `>=3.10,<3.14`，并带有 venv/pip 支持。依赖管理优先使用最新的受支持版本；Windows 内置运行时仍固定为 Python 3.11。Debian/Ubuntu `.deb` 声明 `python3` 和 `python3-venv`；macOS 用户在系统没有可用 `python3` 时，建议安装 Homebrew Python 或 python.org 官方 Python 3.10-3.13 安装包。

Windows 默认依赖根是 `<安装目录>\_internal\deps`。Linux 默认依赖根是 `~/.latexsnipper/deps`。macOS 默认依赖根是 `~/Library/Application Support/LaTeXSnipper/deps`。用户切换依赖目录后，只有主 Python 依赖环境跟随新的依赖根；Pandoc 固定在应用状态目录的共享 `tools` 目录中，部署一次即可复用。

---

## 支持者名单

感谢所有支持 LaTeXSnipper 开发、测试、文档和社区维护的朋友。

| 支持者 | 贡献 |
|---|---|
| [strangelion](https://github.com/strangelion) | 贡献者 |
| [Galileo927](https://github.com/Galileo927) | 贡献者 |
| [ljygo](https://github.com/ljygo) | 赞助者 |
| [Yokie-D](https://github.com/Yokie-D) | 赞助者 |

---

## 支持本项目

LaTeXSnipper 是免费开源、无广告、无内购的个人项目。如果它帮助了你的论文写作、公式识别或文档处理流程，可以通过赞助、反馈问题或参与测试支持项目继续维护。

| 支付宝 | 微信 | 交流群 |
|---|---|---|
| <img width="300" alt="支付宝收款码" src="https://github.com/user-attachments/assets/1efa46b7-07cb-4a3e-821d-f23b7a36ab34" /> | <img width="300" alt="微信收款码" src="https://github.com/user-attachments/assets/19065b1d-ac40-478e-8318-fabb75488c5c" /> | <img width="300" alt="LaTeXSnipper群聊" src="https://github.com/user-attachments/assets/91c30d59-a4a7-4118-b24b-dada0fe002bf" /> |

---

## 许可证

本项目使用 [GNU General Public License v3](LICENSE) 开源。
