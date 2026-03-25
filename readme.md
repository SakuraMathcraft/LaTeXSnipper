# LaTeXSnipper 2.0

<div align="center">

> 识别 + 编辑 + 计算 | 从截图识别工具升级为桌面数学工作台

<img width="1919" height="1019" alt="latexsnipper" src="https://github.com/user-attachments/assets/e5a8e930-165b-4f69-a871-f05dc5ad6a81" />

![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Stars&color=FFD700)
![Forks](https://img.shields.io/github/forks/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Forks&color=1f6feb)
![Issues](https://img.shields.io/github/issues/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Issues&color=d1481e)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)
![Version](https://img.shields.io/badge/version-v2.0-brightgreen?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows-orange?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11-blue?style=flat-square)

[![GitHub Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![Last Commit](https://img.shields.io/github/last-commit/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Activity)](https://github.com/SakuraMathcraft/LaTeXSnipper/graphs/commit-activity)

</div>

---

## 项目简介

**LaTeXSnipper 2.0** 不再只是“截图公式 -> 输出 LaTeX”的识别工具，而是一个围绕数学内容工作的桌面工作台：

- 截图识别数学公式
- 在数学工作台中继续编辑
- 使用双引擎完成计算、化简、求解、因式分解
- 再将结果写回主编辑器或复制到剪贴板

`v2.0` 的核心变化是新增了独立的 **数学工作台**：内嵌 `MathLive math-field`、虚拟数学键盘、`Compute Engine` 与本地 `SymPy/mpmath` 高级求解引擎。

---

## 功能演示

<table>
  <tr>
    <td align="center" width="50%">
      <img width="1141" height="745" alt="latexsnipper5" src="https://github.com/user-attachments/assets/05d512b9-d453-4138-bd33-e682c1d4510c" />
      <br/>
      <b>截图识别</b><br/>
      框选公式区域，快速得到 LaTeX 与多格式结果
    </td>
    <td align="center" width="50%">
      <img width="756" height="668" alt="latexsnipper7" src="https://github.com/user-attachments/assets/bdd73f8d-0aee-41be-b951-da395defc4b0" />
      <br/>
      <b>实时预览</b><br/>
      识别结果即时渲染，可直接复制或继续处理
    </td>
  </tr>
</table>

### 数学工作台演示

2.0 新增的数学工作台支持这样一条完整链路：

1. 从主窗口截图识别公式
2. 一键载入数学工作台
3. 在 `MathLive` 编辑区继续修改公式
4. 使用虚拟数学键盘补录上下标、分式、积分、级数等结构
5. 执行 `计算 / 化简 / 数值化 / 展开 / 因式分解 / 求解`
6. 将结果写回主编辑器或复制 LaTeX / MathJSON

数学工作台的主要能力包括：

- 结构化公式编辑
- 虚拟数学键盘输入
- LaTeX 与 MathJSON 同步查看
- 计算结果区即时渲染
- 内置示例覆盖多项式、积分、无穷级数、无穷乘积、极限、导数
- 前端 `Compute Engine` 与本地 `SymPy/mpmath` 双引擎回退

---

## 核心功能

| 功能 | 说明 |
|------|------|
| 📸 公式识别 | 截图识别数学公式，支持公式/文本/混合内容 |
| 🧮 数学工作台 | 独立工作台窗口，支持编辑、计算、写回 |
| ⌨️ 公式编辑 | 接入 `MathLive math-field` 与虚拟数学键盘 |
| 🔄 多格式输出 | 支持 LaTeX、Markdown、MathML、HTML、OMML、SVG |
| 📐 基础计算 | 支持计算、化简、数值化、展开、求解 |
| 🧠 高级求解 | `SymPy/mpmath` 本地高级引擎兜底复杂表达式 |
| 🌙 主题适配 | 主窗口、工作台、更新器、依赖向导适配浅色/深色模式 |
| 🔐 离线优先 | 识别与高级求解均可在本地进行，保护隐私 |

---

## 数学工作台支持的计算类型

当前 2.0 工作台已经覆盖下列常见场景：

- 多项式展开
- 因式分解
- 方程求解
- 无理根与复根求解回退
- 定积分与广义积分
- 无穷级数
- 无穷乘积
- 极限
- 导数
- 数值近似与常数识别

对于重表达式，系统会按如下策略自动回退：

1. 前端 `Compute Engine` 快速尝试
2. 超时、失败或结果不可靠时切换本地高级引擎
3. 本地高级引擎使用 `SymPy/mpmath`
4. 对部分经典常数结果执行数值识别与闭式恢复

---

## 快速开始

### 方法一：下载可执行文件

1. 访问 [Releases 页面](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
2. 下载最新版 `LaTeXSnipper_setup_v2.0.exe`
3. 双击运行
4. 首次启动按依赖向导完成环境准备
5. 开始截图识别或打开数学工作台

### 方法二：从源码运行

```bash
git clone https://github.com/SakuraMathcraft/LaTeXSnipper.git
cd LaTeXSnipper

python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt
python src/main.py
```

---

## 使用说明

### 基础识别流程

1. 启动 LaTeXSnipper
2. 点击“截图识别”或使用快捷键
3. 框选公式区域
4. 查看识别结果与预览
5. 直接复制，或载入数学工作台继续处理

### 数学工作台流程

1. 打开“数学工作台”
2. 载入主编辑器公式，或直接在工作台内输入
3. 使用虚拟键盘或键盘输入编辑公式
4. 执行对应动作：
   - `计算`
   - `化简`
   - `数值化`
   - `展开`
   - `因式分解`
   - `求解`
5. 复制 LaTeX / MathJSON，或写回主编辑器

### 计算动作区别

- `计算`：尽量求出表达式结果
- `化简`：把表达式改写为更自然、更短或更规范的形式
- `数值化`：给出数值近似
- `展开`：将乘方、乘积等展开
- `因式分解`：分解为因子乘积
- `求解`：求变量的根或解集

---

## 项目结构

```text
LaTeXSnipper/
├── src/
│   ├── main.py
│   ├── deps_bootstrap.py
│   ├── settings_window.py
│   ├── updater.py
│   ├── backend/
│   │   ├── capture_overlay.py
│   │   ├── model.py
│   │   ├── torch_runtime.py
│   │   └── platform/
│   ├── editor/
│   │   ├── workbench_window.py
│   │   ├── workbench_bridge.py
│   │   └── advanced_cas.py
│   ├── assets/
│   │   ├── MathJax-3.2.2/
│   │   └── mathlive/
│   │       ├── index.html
│   │       ├── app.css
│   │       └── app.js
│   ├── core/
│   └── ui/
├── LaTeXSnipper.spec
├── RELEASE_NOTES_v2.0.md
├── TECH_PLAN_v2.0.md
├── version_info.txt
└── readme.md
```

---

## 2.0 架构说明

`v2.0` 的公式编辑与计算能力采用三层结构：

- `WorkbenchWindow`
  负责桌面窗口、工具栏、状态栏与用户交互
- `WorkbenchBridge`
  负责 Python 与页面间的双向通信
- `MathLive + Compute Engine + SymPy/mpmath`
  负责公式输入、前端即时计算与本地高级求解

这意味着后续编辑器能力不会继续堆积进 `main.py`，而是沿着 `src/editor/` 独立演进。

---

## 贡献指南

欢迎通过以下方式参与：

1. Fork 本仓库
2. 创建功能分支
3. 提交改动
4. 推送分支
5. 发起 Pull Request

建议优先关注：

- 数学工作台交互体验
- 高级求解器稳定性
- 打包版运行验证
- 主题适配与界面一致性

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

## 致谢

感谢以下项目：

- [pix2tex](https://github.com/lukas-blecher/LaTeX-OCR)
- [pix2text](https://github.com/breezedeus/pix2text)
- [MathLive](https://github.com/arnog/mathlive)
- [MathLive Compute Engine](https://mathlive.io/compute-engine/)
- [SymPy](https://www.sympy.org/)
- [mpmath](https://mpmath.org/)
- [MathJax](https://www.mathjax.org/)
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)

---

<div align="center">

| 下载 | 问题反馈 | 讨论 | Wiki |
|---|---|---|---|
| [最新版本](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest) | [提交 Issue](https://github.com/SakuraMathcraft/LaTeXSnipper/issues) | [Discussions](https://github.com/SakuraMathcraft/LaTeXSnipper/discussions) | [项目 Wiki](https://github.com/SakuraMathcraft/LaTeXSnipper/wiki) |

</div>
