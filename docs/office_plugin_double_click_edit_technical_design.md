# LaTeXSnipper Office 插件双击编辑技术方案

## 1. 文档目的

本文给出 LaTeXSnipper Office 插件公式双击编辑功能的实施设计。需求以 `docs/需求方案.md` 为唯一业务边界，本文只描述实现方法、状态约束、模块改动、验证方式和实施顺序。

本方案不承担旧文档迁移，不为旧字段、旧 schema 或旧 OLE payload 保留兼容分支。

## 2. 设计结论

新版需求是合理且可实施的，关键设计结论如下：

1. Word 不存在适合本功能的可靠 OMML 或原生公式双击事件，因此 Word 只支持 LaTeXSnipper OLE 的原生 `IOleObject::DoVerb` 路径。
2. PowerPoint 图片公式由 `Application.WindowBeforeDoubleClick` 处理；PowerPoint OLE 在该事件中只捕获目标，最终仍由 `DoVerb` 激活编辑器。
3. 一个宿主加载项实例只拥有一个 MathLive 编辑器窗口，但该窗口允许从公式 A 原子切换到公式 B。
4. 编辑目标必须在 Office UI 线程上的双击回调或 OLE 消息回调中同步捕获，异步代码不得重新读取活动选择或活动文档。
5. 每次公式切换使用单调递增的会话代次隔离异步结果，防止公式 A 的迟到提交结果关闭或污染已经切换到公式 B 的编辑器。
6. `DocumentId` 和 `EquationId` 由 Office 宿主元数据唯一负责；OLE payload 不参与对象身份。

## 3. 实现范围

### 3.1 支持矩阵

| 宿主 | 对象 | 入口 | 插件行为 |
| --- | --- | --- | --- |
| Word | LaTeXSnipper OLE | `IOleObject::DoVerb` | 捕获 OLE 目标并切换编辑器 |
| Word | LaTeXSnipper OMML | 无 | 保持 Word 默认行为 |
| Word | Word 原生公式 | 无 | 保持 Word 默认行为 |
| PowerPoint | LaTeXSnipper 图片 | `WindowBeforeDoubleClick` | 取消默认行为并切换编辑器 |
| PowerPoint | LaTeXSnipper OLE | `WindowBeforeDoubleClick` + `DoVerb` | 前者缓存目标，后者切换编辑器 |
| PowerPoint | 普通图片或 Shape | 无 | 保持 PowerPoint 默认行为 |

### 3.2 明确不修改

本次不修改 OCR、Bridge、渲染后端、批量转换、批量删除、批量格式化、Word 自动编号、PowerPoint 插入位置、独立客户端以及 MathLive 的公式编辑能力。

MathLive 窗体只允许增加“切换配置”和“异步结果代次校验”所需的最小状态，不改编辑控件、符号面板、输入行为或渲染逻辑。

## 4. 总体架构

实现分为四层：

```text
Office 原生入口
    Word/PPT OLE DoVerb 消息
    PowerPoint WindowBeforeDoubleClick
            |
            v
宿主目标捕获层
    WordFormulaEditTarget
    PowerPointFormulaEditTarget
    PowerPointPendingOleTarget
            |
            v
编辑会话协调层
    FormulaEditorSession
    宿主 Controller 当前目标
    状态窗格预览绑定
            |
            v
单实例 MathLive 编辑器
    Configure + Show/Activate
    提交代次校验
```

所有目标捕获和公式切换均在 Office UI 线程串行执行。渲染和提交可以异步执行，但必须携带捕获时的不可变目标和会话代次。

## 5. 核心状态模型

### 5.1 编辑会话状态

`FormulaEditorSession` 维护以下状态：

```text
HasConfiguredSession
Generation
Mode: Insert | Update
CurrentFormulaMetadata
CurrentFormulaIdentity
```

预热只创建和初始化隐藏窗体，不设置 `HasConfiguredSession`。

每次插入或切换到公式时：

1. `Generation` 加一。
2. 替换模式和当前公式元数据。
3. 调用编辑器 `Configure`。
4. 显示并激活同一个窗体。

提交、取消或窗体关闭时，只有事件携带的 `Generation` 仍为当前代次，才允许结束当前会话。

### 5.2 宿主目标状态

宿主 Controller 分别维护：

```text
WordPluginController.CurrentEditTarget
PowerPointPluginController.CurrentEditTarget
```

编辑器更新模式下，Controller 当前目标、`FormulaEditorSession.CurrentFormulaIdentity` 和编辑器配置中的初始公式必须完全一致。

