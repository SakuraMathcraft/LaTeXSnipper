# 共享 MathJax 运行时

客户端与 Office 插件统一使用 MathJax **4.1.3**。这是第一阶段运行时更新；插件字体、字号、最终预览、源码编辑器和预设系统仍按重构方案进入下一阶段。

## 维护入口

- `manifest.json`：唯一手工维护的依赖版本、npm 压缩包 SHA-512、扩展列表、默认字体与资源选择规则。
- `prepare.py`：校验并提取官方 npm 包，生成 `config.js`、`resources.json` 和 `office.props`；支持离线验证，不在普通构建时下载资源。
- `src/assets/MathJax/runtime.js`：共享配置、Promise 转换、串行转换队列、宿主请求结果及取消管理。
- `src/assets/MathJax/office.js`：Office 输入处理；客户端导出不使用此适配器。
- `src/rendering/mathjax_runtime.py`：Python HTML 加载器。CDN 主地址与后备地址及字体均固定同一版本。
- `office.props`：由清单生成的 MSBuild Office 资源项，安装资源脚本使用相同 `resources.json` 清单。
- `probe.cjs`、`liteDOM.js`、`smoke_qt.py`：开发测试工具，不进入应用资源包。`liteDOM.js` 来自同一官方 MathJax 包，受资源包许可证约束。

默认字体保持 TeX，另含 STIX2；保留原有 27 项 TeX 扩展配置。升级前客户端与插件均已使用 `mhchem`，4.1.3 配套化学字体扩展用于延续这项能力。采用官方模块入口 `startup.js`，不修改上游渲染器、不携带 NewCM、语音引擎或重复的组合入口。

客户端资源约 **6.77 MiB**，含 CHTML、SVG、MathML 及对应字体；Office 资源约 **5.40 MiB**，含 SVG、MathML，不含 CHTML/WOFF。两个安装包各自自足。客户端各平台 PyInstaller 配置均收集 `src/assets`，因此使用同一裁剪资源集合；Office 通过清单取所需子集。

## 重建与校验

从 npm 获取清单指定的四个精确版本包（`mathjax`、`@mathjax/mathjax-tex-font`、`@mathjax/mathjax-stix2-font`、`@mathjax/mathjax-mhchem-font-extension`，均为 4.1.3），将 `.tgz` 放入临时目录，然后执行：

```powershell
python -X utf8 .\tools\mathjax\prepare.py --archives <压缩包目录>
python -X utf8 .\tools\mathjax\prepare.py --verify
```

升级时修改清单及完整性校验值，再重建生成文件。验证会拒绝清单漂移、被修改的上游文件和多余资源；有意移除的旧资源须同步删除，不保留版本回退目录。Git 属性保留上游文件和生成清单的字节，避免 Windows 换行转换破坏校验。

## 第一阶段验证记录（2026-09-12）

- Python 导出、源码保留、加载配置和资源测试：34 项通过。
- Ruff：本次修改的 Python 文件通过。
- Office Rendering：.NET Framework 4.8 与 .NET 9 编译通过；Word/PowerPoint 主机由已有测试项目一并编译。
- Office 元数据安全测试：14 项通过。
- Qt WebEngine：3 个真实 SVG/MathML 转换、6 个 CHTML 页面通过，包含本地 TeX/STIX2、客户端预览和 CDN HTML 独立页。
- WebView2：5 组真实 SVG、MathML、EMF 转换通过，包含多行中文、化学公式、正体宏、Office 输入处理和 MathML；缓存、Promise 延迟结果与取消请求通过。
- 安装资源暂存：Office 86 个文件与清单逐文件一致。

复验入口：

```powershell
python -X utf8 -m pytest test/test_mathjax_runtime.py test/test_formula_export_matrix.py test/test_formula_omml_export.py test/test_content_preview.py test/test_handwriting_preview.py test/test_pandoc_export_formats.py -q
python -X utf8 tools/mathjax/smoke_qt.py --cdn
dotnet run --project office_plugin/tests/LaTeXSnipper.OfficePlugin.Rendering.Smoke
dotnet run --project office_plugin/tests/LaTeXSnipper.OfficePlugin.Rendering.Smoke -- --typography
dotnet test office_plugin/tests/LaTeXSnipper.OfficePlugin.MetadataSafety.Tests
```

真实浏览器测试需允许 WebEngine/WebView2 子进程；`--cdn` 还需网络。单独运行 Qt 验证时省略此参数即可只验证离线链路。

`--typography` 直接回归共享字体渲染服务，要求 Windows 已安装 Times New Roman、宋体、微软雅黑及 Office 的 MathML→OMML 转换资源。它在真实 WebView2 中验证两套数学字体、局部样式、混排与布局，检查 SVG / EMF 轮廓、不同 DPI 的 PNG、缓存和 OMML 属性映射；当前 61 组矢量样例与 122 个 PNG 通过。支持范围与下一阶段边界见[重构方案第 11.6 节](../../docs/office_plugin_typography_refactor.md#116-第-3-步实施记录2026-09-13)。

以上第一阶段记录仅对应运行时升级。后续插件字体重构已接入 schema 3、统一字体渲染和绝对字号；当前实现、宿主验证结果与剩余验收项以[重构方案第 11 节](../../docs/office_plugin_typography_refactor.md#11-按顺序落地与验收)为准。正式发行包与安装验收另行执行。

## tools 目录的用途

- `tools/mathjax` 是长期维护工具：固定资源清单、可复现的生成脚本和被测试直接引用的回归入口；不属于应用运行环境，也不是一次性试验目录。此前直接复制整套 MathJax 3 资源，不需要此处的裁剪与校验工具。
- Python 维护命令使用开发者自行选择的环境；发布包运行时由 GitHub Actions 准备。
- 本次验证曾在 `tools/deps/nuget` 下载 .NET 构建包，属于可重建缓存，不是新增运行依赖；收尾时已删除。后续正常 `dotnet restore` 使用开发者原有 NuGet 配置和缓存。
