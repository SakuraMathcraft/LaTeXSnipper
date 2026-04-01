# LaTeXSnipper v2.2 外部模型方案

## 目标

`v2.2` 分为两个阶段：

1. `Beta`
   - 外部模型图片 / 截图识别接入
   - 设置页配置、教程、测试连接、模型名校验
2. `正式版`
   - 在 Beta 已跑通的基础上，继续把文档识别链路接入外部模型

当前这份文档以 `v2.2 正式版` 为目标范围。

## 当前状态

### Beta 已完成

- 设置页新增 `外部模型...`
- 新增 `src/backend/external_model`
- 已支持两类协议：
  - `Ollama`
  - `OpenAI-compatible`
- 已支持配置保存、推荐预设、教程窗口
- 已支持后台 `测试连接`
- 已支持测试连接时校验模型名
- 已接入主窗口图片 / 截图识别链路
- 已完成 `Ollama + qwen2.5vl` 真实联调

### Beta 结论

外部模型基础能力已经可用，且当前测试通过。

因此 `v2.2 正式版` 不再只是“图片识别增强”，而是继续向“文档识别接管”推进。

## v2.2 正式版范围

### 纳入正式版

`v2.2 正式版` 明确包含以下四项：

1. `PDF 识别接管`
2. `整页文档解析接管`
   - 仍然走现有 PDF 识别入口
3. `MinerU 原生接口`
4. `外部模型接管手写识别全链路`

### 本次不单独拆版本

以上能力不再延后到 `v2.3`，而是作为 `v2.2 正式版` 的正式范围。

## 核心原则

正式版虽然扩了范围，但仍然坚持这几个原则：

1. 不重写现有 `pix2text` 主链路
2. 不碰废弃的 Tauri / daemon 路线
3. 外部模型继续放在 `src/backend/external_model`
4. 新能力优先做“并行接管”，而不是“整体重构”
5. 不按具体模型名做渲染或结果适配

也就是说：

- `pix2text` 继续作为内置路径保留
- `external_model` 继续作为独立路径扩展
- 两条链路在入口分流，在结果插入层汇合

## 产品语义

### 来源与内容类型分离

这点对正式版很重要。

不为每个模型单独建立类型标签，例如：

- 不做 `qwen_vl`
- 不做 `glm_ocr`
- 不做 `mineru`

而是分成两层：

1. 识别来源
   - `pix2text`
   - `external_model`
2. 内容类型
   - `formula`
   - `text`
   - `mixed`
   - `page`
   - `table`

现阶段可以继续复用已有成熟渲染系统，不急着大改渲染架构。

## 正式版能力拆解

### 1. PDF 识别接管

目标：

- 当用户选择 `外部模型...` 时，PDF 识别不再强制退回 `pix2text`
- 外部模型可以接管现有 PDF 识别入口

原则：

- 保留现有 PDF 入口和大体交互
- 不重做一个新的 PDF 页面
- 在现有入口内部按后端分流

建议实现：

- 新增 `src/backend/external_model/pdf_worker.py`
- 将 PDF 页面渲染为图片后，交给外部模型识别
- 结果按页聚合，再进入现有结果展示 / 确认流程

### 2. 整页文档解析接管

目标：

- 继续沿用 PDF 识别入口
- 支持整页文本、整页公式、整页混合内容的解析

这里不是单纯“把 PDF 当很多张截图”。

需要增加一个更明确的整页模式，例如：

- `page`
- `document`

建议实现：

- 新增 `src/backend/external_model/document_pipeline.py`
- 负责：
  - 页面图片预处理
  - 按任务类型选择提示词
  - 聚合整页结果
  - 结构化返回

### 3. MinerU 原生接口

目标：

- 支持不走 `OpenAI-compatible`
- 直接接入 MinerU 原生服务接口

这是正式版里唯一一个新增协议族的专项支持。

原因很明确：

- MinerU 不是单纯聊天式 VLM 接口
- 它更像文档解析服务
- 如果继续伪装成 `OpenAI-compatible`，后面维护会越来越乱

建议实现：

