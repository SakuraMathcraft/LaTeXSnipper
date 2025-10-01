# LaTeXSnipper



LaTeXSnipper 是一款用于将图片中的数学公式快速识别并转换为 LaTeX 代码的桌面工具。通过简单的截图操作，即可得到对应的 LaTeX 公式，大幅提升数学文档编辑效率。

---

## 功能

- 截图识别数学公式，生成 LaTeX 代码
- 支持多行公式和复杂符号
- 自动复制 LaTeX 代码到剪贴板
- 内置 Pix2Tex OCR 模型，离线识别
- 界面简洁，易于操作

---

## 安装

### 方法一：下载可执行文件（推荐）

1. 访问 [Releases 页面](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
2. 下载最新版 `LaTeXSnipper.exe`
3. 双击运行即可，无需额外安装 Python

> ⚠️ 注意：首次运行可能需要下载模型文件，请保持网络通畅。

### 方法二：从源码安装

1. 克隆仓库：
```bash
git clone https://github.com/SakuraMathcraft/LaTeXSnipper.git
cd LaTeXSnipper
```
2. 创建并激活虚拟环境：
```bash
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# 或 macOS/Linux:
# source .venv/bin/activate
```
3. 安装依赖：
```bash
pip install -r requirements.txt
```
4. 运行程序：
```bash
python src/main.py
```
⚠️ 注意：第一次运行时，Pix2Tex 模型会自动下载（约 100MB），请保持网络连接。
### 使用说明

1. 打开 LaTeXSnipper。

2. 点击“截图公式”按钮或使用快捷键。

3. 框选屏幕上的数学公式区域。

4. 程序会自动识别公式，并将对应 LaTeX 代码复制到剪贴板。

5. 粘贴到你的文档中即可。
### 文件说明
- `src/`：源代码目录
  - `main.py`：主程序入口
  - `gui.py`：图形界面相关代码
  - `ocr.py`：OCR 识别相关代码
- `requirements.txt`：Python 依赖列表
- `README.md`：项目说明文档
- `LICENSE`：开源许可证
- `releases/`：发布的可执行文件
- `assets/`：图标和资源文件
- `.venv/`：Python 虚拟环境目录
- `.gitignore`：Git 忽略文件列表
## 贡献

欢迎通过 GitHub 提交 Issue 或 Pull Request 贡献代码！  
请遵守 [Code of Conduct](CODE_OF_CONDUCT.md) 和 [贡献指南](CONTRIBUTING.md)。

---
## 许可证

本项目遵循 MIT 许可证，详见 [LICENSE](LICENSE) 文件。

---
## 联系方式
如有问题或建议，可联系项目维护者 [SakuraMathcraft](https://github.com/SakuraMathcraft)。




