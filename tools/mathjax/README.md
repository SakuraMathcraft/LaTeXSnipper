# 共享 MathJax 运行时

客户端与 Office 插件统一使用 MathJax **4.1.3**。当前 Office 插件的公式链路与样式边界见[公式工作流文档](../../docs/office_plugin_formula_workflows.md)。

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

## 验证入口

先使用开发者选定的 Python 环境，从仓库根目录运行：

```powershell
python -X utf8 tools/mathjax/prepare.py --verify
python -X utf8 -m pytest test/test_mathjax_runtime.py test/test_formula_export_matrix.py test/test_formula_omml_export.py test/test_content_preview.py test/test_handwriting_preview.py test/test_pandoc_export_formats.py -q
python -X utf8 tools/mathjax/smoke_qt.py --cdn
dotnet test office_plugin/LaTeXSnipper.OfficePlugin.slnx -c Release
```

Qt 验证省略 `--cdn` 时只验证离线链路；CDN 验证需要网络，WebEngine 子进程必须允许运行。

Office 实际渲染与文档往返使用 `office_plugin/tools/Test-OfficeTypographyE2E.ps1`，覆盖 Word OMML/OLE、PowerPoint 文本内原生公式、OLE/PNG 对象和批处理。先构建插件，再按 [Office 插件说明](../../office_plugin/README.md) 选择宿主与测试范围。浏览器编辑器另有 [共享编辑器回归](../office-editor/README.md)，使用模拟桥接，不能替代真实 Office 验证。

## 工具与发布边界

`tools/mathjax` 是固定资源清单、可复现生成脚本和回归入口，不进入用户运行环境。Python 维护命令使用开发者选定的环境；桌面发布包运行时由 GitHub Actions 准备，Office 发布安装包在本地构建。
