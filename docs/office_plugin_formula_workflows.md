# Office 插件公式链路与元数据边界

本文记录当前 Office 插件的公式源码、渲染、编号、引用、转换、格式化和元数据存储边界。当前实现的核心原则是：**完整 LaTeX 源码是字体、颜色和公式内容的唯一可信来源**。

## 当前源码边界

新建公式打开 MathLive 编辑器时，编辑器不会把设置中的默认字体和颜色立即套到预览上。用户第一次输入时看到的是原始 MathLive 预览；只有新插入公式或执行“格式化所选”时，插件才会把设置转换为 LaTeX 源码包装，例如 `\color{...}{...}`、`\mathbb{...}`、`\boldsymbol{...}`。加载已有公式和更新已有公式都读取并保存同一份完整源码，不额外套用设置中的默认字体或颜色。

当前边界：

- 加载、更新、格式化、转换都只信任完整 LaTeX 源码，侧边栏和编辑器显示同一份源码。
- 用户手写的字体和颜色宏由加载链路按原样保留。
- 设置中的默认字体/颜色只影响“新插入”和“格式化所选”，不会在编辑器打开时改写用户内容。

第一次打开新建编辑器时，默认字体和颜色不会立刻可见；提交新公式后，默认格式才写入公式源码并随元数据保存。

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

元数据只保存完整 `Latex`，字体和颜色以 LaTeX 宏存在于源码中，不保存独立的字体或颜色字段。

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

## 设置项影响边界

### Word 设置

| 设置项 | 影响链路 | 不影响链路 |
| --- | --- | --- |
| 插入后端：OLE / Word OMML | 新插入公式、公式解析、更新公式、转换目标渲染引擎 | 加载所选、删除所选、引用字段 |
| 公式默认颜色 | 新插入公式、公式解析、格式化所选 | 加载所选、更新公式、打开编辑器预览、格式化全文、重编号、引用 |
| 公式默认字体 | 新插入公式、公式解析、格式化所选 | 加载所选、更新公式、打开编辑器预览、格式化全文、重编号、引用 |
| 公式缩放 | 新插入公式、公式解析、格式化所选、自然尺寸记录 | 加载所选、重编号、引用 |
| 编号位置：左 / 右 | 新插入编号公式、给已有公式添加编号、更新编号公式时重建布局 | 已存在编号公式不会仅因保存设置或执行重编号自动左右移动 |
| 编号外框 | 新插入自动编号、给已有公式添加编号、重编号、手动编号显示 | 引用字段自身不独立生成外框，只引用目标编号书签 |
| 包含章编号 | 新插入自动编号、给已有公式添加编号、重编号 | 手动编号文本 |
| 包含节编号 | 新插入自动编号、给已有公式添加编号、重编号 | 手动编号文本 |
| 层级分隔符 | 自动编号前缀，例如 `1-2-3`、`1.2.3` | 手动编号文本、引用字段逻辑 |
| 隐藏章分隔符 | 章分隔符控件的文字可见性 | 自动编号计算；隐藏后仍参与编号 |
| 隐藏节分隔符 | 节分隔符控件的文字可见性 | 自动编号计算；隐藏后仍参与编号 |

设置窗口保存后会立即刷新章/节分隔符的可见性。编号文本本身不因打开设置窗口自动重写；自动编号的重新计算由“重编号”、插入章/节分隔符、插入/更新编号公式等明确命令触发。

### PowerPoint 设置

| 设置项 | 影响链路 | 不影响链路 |
| --- | --- | --- |
| 插入后端：OLE / PNG | 新插入公式、转换目标渲染引擎 | 加载所选、删除所选 |
| 公式默认颜色 | 新插入公式、格式化所选 | 加载所选、更新公式、打开编辑器预览、格式化全文 |
| 公式默认字体 | 新插入公式、格式化所选 | 加载所选、更新公式、打开编辑器预览、格式化全文 |
| 公式缩放 | 新插入公式、格式化所选、自然尺寸记录 | 加载所选 |

