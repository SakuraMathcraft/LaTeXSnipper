# Office 插件编号公式迁移方案评估

## 结论

当前隐藏表格方案应废弃。它看似能把编号单元格做垂直居中，但在 Word 交互模型里副作用太多：

- 插入后的回车、继续输入、删除、选择会落在表格结构内，容易把后续内容吞进表格。
- 表格尾部、单元格尾标记和 ContentControl 的范围边界容易触发 COM 异常。
- 小型单行公式仍然不能稳定和编号视觉居中，因为 OLE 对象基线、表格行高、段落行盒三者仍然互相影响。
- 表格会暴露移动手柄、单元格边界行为和表格尾段落问题，即使隐藏边框也不是“不可见结构”。

下一版编号公式应迁移为 Word 论文写作中更标准的段落制表位结构：

```text
<TAB>公式对象<TAB>(编号域)
```

段落设置两个制表位：

- 中心制表位：页面正文宽度中心，用于公式居中。
- 右对齐制表位：右页边距，用于编号右对齐。

编号应从自管文本 ContentControl 迁移到 Word `SEQ` 域，引用迁移到 Word `REF`/书签机制。实现不保留旧表格或旧 ContentControl 编号文档的兼容逻辑。

## 成熟工作流对比

| 方案 | 成熟度 | 对齐能力 | 自动编号 | 交叉引用 | 编辑体验 | 主要问题 | 结论 |
|---|---:|---:|---:|---:|---:|---|---|
| 隐藏表格：左/中/右三列 | 中 | 中 | 可做 | 可做 | 差 | 表格尾段落、回车吞内容、单元格范围 COM 异常、移动手柄暴露 | 放弃 |
| 段落中心/右制表位 + 文本编号 | 高 | 高 | 插件自管 | 插件自管 | 好 | 编号不是 Word 原生域，引用/更新需要插件维护 | 只适合过渡，不采用 |
| 段落中心/右制表位 + `SEQ` 域 | 高 | 高 | Word 原生 | Word 原生 | 好 | 需要正确插入域、书签和更新域 | 推荐 |
| Word 内置 `#(编号)` 公式编号 | 高 | 高 | 弱/手动 | 弱 | 好 | 依赖 Word 公式编辑器行为，不适合 OLE SVG 公式统一管理 | 可参考，不作为插件主结构 |

参考依据：

