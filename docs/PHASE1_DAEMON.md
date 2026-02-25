# Phase1 Daemon 骨架（已落地）

## 目标

- UI 线程不直接承载模型推理。
- 识别任务统一走本地 daemon RPC。
- 进程生命周期、任务状态、取消、异常都有可观测日志，便于后续 Tauri 对接。

## 当前默认策略

- 默认启用 daemon（`LATEXSNIPPER_USE_DAEMON` 未设置时即启用）。
- 回退开关：`LATEXSNIPPER_USE_DAEMON=0` 强制使用本地 `ModelWrapper`。

## RPC 方法

- `health`
- `warmup`
- `model_status`
- `predict_image`（保留兼容）
- `task_submit`
- `task_status`
- `task_cancel`
- `shutdown`

## 任务类型

- `predict_image`
- `predict_pdf`

## 任务状态

- `queued`
- `running`
- `success`
- `error`
- `cancelled`

## UI 链路（Phase1.5）

- 截图识别：`PredictionWorker -> model.predict(...) -> daemon task queue`
- PDF识别：`PdfPredictWorker -> model.predict_pdf(...) -> daemon task queue`
- 取消：`QProgressDialog cancel -> worker cancel flag -> client task_cancel -> daemon stop at safe checkpoint`

## 日志约定

- daemon 侧结构化事件：`[DAEMON_EVT] {...}`
- 主进程适配层事件：`[DAEMON_CLIENT_EVT] {...}`
- 主窗口收敛日志：`[DAEMON_EVT_HOST] / [DAEMON_ERR_HOST]`
