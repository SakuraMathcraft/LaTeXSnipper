# LaTeXSnipper ✨

<div align="center">

> 🎯 **一键截图，即得 LaTeX 公式** | Screenshot → LaTeX Formula in Seconds
<img width="1919" height="1019" alt="latexsnipper" src="https://github.com/user-attachments/assets/e5a8e930-165b-4f69-a871-f05dc5ad6a81" />

### 📊 项目统计

![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Stars&color=FFD700)
![Forks](https://img.shields.io/github/forks/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Forks&color=1f6feb)
![Issues](https://img.shields.io/github/issues/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Issues&color=d1481e)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)
![Version](https://img.shields.io/badge/version-v1.05-brightgreen?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-orange?style=flat-square)
![Python](https://img.shields.io/badge/python-3.9+-blue?style=flat-square)

[![GitHub Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![Last Commit](https://img.shields.io/github/last-commit/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Activity)](https://github.com/SakuraMathcraft/LaTeXSnipper/graphs/commit-activity)

---

**LaTeXSnipper** 是一款**开源跨平台**桌面工具，基于深度学习模型（pix2tex 和 pix2text），将图片中的数学公式快速识别并转换为多种格式代码。

通过简单的截图操作，即可得到对应的 **LaTeX、MathML、Markdown** 等多格式公式，**大幅提升数学文档编辑效率**！

</div>

---

## 📸 功能演示

<table>
  <tr>
    <td align="center" width="50%">
      <img width="1141" height="745" alt="latexsnipper5" src="https://github.com/user-attachments/assets/05d512b9-d453-4138-bd33-e682c1d4510c" />
      <br/>
      <b>📐 智能识别</b><br/>
      毫秒级识别各类数学公式
    </td>
    <td align="center" width="50%">
      <img width="756" height="668" alt="latexsnipper7" src="https://github.com/user-attachments/assets/bdd73f8d-0aee-41be-b951-da395defc4b0" />
      <br/>
      <b>🔄 多格式转换</b><br/>
      支持 6+ 种输出格式
    </td>
  </tr>
  <tr>
    <td align="center">
      <img width="888" height="675" alt="latexsnipper6" src="https://github.com/user-attachments/assets/5bc3ff1e-d54d-4069-b390-26d4506af95d" />
      <br/>
      <b>👀 实时预览</b><br/>
      识别效果即时反馈
    </td>
    <td align="center">
      <img width="779" height="803" alt="依赖选择" src="https://github.com/user-attachments/assets/9c191b78-8c2c-423f-8747-aebae64ec640" />
      <br/>
      <b>🔐 离线运行</b><br/>
      隐私保护，无需联网
    </td>
  </tr>
</table>

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 📸 **智能识别** | 截图识别数学公式，支持公式/文本/混合内容 |
| 🔄 **多格式转换** | 支持 LaTeX、Markdown、MathML、HTML、OMML、SVG 等格式 |
| 🚀 **离线运行** | 内置模型，无需联网，隐私安全 |
| 🎯 **实时预览** | 公式识别即时预览，效果一目了然 |
| ⚡ **快捷便利** | 一键复制到剪贴板，集成系统快捷键 |
| 📦 **零依赖** | 便携式 exe 可执行文件，开箱即用 |
| 🔧 **高度可定制** | 支持模型选择、导出格式、快捷键自定义 |

---

## 🚀 快速开始

### 方法一：下载可执行文件 (推荐) ⭐

**Windows 用户最简单的方式，内置 Python**

1. 访问 [Releases 页面](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
2. 下载最新版 `LaTeXSnipper_setup_v1.06.exe`
3. 双击运行即可，首次启动会自动下载必要模型（约 2GB+）
4. ✅ 完成！开始截图识别公式

**⚠️ 重要说明（Windows 用户必读）**

请确保已安装 [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)  
否则可能出现缺少 `msvcp140.dll` 等报错。一键下载安装即可。

### 方法二：从源码安装(可能报错，需要调试)

```bash
# 克隆仓库
git clone https://github.com/SakuraMathcraft/LaTeXSnipper.git
cd LaTeXSnipper

# 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# macOS/Linux: source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行程序
python src/main.py
```

---

## 📖 使用说明

### 基础流程

1. **打开应用** - 启动 LaTeXSnipper
2. **截图公式** - 点击"截图公式"按钮或按下配置的快捷键
3. **框选区域** - 用鼠标拖拽框选屏幕上的数学公式
4. **自动识别** - 程序自动识别公式内容
5. **实时预览** - 在预览面板中查看多格式转换结果
6. **复制使用** - 点击复制相应格式代码到剪贴板
7. **粘贴文档** - 粘贴到你的 LaTeX、Word、Markdown 等文档中

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+F` | 启动截图识别（可自定义） |
| `ESC` | 取消当前截图操作 |

### 导出格式说明

- **LaTeX** - 标准数学模式，可直接用于 LaTeX 文档
- **Markdown** - 支持行内 `$...$` 和 block `$$...$$` 格式
- **MathML** - W3C 标准数学标记语言
- **HTML** - HTML5 数学公式表示
- **OMML** - Office Open XML 格式（Word 兼容）
- **SVG** - 向量图形格式，可嵌入网页

---

## 📈 项目活跃度

<div align="center">

### ⭐ Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=SakuraMathcraft/LaTeXSnipper&type=Date)](https://star-history.com/#SakuraMathcraft/LaTeXSnipper&Date)

</div>


## 🤝 贡献指南

欢迎通过以下方式贡献代码：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交改动 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

请确保你的代码：

- 可以优化我们的史山代码
- 包含必要的注释和文档
- 通过所有测试

---

## 📄 许可证

本项目遵循 **MIT 许可证**，详见 [LICENSE](LICENSE) 文件。

你可以自由地使用、修改和分发此项目，只需在许可证中保留原始署名。

---

## � 贡献者

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/SakuraMathcraft">
        <img width="99" height="102" alt="me" src="https://github.com/user-attachments/assets/b0e05780-40ed-4473-b854-1a259f738a9b" />
        <br/>
        <b>SakuraMathcraft</b>
        <br/>
        <sub>💻 开发者 & 维护者</sub>
      </a>
    </td>
  </tr>
</table>

**欢迎贡献！** 如有帮助，请提交 PR 或 Issue。


## 🙏 致谢

感谢以下开源项目的支持：

- [pix2tex](https://github.com/lukas-blecher/LaTeX-OCR) - LaTeX 公式 OCR
- [pix2text](https://github.com/breezedeus/pix2text) - 文字识别
- [MathJax](https://www.mathjax.org/) - 数学公式渲染
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - UI 框架
- [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - 流畅设计

---

**Made with ❤️ by SakuraMathcraft**

<div align="center">


### 📦 快速链接

| 📥 | 🐛 | 💬 | 📖 |
|----|----|----|----|
| [下载最新版本](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest) | [报告 Bug](https://github.com/SakuraMathcraft/LaTeXSnipper/issues/new?template=bug_report.md) | [讨论功能](https://github.com/SakuraMathcraft/LaTeXSnipper/discussions) | [查看 Wiki](https://github.com/SakuraMathcraft/LaTeXSnipper/wiki) |

---

> **⚡ 提示**: 有任何问题？查看 [FAQ](#faq) 或提交 [Issue](https://github.com/SakuraMathcraft/LaTeXSnipper/issues/new)

</div>