PowerPoint 没有 Word 编号、引用、章/节分隔符链路。

## Word 插入链路

### 插入行内公式

1. Ribbon 调用 `InsertInlineAsync`。
2. 打开 MathLive 编辑器，初始源码为空，显示模式为 `Inline`，不把默认字体/颜色写入编辑器草稿。
3. 用户提交后，`CreateMetadataFromOptions` 读取当前设置。
4. 对新公式调用 `ApplyDefaultSourceFormatting`，把默认字体/颜色写入 LaTeX 源码。
5. 按设置的插入后端生成 OMML 或 OLE。
6. 插入完成后保存元数据并移动光标到公式外。

### 插入行间公式

行间公式与行内公式相同，但 `DisplayMode` 为 `Display`，Word 插入范围会解析到当前段落或新段落，普通行间公式居中。

### 插入带编号公式

1. Ribbon 调用 `InsertNumberedAsync`。
2. 打开编辑器时只记录编号意图，不把默认字体/颜色写入编辑器草稿。
3. 提交后生成 display 公式，并设置 `NumberingMode`。
4. 自动编号公式插入时按当前位置前的编号时间线计算当前章/节前缀和是否需要重置 `SEQ`，只写入当前公式的编号字段。
5. 段落使用制表位布局：公式在正文区域中线对齐，编号按设置位于左侧或右侧。
6. 自动编号使用 Word `SEQ` 字段，编号显示范围加书签。
7. 插入完成后不执行全文重编号；全文重编号由“重编号”命令或插入章/节分隔符触发。

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

### 给已有公式添加编号

1. Ribbon 调用 `AutoNumberSelectedAsync`。
2. 只接受已被 LaTeXSnipper 托管的行间公式；行内公式不会被添加编号。
3. 如果所选公式已有编号，直接提示已编号，不重写。
4. 读取当前设置并把 `NumberingMode` 改为 `Automatic`。
5. 按公式当前渲染引擎更新当前公式：
   - OMML：重新生成 OMML 段落布局，插入 content control 后通过 Word COM 在公式段落内写入当前 `SEQ` 字段。
   - OLE：按当前公式高度和布局写入编号字段。
6. 只更新当前公式，不执行全文重编号。

这个边界保证“添加编号”只负责把所选公式变成编号公式；全局序号校正交给“重编号”命令。

### 重编号

1. Ribbon 调用 `RenumberAllAsync`。
2. 扫描当前文档中所有 LaTeXSnipper 托管的自动编号公式：
   - OMML：content control。
   - OLE：inline shape。
3. 同时扫描章/节分隔符 content control。
4. 按文档位置合并排序，计算每个公式的章/节前缀、`SEQ` 是否重置和外框。
5. 对每个公式只更新其现有 `SEQ` 字段代码和编号书签；不会重新渲染公式主体，也不会改写 LaTeX 源码。
6. 一次性建立 `EquationId -> SEQ Field` 映射；字段匹配以编号书签范围和字段结果范围相交为准，不能把字段结果的精确边界当作稳定 ID。
7. 只刷新 LaTeXSnipper 自己的 `SEQ` 字段和 `REF` 引用字段，并对 OLE 编号按公式高度重新应用基线偏移。
8. 找不到元数据、编号书签或 SEQ 字段的异常公式计入跳过数量，剩余公式继续重编号。

重编号不负责插入新公式、不负责格式化源码、不负责转换渲染引擎。

### 章/节分隔符

1. Ribbon 调用 `InsertChapterBoundaryAsync` 或 `InsertSectionBoundaryAsync`。
2. 在当前光标位置插入一个 rich text content control。
3. 控件只保存边界 tag：
   - `latexsnipper-number-boundary-chapter`
   - `latexsnipper-number-boundary-section`
