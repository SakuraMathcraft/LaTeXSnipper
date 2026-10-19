# 桌面发行架构

## 文件归属

桌面安装由业务目录与固定底座组成，用户数据位于安装目录之外。

| 归属 | 内容 | 更新方式 |
|---|---|---|
| `application/` | 项目 Python 源码、worker 源码、翻译与图标、独立更新器和启动器、Linux 桌面集成 | 轻量业务 ZIP |
| `runtime/` | 冻结 Python、Qt/WebEngine、GUI 第三方依赖、Pandoc、内置 MathJax | 完整安装包 |
| `inference/` | 独立 Python、锁定推理依赖、GPU 私有 CUDA/cuDNN 库 | 完整安装包 |
| `models/` | 模型清单与权重 | 完整安装包 |

冻结主进程只包含标准库、声明在 `packaging/runtime/gui-imports.json` 中的第三方模块及固定入口。入口从业务目录加载项目模块；项目源码不编入固定 PYZ。新增第三方依赖或改变冻结导入合同时须更新底座。源码运行仍使用启动应用的开发者 Python。

安装身份记录版本、平台、架构、CPU/GPU 类型、业务文件清单与 `base_id`。底座身份由已构建固定资源的内容身份组合产生，不依赖业务版本号。在线 `desktop-release.json` 只包含业务包、底座身份和完整安装包信息，不携带固定资源下载计划或权重文件清单。清单使用严格的 schema 2；升级至该架构须使用完整安装包，没有历史格式兼容或迁移层。

源码运行使用 `python src/main.py`。安装版由 `src/launcher_main.py` 生成的独立启动器进入冻结 GUI 宿主，再加载 `application/main.py`；共用启动和中断恢复逻辑归属 `update.deployment_launch`。`src/maintenance_main.py` 生成独立更新器，处理离线安装、业务更新与失败恢复，不创建 Qt 应用；需要权限的部署与普通用户 GUI 分进程执行。

## 平台安装约束

