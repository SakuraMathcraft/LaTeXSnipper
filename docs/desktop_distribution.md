# 桌面发行架构

## 资源边界

桌面发行包含三个按内容身份校验的组件：

| 组件 | 内容 |
|---|---|
| application | Qt 应用、独立启动器与更新器、worker 源码、MathJax、Pandoc；Linux 还包含包管理元数据、启动脚本和桌面集成 |
| inference | 独立 Python、锁定的推理依赖及 GPU 私有运行库 |
| models | 模型清单及完整权重 |

发行清单指定平台、架构、CPU/GPU 类型和经过验证的组件组合。内容未变化的组件可以复用；协议或依赖变化时必须一起更新受影响组件。源码运行直接使用开发者选择的 Python。

物理布局由 `runtime.installation_layout` 定义：

- Windows：安装根的 `application/`、`inference/`、`models/` 和 `distribution.json`。
- Linux：组件位于 `/usr/lib/latexsnipper`，安装身份位于 `/var/lib/latexsnipper/distribution.json`。`latexsnipper` 包拥有 application、系统依赖、启动器和桌面集成，另外两个包分别拥有 inference 和 models。应用组件更新同时更新包管理信息。
- macOS：组件位于 `.app/Contents/Resources/desktop`。更新重建并验证整个签名应用，再原子交换应用目录。

安装版只使用安装目录中的模型组件，worker 禁止自动下载模型。缺失或校验失败时报告资源异常，由“应用更新”统一替换受损组件。源码运行使用 MathCraft 平台默认缓存，独立库与 CLI 保留自己的缓存配置与自动下载行为。路径和清理范围见 [用户数据说明](user_data_storage.md)。

## 预览与导出

桌面预览及 SVG/MathML 转换使用内置 MathJax 运行库。HTML 独立页使用同版本 CDN，包括字体资源。

## 更新事务

`DeploymentTransaction` 统一计划、校验、持久化状态、提交和收尾。平台适配器只负责准备、替换、发布身份和故障恢复。

1. 根据权威发行清单检查已安装内容，仅下载变化或损坏的组件。
2. 下载可暂停、继续和取消；复用缓存前校验长度及摘要。
3. 在安装目录之外暂存组件，独立更新器重新认证目标清单。
4. 独立更新器准备好后，UI 停止任务和 worker 并退出。
5. 安装目标组合，验证资源及 worker，再提交安装身份。
6. 清理当前事务备份。清理失败记录诊断并保留待清理状态，不改变已提交结果，也不阻止正常启动；下次更新先重试清理。

只恢复未完成的事务，不提供历史版本选择或手动降级。持久化提交后的事务不会因为后续清理失败而撤销。尚有备份被占用时，新的部署等待清理完成，日常 UI 可以继续使用。

取消或接管失败后，后台清理等待更新器与 watcher 都退出，再移除各自任务目录和暂存内容。下载载荷缓存保留以支持经过校验的复用。

“应用诊断”只报告组件完整性与运行状态；“应用更新”统一处理应用、推理环境和模型组件的更新与修复。启动器、GUI 可执行文件或安装身份本身缺失、损坏时可能无法打开诊断窗口，需要重新运行安装器。

## 构建与验收

发行来源、依赖和资源锁定在 `packaging/runtime/`。应用与推理组件分别计算输入指纹，覆盖源码、实际平台依赖和构建辅助脚本；缓存命中还必须通过载荷完整性校验。

`scripts/payload_pruning.py` 统一维护三平台载荷裁剪：推理环境移除开发工具、交互式 Python/Tk 工具和 OpenCV 非识别资源，保留 `unittest` 等依赖可能导入的标准库。Windows 的独立 FFmpeg 视频插件可移除；Linux/macOS 保留 OpenCV 扩展直接链接的编解码及图形库。Qt 按相同模块清单处理 DLL、ELF、dylib 和 framework 布局，保留 WebEngine 核心资源及中英文本地化。GPU 私有运行库仍由原有白名单提取。裁剪后在目标平台执行导入、推理与应用原生验收。

普通 CI 保留编译、发行输入、翻译、注释和 Office 构建检查。完整测试、类型检查及 Qt 实际渲染检查用于变更验证。

开发检查使用启动应用的 Python：

```sh
python -m ruff check .
python -m ruff format --check .
python -m pyright --pythonpath <selected-python>
python -m pytest -q
```

Ruff 负责常见错误、导入顺序、Python 版本规则和格式，目标为库支持的 Python 3.10。Pyright 使用 `basic`，覆盖应用、OCR 库、构建脚本和 MathJax 工具；库按 Python 3.10 检查，其余按 3.11。Qt UI 的动态宿主属性及延迟创建控件不执行属性与可空成员诊断；手写窗口保留属性检查，仅放宽可空成员诊断。业务代码与更新、资源模块保留这些检查。

Bandit 通过 `security` extra 提供，用于网络、文件及进程边界的专项检查；运行 `python -m bandit -c pyproject.toml -r src mathcraft_ocr scripts -ll -ii` 检查中高风险、中高置信度提示。只在确认具体误报后用带规则编号的 `nosec` 标注并说明原因。

安装器只在 GitHub Actions 构建。Windows 默认生成未签名安装包；SignPath 配置完整时尝试签名，未配置或签名失败仍使用未签名产物。macOS 使用不需要开发者证书的本地 ad-hoc 签名，不要求 Apple 公证。

常规构建使用 GitHub 托管 runner 完成装配与原生安装检查。CUDA 硬件验收仅在手动选择 `validate_gpu` 时使用自托管 runner；未选择时不阻塞构建或发布。平台系统调用的模拟测试不能替代原生安装与硬件测试。

MathJax 原生检查入口为 `tools/mathjax/smoke_qt.py`，覆盖预览、字体和 SVG/MathML 转换。冻结应用验收还检查 PDF、XML、MathJax 转换与网络速度计所需模块。