Controller 不再使用仅靠 `FormulaMetadata` 或当前 Selection 推断编辑目标的逻辑。

### 5.3 原子切换不变量

公式 A 切换到公式 B 时必须满足：

```text
CurrentEditTarget.EquationId
== FormulaEditorSession.CurrentFormulaIdentity.EquationId
== 编辑器当前配置的 InitialFormula.Identity.EquationId
== 状态窗格当前临时预览对应的 EquationId
```

切换在 UI 线程内按以下顺序完成：

1. 完整验证目标 B。
2. 创建不可变的 B 编辑请求。
3. 暂存新的会话代次。
4. 替换 Controller 当前目标。
5. 配置编辑器为 B。
6. 切换状态窗格临时预览为 B。
7. 提交新的会话代次并激活窗口。

如果配置或预览切换失败，恢复切换前的目标、会话状态和预览；不得留下半切换状态。这里的回滚只保障本次内存事务完整性，不是旧格式兼容。

## 6. 编辑目标模型

### 6.1 WordFormulaEditTarget

新增不可变类型，至少包含：

```text
Document             原始 Word Document COM 引用
WindowHandle         双击时所属 Word 窗口，用于绑定状态窗格
DocumentId
EquationId
FormulaMetadata
IsOle                必须为 true 才能来自双击入口
```

提交前通过原始 `Document` 查找 `EquationId`，要求恰好找到一个 LaTeXSnipper OLE。不得读取 `ActiveDocument` 或当前 Selection。

### 6.2 PowerPointFormulaEditTarget

扩展现有类型，至少包含：

```text
Presentation         原始 Presentation COM 引用
WindowHandle         双击时所属 DocumentWindow
Shape                 双击时捕获的 Shape COM 引用
DocumentId
EquationId
FormulaMetadata
RenderEngine
```

提交前在原始 `Presentation` 内按 `EquationId` 查找，要求结果唯一，并验证目标仍属于原演示文稿。Shape 引用只用于验证捕获对象，不作为持久身份。

### 6.3 目标失效规则

出现以下任一情况时拒绝提交：

- 原 Document 或 Presentation 已关闭；
- 目标对象已删除；
- `DocumentId` 不再匹配；
- `EquationId` 找不到或不唯一；
- 对象宿主元数据不完整；
- 目标类型或渲染引擎与捕获时不一致。

拒绝提交时保持编辑器和当前草稿，不更新当前选择，也不插入新公式。

## 7. 双击路由设计

### 7.1 纯 OLE 激活消息窗口

删除 `FormulaDoubleClickWindow`，新增 `OleActivationMessageWindow`。

该类只负责：

```text
RegisterWindowMessage("LaTeXSnipper.OfficePlugin.OleFormulaActivate")
接收注册消息
在 Office UI 线程同步调用宿主 OLE 激活回调
在宿主窗口变化时安全重绑句柄
Dispose 时释放 NativeWindow 句柄
```

该类禁止包含鼠标钩子、鼠标消息、计时器、重复事件过滤或 SelectionChange 推断。

### 7.2 Word OLE 调用链

```text
用户双击 Word OLE
-> Office 调用 FormulaOleObject::DoVerb
-> Native Handler 向当前 Office 根窗口发送注册消息
-> OleActivationMessageWindow.WndProc
-> 在 UI 线程同步捕获 WordFormulaEditTarget
-> 严格确认单一 LaTeXSnipper OLE 和完整宿主元数据
-> Controller 原子切换当前目标、编辑器和状态窗格预览
```

Word 不订阅任何双击鼠标事件。现有 `WindowSelectionChange` 仅保留其原有非双击职责，不得调用双击编辑链路。

### 7.3 PowerPoint 图片调用链

```text
Application.WindowBeforeDoubleClick
-> 使用事件提供的 Selection 同步检查单选 Shape
-> 读取并验证完整宿主元数据
-> 确认 RenderEngine == Image
-> 同步构造 PowerPointFormulaEditTarget
-> Cancel = true
-> Controller 原子切换目标、编辑器和状态窗格预览
```

事件回调不得先启动异步任务再读取 `ActiveWindow.Selection`。

不满足条件时 `Cancel` 保持 `false`，插件不执行任何操作。

### 7.4 PowerPoint OLE 调用链