4. 控件显示文本为“章分隔符”或“节分隔符”；是否隐藏由设置控制。
5. 插入边界后立即执行一次重编号，因为边界会改变其后的自动编号前缀和 `SEQ` 重置点。

章/节分隔符只服务插件自动编号，不绑定 Word 标题级别，也不改变 Word 文档大纲。

### 插入引用

插入引用的链路：

1. 插入占位符 `[请选择公式]`。
2. 用户选择带编号公式或其所在段落；选中编号数字不是稳定入口。
3. 插件找到目标公式 ID。
4. 用目标编号范围创建或更新书签。
5. 用 Word `REF` 字段替换占位符。
6. 引用字段更新后重置普通文本基线。

引用不保存自己的编号文本。它只保存到目标编号书签的 Word `REF` 字段，因此重编号后引用由 Word 字段更新得到新结果。

## Word 加载所选

加载所选只读取被选中的公式对象：

- OMML：读取 content control `Tag`，再读取 `Document.Variables`。
- OLE：读取 inline shape `AlternativeText`，再读取 `Document.Variables`。

加载后：

- 编辑器打开完整 `Latex`。
- 侧边栏临时显示同一份完整 `Latex`。
- 不读取独立字体/颜色元数据。
- 按原样保留字体或颜色宏。

## Word 删除所选

删除所选支持：

- 选中的托管公式。
- 选区内的 OLE 公式。
- 选中的章/节编号边界控件。
- 选中的 REF 引用字段。
- 当前待完成的引用占位符。

删除时先收集目标，再按文档位置倒序删除，避免前面的删除动作改变后续范围。删除操作在一个 Word undo record 内执行。

当前不支持“只选中编号数字就删除对应公式”。这是有意收窄后的边界，避免编号字段和公式对象之间产生不稳定的反向选择关系。

删除引用字段只删除引用本身，不删除目标公式。删除章/节分隔符只删除边界控件；如果需要刷新后续自动编号，需要再执行“重编号”。

## Word 转换链路

### OMML 转 OLE

该命令覆盖两类来源，复杂度不同。

#### 托管 OMML 公式转 OLE

1. 加载选中的托管 OMML 公式条目。
2. 从 content control `Tag` 和 `Document.Variables` 读取完整 LaTeX 源码。
3. 切换 `RenderEngine` 为 `MathJaxSvg`。
4. MathJax 3.2.2 生成 SVG。
5. SVG 转 EMF presentation。
6. 用 OLE 对象替换原公式，并保存同一份完整 LaTeX 元数据。

#### Word 原生 OMML 公式转 OLE

1. 加载选区内未被 LaTeXSnipper content control 托管的 Word 原生 `OMath`。
2. 读取 Word 原生 OMML OOXML。
3. 使用 `OmmlToMathMlConverter` 把 OMML 转为 MathML。
4. 创建新的 `FormulaMetadata`，把 MathML 字符串存入 `Latex` 字段，并把 `RenderEngine` 设为 `MathJaxSvg`。
5. MathJax 3.2.2 按 MathML 输入渲染 SVG。
6. SVG 转 EMF presentation。
7. 删除原 Word 原生公式，在原位置插入 LaTeXSnipper OLE 对象。

这条链路的源码字段保存的是 MathML，不是 LaTeX。它的目的只是把 Word 原生公式转换为可由插件持久化、加载和继续转换的 OLE 公式。由于格式化链路按 LaTeX 宏重写源码，不能对这类 MathML 源码执行“格式化所选”，否则会把 MathML 当 LaTeX 包装并导致乱码。当前格式化命令不会处理 Word 原生 OMML；已经转成 OLE 后的 MathML 源码公式也应视为转换来源保真对象，而不是 LaTeX 格式化对象。

### OLE 转 OMML

1. 读取 OLE 元数据中的完整 LaTeX。
2. MathJax 3.2.2 转 MathML。
3. `MathMlToOmmlConverter` 转 OMML。
4. 用 Word content control 替换 OLE 对象。
5. 恢复公式 ID、编号状态、字号和元数据。

