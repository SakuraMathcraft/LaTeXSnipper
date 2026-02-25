# Phase2 RPC 接口冻结

## 冻结文件

- JSON Contract（跨语言真源）：`contracts/daemon_rpc_contract.v1.json`
- Python 侧读取与常量入口：`src/backend/rpc_contract.py`

## 版本策略

- 当前版本：`1.0.0`
- 规则：
  - 向后兼容的小增量：仅增加可选字段，`minor` 升级（例如 `1.1.0`）
  - 破坏性变更：`major` 升级（例如 `2.0.0`）

## 已冻结枚举

- methods:
  - `health`
  - `warmup`
  - `model_status`
  - `predict_image`
  - `task_submit`
  - `task_status`
  - `task_cancel`
  - `shutdown`
- task kinds:
  - `predict_image`
  - `predict_pdf`
- task status:
  - `queued`
  - `running`
  - `success`
  - `error`
  - `cancelled`

## Rust/Tauri 侧建议

1. 启动时读取 `contracts/daemon_rpc_contract.v1.json`。
2. 先调用 `health`，检查返回 `contract.name/version`。
3. 若版本不匹配，前端提示“客户端与后端协议版本不兼容”并阻断任务提交。
4. 所有 RPC method / task kind / task status 均从 contract 枚举生成，不写硬编码字符串。
