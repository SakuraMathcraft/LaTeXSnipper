# Windows 原生 Office 插件目标架构

`office_plugin` 是 LaTeXSnipper Office 集成的最终主线。目标是做成类似 MathType/AxMath 的 Windows 原生插件：安装后 Word 和 PowerPoint 持久显示 Ribbon，每个 LaTeXSnipper 公式都是可识别、可保存源数据、可双击打开编辑器的对象。

`office_addin` 暂时保留为迁移参考，迁移完成后删除。

## 产品目标

- 绑定 Windows 桌面版 Office，不再追求 Office.js 的 Web/Mac 覆盖。
- 原生 Ribbon 持久加载，不依赖 Microsoft 365 企业账号、Office 管理中心或 sideload manifest。
- 支持全局和 Office 内快捷键。
- Word 支持 OMML 公式和 LaTeXSnipper OLE 公式对象。
- PowerPoint 支持当前 OMML 图片插入和 LaTeXSnipper OLE 公式对象。
- 每个公式对象保存 LaTeX 源码、渲染参数、编号信息和 LaTeXSnipper 对象版本。
- 双击公式对象打开 LaTeXSnipper 编辑器，修改后原地更新。
- 本地 MathJax/MathLive/自绘渲染管线完全离线运行。

## 推荐技术路线

第一阶段优先使用 VSTO/C# 建立原生 Office 插件骨架；必要时用 COM/OLE 组件承载公式对象和自绘渲染。

| 层 | 建议 |
|---|---|
| Office 插件外壳 | VSTO Add-in for Word/PowerPoint |
| Ribbon | Ribbon XML，便于精确控制命令、图标和快捷键 |
| 公式对象 | LaTeXSnipper OLE/ActiveX 对象，支持嵌入、激活、双击编辑 |
| 编辑器 | WPF 或 WinUI 窗口；初期可复用本地 MathLive/WebView2，最终可替换为原生编辑器 |
| 渲染 | 本地 MathJax/MathLive 渲染服务 + 原生 GDI+/Direct2D/SVG/EMF 输出 |
| Bridge | 继续复用 LaTeXSnipper 桌面端本地服务，负责 OCR、转换和渲染 |
| 安装器 | Inno/MSI 写入 VSTO/COM/OLE 注册表，检测 Office 位数、VSTO Runtime、WebView2 Runtime |

裸 COM Add-in 控制力更强，但生命周期、异常隔离、注册和 Ribbon 维护成本更高。第一版建议先用 VSTO 收敛 Word/PPT 工作流，再把公式对象和渲染管线下沉为独立 COM/OLE 组件。

## 对象模型

### 统一公式身份

每个公式都有稳定 ID：

```text
latexsnipper:{document-id}:{equation-id}
```

对象内部保存：

- LaTeX 源码
- 显示模式
- 渲染后宽高
- 编号模式：无编号、自动编号、手动编号
- 编号值
- 渲染引擎：OMML、MathJax Native、图片兼容
- LaTeXSnipper 对象格式版本

这些数据必须随 Word/PPT 文档保存，不能依赖外部临时缓存。

### Word

Word 支持两条输出路径：

| 路径 | 用途 |
|---|---|
| OMML 原生公式 | 文档可编辑性优先，适合普通 Word 数学排版 |
| LaTeXSnipper OLE 公式对象 | 自绘效果、TeX 兼容性、双击编辑和 MathType 式体验优先 |

编号公式不再依赖 Office.js 的脆弱表格写入路径。最终可以由对象自身绘制编号区域，也可以由插件创建可控的 Word 布局容器，但公式身份必须绑定到单个 LaTeXSnipper 对象。

### PowerPoint

PowerPoint 支持两条输出路径：

| 路径 | 用途 |
|---|---|
| 图片插入 | 保留当前稳定行为，适合兼容导出和简单演示 |
| LaTeXSnipper OLE 公式对象 | 支持双击编辑、自绘渲染、源数据保存和精确缩放 |

自动编号不应使用全局递增缓存。若需要自动编号，必须扫描当前幻灯片/演示文稿中仍存在的 LaTeXSnipper 对象，按对象数据计算最大编号或重排编号。

## 渲染管线

```text
LaTeX source
  -> normalize
  -> render request
       -> OMML converter
       -> MathJax native renderer
       -> image/SVG/EMF renderer
  -> Office adapter
       -> Word OMML
       -> Word OLE object
       -> PowerPoint image
       -> PowerPoint OLE object
```

本地 MathJax 原生渲染管线的目标：

- 离线运行，不加载 CDN。
- 输出紧贴公式边界的位图/SVG/EMF。
- 支持对象 DPI、缩放、透明背景、深浅色策略。
- 与 OLE 对象自绘共享同一套布局结果。
- 渲染失败时返回明确错误，不生成不可编辑的半成品对象。

## 命令设计

| 命令 | Word | PowerPoint |
|---|---|---|
| `Open Editor` | 打开编辑器，可从当前选择加载公式 | 打开编辑器，可从当前选择加载公式 |
| `Insert OMML` | 插入 Word 原生 OMML | 插入当前兼容图片 |
| `Insert Native Object` | 插入 LaTeXSnipper OLE 公式对象 | 插入 LaTeXSnipper OLE 公式对象 |
| `Load Selected` | 加载选中 LaTeXSnipper 对象或受管 OMML | 加载选中 LaTeXSnipper 对象 |
| `Update Selected` | 原地更新对象 | 原地更新对象 |
| `Delete Selected` | 删除对象并清理元数据 | 删除对象并清理元数据 |
| `Auto Numbered` | 对受管公式启用自动编号 | 对受管对象启用自动编号 |
| `Renumber All` | 扫描文档对象重排 | 扫描演示文稿对象重排 |
| `Screenshot OCR` | 调用桌面端 OCR，写入编辑器 | 调用桌面端 OCR，写入编辑器 |

快捷键应在 Ribbon XML/VSTO 层注册，并与 LaTeXSnipper 桌面端全局快捷键保持不冲突。

## 安装与持久化

Windows 安装器负责：

- 安装 VSTO 插件。
- 注册 Word 和 PowerPoint 加载项。
- 注册 LaTeXSnipper OLE/COM 公式对象。
- 安装或检测 VSTO Runtime、WebView2 Runtime。
- 写入当前用户或机器级注册表项。
- 安装图标、Ribbon 资源和本地渲染资源。
- 卸载时清理插件注册、OLE 注册和临时缓存。

自定义安装位置不能影响插件加载。注册表中只保存稳定入口和资源根路径；插件启动时校验路径存在，不存在则显示可操作错误。

## 迁移阶段

1. 新建 `office_plugin` 项目骨架。
2. Word VSTO Ribbon 持久显示，命令能打开编辑器。
3. 复用 Bridge 完成 Word OMML 插入。
4. 迁移 Word 受管公式元数据、加载、更新、删除。
5. 迁移 Word 编号和重编号。
6. 实现 PowerPoint 图片插入，达到 `office_addin` 当前能力。
7. 引入 LaTeXSnipper OLE 公式对象。
8. 接入本地 MathJax 原生渲染管线。
9. 实现 Word/PPT 双击编辑和原地更新。
10. 完成快捷键、安装器、卸载器和回归测试。
11. 删除 `office_addin`。

## 不做的事

- 不继续投入 Office.js 持久安装方案。
- 不依赖企业账号作为普通用户安装前提。
- 不用图片对象伪装成可编辑公式。
- 不保留无法识别来源的历史兼容逻辑。
- 不让文档对象生命周期依赖任务窗格是否打开。
