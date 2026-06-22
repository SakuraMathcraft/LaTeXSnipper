# LaTeXSnipper

> 桌面数学工作台：截图、识别、手写、编辑、计算和导出。

[English](readme.md) · [FAQ](docs/faq.md) · [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)

## 核心功能

| 功能 | 说明 |
|---|---|
| 公式识别 | MathCraft OCR 支持公式、文本和图文混排识别 |
| PDF 识别 | 按页识别 PDF，输出 Markdown/LaTeX，并支持 DPI 控制 |
| 手写识别 | 独立手写窗口，支持自动识别和实时预览 |
| 数学工作台 | 基于 MathLive 和 Compute Engine 的编辑、计算、化简、展开、因式分解和求解 |
| 多格式导出 | LaTeX、Markdown、MathML、HTML、OMML、SVG、Word、ODT、PowerPoint、EPUB、PDF、Typst、纯文本等 |
| Office 插件 | Windows 桌面版 Word/PowerPoint 插件，支持 OLE、OMML、PNG 和本地截图识别桥接 |
| 本地优先 | 默认支持本地识别和本地计算，便于隐私敏感场景使用 |

## 平台支持

| 平台 | 状态 | 说明 |
|---|---|---|
| Windows | 主要发布平台 | Inno 安装包，内置规范化 Python 3.11 模板依赖根 |
| Linux | 支持 | `.deb` 包，依赖用户系统 Python `>=3.10,<3.13` 创建隔离依赖环境 |
| macOS | 支持 | `.dmg` / `.app.zip`，依赖用户系统 Python `>=3.10,<3.13` 创建隔离依赖环境 |

Windows 默认依赖根是 `<安装目录>\_internal\deps`。Linux 默认依赖根是 `~/.latexsnipper/deps`。macOS 默认依赖根是 `~/Library/Application Support/LaTeXSnipper/deps`。用户切换依赖目录后，只有主 Python 依赖环境跟随新的依赖根；Pandoc 和 Argos 翻译环境固定在应用状态目录的共享 `tools` 目录中，部署一次即可复用。

## Office 插件

从 [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) 下载 `OfficePluginSetup-<version>.exe`。插件支持 Windows 桌面版 Office 2019、2021、2024、LTSC 2021/2024 和 Microsoft 365 Apps，覆盖 32 位与 64 位 Office。

详细说明见 [office_plugin/README.md](office_plugin/README.md)。

## 卸载与用户数据

Windows 卸载程序会在卸载前显示可选清理窗口。确认后会关闭正在运行的 LaTeXSnipper，并按勾选项删除：

- 用户配置、历史记录、日志和临时文件。
- 配置中记录过的 Python 依赖环境，以及共享工具目录。
- 默认 MathCraft 模型权重目录。

Linux/macOS 包管理器卸载不会自动删除 home 目录中的用户数据。需要清理时运行随包提供的 `latexsnipper-clean-user-data` / `Uninstall User Data.command`。

更完整的数据目录说明见 [docs/user_data_storage.md](docs/user_data_storage.md)。

## 开发验证

Windows 开发和检查使用仓库内 IDE 环境：

```powershell
.\tools\deps\python311\python.exe -m ruff check .
.\tools\deps\python311\python.exe -m pyright
.\tools\deps\python311\python.exe -m pytest test
.\tools\deps\python311\python.exe -m coverage run -m pytest test -q
.\tools\deps\python311\python.exe -m coverage report --skip-covered
```

提交前请阅读 [docs/developer_code_standards.md](docs/developer_code_standards.md)。

## 支持者名单

感谢所有支持 LaTeXSnipper 开发、测试、文档和社区维护的朋友。

| 支持者 | 贡献 |
|---|---|
| 占位 | Sponsor / contributor list will be added here. |

## 支持本项目

LaTeXSnipper 是免费开源、无广告、无内购的个人项目。如果它帮助了你的论文写作、公式识别或文档处理流程，可以通过赞助、反馈问题或参与测试支持项目继续维护。

| 支付宝 | 微信 | 交流群 |
|---|---|---|
| <img width="260" alt="支付宝收款码" src="https://github.com/user-attachments/assets/1efa46b7-07cb-4a3e-821d-f23b7a36ab34" /> | <img width="260" alt="微信收款码" src="https://github.com/user-attachments/assets/19065b1d-ac40-478e-8318-fabb75488c5c" /> | <img width="260" alt="LaTeXSnipper群聊" src="https://github.com/user-attachments/assets/91c30d59-a4a7-4118-b24b-dada0fe002bf" /> |

## 许可证

本项目使用 [GNU General Public License v3](LICENSE) 开源。