转换只处理当前选区内的公式，不扫描全文。多选转换入口只收集 `EquationId`、起始位置、渲染类型和必要元数据快照，不跨批持有 `ContentControl`、`InlineShape` 或 shape 这类 live COM object。转换按文档位置倒序分批执行，每批重新按稳定 ID 确认对象仍存在；找不到对象则计入跳过数量，剩余公式继续处理。Word 每批使用短 undo record，避免把大量对象包进一个超长事务。

`OMML 转 OLE` 命令会额外识别当前选区内的 Word 原生 OMML 公式，并按上面的 MathML 源码链路转换为 LaTeXSnipper OLE。该能力只属于显式转换入口。

## Word 公式解析链路

“解析所选”和“解析全文”把带明确 LaTeX 定界符的普通文本转换为现有 LaTeXSnipper 托管公式。解析结果不使用新的元数据格式，后续可继续加载、编辑、转换、格式化、编号和引用。

### 扫描范围与定界符

- 识别 `$...$`、`\(...\)`、`$$...$$` 和 `\[...\]`，其中 `$$...$$` 优先于 `$...$`。
- `$...$` 与 `\(...\)` 生成无编号行内公式；`$$...$$` 与 `\[...\]` 生成行间公式。
- 只处理完整闭合且内容非空的公式；行内公式不能跨段落。未闭合、空内容或转换失败的源码原样保留。
- 定界符是否转义按其前方连续反斜杠数量判断；奇数表示转义，偶数表示有效定界符。`\$` 因此是普通美元符号。
- `\begin{...}...\end{...}` 只可作为定界符内部内容，不作为外层公式边界。
- 正文与每个表格单元格独立扫描，定界符不能跨越单元格或不安全区域闭合。
- “解析所选”要求完整起止定界符都位于非空选区中；部分选择和折叠光标不扩展扫描范围。
- “解析全文”只扫描主正文 story 及其中的表格，不扫描页眉、页脚、脚注、尾注、批注或文本框。

扫描时会把已有 LaTeXSnipper 公式、Word 原生公式、字段、超链接、content control、公式引用、编号边界及受保护内容作为硬边界。解析不会进入这些对象，也不会利用定界符外的 `(1)`、`（1）` 或 `[1]` 推断编号。

### 设置、编号与预处理

解析开始时只读取一次当前设置和状态窗格编号选项，整批公式使用同一快照：

1. 插入后端决定生成 Word OMML 还是 OLE。
2. 默认字体和颜色写入完整 LaTeX 源码，缩放倍率写入既有 `FontScale` 字段。
3. 行内公式始终无编号。
4. 行间公式存在唯一、顶层、非注释且非转义的 `\tag{...}` 时，预处理先移除该命令，并把非空 tag 文本写入既有手动编号字段。这一优先级高于状态窗格编号选项，MathJax 不负责排版编号。
5. 不含有效 `\tag` 的行间公式遵循状态窗格当前的自动编号或自定义编号选项；解析本身不执行全文重编号。

空 `\tag{}`、重复顶层 `\tag`、未闭合 tag、`\tag*`、嵌套分组中的 `\tag`，以及行内公式中的顶层 `\tag` 均视为当前公式解析失败。注释或转义的 `\tag` 保留在公式源码中但不作为插件编号；`\label`、`\ref` 和 `\eqref` 不参与插件编号或引用推断。

### 批处理、状态与重试

候选公式按文档位置倒序、每 5 个一批处理，每批使用短 Word undo record 并更新一次进度。单个公式准备或替换失败时保留原文并继续：无失败时最终只显示成功解析数量，有失败时显示处理总数、成功数和失败数；未发现候选时单独提示“未找到可解析的公式”。

