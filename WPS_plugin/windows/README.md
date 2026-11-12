# Windows 平台适配

使用 WPS 官方的 JS 加载项与发布机制。Windows 目录管理加载入口、安装及卸载、平台相关的本机调用和实机验证。文字与演示共用的代码放在 [WPS 公共目录](../shared/README.md)。

- 在目标 WPS 发行版验证加载项安装、功能区、任务窗格和卸载。
- 文字验证 `OMaths.Add`、文档变量、内容控件、书签和域能按现有文档契约保存。演示验证形状标签、图片类型、位置和层次在保存后保留。
- 用现有 Windows Microsoft Office 插件生成的样本完成 [往返验收](../README.md#验收与贡献)。

参考 [WPS 加载项开发与部署](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/wps-integration-mode/wps-addin-development/wps-addin-development-instructions)、[文字公式接口](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wps/OMaths/member/Add) 和 [演示形状接口](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wpp/Shapes/obj)。