- 新增：
  - `src/backend/external_model/mineru_client.py`
  - `src/backend/external_model/mineru_worker.py`
- 设置页协议新增：
  - `MinerU`
- 配置项允许填写：
  - Base URL
  - API Token / Key
  - 接口路径
  - 文档解析模式

### 4. 手写识别全链路接管

目标：

- 当用户当前选择 `external_model` 时
- 手写识别不再强制走 `pix2text`
- 从画板导出图像，到识别，到结果展示，整条链路都走外部模型

原则：

- 保留现有手写识别窗口和交互
- 只在识别提交点分流

建议实现：

- 手写识别本质仍是图片识别
- 但需要单独检查：
  - 自动识别触发
  - 连续识别
  - 清空重写
  - 手写窗口关闭时线程回收

## 项目结构

正式版建议扩成这样：

```text
src/
  main.py
  settings_window.py

  backend/
    model.py
    external_model/
      __init__.py
      client.py
      worker.py
      pdf_worker.py
      document_pipeline.py
      mineru_client.py
      mineru_worker.py
      presets.py
      prompts.py
      schemas.py
      errors.py
```

### 各模块职责

#### `client.py`

- 处理通用图片识别请求
- 适配 `Ollama` / `OpenAI-compatible`
- 做统一结果归一化

#### `worker.py`

- 处理图片 / 截图识别后台线程

#### `pdf_worker.py`

- 处理 PDF 页级识别任务
- 控制页循环、进度、取消、聚合

#### `document_pipeline.py`

- 处理整页文档提示词、任务路由、结构化结果组装

#### `mineru_client.py`

- 专门处理 MinerU 原生接口
- 不和通用 VLM 协议混在一起

#### `mineru_worker.py`

- 专门处理 MinerU 文档任务的后台执行

## 设置页方案

### 识别模型下拉框

仍保持极简：

- `pix2text - 兼容模式`
- `外部模型...`

不把具体模型名塞进主下拉框。

### 外部模型协议

正式版建议支持三类：

- `Ollama`
- `OpenAI-compatible`
- `MinerU`

### 引导要求

设置页仍然是核心引导入口。

需要继续保证：

- 用户知道哪些字段必填
- 能区分本地接口和线上接口
- 能知道模型名 / 接口路径填错时该怎么排查
- 能先测试连接，再开始识别

## 结果与类型策略

### 不按模型做类型适配

正式版继续坚持：

- 不为每个模型单独做 UI 类型分支
- 不为每个模型单独做渲染分支

### 统一结果结构

建议补强统一结果结构：

```python
{
    "backend": "external_model",
    "provider": "ollama",
    "model_name": "qwen2.5vl:7b",
    "content_type": "formula",
    "text": "...",
    "latex": "...",
    "markdown": "...",
    "blocks": [],
    "raw": {...}
}
```

### 正式版目标

正式版至少应做到：

- 外部模型来源可区分
- 内容类型可稳定映射到现有渲染系统
- PDF / 整页 / 手写链路都能把结果带入同一套展示逻辑

## 集成策略

### 保持 `pix2text` 不动

仍然不要主动重构：

- `src/backend/model.py`
- 旧 `pix2text` worker
- 旧 Tauri / daemon 路线

### 在主流程中继续按入口分流

`src/main.py` 中继续采用低风险分流：

1. 图片 / 截图识别
2. PDF 识别
3. 手写识别

每个入口分别判断：

- 当前是否为 `external_model`
- 如果是，则走 `external_model` 自己的 worker / pipeline
- 如果不是，则保持原有 `pix2text` 路线

## 建议开发阶段

### Phase 1: PDF 接管

- 接通 PDF 入口分流
- 新增 `pdf_worker.py`
- 支持页渲染、页级调用、结果聚合

### Phase 2: 整页文档解析

- 新增 `document_pipeline.py`
- 支持整页识别提示词和结构化结果
- 让 PDF 识别入口支持整页模式

### Phase 3: 手写识别接管

- 在手写识别入口加 `external_model` 分流
- 跑通手写到结果展示全链路

### Phase 4: MinerU 原生接口

