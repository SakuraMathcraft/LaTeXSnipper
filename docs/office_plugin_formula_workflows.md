# Office 插件公式链路与元数据边界

本文记录当前 Office 插件的公式源码、渲染、编号、引用、转换、格式化和元数据存储边界。当前实现的核心原则是：**完整 LaTeX 源码是字体、颜色和公式内容的唯一可信来源**。

## 当前源码边界

新建公式打开 MathLive 编辑器时，编辑器不会把设置中的默认字体和颜色立即套到预览上。用户第一次输入时看到的是原始 MathLive 预览；点击插入或更新后，插件才会把设置转换为 LaTeX 源码包装，例如 `\color{...}{...}`、`\mathbb{...}`、`\boldsymbol{...}`。再次加载所选公式时，编辑器和侧边栏都读取同一份完整 LaTeX 源码，因此会显示已经写入源码的字体和颜色包装。

这个边界优于旧实现：

- 不再同时维护“源码、隐藏 FontColor/FontStyle 元数据、编辑器临时样式”三套状态。
- 加载、更新、格式化、转换都只信任完整 LaTeX 源码，避免侧边栏和编辑器源码不一致。
- 用户手写的字体和颜色宏不会被加载链路剥离。
- 设置中的默认字体/颜色只影响“新插入”和“格式化所选”，不会在编辑器打开时改写用户内容。

代价是：第一次打开新建编辑器时，默认字体和颜色不会立刻可见。这个现象在当前边界内是预期内的，因为默认设置还没有被写入 LaTeX 源码。

## 统一元数据模型

共享元数据对象为 `FormulaMetadata`，字段为：

| 字段 | 用途 |
| --- | --- |
| `Identity.DocumentId` | 当前宿主文档或演示文稿标识 |
| `Identity.EquationId` | 公式稳定 ID |
| `Latex` | 完整 LaTeX 源码，包含字体和颜色宏 |
| `DisplayMode` | 行内或行间 |
| `NumberingMode` | 无编号、自动编号、手动编号 |
| `NumberText` | 手动编号文本 |
| `RenderEngine` | `Omml`、`MathJaxSvg` 或 `Image` |
| `SchemaVersion` | 元数据结构版本 |
| `FontScale` | 插件设置中的缩放倍率 |

元数据不再单独保存 `FontColor` 或 `FontStyle`。字体和颜色只存在于 `Latex` 中。

## Word 元数据存储

Word 中公式对象自身只保存短标签：

```text
latexsnipper-eq-{equationId}|{revision}
```

短标签写入：

- OMML 公式：content control 的 `Tag`
- OLE 公式：inline shape 的 `AlternativeText`

完整 JSON 元数据写入 Word `Document.Variables`：

```text
LS.E.{equationId}.{revision}
```

这样可以避开 Word content control tag 的 64 字符限制。每次保存都会生成新的 10 位 revision，并把短标签指向新 revision。加载时必须同时拿到 equationId 和 revision，然后从 `Document.Variables` 读取完整 JSON。

OLE 公式还会在同一份 JSON 中保存自然宽高：

| 字段 | 用途 |
| --- | --- |
| `naturalWidthPoints` | OLE 初始自然宽度 |
| `naturalHeightPoints` | OLE 初始自然高度 |

这些字段用于判断用户是否手动拉伸公式，并支持格式化时恢复自然尺寸。

OMML 的自然字号单独存储在：

```text
LaTeXSnipper.OmmlNaturalFontSize.{equationId}
```

用于恢复 Word 原生公式的自然字号。

## PowerPoint 元数据存储

PowerPoint 公式以 shape 为单位保存元数据。短字段写入 shape tags：

| Tag | 用途 |
| --- | --- |
| `LaTeXSnipperEquationId` | 公式 ID |
| `LaTeXSnipperDisplayMode` | 显示模式 |
| `LaTeXSnipperSchemaVersion` | schema |
| `LaTeXSnipperRenderEngine` | 渲染类型 |
| `LaTeXSnipperFontScale` | 缩放倍率 |
| `LaTeXSnipperNaturalWidthPoints` | 自然宽度 |
| `LaTeXSnipperNaturalHeightPoints` | 自然高度 |
| `LaTeXSnipperImagePath` | PNG 插入时的临时图片路径 |

