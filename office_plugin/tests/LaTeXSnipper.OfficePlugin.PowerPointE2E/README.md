# PowerPoint 文档往返验收

启动独立的真实 PowerPoint 实例，在两页中插入 PNG 公式，通过正式适配器和控制器验证：

- 完整字体快照、中文和复杂多行源码往返；
- 选中加载与修改源码后，原位置和用户手动缩放保持；
- 全文格式化应用当前默认快照、恢复自然尺寸；重复格式化稳定；
- 保存 PPTX、关闭并重新打开后，源码、身份、样式、页码与位置一致。

测试使用独立渲染实例，不修改用户设置或 COM 注册；格式化读取当前设置。默认验证 PNG；可加 `--ole` 验证 PNG/OLE 双向转换、OLE 激活、重新编辑与保存重开，需要预先注册匹配的 schema 3 handler。

先关闭 PowerPoint，输出路径必须尚不存在：

```powershell
dotnet run --project office_plugin/tests/LaTeXSnipper.OfficePlugin.PowerPointE2E -- "$env:TEMP/latexsnipper-ppt-$([Guid]::NewGuid().ToString('N')).pptx"
```

测试保存的 PPTX 可用于人工复核；临时 PNG 在测试结束时清理。需要 Windows、PowerPoint、WebView2 和字体回归所需的系统字体。
