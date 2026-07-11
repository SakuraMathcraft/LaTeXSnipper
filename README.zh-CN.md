# LaTeXSnipper

<div align="center">

**在一个桌面工作区中完成数学内容的截图、识别、编辑、计算与导出。**

<img width="1919" height="1020" alt="LaTeXSnipper 桌面工作区" src="https://github.com/user-attachments/assets/9d00310b-d1b6-4321-b961-8837b3efb864" />

[![Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![CI](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/ci.yml)
[![macOS CI](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/macos-ci-artifact.yml/badge.svg?branch=main)](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/macos-ci-artifact.yml)
[![License](https://img.shields.io/github/license/SakuraMathcraft/LaTeXSnipper?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/stargazers)
![Platforms](https://img.shields.io/badge/Windows%20%7C%20Linux%20%7C%20macOS-supported-orange?style=flat-square)

[下载](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) · [用户手册](user_manual/LaTeXSnipper_User_Manual.pdf) · [常见问题](docs/faq.md) · [基准测试](benchmarks/mathcraft_ocr/README.md)

[English](readme.md) · 简体中文

</div>

## 项目概览

LaTeXSnipper 是一款本地优先的桌面数学 OCR 与文档工作流应用，将截图、图片、PDF、手写识别与 MathLive 编辑、实时渲染、符号计算、历史记录、收藏夹和文档导出整合在同一界面中。

内置 MathCraft OCR 运行时提供三种边界明确的结果类型：

| 模式 | 适用输入 | 结果与渲染方式 |
|---|---|---|
| 公式 | 独立公式与推导过程 | LaTeX 公式 |
| 混合 | 同时包含文字和公式的数学页面 | 含 LaTeX 数学内容的 Markdown |
| 纯文本 | 普通文字区域 | 纯文本 |

外部视觉模型可通过 Ollama 或 OpenAI-compatible 接口复用这三种结果契约；MinerU Local 通过原生文档解析接口接入。

## 快速开始

1. 从 [GitHub Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) 下载对应平台的安装包。
2. 启动 LaTeXSnipper，并在提示时打开依赖向导。
3. 安装所需功能层。稳定默认组合为 `BASIC + CORE + MATHCRAFT_CPU`；具备兼容 NVIDIA 环境时可选择 `MATHCRAFT_GPU`。
4. 从主窗口或全局快捷键发起截图识别，然后编辑、复制、收藏或导出结果。

Windows 安装包包含最小 Python 3.11 依赖运行时。Linux 和 macOS 使用系统 Python `>=3.10,<3.13` 创建可选依赖环境，推荐 Python 3.11。完整安装和故障排查见[用户手册](user_manual/LaTeXSnipper_User_Manual.pdf)。

## 核心能力

| 领域 | 能力 |
|---|---|
| 识别 | 截图、图片、PDF 页码范围、手写、公式/纯文本/混合模式 |
| 编辑 | MathLive 可视化编辑器、虚拟键盘、MathJax 实时预览、多行公式 |
| 计算 | 计算、化简、数值化、展开、因式分解和求解 |
| 内容管理 | 带稳定渲染属性的历史记录和收藏夹 |
| 外部模型 | Ollama、OpenAI-compatible 视觉接口和 MinerU Local |
| 导出 | 覆盖 LaTeX、Markdown、MathML、HTML、OMML、SVG、Office 文档、EPUB、PDF、Typst 和文本等 20 种格式 |
| 桌面集成 | 全局快捷键、系统托盘/菜单栏、剪贴板和多显示器截图 |

识别和计算可以完全在本地运行；外部服务为可选能力，由用户显式配置。

## 可复现基准

MathCraft OCR 自带可进入版本控制的基准套件，包括数据清单、运行脚本、指标计算、协议说明和精简结果报告。大型公开数据集和完整预测结果保存在仓库之外。

| 基准 | 规模 | 已报告结果 | 评估用途 |
|---|---:|---|---|
| UniMER-Test | 23,757 个公式 | BLEU-4 `0.7946`；23,701 个可渲染样本的官方 CDM `0.9288` | 印刷与手写公式 OCR |
| MathWriting test | 7,644 个样本 | BLEU-4 `0.5467`；官方 CDM `0.750`；预测渲染成功率 `98.63%` | 独立手写压力测试 |
| OpenStax 混合页面 | 200 页 | `0` 失败、`0` 空结果；中位耗时 `6.65 秒/页` | 混合页面完成率、结构和运行时间 |

上述记录均使用 `CUDAExecutionProvider`，耗时受硬件影响。三个数据集承担不同评估任务，表格不能视为模型排行榜。完整协议和复现方式见[基准测试文档](benchmarks/mathcraft_ocr/README.md)，精简结果见[结果目录](benchmarks/mathcraft_ocr/results)，发布级表格与对比图见[模型仓库基准页](https://github.com/SakuraMathcraft/MathCraft-Models/tree/main/benchmarks)。

## Microsoft Office 插件

Windows Office 插件将 LaTeXSnipper 集成到桌面版 Word 和 PowerPoint：

- Word OLE 和原生 OMML 公式插入
- PowerPoint OLE 和高 DPI PNG 插入
- 共享 MathLive 公式编辑器与符号库
- 公式加载、更新、删除、编号和重编号
- 持久化源码、渲染、编号和公式身份元数据
- 通过本地桌面 Bridge 调用截图 OCR

请从 [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) 下载 `OfficePluginSetup-<version>.exe`。插件支持 Windows 桌面版 Office 2019、2021、2024、LTSC 2021/2024 和 Microsoft 365 Apps，覆盖 32 位与 64 位 Office。详细要求见 [Office 插件文档](office_plugin/README.md)。

## 导出格式

内置导出无需 Pandoc：

- LaTeX inline、display 和 equation
- Markdown 行内公式和块公式
- MathML 标准形式、`.mml`、`<m>` 和属性形式
- HTML、Word OMML 和 SVG 源码

可选 `PANDOC` 功能层支持 Word `.docx`、ODT `.odt`、PowerPoint `.pptx`、EPUB `.epub`、PDF `.pdf`、独立 HTML、Typst 和纯文本。文档内容中的完整 SVG 块会经过验证、渲染并作为图像资产嵌入文档；PDF 导出还需要可用的 LaTeX PDF 引擎。

## 平台支持

| 平台 | 打包形式 | 集成说明 |
|---|---|---|
| Windows | 当前用户 Inno 安装包 | 原生全局快捷键、托盘集成、内置最小 Python 运行时 |
| Linux | Debian 软件包 | `pynput` 快捷键 provider；Qt 截图并支持可选 Wayland/X11 或 portal 工具 |
| macOS | `.app.zip` 和 DMG | 原生快捷键 provider、Dock/菜单集成，截图需要屏幕录制权限 |

配置、日志、依赖环境、共享工具、临时文件和模型权重均遵循平台用户数据目录，详见[用户数据存储说明](docs/user_data_storage.md)。

## Star 趋势

<a href="https://repostars.dev/?repos=SakuraMathcraft%2FLaTeXSnipper">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://repostars.dev/api/embed?repo=SakuraMathcraft%2FLaTeXSnipper&amp;theme=dark">
    <source media="(prefers-color-scheme: light)" srcset="https://repostars.dev/api/embed?repo=SakuraMathcraft%2FLaTeXSnipper&amp;theme=light">
    <img alt="LaTeXSnipper Star 趋势图" src="https://repostars.dev/api/embed?repo=SakuraMathcraft%2FLaTeXSnipper&amp;theme=light">
  </picture>
</a>

## 支持者名单

感谢所有支持开发、测试、文档和社区维护的朋友。

| 支持者 | 贡献 |
|---|---|
| [strangelion](https://github.com/strangelion) | 贡献者 |
| [Galileo927](https://github.com/Galileo927) | 贡献者 |
| [ljygo](https://github.com/ljygo) | 赞助者 |
| [Yokie-D](https://github.com/Yokie-D) | 赞助者 |

## 支持项目

LaTeXSnipper 免费开源、无广告，由个人独立维护。赞助、问题反馈、可复现测试和文档贡献都有助于项目长期维护。

| 支付宝 | 微信 | 交流群 |
|---|---|---|
| <img width="240" alt="支付宝" src="https://github.com/user-attachments/assets/1efa46b7-07cb-4a3e-821d-f23b7a36ab34" /> | <img width="240" alt="微信" src="https://github.com/user-attachments/assets/19065b1d-ac40-478e-8318-fabb75488c5c" /> | <img width="240" alt="LaTeXSnipper 交流群" src="https://github.com/user-attachments/assets/91c30d59-a4a7-4118-b24b-dada0fe002bf" /> |

## 许可证

LaTeXSnipper 使用 [GNU General Public License v3.0](LICENSE) 开源。
