# Office 插件字体支持评估

本文基于当前仓库打包资源：

- 编辑器预览：MathLive `0.110.0`，本地文件 `src/assets/mathlive/vendor/mathlive.min.mjs`
- 实际插入渲染：MathJax `3.2.2`，本地文件 `src/assets/MathJax-3.2.2`
- Office 插件默认字体设置枚举：`FormulaFontStyle.TeX`、`RomanUpright`、`Bold`、`BoldUpright`、`BoldItalic`、`Italic`、`SansSerif`、`SansSerifBold`、`SansSerifItalic`、`SansSerifBoldItalic`、`Typewriter`、`Calligraphic`、`Script`、`Fraktur`、`Blackboard`

## 结论

插件的“默认字体”只暴露同时满足三条链路的数学样式命令：

- MathLive `0.110.0` 可用对应 `variant` 预览新输入内容。
- MathJax `3.2.2` 可用宏包命令生成 SVG/MathML，且整公式包装样例无 `merror`、unknown command 或缺字异常。
- 插件保存的源码是宏包命令本身，不转成 Unicode 数学字母，也不剥掉字体外壳。

按上述标准，`Calligraphic`、`Script`、`Fraktur`、`Blackboard` 是可支持的默认字体。此前把它们限定为“只适合源码局部记号”是不充分的判断；本地 MathJax 3.2.2 实测可渲染 `\mathcal{e^{i\pi}+1=0}`、`\mathscr{e^{i\pi}+1=0}`、`\mathfrak{e^{i\pi}+1=0}`、`\mathbb{e^{i\pi}+1=0}`。

侧边栏是独立的状态窗格。加载所选公式时只临时展示公式属性，不改写侧边栏用户内容；侧边栏插入路径不套用设置里的默认字体。需要默认字体时使用完整编辑器窗口，字体作为公式元数据进入渲染链路。

## 默认字体支持范围

| 字体/样式 | 默认字体命令 | MathLive 预览 | MathJax 3.2.2 渲染 | 设置页 | 备注 |
|---|---|---:|---:|---:|---|
| TeX 原生数学样式 | 不包装 | 支持 | 支持 | 保留 | 默认 |
| 罗马正体 | `\mathrm{...}` | 支持 | 支持 | 保留 | 适合变量名/文本式数学字母 |
| 粗体符号 | `\boldsymbol{...}` | 支持 | 支持，插件加载 `boldsymbol` | 保留 | 适合希腊字母和符号 |
| 粗体字母 | `\mathbf{...}` | 支持 | 支持 | 保留 | 适合拉丁字母和数字 |
| 粗斜体 | `\mathbfit{...}` | 支持 | 支持 | 保留 | 适合向量/张量变量 |
| 数学斜体 | `\mathit{...}` | 支持 | 支持 | 保留 | 显式样式 |
| 无衬线 | `\mathsf{...}` | 支持 | 支持 | 保留 | 数学无衬线 |
| 无衬线粗体 | `\mathbfsf{...}` | 支持 | 支持 | 保留 | 数学无衬线粗体 |
| 无衬线斜体 | `\mathsfit{...}` | 支持 | 支持 | 保留 | 数学无衬线斜体 |
| 无衬线粗斜体 | `\mathbfsfit{...}` | 支持 | 支持 | 保留 | 数学无衬线粗斜体 |
| 等宽 | `\mathtt{...}` | 支持 | 支持 | 保留 | 代码式数学符号 |
| 花体 | `\mathcal{...}` | 支持 | 支持 | 保留 | 数学字母变体，字符覆盖由 MathLive/MathJax 定义 |
| 手写体 | `\mathscr{...}` | 支持 | 支持 | 保留 | 数学字母变体，字符覆盖由 MathLive/MathJax 定义 |
| 哥特体 | `\mathfrak{...}` | 支持 | 支持 | 保留 | 数学字母变体，字符覆盖由 MathLive/MathJax 定义 |
| 黑板粗体 | `\mathbb{...}` | 支持 | 支持 | 保留 | 数学字母变体，字符覆盖由 MathLive/MathJax 定义 |

## 显式源码命令

| 命令 | 支持方式 | 默认字体选项 |
|---|---|---:|
| `\mathcal{A}` | 用户显式源码，交给 MathJax 原样渲染 | 暴露 |
| `\mathscr{A}` | 用户显式源码，交给 MathJax 原样渲染 | 暴露 |
| `\mathfrak{A}` / `\mathfrak{a}` | 用户显式源码，交给 MathJax 原样渲染 | 暴露 |
| `\mathbb{R}` | 用户显式源码，交给 MathJax 原样渲染 | 暴露 |
| `\upalpha` 等 | 用户显式源码，插件加载 `upgreek` | 不暴露 |

## 实现边界

- `MathLiveLatexStyleNormalizer.NormalizeLatex()` 只做 MathLive 到 MathJax 的必要语法统一，例如 `\bm{...}` 统一为 `\boldsymbol{...}`。
- 不把 `\mathbb`、`\mathcal`、`\mathscr`、`\mathfrak` 转成 Unicode 数学字母。
- 字母变体字体作为默认字体时保存为宏包命令，例如 `\mathbb{...}`；字符覆盖和具体 glyph 由 MathJax/MathLive 决定。
- 侧边栏 `taskpane` 不做字体规范化，不读取默认字体设置，不改写用户 textarea。
- 完整编辑器窗口可按设置保存默认字体元数据，但加载已有公式时源码仍以公式 metadata 的 LaTeX 为准。

## 回归样例

| 样式 | 样例 |
|---|---|
| TeX | `\Gamma(z)=\int_0^\infty t^{z-1}e^{-t}\,dt` |
| Roman | `\mathrm{ABCxyz}` |
| Bold symbol | `\boldsymbol{\Gamma+\alpha+\nabla f}` |
| Bold upright | `\mathbf{ABC123}` |
| Bold italic | `\mathbfit{ABCxyz}` |
| Italic | `\mathit{ABCxyz}` |
| Sans serif | `\mathsf{ABCxyz}` |
| Sans serif italic | `\mathsfit{ABCxyz}` |
| Sans serif bold italic | `\mathbfsfit{ABCxyz}` |
| Typewriter | `\mathtt{ABC123}` |
| Calligraphic | `\mathcal{e^{i\pi}+1=0}` |
| Script | `\mathscr{e^{i\pi}+1=0}` |
| Fraktur | `\mathfrak{e^{i\pi}+1=0}` |
| Blackboard | `\mathbb{e^{i\pi}+1=0}` |

参考：

- MathLive commands: https://mathlive.io/mathfield/reference/commands/
- MathJax 3.2 TeX input: https://docs.mathjax.org/en/v3.2/input/tex/
- MathJax 3.2 TeX commands: https://docs.mathjax.org/en/v3.2/input/tex/macros/
