use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

pub const DEFAULT_CONTRACT_FILE: &str = "daemon_rpc_contract.v1.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RpcContract {
    pub name: String,
    pub version: String,
    #[serde(default)]
    pub transport: serde_json::Value,
    #[serde(default)]
    pub auth: serde_json::Value,
    #[serde(default)]
    pub enums: RpcEnums,
    #[serde(default)]
    pub methods: HashMap<String, MethodSpec>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RpcEnums {
    #[serde(default)]
    pub methods: Vec<String>,
    #[serde(default)]
    pub task_kinds: Vec<String>,
    #[serde(default)]
    pub task_status: Vec<String>,
    #[serde(default)]
    pub task_terminal_status: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MethodSpec {
    #[serde(default)]
    pub params_required: Vec<String>,
    #[serde(default)]
    pub params_optional: Vec<String>,
    #[serde(default)]
    pub response_ok_fields: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ContractSummary {
    pub path: String,
    pub name: String,
    pub version: String,
    pub methods: Vec<String>,
    pub task_kinds: Vec<String>,
}

pub fn default_contract_candidates() -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = Vec::new();

    if let Ok(raw) = std::env::var("LATEXSNIPPER_RPC_CONTRACT") {
        let p = PathBuf::from(raw.trim());
        if !p.as_os_str().is_empty() {
            out.push(p);
        }
    }

    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    out.push(cwd.join("contracts").join(DEFAULT_CONTRACT_FILE));
    out.push(cwd.join("..").join("contracts").join(DEFAULT_CONTRACT_FILE));
    out.push(
        cwd.join("..")
            .join("..")
            .join("contracts")
            .join(DEFAULT_CONTRACT_FILE),
    );
    out.push(
        cwd.join("..")
            .join("..")
            .join("..")
            .join("contracts")
            .join(DEFAULT_CONTRACT_FILE),
    );

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            out.push(dir.join("contracts").join(DEFAULT_CONTRACT_FILE));
            out.push(dir.join("..").join("contracts").join(DEFAULT_CONTRACT_FILE));
            out.push(
                dir.join("..")
                    .join("..")
                    .join("contracts")
                    .join(DEFAULT_CONTRACT_FILE),
            );
        }
    }

    dedup_paths(out)
}

fn dedup_paths(input: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut seen = std::collections::HashSet::new();
    let mut out = Vec::new();
    for p in input {
        let key = p.to_string_lossy().to_lowercase();
        if seen.insert(key) {
            out.push(p);
        }
    }
    out
}

pub fn resolve_contract_path(explicit: Option<&str>) -> Result<PathBuf, String> {
    if let Some(v) = explicit {
        let p = PathBuf::from(v.trim());
        if p.exists() {
            return Ok(p);
        }
        return Err(format!("contract not found: {}", p.display()));
    }

    for p in default_contract_candidates() {
        if p.exists() {
            return Ok(p);
        }
    }
    Err("contract not found in default candidates".to_string())
}

pub fn load_contract_from_path(path: &Path) -> Result<RpcContract, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("read contract failed: {e}"))?;
    let contract: RpcContract =
        serde_json::from_str(&text).map_err(|e| format!("parse contract json failed: {e}"))?;
    if contract.name.trim().is_empty() || contract.version.trim().is_empty() {
        return Err("invalid contract: empty name/version".to_string());
    }
    Ok(contract)
}

pub fn load_contract(explicit: Option<&str>) -> Result<(PathBuf, RpcContract), String> {
    let p = resolve_contract_path(explicit)?;
    let c = load_contract_from_path(&p)?;
    Ok((p, c))
}

pub fn to_summary(path: &Path, c: &RpcContract) -> ContractSummary {
    ContractSummary {
        path: path.display().to_string(),
        name: c.name.clone(),
        version: c.version.clone(),
        methods: c.enums.methods.clone(),
        task_kinds: c.enums.task_kinds.clone(),
    }
}
