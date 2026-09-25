# Office 插件公式链路与元数据边界

本文记录 schema 3 的 Office 插件公式链路。公式内容与显式局部样式来自 `Latex`，公式默认样式与绝对字号来自不可变的 `Typography` 快照。

## 当前源码与样式边界

- 新建和格式化从当前设置产生样式快照；普通编辑、重编号及转换保留公式已有快照。
- 局部字体与颜色命令优先于默认样式。默认样式在 MathJax 解析后、布局前应用。
- Word OLE、PPT OLE / PNG 使用同一 SVG 轮廓；OMML 复用带样式 MathML，再映射 Word 属性，最终排版由 Word 管理。
- MathLive 目前仍是编辑参考。三类字体的完整设置面板、最终效果预览与预设功能按重构方案后续阶段实施。

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
| `Typography` | 符号字体、数字字体、汉字字体、数学样式、绝对 pt 字号、颜色与样式版本 |

`Typography` 保存完整快照；文档重绘不依赖本机预设。只读取 schema 3，损坏或不支持的版本在入口拒绝，不迁移或删除原对象。

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

OMML 的自然字号直接取 `Typography.FontSizePoints`，不另建文档变量。

## PowerPoint 元数据存储

PowerPoint 公式以 shape 为单位保存元数据。短字段写入 shape tags：

| Tag | 用途 |
| --- | --- |
| `LaTeXSnipperDocumentId` | 当前演示文稿标识 |
| `LaTeXSnipperEquationId` | 公式 ID |
| `LaTeXSnipperDisplayMode` | 显示模式 |
| `LaTeXSnipperSchemaVersion` | schema |
| `LaTeXSnipperRenderEngine` | 渲染类型 |
| `LaTeXSnipperNaturalWidthPoints` | 自然宽度 |
| `LaTeXSnipperNaturalHeightPoints` | 自然高度 |
| `LaTeXSnipperImagePath` | PNG 插入时的临时图片路径 |

完整 LaTeX 源码使用 UTF-8 转十六进制后分块存储：

| Tag | 用途 |
| --- | --- |
| `LaTeXSnipperLatexBytes` | 原始 UTF-8 字节数 |
| `LaTeXSnipperLatexChunks` | 分块数量 |
| `LaTeXSnipperLatex0000` 起 | 十六进制源码分块 |

每块长度为 200 个十六进制字符，并校验字节数、分块数量和十六进制解析结果。样式 JSON 使用同一编码与分块实现，前缀为 `LaTeXSnipperTypography`，保存 `Bytes`、`Chunks` 和 `0000` 起的分块。这样同时保留长源码、中文字体名称和字体名称的大小写。

## 设置项影响边界

### Word 设置

| 设置项 | 影响链路 | 不影响链路 |
| --- | --- | --- |
| 插入后端：OLE / Word OMML | 新插入公式、公式解析、更新公式、转换目标渲染引擎 | 加载所选、删除所选、引用字段 |
| 公式默认颜色 | 新插入公式、公式解析、格式化所选 / 全文 | 加载所选、普通更新、重编号、引用 |
| 公式默认字体 | 新插入公式、公式解析、格式化所选 / 全文 | 加载所选、普通更新、重编号、引用 |
| 绝对字号与跟随文字字号 | 新建和解析时解析有效文字字号；格式化使用设置的固定字号 | 加载、普通更新、重编号与转换不重新跟随光标 |
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
| 公式默认颜色 | 新插入公式、格式化所选 / 全文 | 加载所选、普通更新、转换 |
| 公式默认字体 | 新插入公式、格式化所选 / 全文 | 加载所选、普通更新、转换 |
| 绝对字号与跟随文字字号 | 新建时解析有效文字选区，否则使用配置的后备字号 | 普通更新与转换保留快照 |

PowerPoint 没有 Word 编号、引用、章/节分隔符链路。

## Word 插入链路

### 插入行内公式

1. Ribbon 调用 `InsertInlineAsync`。
2. 打开 MathLive 编辑器，初始源码为空，显示模式为 `Inline`，不把默认字体/颜色写入编辑器草稿。
3. 用户提交后，`CreateMetadataFromOptions` 读取当前设置。
4. 解析新建字号上下文并生成完整 `Typography` 快照。
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
- 同时恢复完整 `Typography` 快照，普通更新沿用该快照。
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
4. MathJax 4.1.3 生成 SVG。
5. SVG 转 EMF presentation。
6. 用 OLE 对象替换原公式，并保存同一份完整 LaTeX 元数据。

