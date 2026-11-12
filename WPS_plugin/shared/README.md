# WPS 公共模块

本目录承载 Windows 和 macOS 共用的 WPS 插件实现。文字和演示各自封装宿主文档操作，共用公式编辑会话、元数据、OCR 请求流程和往返测试样本。平台加载、安装和本机桥接归入对应系统目录。

编辑器、符号模板和 MathJax 排版适配器的源码位于 [Office 插件公共资源](../../office_plugin/shared/)，由 WPS 插件构建时引用。公式数据按 [现有 Office 文档契约](../../docs/office_plugin_formula_workflows.md) 读写。