```text
Application.WindowBeforeDoubleClick
-> 同步捕获并验证单选 LaTeXSnipper OLE Shape
-> 保存一次性 PowerPointPendingOleTarget
-> Cancel 保持 false，不打开编辑器
-> PowerPoint 继续默认 OLE 激活
-> FormulaOleObject::DoVerb 发送注册消息
-> OleActivationMessageWindow 收到消息
-> 原子消费 pending target 并立即清空
-> 再次验证目标仍存在且身份一致
-> Controller 原子切换目标、编辑器和状态窗格预览
```

pending target 必须在以下情况清空：

- 成功或失败消费后；
- 窗口切换；
- 演示文稿关闭；
- 选择切换到其他对象；
- 目标被删除；
- 新的 OLE 双击覆盖旧 pending target。

如果 OLE 消息到达时没有 pending target，允许同步检查当前单选 Shape，用于 Office 的 `Edit Formula` Verb 路径。仍无法得到唯一目标时静默忽略，不得猜测。

## 8. 单实例编辑器与异步代次

### 8.1 正常切换

编辑器窗体已经显示时，切换公式不新建窗体，只执行：

```text
Configure(newMetadata, updateMode: true, generation)
Show
Restore from minimized if needed
Activate
BringToFront
```

公式 A 在编辑器中的未提交文本直接丢弃，不写入 Office 文档，也不保存为多公式草稿。

### 8.2 提交期间切换

为避免异步串线，提交请求携带：

```text
Generation
InitialFormulaIdentity
不可变 WordFormulaEditTarget 或 PowerPointFormulaEditTarget
```

如果 A 的提交尚未结束时用户切换到 B：

- A 的提交仍只允许更新已捕获的 A；因为用户已经明确提交 A，所以不取消已发生的业务提交。
- A 的迟到结果不得关闭 B 的编辑器、恢复 B 的状态窗格、清空 B 的目标或覆盖 B 的状态消息。
- 编辑器窗体在处理提交结果时先比较 `Generation`；结果已过期时只结束 A 自身的后台流程。

这保证“已提交的 A 可以完成”和“当前正在编辑的 B 不被污染”同时成立。

### 8.3 取消和关闭

取消或关闭事件也携带当前代次。只有代次匹配时才：

1. 清空当前宿主目标；
2. 结束当前编辑会话；
3. 恢复对应状态窗格原始草稿。

过期配置产生的取消或关闭通知不得结束新公式会话。

## 9. 状态窗格预览与草稿恢复

保留现有：

```text
WordStatusTaskPaneControl._savedDraftState
PowerPointStatusTaskPaneControl._savedLatex
```

它们继续作为每个状态窗格控件的原始草稿快照，不在 Controller 中复制第二份草稿数据。

为避免活动窗口变化导致恢复错误，状态窗格宿主增加按捕获窗口操作的预览接口，而不是在提交时调用“当前活动窗格”：

```text
BeginFormulaPreview(windowHandle, metadata)
SwitchFormulaPreview(windowHandle, metadata)
EndFormulaPreview(windowHandle)
```

同一窗格内 A 切换到 B 时：

- `_savedDraftState` 或 `_savedLatex` 只在首次进入编辑时保存一次；
- 直接把临时预览从 A 替换为 B；
- 不覆盖已保存的原始草稿。

跨窗口切换时：

- 离开的窗格恢复自身原始草稿；
- 新目标窗格保存自己的原始草稿并显示新公式；
- 当前会话记录实际处于临时预览状态的窗格句柄；
- 会话结束时只恢复该窗格，不依赖当前活动窗口。

OCR 和任务窗格插入继续使用现有接口及语义，不接入公式编辑预览会话。

## 10. Office 宿主身份设计

### 10.1 文档身份

当前格式为每个 Office 文档持久化真实 `DocumentId`：

- Word：使用文档侧变量或现有 Word 元数据存储体系中的专用键；
- PowerPoint：使用 Presentation 自定义文档属性中的专用键。

新插入对象的宿主元数据必须同时保存当前 `DocumentId` 和新 `EquationId`。

### 10.2 PowerPoint Shape 元数据

PowerPoint Shape Tags 增加 `DocumentId`，并继续保存 `EquationId`、LaTeX、显示模式、渲染引擎、schema 和自然尺寸。

当前格式读取要求所有必需 Tag 完整，不从 Shape.Name、AlternativeText、位置或 OLE payload 补全缺失字段。

### 10.3 复制后的身份修正

捕获编辑目标时执行当前格式身份确认：

1. 对象 `DocumentId` 等于当前宿主 `DocumentId`，且 `EquationId` 唯一：直接使用。
2. 对象元数据完整，但 `DocumentId` 属于其他宿主：判定为跨文档复制，为当前副本生成新的 `EquationId`，并写入当前 `DocumentId`。
3. 当前宿主内存在重复 `EquationId`：只为本次操作对象生成新 `EquationId`，不修改原对象。
4. 缺少当前格式字段或 schema 不匹配：拒绝编辑，不迁移。

