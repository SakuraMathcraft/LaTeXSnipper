# PowerPoint 文档往返验收

启动独立的真实 PowerPoint 实例，在两页中插入 PNG 公式，通过正式适配器和控制器验证：

- 完整字体快照、中文和复杂多行源码往返；
- 选中加载与修改源码后，原位置和用户手动缩放保持；
- 全文格式化应用当前默认快照、恢复自然尺寸；重复格式化稳定；
- 文本光标处插入原生公式，包括中文；选中已有公式时可以新建其他公式；
- 多选格式化、转换和全文格式化的单项失败续跑、错误信息与重试；
- OLE 跨演示文稿复制、来源关闭、同页副本独立编辑与固定演示文稿目标保存；
- `-IncludeMathType` 验证从工作线程双向转换原生 MathType、多选单项失败续跑和重试、分式/中文、根式/矩阵/分段/对齐、颜色/字号、用户拉伸尺寸、层次、剪贴板、取消和跨演示文稿复制；核心验收不激活 MathType 或加载 SDK；
- 保存 PPTX、关闭并重新打开后，源码、身份、样式、页码与位置一致。

测试使用独立渲染实例，不修改用户设置；格式化读取当前设置。完整测试包含选中对象后再次插入 OLE，不能作为纯 PNG 测试运行。`--ole` 还验证 PNG/OLE 双向转换、OLE 激活、重新编辑与保存重开；`--copy` 只验证 OLE 复制、独立编辑与保存重开；`--batch` 只验证 PNG 批处理，不依赖 OLE handler。

先关闭 PowerPoint，输出路径必须尚不存在：

```powershell
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint
# 只检查 OLE 复制往返：
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode Copy
# 检查 MathType 批量转换与 OLE 复制：
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode Copy -IncludeMathType
# 只检查 MathType 双向转换：
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode MathType
# 额外打开已安装的 MathType 编辑服务器，修改内容后再导入：
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode MathType -PowerPointMathTypeNativeEdit
# 交互式双击验收：出现 READY 后在 90 秒内双击第一页公式，验证正式回调加载命中的对象：
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode Gesture
# 只检查批处理：
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode Batch
```

先构建 Release 版本；需要 Windows、PowerPoint、WebView2 和所需系统字体。统一脚本使用唯一的临时输出目录，并为完整测试临时注册 OLE handler；详细要求见 [插件说明](../../README.md)。完整测试保存的 PPTX 可用于人工复核；批处理模式不保存 PPTX，临时 PNG 在测试结束时清理。

核心 MathType 验收通过修改保存文件中的原生内容，确认“转为 OLE”读取当前 MathML 与字号。可选原生编辑验收需要安装 MathType，并通过其实际编辑服务器修改同一对象；SDK 辅助代码只编译进测试程序。
