# Tauri MVP (Phase2)

本目录是 LaTeXSnipper 的 Tauri MVP 骨架，包含：

- 主窗口骨架（识别 / 设置 / 日志）
- Daemon RPC 联调（contract 读取、health 握手、task submit/poll/cancel）
- Windows 窗口效果自动降级（Mica -> Acrylic -> none）

## 目录

- `src-tauri/src/contract.rs`: 读取冻结 RPC contract
- `src-tauri/src/rpc_client.rs`: TCP JSON-Line RPC 客户端
- `src-tauri/src/commands.rs`: Tauri 命令桥接
- `src-tauri/src/window_effects.rs`: Mica/Acrylic 自动降级
- `src-tauri/src/main.rs`: 命令注册 + 启动时应用窗口效果
- `dist/`: MVP 静态前端（无需额外前端构建工具）

## 启动

```powershell
cd apps/tauri-client/src-tauri
cargo tauri dev
```

## 命令

- `load_rpc_contract(contractPath?)`
- `daemon_health_handshake({ endpoint, contractPath? })`
- `daemon_task_submit({ endpoint, kind, params })`
- `daemon_task_status({ endpoint, taskId })`
- `daemon_task_poll({ endpoint, taskId, options? })`
- `daemon_task_submit_and_poll({ endpoint, kind, params, options? })`
- `daemon_task_cancel({ endpoint, taskId })`
- `apply_window_effects()`

## 说明

- 前端默认读取全局 `window.__TAURI__.core.invoke`。
- RPC contract 默认从仓库 `contracts/daemon_rpc_contract.v1.json` 搜索。
- 可通过环境变量覆盖 contract 路径：
  - `LATEXSNIPPER_RPC_CONTRACT=E:\path\daemon_rpc_contract.v1.json`