命令取消或超时后，已经完成的批次仍是正常托管公式，未处理的定界文本保持原样。再次执行解析即可继续；扫描器会跳过已生成的托管公式，因此不会重复转换。

## Word 格式化链路

### 格式化所选

格式化所选会按当前设置重写选中公式的 LaTeX 源码：

1. 移除已有颜色包装。
2. 移除顶层字体包装。
3. 按当前设置重新包裹字体宏。
4. 按当前设置重新添加颜色宏。
5. 更新 `FontScale`。
6. 按公式当前渲染引擎重新渲染并替换。

多行环境和 `\displaylines` 按顶层段落或对齐段落包装。

多选格式化所选同样只使用稳定快照，不跨批持有 live COM object。涉及对象替换的 Word/PowerPoint 公式按倒序分批处理；每批更新一次状态窗格进度，避免 UI 更新本身成为瓶颈。Word 每批使用短 undo record。

行内基线修正只扫描当前段落内的 content control 和 inline shape。

### 格式化全文

格式化全文只恢复被用户手动改过尺寸的公式：

- OMML 恢复自然字号。
- OLE / PowerPoint shape 恢复自然宽高。

它不会批量改写所有 LaTeX 源码，避免误改用户手写字体、颜色或复杂宏。

## PowerPoint 插入、加载、删除、转换、格式化

PowerPoint 没有 Word 编号和引用链路，公式对象是 shape：

- 插入公式：打开编辑器，提交新公式时把默认设置写入完整 LaTeX 源码，再按设置插入 PNG 或 OLE；更新已有公式时保留编辑器提交的完整源码。
- 从侧边栏插入：读取侧边栏当前 LaTeX，作为新公式插入时应用默认源码格式。
- 加载所选：只读取选中 shape 的完整 LaTeX 元数据。
- 删除所选：删除选中的托管公式 shape；PNG 公式会清理插件临时图片文件。
- OLE/PNG 转换：读取完整 LaTeX，切换 render engine，删除原 shape 后在原 slide、原位置按原 scale 插入。
- 格式化所选：按当前设置重写 LaTeX 源码并恢复 scale。
- 格式化全文：仅恢复所有托管公式 shape 的自然宽高。

PowerPoint 编辑器固定白底黑字，因为 PowerPoint 编辑画布背景板固定为白色。Word 编辑器按系统深色模式适配。

## 链路复杂度核对

| 链路 | 当前复杂度 | 说明 |
| --- | --- | --- |
| Word 新插入 OLE | 中 | LaTeX 源码应用默认格式，MathJax SVG 渲染，SVG 转 EMF，插入 OLE 并写元数据 |
| Word 新插入 OMML | 中 | LaTeX 源码应用默认格式，MathJax 转 MathML，MathML 转 OMML，插入 content control 并写元数据 |
| 托管 OMML 转 OLE | 中 | 读取托管 LaTeX 元数据，改渲染引擎，重渲染为 OLE |
| Word 原生 OMML 转 OLE | 高 | 提取 Word 原生 OMML，转 MathML，把 MathML 作为源码保存，再生成 OLE；不参与 LaTeX 格式化 |
| OLE 转 OMML | 高 | 读取 LaTeX 或 MathML 源码，MathJax 输出 MathML，再由 Word OMML 转换器生成 content control |
| Word 编号公式 | 高 | 公式对象、tab stop、SEQ 字段、编号范围书签和文档变量必须一起维护 |
| Word 重编号 | 中 | 一次扫描公式、章/节边界和字段；异常公式跳过，引用字段只更新 LaTeXSnipper REF |
| Word 引用 | 中 | 占位符、目标公式选择、书签和 REF 字段组合；稳定入口是公式或公式所在段落 |
| 批量转换所选 | 高 | 稳定快照、倒序分批、每批短 undo；主要耗时仍是 MathJax 渲染和 Office COM 替换 |
| Word 公式解析 | 高 | 安全范围扫描、tag 预处理、MathJax/OMML 或 OLE 渲染、倒序分批替换及失败续跑 |
| 格式化所选 | 中 | 仅适合 LaTeX 源码公式；会重写顶层字体和颜色宏并重新渲染；多选时分批处理 |
| 格式化全文 | 低 | 只恢复自然字号或自然尺寸，不批量改写源码 |
| PowerPoint OLE/PNG | 中 | shape 元数据、自然尺寸、渲染引擎切换和位置缩放维护；多选转换和格式化按批处理 |