身份修正只修改宿主元数据，不修改公式内容和 OLE payload。

### 10.4 Schema

宿主公式元数据升级为新的当前 schema。旧 schema 不读取、不自动升级。OLE payload 维持独立的当前 schema，并由 Native 和托管序列化端严格一致地验证。

## 11. Native OLE 协议

### 11.1 Verb

`FormulaOleObject::DoVerb` 只接受：

```text
OLEIVERB_PRIMARY
OLEIVERB_OPEN
OLEIVERB_SHOW
```

其他 Verb 返回 `OLEOBJ_E_INVALIDVERB`。

成功发送激活消息后返回 `OLEOBJ_S_CANNOT_DOVERB_NOW`，阻止 PowerPoint 继续进入 UI 激活或原位编辑流程。

`EnumVerbs()` 只返回一个 `Edit Formula`。

### 11.2 MiscStatus

Native `GetMiscStatus()` 和安装器 32/64 位注册表统一为十进制 `672272`，对应：

```text
OLEMISC_CANTLINKINSIDE
OLEMISC_RENDERINGISDEVICEINDEPENDENT
OLEMISC_NOUIACTIVATE
OLEMISC_IGNOREACTIVATEWHENVISIBLE
OLEMISC_SETCLIENTSITEFIRST
```

不得包含 `OLEMISC_STATIC`。

`IsRunning()` 返回 `FALSE`。

### 11.3 Payload

OLE payload 只包含当前 schema 的公式内容与展示信息。Native 严格验证当前 schema 和必需字段。

删除：

```text
RemoveJsonProperty
SanitizePayloadIdentity
旧字段剥离
旧 schema fallback
无效 payload 自动修复
```

Native 对象构造期间所需的临时空状态不视为旧 payload fallback；一旦从持久化 Storage 或待插入 payload 加载，就必须满足当前格式。

## 12. 主要接口调整

建议的接口方向如下，最终命名保持项目现有风格：

```text
IFormulaEditor
    WarmUpAsync(...)
    ConfigureAndActivate(initialFormula, updateMode, generation)

FormulaEditorSession
    SwitchToInsert(initialDraft)
    SwitchToEdit(metadata)
    IsCurrent(generation, identity)
    Complete(generation)

IWordApplicationAdapter
    CaptureSelectedOleEditTarget(document, window)
    UpdateOleFormulaObjectAsync(target, ...)

IPowerPointApplicationAdapter
    CaptureDoubleClickTarget(presentation, window, selection)
    UpdateFormulaImageAsync(target, ...)
    UpdateOleFormulaObjectAsync(target, ...)
```

捕获方法必须同步执行，因为其输入来自 Office 事件瞬间。渲染、替换和文件操作继续使用异步接口。

显式功能区“编辑所选公式”复用相同 Target 和 Session 模型，但 OMML/Word 原生公式仍只通过显式命令处理，不增加双击入口。

## 13. 文件级改动计划

### 删除

```text
office_plugin/hosts/OfficeVstoShared/FormulaDoubleClickWindow.cs
```

### 新增

```text
office_plugin/hosts/OfficeVstoShared/OleActivationMessageWindow.cs
office_plugin/hosts/WordAddIn/WordFormulaEditTarget.cs
```

根据实现拆分情况，可新增宿主文档身份存储类和 PowerPoint pending OLE target 类型；不得把这些职责继续堆入 Controller。

### 重点修改

```text
office_plugin/hosts/WordVstoAddIn/ThisAddIn.cs
office_plugin/hosts/PowerPointVstoAddIn/ThisAddIn.cs
office_plugin/hosts/WordVstoAddIn/*.csproj
office_plugin/hosts/PowerPointVstoAddIn/*.csproj
office_plugin/hosts/WordAddIn/WordPluginController.cs
office_plugin/hosts/PowerPointAddIn/PowerPointPluginController.cs
office_plugin/hosts/WordAddIn/IWordApplicationAdapter.cs
office_plugin/hosts/PowerPointAddIn/IPowerPointApplicationAdapter.cs
office_plugin/hosts/WordAddIn/DynamicWordApplicationAdapter*.cs
office_plugin/hosts/PowerPointAddIn/DynamicPowerPointApplicationAdapter.cs
office_plugin/hosts/WordAddIn/WordFormulaMetadataStore.cs
office_plugin/hosts/PowerPointAddIn/PowerPointFormulaMetadataStore.cs
office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/FormulaEditorSession.cs
office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/MathLiveFormulaEditor.cs
office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/MathLiveFormulaEditorForm.cs
office_plugin/hosts/OleFormulaObjectNative/src/FormulaOleObject.cpp
office_plugin/hosts/OleFormulaObjectNative/src/Presentation.cpp
office_plugin/installer/setup.iss
```