- Microsoft 官方 Word field code 文档列出并支持域代码机制，包括 `SEQ` 这类编号域：[List of field codes in Word](https://support.microsoft.com/en-us/word/list-of-field-codes-in-word)
- Microsoft Q&A 中也明确 `SEQ` 属于 Insert Field 的 Numbering 类别，并需要 sequence identifier：[Inserting SEQ Field Codes](https://learn.microsoft.com/en-us/answers/questions/4876525/inserting-seq-field-codes)
- Waterloo 的 Word 公式编号教程使用“中心制表位 + 右对齐制表位 + sequence”的写作流程：[Creating, numbering and cross referencing equations with Microsoft Word](https://uwaterloo.ca/information-systems-technology/creating-numbering-and-cross-referencing-equations-microsoft)
- Word 用户社区长期推荐公式居中、编号右对齐用 center tab + right tab，而不是表格或空格：[How to add a tab stop in Word with a center and right alignment?](https://superuser.com/questions/1137089/how-to-add-a-tab-stop-in-word-with-a-center-and-right-alignment)

## 推荐目标结构

### 段落布局

编号公式是一个普通段落，不是表格：

```text
\t[LaTeXSnipper 公式对象]\t([SEQ 域结果])
```

段落格式：

- `ParagraphFormat.Alignment = wdAlignParagraphLeft`
- 清空原有 TabStops
- `TabStops.Add(center, wdAlignTabCenter, wdTabLeaderSpaces)`
- `TabStops.Add(right, wdAlignTabRight, wdTabLeaderSpaces)`
- `SpaceBefore = 0`
- `SpaceAfter = 0`
- `LineSpacingRule = Single`
- `DisableLineHeightGrid = true`

`center` 和 `right` 都从当前节的可用正文宽度计算：

```text
contentLeft = section.LeftMargin
contentWidth = pageWidth - leftMargin - rightMargin
center = contentWidth / 2
right = contentWidth
```

Word 的 TabStops 坐标通常相对段落左缩进/正文区域；实现时应以当前段落范围实测为准，不硬编码英寸值。

### 公式对象

OLE SVG 公式仍使用 InlineShape 插入到中心制表位后。小型单行公式编号不对齐的根因不是编号横向位置，而是 OLE inline shape 的基线和 Word 行盒不一致：

- 行间公式不应再调用 inline 公式的基线下沉逻辑。
- display/numbered 公式的 OLE `Range.Font.Position` 应为 `0`。
- 编号字段应按 OLE 对象实际高度上移到公式视觉中线：`(formulaHeight - baseFontSize) / 2`。
- 不再按 LaTeX 行数、多行环境或表格行高猜测偏移。

### 编号

编号域建议结构：

```text
(
  { SEQ LaTeXSnipperEquation \* Arabic }
)
```

如果设置启用章/节编号，章/节边界只作为插件公式编号的前缀来源；`NumberSeparator` 只决定公式编号字段文本中的层级分隔符。

### 引用

每个编号公式应给编号结果或整个编号括号建立书签，例如：

```text
_LaTeXSnipperEq_8F3A...
```

插入引用时使用：

```text
{ REF _LaTeXSnipperEq_8F3A... \h }
```

书签范围必须覆盖完整括号和内部字段，即完整 `(前缀 + SEQ)`。Word 自己灰显 `SEQ` 字段时可能只高亮字段结果数字，这不是插件范围；插件引用和重编号只认完整编号书签。

引用控件也应从 ContentControl 迁移为 Word 域。插件可保留命令入口，但不再维护一套自定义引用控件。

## 需要删除的旧逻辑

迁移实现时直接删除，不做兼容分支：

- 隐藏表格插入、规范化、删除、移动光标逻辑。
- 编号 ContentControl 插入与更新逻辑。
- 插件自管自动编号计数器作为编号来源的逻辑。
- 旧的编号段落/表格检测和“修复历史文档”逻辑。
- 按 LaTeX 行数、多行环境、表格行高估算编号垂直偏移的逻辑。
- 用 ContentControl 包装引用的逻辑。

保留：

- 公式对象身份元数据：仍需要识别 LaTeXSnipper 管理的 OLE/OMML 公式。
- 公式对象选择、加载、更新、删除命令。
- 渲染后尺寸和缩放元数据。

## 当前迁移进度

| 模块 | 状态 | 说明 |
|---|---:|---|
| 隐藏表格编号公式 | 已迁移 | 编号公式改为普通段落、中心制表位、右制表位。 |
| 编号 ContentControl | 已迁移 | 自动编号改为 `SEQ LaTeXSnipperEquation` 字段，手动编号是普通文本。 |
| 引用 ContentControl | 已迁移 | 引用改为 `REF _LaTeXSnipperEq_* \h` 字段。Word 字段灰显不等同于插件外框，不能再依赖旧控件边框判断范围。 |
| 完整编号书签 | 已迁移 | 自动编号的完整显示文本由单个 `SEQ` 字段结果生成，书签覆盖该字段结果，引用不再指向裸数字。 |
| 完整编号范围 | 已迁移 | 新编号不再用“普通文本前缀/外框 + SEQ 字段”的分裂结构；编号范围只来自当前字段结果书签。 |
| 删除所选 | 已迁移 | 可删除选中的公式、编号、章/节边界、`REF` 引用字段和待选择引用占位符。编号本身不是独立控件；选中编号会反查并删除整段编号公式。 |
| 引用目标选择 | 已迁移 | 插入引用后可选公式，也可选公式编号；选中编号会通过书签反查公式。 |
| 章/节分割符 | 已迁移 | 重编号按章/节边界生成前缀，并按设置的分割符写入编号字段前缀。 |
| 编号格式/外框设置 | 已迁移 | `NumberFormat` 写入 `SEQ` 域格式开关，`NumberEnclosure` 写入编号包裹符：`()`, `[]`, `{}` 或无外框。 |
| 插入自动编号公式 | 已迁移 | 插入时只生成当前公式的本地编号字段和前缀，不触发全篇重编号。 |
| OLE 编号中线 | 已迁移 | 编号字段按实际 OLE 高度上移到公式中线。 |
| Word 端视觉验收 | 待验证 | 需要在 Word 中覆盖单行小公式、单行高公式、多行公式、左右编号、章/节边界、引用删除。 |

## 迁移实施计划

### Phase 1：回退表格结构并建立新编号段落模型

1. 删除 `InsertNumberedFormulaTable`、`NormalizeNumberedFormulaTable`、`TryDeleteContainingTable`、`TryMoveSelectionAfterContainingTable` 等表格路径。
2. 新增 `InsertNumberedFormulaParagraph`：
   - 清理当前插入段落内容。
   - 设置两个制表位。
   - 插入第一个 tab。
   - 插入公式 InlineShape 或 OMML content control。
   - 插入第二个 tab。
   - 插入 SEQ 编号域。
3. numbered/display OLE 不再应用 inline baseline 下沉。
4. 插入完成后选择点移动到该段落之后的新普通段落。

### Phase 2：SEQ 域编号

1. 新增 `WordEquationNumberFieldBuilder`，只负责生成字段代码和插入字段。
2. 自动编号使用 `SEQ LaTeXSnipperEquation`。
3. 手动编号不再伪装为自动编号；如果用户输入手动编号，则插入普通文本编号，不参与 SEQ。
4. `RenumberAutomaticFormulasAsync` 改为更新域，而不是遍历 ContentControl 改文本。
5. 插入自动编号公式不调用全篇重编号；插入逻辑只根据插入点之前的章/节边界和已有自动公式生成当前公式字段。

### Phase 3：REF 引用

1. 给编号公式建立稳定书签。
2. 插入引用时插入 `REF bookmark \h` 域。
3. 删除引用 ContentControl。
4. “更新全部编号/引用”调用 Word 字段更新，而不是插件自算。

### Phase 4：测试约束

结构测试应明确禁止以下字符串重新出现：

- `Tables.Add`
- `NormalizeNumberedFormulaTable`
- `TryDeleteContainingTable`
- `TryMoveSelectionAfterContainingTable`
- `BuildNumberTag`
- `BuildNumberAlias`
- `InsertNumberControlAtRange`
- `ApplyNumberControlVerticalAlignment`
- `CalculateNumberVerticalOffset`
- `EstimateFormulaRows`

并要求存在：

- `SEQ LaTeXSnipperEquation`
- `Fields.Add`
- `TabStops.Add(center`
- `TabStops.Add(right`
- `Bookmarks.Add`
- `REF `

## 风险与处理

| 风险 | 处理 |
|---|---|
| Word 字段插入 API 比直接写文本更脆 | 封装到单一 `WordFieldInserter`，禁止业务代码直接拼 COM 调用 |
| 域更新可能不自动刷新显示 | 插入/重编号/引用命令结束时调用目标 Range 或 Document.Fields.Update |
| OLE 小公式仍有视觉基线差 | 编号字段按 OLE 实际高度对齐公式中线；SVG 自身留白仍应在渲染阶段收紧 |

## 推荐决策

采用：

```text
普通段落 + 中心制表位 + 右制表位 + SEQ 域 + REF 域
```

废弃：

```text
隐藏表格 + 编号 ContentControl + 插件自管编号文本
```

这条迁移路线更接近 Word 中成熟的公式编号工作流，也能避免表格结构带来的换行、选择、删除和范围边界问题。
