use crate::contract::RpcContract;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DaemonEndpoint {
    pub host: String,
    pub port: u16,
    pub token: String,
    #[serde(default)]
    #[serde(alias = "timeoutMs")]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthHandshakeResult {
    pub ok: bool,
    pub endpoint: String,
    pub contract_name_expected: String,
    pub contract_version_expected: String,
    pub contract_name_remote: String,
    pub contract_version_remote: String,
    pub contract_match: bool,
    pub ready: bool,
    pub status: String,
    #[serde(default)]
    pub raw: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskSubmitResult {
    pub ok: bool,
    pub task_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskSnapshot {
    pub task_id: String,
    pub kind: String,
    pub status: String,
    #[serde(default)]
    pub progress_current: i64,
    #[serde(default)]
    pub progress_total: i64,
    #[serde(default)]
    pub error: String,
    #[serde(default)]
    pub error_type: String,
    #[serde(default)]
    pub error_code: String,
    #[serde(default)]
    pub details: Value,
    #[serde(default)]
    pub output: Value,
    #[serde(default)]
    pub raw: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PollOptions {
    #[serde(default)]
    #[serde(alias = "pollIntervalMs")]
    pub poll_interval_ms: Option<u64>,
    #[serde(default)]
    #[serde(alias = "timeoutMs")]
    pub timeout_ms: Option<u64>,
}

fn endpoint_addr(endpoint: &DaemonEndpoint) -> Result<std::net::SocketAddr, String> {
    let raw = format!("{}:{}", endpoint.host.trim(), endpoint.port);
    let mut addrs = raw
        .to_socket_addrs()
        .map_err(|e| format!("resolve daemon addr failed: {e}"))?;
    addrs
        .next()
        .ok_or_else(|| format!("resolve daemon addr returned none: {raw}"))
}

fn timeout(endpoint: &DaemonEndpoint) -> Duration {
    let ms = endpoint.timeout_ms.unwrap_or(12_000).clamp(500, 120_000);
    Duration::from_millis(ms)
}

fn rpc_call(endpoint: &DaemonEndpoint, method: &str, params: Value) -> Result<Value, String> {
    let addr = endpoint_addr(endpoint)?;
    let to = timeout(endpoint);

    let mut stream =
        TcpStream::connect_timeout(&addr, to).map_err(|e| format!("connect daemon failed: {e}"))?;
    stream
        .set_read_timeout(Some(to))
        .map_err(|e| format!("set read timeout failed: {e}"))?;
    stream
        .set_write_timeout(Some(to))
        .map_err(|e| format!("set write timeout failed: {e}"))?;

    let req = json!({
        "token": endpoint.token,
        "method": method,
        "params": params,
    });
    let mut line =
        serde_json::to_string(&req).map_err(|e| format!("serialize request failed: {e}"))?;
    line.push('\n');
    stream
        .write_all(line.as_bytes())
        .map_err(|e| format!("write request failed: {e}"))?;

    let mut reader = BufReader::new(stream);
    let mut buf = String::new();
    reader
        .read_line(&mut buf)
        .map_err(|e| format!("read response failed: {e}"))?;
    if buf.trim().is_empty() {
        return Err("empty daemon response".to_string());
    }
    let val: Value =
        serde_json::from_str(buf.trim()).map_err(|e| format!("parse response json failed: {e}"))?;
    Ok(val)
}

fn ensure_ok_response(v: &Value, method: &str) -> Result<(), String> {
    if v.get("ok").and_then(|x| x.as_bool()) == Some(true) {
        return Ok(());
    }
    let err = v
        .get("error")
        .and_then(|x| x.as_str())
        .unwrap_or("unknown error");
    let typ = v
        .get("error_type")
        .and_then(|x| x.as_str())
        .unwrap_or("RemoteError");
    Err(format!("{method} failed: {err} ({typ})"))
}

pub fn health_handshake(
    endpoint: &DaemonEndpoint,
    contract: &RpcContract,
) -> Result<HealthHandshakeResult, String> {
    let raw = rpc_call(endpoint, "health", json!({}))?;
    ensure_ok_response(&raw, "health")?;

    let remote = raw.get("contract").cloned().unwrap_or_else(|| json!({}));
    let remote_name = remote
        .get("name")
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .to_string();
    let remote_ver = remote
        .get("version")
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .to_string();
    let contract_match = remote_name == contract.name && remote_ver == contract.version;

    Ok(HealthHandshakeResult {
        ok: true,
        endpoint: format!("{}:{}", endpoint.host, endpoint.port),
        contract_name_expected: contract.name.clone(),
        contract_version_expected: contract.version.clone(),
        contract_name_remote: remote_name,
        contract_version_remote: remote_ver,
        contract_match,
        ready: raw.get("ready").and_then(|x| x.as_bool()).unwrap_or(false),
        status: raw
            .get("status")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        raw,
    })
}

pub fn submit_task(
    endpoint: &DaemonEndpoint,
    kind: &str,
    params: Value,
) -> Result<TaskSubmitResult, String> {
    let raw = rpc_call(
        endpoint,
        "task_submit",
        json!({
            "kind": kind,
            "params": params,
        }),
    )?;
    ensure_ok_response(&raw, "task_submit")?;
    let task_id = raw
        .get("task_id")
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .to_string();
    if task_id.is_empty() {
        return Err("task_submit failed: empty task_id".to_string());
    }
    Ok(TaskSubmitResult { ok: true, task_id })
}

pub fn get_task_status(endpoint: &DaemonEndpoint, task_id: &str) -> Result<TaskSnapshot, String> {
    let raw = rpc_call(
        endpoint,
        "task_status",
        json!({
            "task_id": task_id,
        }),
    )?;
    ensure_ok_response(&raw, "task_status")?;
    let t = raw
        .get("task")
        .and_then(|x| x.as_object())
        .ok_or_else(|| "task_status invalid: missing task object".to_string())?;

    Ok(TaskSnapshot {
        task_id: t
            .get("task_id")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        kind: t
            .get("kind")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        status: t
            .get("status")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        progress_current: t
            .get("progress_current")
            .and_then(|x| x.as_i64())
            .unwrap_or(0),
        progress_total: t
            .get("progress_total")
            .and_then(|x| x.as_i64())
            .unwrap_or(0),
        error: t
            .get("error")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        error_type: t
            .get("error_type")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        error_code: t
            .get("error_code")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        details: t.get("details").cloned().unwrap_or_else(|| json!({})),
        output: t.get("output").cloned().unwrap_or_else(|| json!({})),
        raw,
    })
}

pub fn cancel_task(endpoint: &DaemonEndpoint, task_id: &str) -> Result<bool, String> {
    let raw = rpc_call(
        endpoint,
        "task_cancel",
        json!({
            "task_id": task_id,
        }),
    )?;
    ensure_ok_response(&raw, "task_cancel")?;
    Ok(true)
}

pub fn shutdown_daemon(endpoint: &DaemonEndpoint) -> Result<bool, String> {
    let raw = rpc_call(endpoint, "shutdown", json!({}))?;
    ensure_ok_response(&raw, "shutdown")?;
    Ok(true)
}

pub fn poll_task(
    endpoint: &DaemonEndpoint,
    task_id: &str,
    opts: PollOptions,
) -> Result<TaskSnapshot, String> {
    let poll_ms = opts.poll_interval_ms.unwrap_or(200).clamp(50, 5000);
    let timeout_ms = opts.timeout_ms.unwrap_or(600_000).clamp(1_000, 7_200_000);
    let started = Instant::now();

    loop {
        let snap = get_task_status(endpoint, task_id)?;
        match snap.status.as_str() {
            "success" | "error" | "cancelled" => return Ok(snap),
            _ => {}
        }
        if started.elapsed() >= Duration::from_millis(timeout_ms) {
            return Err(format!("task polling timeout: {timeout_ms}ms"));
        }
        std::thread::sleep(Duration::from_millis(poll_ms));
    }
}

pub fn submit_and_poll(
    endpoint: &DaemonEndpoint,
    kind: &str,
    params: Value,
    opts: PollOptions,
) -> Result<TaskSnapshot, String> {
    let submit = submit_task(endpoint, kind, params)?;
    poll_task(endpoint, &submit.task_id, opts)
}
