# Word 公式解析端到端测试

该测试启动真实 Microsoft Word，生成包含正文、真实表格、相邻定界符、复杂 LaTeX、非法 `\tag`、未闭合源码和不安全区域的文档，然后调用插件正式控制器完成解析。

测试分别覆盖 OMML 和 OLE 后端，并验证：

- 37 个初始候选中，33 个成功转换，4 个非法 `\tag` 原文保留；
- 首批 5 个处理后模拟超时，第二次解析可继续完成；
- 第三次解析只再次统计 4 个确定失败项，不重复转换已有公式；
- 表格单元格独立扫描，未闭合定界符不跨单元格；
- 相邻 `$q$$\dot q$$\ddot q$` 全部转换；
- `\(`、`\[` 前导反斜杠奇偶性、内部类似定界符、孤立结束符和文档首尾边界；
- 完整、部分及折叠选择范围，以及页眉等非主正文 story 的隔离；
- 合法 `\tag { 7 }`、公式开头 `\tag{8}` 和注释中的 `\tag` 词法边界；
- ContentControl、字段、超链接和 Word 原生公式保持不变；
- `\tag{5}`、`\tag{EL-field}` 和 `\tag{T-3}` 写入现有手动编号元数据，渲染源码不保留 `\tag`；
- 生成公式由 schema 3 元数据加载，并使用所选 OMML/OLE 渲染引擎；
- 全文格式化为粗斜体、15.5 pt 后，所有公式保存相同的完整样式快照，源码和公式身份不变；
- 带标签、表格内、行内、独行与手动编号公式可重复处理，保存并重新打开后继续验证文档结构和样式快照。
- OLE 复制到新文档、关闭来源、同文档副本独立身份与编辑、切换活动文档后的固定目标保存；
- `-IncludeMathType` 验证 Word 的直接 MTEF/CFB 转换、分式、中文、上下标、根式、矩阵、积分、颜色、粗体、预览与保存重开，不激活 MathType；
- OLE 后端额外验证行内与手动编号公式的 OMML/OLE 双向转换、原生激活和重新编辑，检查源码、完整样式、身份和编号保持。

运行前必须关闭所有 Word 窗口，且测试完成前不要再次启动 Word，以确保测试实例与日常文档隔离：

```powershell
.\office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope Word
```

先构建 Release 版本；统一脚本默认使用 Release，可通过 `-Configuration Debug` 改变。通过后，临时输出目录会生成 OMML/OLE 两份 DOCX、Word 导出的同名 PDF 和日志；可通过 `-OutputDirectory` 指定位置。只测原生公式时使用 `-WordBackend Omml`，不涉及 OLE 注册。

仅运行 Word MathType 核心转换验收：

```powershell
.\office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope Word -WordBackend Ole -WordMathTypeOnly
```

核心验收覆盖红色 Euler 和用户报告的红色 cases、WMF 实际绘制非空、对象数量及保存重开尺寸、混合选择和首项失败续跑、两个相同公式仅转换一个、保留用户缩放、正文/表格文字和段落结构、批量取消后重试、关闭来源后的跨文档复制。核心测试不因没有 MathType 而跳过。

追加 `-WordMathTypeNativeEdit` 才启用需要安装 MathType 的独立验收：实际原生服务器读取生成的每个对象，修改内容，再通过不激活 MathType 的正式反向入口读取最新内容。SDK MathML 导出器可能省略颜色，因此颜色以持久化 MTEF 和可见预览验证，不能只依据 SDK 返回的 MathML。尚未完成未安装 MathType 的隔离环境验证。