#### Word 原生 OMML 公式转 OLE

1. 加载选区内未被 LaTeXSnipper content control 托管的 Word 原生 `OMath`。
2. 读取 Word 原生 OMML OOXML。
3. 使用 `OmmlToMathMlConverter` 把 OMML 转为 MathML。
4. 创建新的 `FormulaMetadata`，把 MathML 字符串存入 `Latex` 字段，并把 `RenderEngine` 设为 `MathJaxSvg`。
5. MathJax 4.1.3 按 MathML 输入渲染 SVG。
6. SVG 转 EMF presentation。
7. 删除原 Word 原生公式，在原位置插入 LaTeXSnipper OLE 对象。

这条链路把 MathML 保存为公式源码，并写入新的样式快照。转换完成后按托管公式处理；共享渲染器识别 MathML 输入，格式化同样应用样式快照。

### OLE 转 OMML

1. 读取 OLE 元数据中的完整 LaTeX。
2. MathJax 4.1.3 转 MathML。
3. `MathMlToOmmlConverter` 转 OMML。
4. 用 Word content control 替换 OLE 对象。
5. 恢复公式 ID、编号状态、字号和元数据。

转换只处理当前选区内的公式，不扫描全文。多选转换入口只收集 `EquationId`、起始位置、渲染类型和必要元数据快照，不跨批持有 `ContentControl`、`InlineShape` 或 shape 这类 live COM object。转换按文档位置倒序分批执行，每批重新按稳定 ID 确认对象仍存在；找不到对象则计入跳过数量，剩余公式继续处理。Word 每批使用短 undo record，避免把大量对象包进一个超长事务。

`OMML 转 OLE` 命令会额外识别当前选区内的 Word 原生 OMML 公式，并按上面的 MathML 源码链路转换为 LaTeXSnipper OLE。该能力只属于显式转换入口。

## Word 公式解析链路

“解析所选”和“解析全文”把带明确 LaTeX 定界符的普通文本转换为现有 LaTeXSnipper 托管公式。解析结果使用统一的 schema 3，后续可继续加载、编辑、转换、格式化、编号和引用。

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
2. 默认字体、颜色和绝对字号写入 `Typography`；跟随字号时按候选公式所在文字范围解析。
3. 行内公式始终无编号。
4. 行间公式存在唯一、顶层、非注释且非转义的 `\tag{...}` 时，预处理先移除该命令，并把非空 tag 文本写入既有手动编号字段。这一优先级高于状态窗格编号选项，MathJax 不负责排版编号。
5. 不含有效 `\tag` 的行间公式遵循状态窗格当前的自动编号或自定义编号选项；解析本身不执行全文重编号。

空 `\tag{}`、重复顶层 `\tag`、未闭合 tag、`\tag*`、嵌套分组中的 `\tag`，以及行内公式中的顶层 `\tag` 均视为当前公式解析失败。注释或转义的 `\tag` 保留在公式源码中但不作为插件编号；`\label`、`\ref` 和 `\eqref` 不参与插件编号或引用推断。

### 批处理、状态与重试

候选公式按文档位置倒序、每 5 个一批处理，每批使用短 Word undo record 并更新一次进度。单个公式准备或替换失败时保留原文并继续：无失败时最终只显示成功解析数量，有失败时显示处理总数、成功数和失败数；未发现候选时单独提示“未找到可解析的公式”。

命令取消或超时后，已经完成的批次仍是正常托管公式，未处理的定界文本保持原样。再次执行解析即可继续；扫描器会跳过已生成的托管公式，因此不会重复转换。

## Word 格式化链路

“格式化所选”和“格式化全文”共用同一流程，区别仅在收集范围：

1. 获取公式及其完整元数据，比较当前默认样式与快照，并检查用户缩放。
2. 用当前默认样式生成新快照，保留源码、身份、编号和渲染类型。
3. OLE 经共享 SVG / EMF 重绘；OMML 经带样式 MathML 和 Word 属性映射重绘。
4. 主动格式化恢复自然尺寸。普通编辑保留用户缩放；缩放不写回样式字号。

对象替换按文档位置倒序、每 5 个一批处理；每批使用短 Word undo record 并更新进度。行内基线修正只扫描当前段落。未带插件元数据的原生 Word 公式仍通过独立的原生公式转换入口处理。

## PowerPoint 插入、加载、删除、转换、格式化

PowerPoint 没有 Word 编号和引用链路，公式对象是 shape：