完整 LaTeX 源码使用 UTF-8 转十六进制后分块存储：

| Tag | 用途 |
| --- | --- |
| `LaTeXSnipperLatexBytes` | 原始 UTF-8 字节数 |
| `LaTeXSnipperLatexChunks` | 分块数量 |
| `LaTeXSnipperLatex0000` 起 | 十六进制源码分块 |

每块长度为 200 个十六进制字符，并校验字节数、分块数量和十六进制解析结果。这样可以安全保存较长 LaTeX 源码，不依赖单个 tag 容量。

## Word 插入链路

### 插入行内公式

1. Ribbon 调用 `InsertInlineAsync`。
2. 打开 MathLive 编辑器，初始源码为空，显示模式为 `Inline`。
3. 用户提交后，`CreateMetadataFromOptions` 读取当前设置。
4. 对新公式调用 `ApplyDefaultSourceFormatting`，把默认字体/颜色写入 LaTeX 源码。
5. 按设置的插入后端生成 OMML 或 OLE。
6. 插入完成后保存元数据并移动光标到公式外。

### 插入行间公式

行间公式与行内公式相同，但 `DisplayMode` 为 `Display`，Word 插入范围会解析到当前段落或新段落，普通行间公式居中。

### 插入带编号公式

1. Ribbon 调用 `InsertNumberedAsync`。
2. 打开编辑器时只记录编号意图，不把默认字体/颜色注入预览。
3. 提交后生成 display 公式，并设置 `NumberingMode`。
4. 自动编号公式插入时不会立即执行全文重编号，只插入当前编号字段；重编号由显式重编号或边界插入链路触发。
5. 段落使用左对齐加两个 tab stop：页面中线用于公式居中，页面右侧用于右编号。
6. 编号使用 Word `SEQ` 字段，编号范围加书签。

## Word 编号与引用

自动编号使用：

```text
SEQ LaTeXSnipperEquation
```

引用使用：

```text
REF LaTeXSnipperEq_{equationId} \h
```

编号状态由文档中的公式和编号边界共同计算：

- chapter boundary 增加章号并重置节号。
- section boundary 增加节号。
- 设置中的层级分割符只用于构造编号前缀，例如 `1-2-3`。
- 编号外框由设置中的 enclosure 控制，例如 `()`、`[]`、`{}` 或无外框。

插入引用的链路：

1. 插入占位符 `[请选择公式]`。
2. 用户选择带编号公式或其所在段落。
3. 插件找到目标公式 ID。
4. 用目标编号范围创建或更新书签。
5. 用 Word `REF` 字段替换占位符。
6. 引用字段更新后重置普通文本基线。

选中编号本身不作为稳定引用入口；当前稳定入口是选中公式或公式所在段落。

## Word 加载所选

加载所选只读取被选中的公式对象：

- OMML：读取 content control `Tag`，再读取 `Document.Variables`。
- OLE：读取 inline shape `AlternativeText`，再读取 `Document.Variables`。

加载后：

- 编辑器打开完整 `Latex`。
- 侧边栏临时显示同一份完整 `Latex`。
- 不套用隐藏字体/颜色元数据。
- 不剥离字体或颜色宏。

## Word 删除所选

删除所选支持：

- 选中的托管公式。
- 选区内的 OLE 公式。
- 选中的章/节编号边界控件。
- 选中的 REF 引用字段。
- 当前待完成的引用占位符。

删除时先收集目标，再按文档位置倒序删除，避免前面的删除动作改变后续范围。删除操作在一个 Word undo record 内执行。

当前不支持“只选中编号数字就删除对应公式”。这是有意收窄后的边界，避免编号字段和公式对象之间产生不稳定的反向选择关系。

## Word 转换链路

### OMML 转 OLE

1. 加载选中公式条目。
2. 读取完整 LaTeX 源码。
3. 切换 `RenderEngine` 为 `MathJaxSvg`。
4. MathJax 3.2.2 生成 SVG。
5. SVG 转 EMF presentation。
6. 用 OLE 对象替换原公式，并保存同一份完整 LaTeX 元数据。

### OLE 转 OMML