状态窗格相关文件只增加按窗口绑定的预览切换能力，保留 `_savedDraftState` 和 `_savedLatex`。

## 14. 错误处理原则

- 非 LaTeXSnipper 对象：静默忽略，保留 Office 默认行为。
- 元数据不完整或旧 schema：拒绝编辑，不修复。
- 目标关闭、删除或身份冲突：提交失败并在编辑器中显示错误，保留草稿。
- OLE 激活消息没有唯一目标：静默忽略。
- 编辑器切换失败：保持切换前的完整会话。
- 过期异步结果：不得修改当前编辑器、目标或状态窗格。

不捕获并吞掉无法区分的业务异常。只有“当前对象不是可编辑公式”这种预期判定可以转为静默忽略。

## 15. 测试与验收

### 15.1 自动化验证

1. 使用项目 `tools` 下的 Python 环境运行现有测试。
2. 构建全部 Office 托管项目。
3. 使用 Visual Studio 2022 Community 的完整 VC 工具链构建 Native OLE x86 和 x64 Release。
4. 构建 Word 和 PowerPoint VSTO Release 项目。
5. 对会话代次、目标切换、复制身份和目标失效增加行为测试。
6. 结构测试只验证仍有价值的当前协议，不为每个已删除旧符号堆积防回归断言。

### 15.2 手工 Office 验收矩阵

| 场景 | 预期 |
| --- | --- |
| Word 双击 LaTeXSnipper OLE | 只打开或切换一次编辑器 |
| Word 双击 OMML/原生公式/普通对象 | 插件无动作 |
| PowerPoint 双击图片公式 | `Cancel = true`，切换编辑器 |
| PowerPoint 双击 OLE | 只由 DoVerb 最终切换一次 |
| PowerPoint 双击普通图片或 Shape | 保持默认行为 |
| 编辑 A 后双击 B | 同一窗体立即显示 B，A 未提交文本被放弃 |
| A 提交中切换 B | A 可完成已提交更新，B 窗口不关闭且不被污染 |
| 切换到另一文档后提交 | 更新双击时捕获的目标 |
| 删除目标后提交 | 拒绝提交，不插入新对象 |
| 同文档复制后编辑副本 | 副本获得新 EquationId，原对象不变 |
| 跨文档复制后编辑副本 | 副本绑定新 DocumentId 和 EquationId |
| A/B 在同一状态窗格切换 | 原草稿只保存一次，预览直接切到 B |
| A/B 位于不同 Office 窗口 | 各窗格草稿都能正确恢复 |

### 15.3 静态清理检查

最终代码中不得存在：

```text
WH_MOUSE
SetWindowsHookEx
WM_LBUTTONDBLCLK
WmImageActivation
DuplicateWindowMilliseconds
基于时间的双击去重
RemoveJsonProperty
SanitizePayloadIdentity
旧 payload/schema 兼容分支
```

## 16. 分阶段实施顺序

### 阶段一：入口清理

删除通用鼠标双击实现，建立纯 OLE 消息窗口，修正 Native Verb 返回值和 MiscStatus，完成 Native 与 VSTO 编译。

### 阶段二：同步目标捕获

实现 Word OLE target、PowerPoint `WindowBeforeDoubleClick` 分流及一次性 pending OLE target，验证三条调用链不会重复触发。

### 阶段三：原子公式切换

实现 Session 代次、单窗体重新 Configure、Controller 强类型目标切换和过期异步结果隔离。

### 阶段四：状态窗格绑定

实现按捕获窗口切换和恢复临时预览，验证同窗格与跨窗格 A/B 切换。

### 阶段五：身份收紧

实现真实 DocumentId、复制重编号、当前 schema 严格读取，删除 Native payload 身份清洗和历史兼容。

### 阶段六：完整验证

运行全部测试和构建，执行 Office 手工验收矩阵，整理修改文件、删除实现、三条调用链、会话切换说明、状态窗格说明和身份说明。

每个阶段完成并验证后再进入下一阶段。除非用户明确要求，不创建提交、不推送分支。