- 新建保存源码与样式快照，按设置插入 PNG 或 OLE；普通更新使用已有快照。
- 加载从 shape 元数据恢复完整信息；删除同时清理对应 PNG 临时文件。
- OLE / PNG 转换保留源码、样式和原位置 / 用户缩放。
- 所选 / 全文格式化共用样式流程；全文遍历演示文稿各页的托管公式，恢复新的自然尺寸。

PowerPoint 编辑器固定白底黑字，Word 编辑器按系统深色模式适配。编辑参考与最终预览的进一步分工见字体重构方案。

## 链路复杂度核对

| 链路 | 当前复杂度 | 说明 |
| --- | --- | --- |
| Word 新插入 OLE | 中 | 源码与样式快照，MathJax SVG 渲染，SVG 转 EMF，插入 OLE 并写元数据 |
| Word 新插入 OMML | 中 | 源码与样式快照，MathJax 转 MathML，MathML 转 OMML，插入 content control 并写元数据 |
| 托管 OMML 转 OLE | 中 | 读取托管 LaTeX 元数据，改渲染引擎，重渲染为 OLE |
| Word 原生 OMML 转 OLE | 高 | 提取 Word 原生 OMML，转 MathML，把 MathML 作为源码保存，再生成 OLE；之后同样支持样式快照格式化 |
| OLE 转 OMML | 高 | 读取 LaTeX 或 MathML 源码，MathJax 输出 MathML，再由 Word OMML 转换器生成 content control |
| Word 编号公式 | 高 | 公式对象、tab stop、SEQ 字段、编号范围书签和文档变量必须一起维护 |
| Word 重编号 | 中 | 一次扫描公式、章/节边界和字段；异常公式跳过，引用字段只更新 LaTeXSnipper REF |
| Word 引用 | 中 | 占位符、目标公式选择、书签和 REF 字段组合；稳定入口是公式或公式所在段落 |
| 批量转换所选 | 高 | 稳定快照、倒序分批、每批短 undo；主要耗时仍是 MathJax 渲染和 Office COM 替换 |
| Word 公式解析 | 高 | 安全范围扫描、tag 预处理、MathJax/OMML 或 OLE 渲染、倒序分批替换及失败续跑 |
| 格式化所选 | 中 | 应用样式快照并重绘；多选时分批处理 |
| 格式化全文 | 中 | 复用所选格式化流程，范围为全部托管公式 |
| PowerPoint OLE/PNG | 中 | shape 元数据、自然尺寸、渲染引擎切换和位置缩放维护；多选转换和格式化按批处理 |

## 当前性能策略

- 重编号：`document.Fields` 只扫描一次并建立 `EquationId -> SEQ Field` 映射；字段匹配以书签范围和字段结果范围相交为准；引用更新只处理 LaTeXSnipper REF 字段，不调用全文 `document.Fields.Update()`。
- 重编号容错：元数据、编号书签或 SEQ 字段缺失的异常公式会被跳过并计数，剩余公式继续重编号。
- 添加编号/插入编号公式：编号状态计算优先按当前位置前的对象构建时间线，减少不必要的元数据读取。
- 格式化所选行内基线：只扫描当前段落对象，避免大文档中选一个公式也遍历全文。
- 批量转换和批量格式化所选：只收集稳定快照；不跨批持有 live COM object；按 5 个公式一批处理；转换和涉及替换的格式化按倒序执行；每批更新一次状态窗格；Word 每批使用短 undo record 和短屏幕刷新暂停区间。
- 公式解析：先收集包含位置、原文、LaTeX、显示模式和文字字号的稳定候选；按文档位置倒序、每 5 个一批准备和替换；不跨批持有 live COM object；失败项保留原文并允许下次续跑。

## OLE payload 与字体输出

pending payload 的 schema 为 3，包含源码、显示 / 编号 / 渲染类型、完整样式字段、运行时版本，以及 presentation 自然宽高、基线、MIME 与 base64 数据。`FormulaTypographyFields` 统一定义样式字段；OLE 使用平铺字段，Word JSON 使用 `typography` 对象，PPT 使用编码后的样式 JSON。

原生 handler 校验 schema 与样式版本、字体方案、数学样式、字号范围和呈现数据，原样保存 payload。身份仍由宿主对象与文档元数据管理，不写入 OLE payload。

MathJax 4.1.3 在排版前取得字形度量与轮廓。最终 SVG 不包含依赖字体的文本回退，EMF / PNG 复用同一几何。TeX 缺字统一尝试 STIX2 同样式数学字形补充；数字和中文系统字体返回实际解析与回退诊断。

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