1. 读取 OLE 元数据中的完整 LaTeX。
2. MathJax 3.2.2 转 MathML。
3. `MathMlToOmmlConverter` 转 OMML。
4. 用 Word content control 替换 OLE 对象。
5. 恢复公式 ID、编号状态、字号和元数据。

转换只处理被选中的托管公式，不扫描和修复旧内容。

## Word 格式化链路

### 格式化所选

格式化所选会重写选中公式的 LaTeX 源码：

1. 移除已有颜色包装。
2. 移除顶层字体包装。
3. 按当前设置重新包裹字体宏。
4. 按当前设置重新添加颜色宏。
5. 更新 `FontScale`。
6. 按公式当前渲染引擎重新渲染并替换。

多行环境和 `\displaylines` 会按顶层段落或对齐段落包装，避免把整段环境粗暴包成一个不可控外壳。

### 格式化全文

格式化全文只恢复被用户手动改过尺寸的公式：

- OMML 恢复自然字号。
- OLE / PowerPoint shape 恢复自然宽高。

它不会批量改写所有 LaTeX 源码，避免误改用户手写字体、颜色或复杂宏。

## PowerPoint 插入、加载、删除、转换、格式化

PowerPoint 没有 Word 编号和引用链路，公式对象是 shape：

- 插入公式：打开编辑器，提交后把设置写入完整 LaTeX 源码，再按设置插入 PNG 或 OLE。
- 从侧边栏插入：直接读取侧边栏当前 LaTeX，并在插入时应用默认源码格式。
- 加载所选：只读取选中 shape 的完整 LaTeX 元数据。
- 删除所选：删除选中的托管公式 shape；PNG 公式会清理插件临时图片文件。
- OLE/PNG 转换：读取完整 LaTeX，切换 render engine，删除原 shape 后在原 slide、原位置按原 scale 插入。
- 格式化所选：按当前设置重写 LaTeX 源码并恢复 scale。
- 格式化全文：仅恢复所有托管公式 shape 的自然宽高。

PowerPoint 编辑器固定白底黑字，因为 PowerPoint 编辑画布背景板固定为白色。Word 编辑器按系统深色模式适配。

## OLE payload

OLE 对象创建前，插件把 `FormulaMetadata` 和 `OlePresentationResult` 序列化到 pending payload。payload 包含：

- 完整 LaTeX。
- display / numbering / render engine。
- fontScale。
- MathJax renderer version。
- presentation 宽高、基线、MIME 和 base64 payload。

payload 不包含单独 FontColor / FontStyle。OLE 控件读取后得到的仍然是完整 LaTeX 源码。

## 字体方框修正边界

MathJax 3.2.2 的 SVG 对部分数学字母会输出 `<text data-variant="...">`，例如 `\mathbb` 的小写字母和数字。插入 Office 时插件会把 SVG 转为 EMF/PNG，因此这些 `<text>` 节点不能落到普通系统 UI 字体。

当前 SVG 文本绘制规则：

- 带 `data-variant` 的数学文本优先使用 `Cambria Math` 和 `Segoe UI Symbol`。
- 普通文本仍使用中文/UI 字体顺序。
- 路径字形仍按 MathJax SVG path/use 直接绘制。

这解决了浏览器预览正常但插入后数学字符变方框的问题。

## Undo 与外部传递

Word 插入、更新、删除、编号、转换和格式化都在必要位置使用 Word undo record。用户撤销后，Word 会同时回撤对象、字段和文档变量的变化。

文档发给其他用户再返回时，插件能否加载取决于 Office 是否保留：

- Word content control `Tag` 或 OLE inline shape `AlternativeText`。
- Word `Document.Variables`。
- PowerPoint shape tags。
- OLE 对象本身或 PNG shape。

这些都是 Office 文档内的原生持久化载体，不依赖本机临时内存。PowerPoint PNG 的临时图片路径只用于本机清理文件，不影响公式元数据加载。

## 当前明确边界

- 不为旧隐藏 FontColor / FontStyle 元数据做兼容。
- 不从编号数字反向删除公式。
- 不把默认字体/颜色作为编辑器打开时的临时样式。
- 不在加载所选时改写侧边栏用户草稿以外的持久源码。
- 不在格式化全文时批量重写所有公式源码。
- 不保留迁移期文档或历史兜底逻辑。