- 新增 `MinerU` 协议
- 增加专用 client / worker
- 跑通 PDF / 文档类场景

### Phase 5: 收口与回归

- 回归 `external_model -> pix2text` 切换
- 回归图片 / PDF / 手写三条主链路
- 回归错误提示、线程回收、窗口关闭行为

## 当前执行进度（2026-04-01）

### Phase 1：已收口

- `PDF 入口分流` 已接通并稳定运行
- `src/backend/external_model/pdf_worker.py` 已用于页级渲染与聚合
- 取消识别、进度回传、结果聚合已在外部模型 PDF 路径可用

### Phase 2：已收口

- 已新增 `src/backend/external_model/document_pipeline.py`
- 已在 PDF 外部模型流程接入 `document/page` 解析模式
- 已实现按提示词路由、页级处理、结构化聚合（`backend/mode/pages`）

### Phase 3：已收口

- 已在手写识别入口支持 `external_model` 分流
- 已支持手写识别任务在 `pix2text / external_model` 间按当前偏好自动路由
- 已补外部模型配置校验，未配置时可直接引导打开设置
- 已保持自动识别、连续识别、窗口关闭线程回收的既有行为

### Phase 4：已收口

- 已新增 `src/backend/external_model/mineru_client.py`
- 已新增 `src/backend/external_model/mineru_worker.py`
- 设置页协议新增 `MinerU`，支持配置：
  - 解析接口路径
  - 健康检查路径
  - 文档解析模式（auto/document/page）
- `external_model` 主链路已支持 `MinerU` 协议测试连接与识别调用
- 主窗口外部模型配置判定已兼容 `MinerU`（不再强制模型名）

### Phase 5：已完成（全链路回归收口）

- 已回归 `external_model -> pix2text` 切换路径，保持延迟加载策略与状态文案一致
- 已回归图片 / 截图识别链路：
  - 外部模型连接状态与主窗口状态栏联动
  - 真实模型名显示与“已连接/待连接”状态一致
- 已回归 PDF 识别链路：
  - 外部模型分流、取消、进度、结果窗口展示保持可用
  - `document/page` 模式与偏好模板流程保持可用
- 已回归手写识别链路：
  - `external_model` 分流保持可用
  - 自动识别、连续识别、窗口关闭线程回收保持可用
- 已回归错误提示与配置引导：
  - 按协议动态提示必填项（MinerU 不再误提示“模型名必填”）
  - 未配置时统一可引导回设置页

### 仍待后续阶段

- 无（`v2.2` 计划范围内阶段已全部收口）

## 风险与控制

### 风险 1：范围变大

控制方式：

- 不做总架构重写
- 继续按入口分阶段接管

### 风险 2：文档结果不一致

控制方式：

- 将结果归一化前置到 `external_model` 模块内部
- 提示词集中管理

### 风险 3：MinerU 接口特殊性导致耦合失控

控制方式：

- MinerU 独立 client
- 不伪装成 `OpenAI-compatible`

### 风险 4：影响现有 `pix2text`

控制方式：

- 不修改 `model.py`
- 所有新增逻辑在 `src/backend/external_model`
- 主窗口只做分流和结果接线

## 正式版完成标准

`v2.2 正式版` 以这些条件作为完成标准：

1. 外部模型可接管图片 / 截图识别
2. 外部模型可接管 PDF 识别入口
3. 外部模型可完成整页文档解析
4. 外部模型可接管手写识别全链路
5. `MinerU` 原生接口可配置并可联调
6. 结果能进入现有确认、历史、收藏、展示流程
7. `pix2text` 原链路不回归

## 最终结论

`v2.2 beta` 已经完成“外部模型基础接入”。

`v2.2 正式版` 现在明确升级为“外部模型文档识别接管版本”，范围包括：

- PDF 识别接管
- 整页文档解析接管
- MinerU 原生接口
- 手写识别全链路接管

实现策略仍然保持低风险：

- 不重写旧链路
- 不碰废弃架构
- 继续围绕 `src/backend/external_model` 扩展
- 通过入口分流完成能力接管
