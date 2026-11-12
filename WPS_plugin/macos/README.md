# macOS 平台适配

macOS 采用目标 WPS 发行版公开支持的客户端扩展入口。Mac 目录管理加载、安装与卸载、宿主权限和本机桥接，并复用 [WPS 公共目录](../shared/README.md) 的编辑器与文档工作流。

WPS 的[客户端开发概述](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/wps-integration-mode/wps-client-dev-introduction)列出了 macOS，[JS 加载项概述](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/wps-integration-mode/wps-addin-development/addin-overview)的适配说明列出 Windows 和 Linux。Mac 的加载入口、可调用的宿主接口以及支持的发行版需要实机确认。

- 在目标 WPS for Mac 版本验证能安装并加载文字、演示插件，显示功能区和任务窗格，并操作当前文档及选区。
- 验证文字 OMML、域及文档变量和演示 PNG／SVG 及形状标签能原位更新并保存重开。通过受支持的宿主接口适配平台差异，复用同一套元数据和编辑流程。
- 按 [验收要求](../README.md#验收与贡献) 验证 Windows Microsoft Office 与 WPS for Mac 的文档往返。记录 WPS 版本、系统版本和实际可用的加载方式。