- Windows：安装根包含上述四个目录、根启动器和 `distribution.json`。业务更新只交换 `application/` 与根启动器。卸载器拥有这些安装资源。
- Linux：四个目录位于 `/usr/lib/latexsnipper`，分别由 `latexsnipper`、`latexsnipper-runtime`、`latexsnipper-inference`、`latexsnipper-models` 包管理；身份位于 `/var/lib/latexsnipper/distribution.json`。业务更新通过 dpkg 替换 `latexsnipper` 包，包管理器移除废弃的已归属文件。系统启动脚本、桌面入口与依赖声明由该包拥有。
- macOS：业务目录和身份位于 `.app/Contents/Resources/desktop`；三个固定资源目录位于 `.app/Contents/Frameworks/LaTeXSnipperBase.bundle/Contents/Resources`。固定底座是独立签名的嵌套包。业务更新准备小型外层应用，退出 UI 后移动原底座目录、对外层应用重新执行本地 ad-hoc 签名，再交换应用目录。更新不遍历或重新哈希底座文件，不使用 `codesign --deep` 检查权重；只验证外层资源封印和嵌套签名身份。签名失败或中断时恢复原应用和底座位置。此布局遵循 Apple 的[嵌套代码资源封印规则](https://developer.apple.com/library/archive/technotes/tn2206/)。

Windows 默认安装包未签名；SignPath 配置完整时尝试签名，未配置或失败仍使用未签名产物。macOS 使用不需要开发者证书的 ad-hoc 签名，没有 Developer ID 或 Apple 公证要求。

## 业务更新与损坏处理

更新只选择匹配平台、架构及已安装 CPU/GPU 类型的业务包。`base_id` 不同则禁止业务部署，并引导下载对应完整安装包。普通更新不会扫描已安装的推理环境或模型，也不提供其下载、修复或版本切换。

业务包按长度、SHA256 和文件清单校验，安全解包到安装目录之外。独立更新器重新核对 GitHub 权威发行元数据，然后准备替换；UI 退出后才修改安装。业务目录整体由发行包拥有，替换会清理已删除的业务文件；固定资源与用户数据保留。更新在验证业务文件和 worker 协议后提交身份。

事务日志与临时备份仅用于本次失败或中断恢复，不提供历史版本回滚。提交后的清理失败只延后删除备份，不撤销已完成更新。下载支持暂停、继续和取消；复用下载缓存前验证包摘要。

诊断只报告安装版本、底座身份、worker 状态及实际错误；模型资源查看显示 worker 实际使用路径，不全量校验权重。安装版 worker 加载模型时仍按模型清单校验，禁止自动下载。底座缺失、损坏、启动失败或需要更换 CPU/GPU 类型时，重新运行对应完整安装包。独立 mathcraft-ocr 库与 CLI 的缓存和自动下载策略保持独立。用户数据路径见[用户数据说明](user_data_storage.md)。

## 构建与发布

安装器只在 GitHub Actions 构建。`.github/workflows/release.yml` 执行以下工作：

1. 准备任务校验版本，并探测共享模型缓存；仅缺失时安装模型装配工具、下载权重并保存缓存，避免各平台重复生产同一模型包。
2. 平台任务先计算输入指纹、并行探测持久缓存，再安装依赖。全部命中时只安装装配所需的 Requests 和 Pillow；仅 GUI 底座缺失时安装完整 GUI 依赖，仅 GUI 或维护程序缺失时安装 PyInstaller。pip 缓存按装配、维护程序冻结、GUI 冻结分组，避免普通装配下载整套 Qt wheel 缓存。Linux 系统构建依赖也只在原生底座缺失时安装。
3. 使用仓库 `GITHUB_TOKEN` 从 `desktop-base-<target>-<resource>-<fingerprint>` 草稿构建缓存并行恢复资源 ZIP 和 `stamp.json`。校验输入身份、包摘要及解包清单后装配。该持久缓存不依赖 Actions 临时缓存；普通用户发布页不公开这些构建资源。缓存不存在时只生产缺失项，串行生产以复用公共下载、限制峰值内存；鉴权、下载或校验失败直接报错。
4. 每次装配当前业务源码，复用未变更的独立更新器和启动器，生成一个平台业务 ZIP。Windows/Linux 的 CPU、GPU 安装包共享 GUI、模型和业务载荷；各自只使用对应推理环境。macOS 优先恢复整体已签名嵌套底座；整体缺失时复用其已有 GUI、CPU 推理与模型缓存，只重建缺失部分，再封印嵌套底座。日常装配不重新签署或封印权重。使用这些资源装配离线完整安装包，首次安装无需下载模型或推理依赖。
5. 平台 runner 构建完成后直接上传完整安装包与业务包；Office 安装包和用户手册独立上传。最终任务只汇总小型元数据并公开草稿，不重新下载大型载荷。只有 Office 任务下载 Git LFS 安装器。Windows 打包工具、Typst 和按文档输入识别的手册 PDF 使用 Actions 缓存。用户发行页保留桌面安装包、Office 安装包、用户手册、业务 ZIP 与 `desktop-release.json`。Linux 离线安装包使用多线程 `.tar.xz` 压缩；macOS 将已装配应用移动到磁盘映像暂存目录，避免再次复制完整底座。单项发行资源必须小于 GitHub 的 2 GiB 限制。

`scripts/release_build_inputs.py` 定义缓存输入归属：GUI 底座使用其依赖、冻结导入合同、共用的 `LaTeXSnipper.spec`、固定入口与资源；CPU/GPU 推理分别使用对应锁定来源，CUDA 变化只影响 GPU；模型身份只由锁定权重、清单、格式、许可和布局版本决定，通用构建脚本变化不会触发权重重建。模型装配布局变更时须更新布局版本。维护程序指纹跟踪两个入口的本地 Python 导入闭包及冻结工具，普通 UI 源码不影响它。macOS 签名输入归属于相应原生载荷及嵌套底座。清理缓存时保留仍需复现的底座；删除缓存后可重新构建，但不同的实际内容会产生不同 `base_id`。

构建缓存草稿由工作流维护，不应手动发布。工作流串行执行以避免重复创建相同固定缓存；平台内构建仍并行。固定资源的校验用于构建输入可信性，不新增发布后验收关卡。

`scripts/qt_payload.py` 裁剪 GUI 载荷，保留 Qt WebEngine 核心资源及中英文语言资源；`scripts/payload_pruning.py` 裁剪推理载荷，保留依赖需要的标准库和 OpenCV 原生依赖，移除开发工具和不使用的数据。GPU 库按声明来源装配。

## 开发检查与原生验收

开发检查使用启动应用的 Python：

```sh
python -m ruff check .
python -m ruff format --check .
python -m pyright --pythonpath <selected-python>
python -m pytest -q
```

Ruff 负责常见错误、导入顺序、Python 版本规则和格式，目标为库支持的 Python 3.10。Pyright 使用 `basic`，覆盖应用、OCR 库、构建脚本和 MathJax 工具；库按 Python 3.10 检查，其余按 3.11。Qt UI 的动态宿主属性及延迟创建控件不执行属性与可空成员诊断；手写窗口保留属性检查，仅放宽可空成员诊断。业务代码与更新、资源模块保留这些检查。

Bandit 通过 `security` extra 提供，用于网络、文件及进程边界的专项检查；运行 `python -m bandit -c pyproject.toml -r src mathcraft_ocr scripts -ll -ii` 检查中高风险、中高置信度提示。只在确认具体误报后用带规则编号的 `nosec` 标注并说明原因。

普通 CI 检查编译、UTF-8、发行输入、翻译与 Office 构建。`scripts/validate_desktop_release.py` 可在 GitHub Actions 单独验收完整安装、业务替换、CPU/GPU 安装类型替换和卸载；CPU 验收还启动冻结 GUI 检查 PDF、XML、网络速度计与 MathJax。此验收不作为每次发布的强制关卡。CUDA 硬件验收仅在手动选择 `validate_gpu` 时使用自托管 runner。平台系统调用的模拟测试不能替代原生安装、签名和硬件验收。

在 Actions 的 **CI → Run workflow** 中，`platform_validation` 可选 `windows`、`linux`、`macos` 或 `all`；默认 `none` 保留普通检查。选择平台后只运行桌面集成检查，不构建安装包、不下载 OCR 权重、不改变发布流程。验证覆盖原生快捷键注册与清理、Windows/X11 系统按键触发、Qt 状态图标创建与窗口恢复，以及三平台菜单的中英文动作和 macOS 生命周期事件分发。Linux 使用 Xvfb 与独立 D-Bus 会话；Wayland 测试使用模拟 Portal，只验证协议与授权状态处理。macOS 的系统按键注入因额外权限要求明确跳过。结果中的跳过项必须单独确认，不能作为已验收功能。

本地交互桌面可设置 `LATEXSNIPPER_PLATFORM_VALIDATION=1` 后运行 `python -X utf8 -m pytest -q -rs test/test_platform_integration.py test/test_qhotkey_linux.py test/test_qhotkey_macos.py`。测试会短暂创建窗口、状态图标，并在 Windows/X11 注入 `Ctrl+Shift+F8`。macOS 的实际 Dock 点击、菜单栏图标与系统快捷键、GNOME/KDE 的真实 Portal 授权、托盘可见性与截图权限仍需对应桌面会话验收；Xvfb 中创建图标成功不代表桌面提供托盘宿主。

MathJax 原生检查入口为 `tools/mathjax/smoke_qt.py`，覆盖预览、字体和 SVG/MathML 转换。冻结应用检查还覆盖 PDF、XML 与网络速度计所需模块。桌面预览使用本地 MathJax；HTML 独立页继续使用同版本 CDN。
