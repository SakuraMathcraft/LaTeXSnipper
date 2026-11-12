# Windows 平台适配

使用 WPS 官方的 JS 加载项与发布机制。Windows 目录管理加载入口、安装及卸载、平台相关的本机调用和实机验证。文字与演示共用的代码放在 [WPS 公共目录](../shared/README.md)。

- 在目标 WPS 发行版验证加载项安装、功能区、任务窗格和卸载。
- 文字通过 `InlineShapes.AddOLEObject` 创建行内 OLE，演示通过 `Shapes.AddOLEObject` 创建 OLE 形状。复用现有 LaTeXSnipper Windows OLE 组件和类标识，验证与目标 WPS 位数匹配。WPS 插件安装需能独立提供所需组件，并与现有 Office 插件共存。卸载时保留仍被其他插件使用的组件及注册项。
- 两个宿主都实现 OLE 插入、加载、双击编辑、删除、格式化和显式转换。实测 WPS 和 Microsoft Office 两边创建的 OLE 公式在另一方双击时都能进入各自插件的编辑器，并可修改、保存和重开。
- 文字验证 `OMaths.Add`、文档变量、内容控件、书签和域能按现有文档契约保存。演示验证形状标签、图片类型、位置和层次在保存后保留。
- 对照 Windows Office 插件逐项验证现有外部 OLE 公式格式转换，以及演示文本框内的原生公式插入。对实测支持的操作保留现有工作流，并记录有证据的宿主限制。
- 用现有 Windows Microsoft Office 插件生成的样本完成 [往返验收](../README.md#验收与贡献)。

参考 [WPS 加载项开发与部署](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/wps-integration-mode/wps-addin-development/wps-addin-development-instructions)、[文字 OLE 接口](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wps/InlineShapes/member/AddOLEObject)、[演示 OLE 接口](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wpp/Shapes/member/AddOLEObject) 和 [文字原生公式接口](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wps/OMaths/member/Add)。