## 当前性能策略

- 重编号：`document.Fields` 只扫描一次并建立 `EquationId -> SEQ Field` 映射；字段匹配以书签范围和字段结果范围相交为准；引用更新只处理 LaTeXSnipper REF 字段，不调用全文 `document.Fields.Update()`。
- 重编号容错：元数据、编号书签或 SEQ 字段缺失的异常公式会被跳过并计数，剩余公式继续重编号。
- 添加编号/插入编号公式：编号状态计算优先按当前位置前的对象构建时间线，减少不必要的元数据读取。
- 格式化所选行内基线：只扫描当前段落对象，避免大文档中选一个公式也遍历全文。
- 批量转换和批量格式化所选：只收集稳定快照；不跨批持有 live COM object；按 5 个公式一批处理；转换和涉及替换的格式化按倒序执行；每批更新一次状态窗格；Word 每批使用短 undo record 和短屏幕刷新暂停区间。
- 公式解析：先收集仅包含位置、原文、LaTeX 和显示模式的稳定候选；按文档位置倒序、每 5 个一批准备和替换；不跨批持有 live COM object；失败项保留原文并允许下次续跑。

## OLE payload

OLE 对象创建前，插件把 `FormulaMetadata` 和 `OlePresentationResult` 序列化到 pending payload。payload 包含：

- 完整 LaTeX。
- display / numbering / render engine。
- fontScale。
- MathJax renderer version。
- presentation 宽高、基线、MIME 和 base64 payload。

payload 不包含独立的字体或颜色字段。OLE 控件读取后得到的是完整 LaTeX 源码。

## 字体方框修正边界

MathJax 3.2.2 的 SVG 对部分数学字母会输出 `<text data-variant="...">`，例如 `\mathbb` 的小写字母和数字。插入 Office 时插件会把 SVG 转为 EMF/PNG，因此这些 `<text>` 节点不能落到普通系统 UI 字体。

当前 SVG 文本绘制规则：

- 带 `data-variant` 的数学文本优先使用 `Cambria Math` 和 `Segoe UI Symbol`。
- 普通文本仍使用中文/UI 字体顺序。
- 路径字形仍按 MathJax SVG path/use 直接绘制。

这解决了浏览器预览正常但插入后数学字符变方框的问题。

## Undo 与外部传递

Word 插入、更新、删除、编号、解析、转换和格式化都在必要位置使用 Word undo record。用户撤销后，Word 会同时回撤对象、字段和文档变量的变化。

文档发给其他用户再返回时，插件能否加载取决于 Office 是否保留：

- Word content control `Tag` 或 OLE inline shape `AlternativeText`。
- Word `Document.Variables`。
- PowerPoint shape tags。
- OLE 对象本身或 PNG shape。

这些都是 Office 文档内的原生持久化载体，不依赖本机临时内存。PowerPoint PNG 的临时图片路径只用于本机清理文件，不影响公式元数据加载。

## 当前明确边界

- 不从编号数字反向删除公式。
- 不把默认字体/颜色作为编辑器打开时的临时样式。
- 不在加载所选时改写侧边栏用户草稿以外的持久源码。
- 不在格式化全文时批量重写所有公式源码。
- 不把解析与全文重编号耦合；解析后的全局序号校正仍由用户显式执行“重编号”。
- 不扫描非主正文 story，也不跨已有公式、字段、受保护对象或表格单元格边界配对定界符。
