use crate::contract::{load_contract, to_summary, ContractSummary, RpcContract};
use crate::rpc_client::{
    cancel_task, get_task_status, health_handshake, poll_task, shutdown_daemon, submit_and_poll,
    submit_task, DaemonEndpoint, HealthHandshakeResult, PollOptions, TaskSnapshot, TaskSubmitResult,
};
use crate::window_effects;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::Write;
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use sysinfo::System;
use tauri::Emitter;

#[cfg(target_os = "windows")]
use windows_sys::Win32::Graphics::Gdi::{
    BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, DeleteDC, DeleteObject, GetDC, GetDIBits,
    GetObjectW, ReleaseDC, SelectObject, BITMAP, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
    DIB_RGB_COLORS, HBITMAP, HDC, HGDIOBJ, SRCCOPY,
};
#[cfg(target_os = "windows")]
use windows_sys::Win32::System::DataExchange::{
    CloseClipboard, GetClipboardData, GetClipboardSequenceNumber, IsClipboardFormatAvailable,
    OpenClipboard,
};
#[cfg(target_os = "windows")]
use windows_sys::Win32::System::Ole::CF_BITMAP;
#[cfg(target_os = "windows")]
use windows_sys::Win32::System::Threading::GetCurrentThreadId;
#[cfg(target_os = "windows")]
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
    RegisterHotKey, SendInput, UnregisterHotKey, HOT_KEY_MODIFIERS, INPUT, INPUT_0, INPUT_KEYBOARD,
    KEYBDINPUT, KEYEVENTF_KEYUP, VK_LWIN, VK_SHIFT,
};
#[cfg(target_os = "windows")]
use windows_sys::Win32::UI::WindowsAndMessaging::{
    DispatchMessageW, GetMessageW, GetSystemMetrics, PeekMessageW, PostThreadMessageW,
    TranslateMessage, MSG, PM_NOREMOVE, SM_CXSCREEN, SM_CXVIRTUALSCREEN, SM_CYSCREEN,
    SM_CYVIRTUALSCREEN, SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, WM_HOTKEY,
};

#[derive(Debug, Clone, Deserialize)]
pub struct TaskSubmitInput {
    pub endpoint: DaemonEndpoint,
    pub kind: String,
    #[serde(default)]
    pub params: Value,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TaskStatusInput {
    pub endpoint: DaemonEndpoint,
    #[serde(alias = "taskId")]
    pub task_id: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TaskPollInput {
    pub endpoint: DaemonEndpoint,
    #[serde(alias = "taskId")]
    pub task_id: String,
    #[serde(default)]
    pub options: Option<PollOptions>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TaskSubmitAndPollInput {
    pub endpoint: DaemonEndpoint,
    pub kind: String,
    #[serde(default)]
    pub params: Value,
    #[serde(default)]
    pub options: Option<PollOptions>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct HandshakeInput {
    pub endpoint: DaemonEndpoint,
    #[serde(default)]
    #[serde(alias = "contractPath")]
    pub contract_path: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct WindowEffectsInput {
    #[serde(default)]
    pub mode: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct WindowCompactModeInput {
    #[serde(default)]
    pub compact: bool,
}

fn contract_for_path(path: Option<String>) -> Result<(std::path::PathBuf, RpcContract), String> {
    load_contract(path.as_deref())
}

#[derive(Debug, Clone)]
struct HotkeySpec {
    modifiers: u32,
    vk: u32,
    label: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct HotkeyRegisterInput {
    pub shortcut: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct HotkeyStatus {
    pub registered: bool,
    pub shortcut: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CaptureFileResult {
    pub path: String,
    pub width: i32,
    pub height: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct CaptureBase64Result {
    pub image_b64: String,
    pub width: i32,
    pub height: i32,
    pub format: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DaemonBootstrapInput {
    pub endpoint: DaemonEndpoint,
    #[serde(default)]
    pub model: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DaemonShutdownInput {
    pub endpoint: DaemonEndpoint,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PickFileInput {
    #[serde(default)]
    pub kind: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SetRuntimeEnvConfigInput {
    #[serde(alias = "installBaseDir")]
    pub install_base_dir: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LaunchDependencyWizardInput {
    #[serde(default)]
    #[serde(alias = "installBaseDir")]
    pub install_base_dir: Option<String>,
    #[serde(default)]
    #[serde(alias = "pythonExe")]
    pub python_exe: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DaemonBootstrapResult {
    pub ok: bool,
    pub pid: u32,
    pub message: String,
    pub endpoint: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RuntimeEnvConfig {
    pub config_path: String,
    pub install_base_dir: String,
    pub python_exe: String,
    pub cache_dir: String,
    pub deps_state_path: String,
    pub installed_layers: Vec<String>,
    pub failed_layers: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LaunchDependencyWizardResult {
    pub ok: bool,
    pub pid: u32,
    pub message: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SaveTextFileInput {
    pub content: String,
    #[serde(default)]
    #[serde(alias = "suggestedName")]
    pub suggested_name: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct AppInfo {
    pub name: String,
    pub version: String,
    pub os: String,
    pub arch: String,
    pub profile: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SystemUsage {
    pub cpu_percent: f32,
    pub memory_used_mb: u64,
    pub memory_total_mb: u64,
    pub memory_percent: f32,
    pub gpu_percent: Option<f32>,
    pub gpu_memory_used_mb: Option<u64>,
    pub gpu_memory_total_mb: Option<u64>,
    pub gpu_name: Option<String>,
    pub gpu_source: String,
}

const HOTKEY_ID: i32 = 0x4C53;
const HOTKEY_MSG_RELOAD: u32 = 0x8000 + 71;
const HOTKEY_MSG_STOP: u32 = 0x8000 + 72;
const HK_MOD_ALT: u32 = 0x0001;
const HK_MOD_CONTROL: u32 = 0x0002;
const HK_MOD_SHIFT: u32 = 0x0004;
const HK_MOD_WIN: u32 = 0x0008;
const HK_MOD_NOREPEAT: u32 = 0x4000;

static HOTKEY_THREAD_ID: AtomicU32 = AtomicU32::new(0);
static HOTKEY_PENDING_SPEC: OnceLock<Mutex<Option<HotkeySpec>>> = OnceLock::new();
static HOTKEY_CURRENT_LABEL: OnceLock<Mutex<Option<String>>> = OnceLock::new();
static SYSTEM_MONITOR: OnceLock<Mutex<System>> = OnceLock::new();

fn pending_spec_slot() -> &'static Mutex<Option<HotkeySpec>> {
    HOTKEY_PENDING_SPEC.get_or_init(|| Mutex::new(None))
}

fn current_hotkey_slot() -> &'static Mutex<Option<String>> {
    HOTKEY_CURRENT_LABEL.get_or_init(|| Mutex::new(None))
}

fn system_monitor() -> &'static Mutex<System> {
    SYSTEM_MONITOR.get_or_init(|| {
        let mut s = System::new_all();
        s.refresh_all();
        Mutex::new(s)
    })
}

fn set_current_hotkey_label(label: Option<String>) {
    if let Ok(mut guard) = current_hotkey_slot().lock() {
        *guard = label;
    }
}

fn get_current_hotkey_label() -> String {
    current_hotkey_slot()
        .lock()
        .ok()
        .and_then(|g| g.clone())
        .unwrap_or_default()
}

fn parse_vk(token_upper: &str) -> Option<u32> {
    if token_upper.len() == 1 {
        let ch = token_upper.chars().next()?;
        if ch.is_ascii_alphabetic() {
            return Some(ch as u32);
        }
        if ch.is_ascii_digit() {
            return Some(ch as u32);
        }
    }
    if let Some(num) = token_upper.strip_prefix('F') {
        if let Ok(v) = num.parse::<u32>() {
            if (1..=24).contains(&v) {
                return Some(0x70 + (v - 1));
            }
        }
    }
    match token_upper {
        "SPACE" => Some(0x20),
        "TAB" => Some(0x09),
        "ENTER" | "RETURN" => Some(0x0D),
        "ESC" | "ESCAPE" => Some(0x1B),
        "UP" => Some(0x26),
        "DOWN" => Some(0x28),
        "LEFT" => Some(0x25),
        "RIGHT" => Some(0x27),
        _ => None,
    }
}

fn parse_hotkey_shortcut(shortcut: &str) -> Result<HotkeySpec, String> {
    let raw = shortcut.trim();
    if raw.is_empty() {
        return Err("hotkey empty".to_string());
    }

    let mut modifiers: u32 = HK_MOD_NOREPEAT;
    let mut vk: Option<u32> = None;
    let mut normalized: Vec<String> = Vec::new();
    let parts = raw
        .split('+')
        .map(|x| x.trim())
        .filter(|x| !x.is_empty())
        .collect::<Vec<_>>();
    if parts.is_empty() {
        return Err("hotkey invalid".to_string());
    }

    for part in parts {
        let p = part.to_ascii_uppercase();
        match p.as_str() {
            "CTRL" | "CONTROL" => {
                modifiers |= HK_MOD_CONTROL;
                if !normalized.iter().any(|x| x == "Ctrl") {
                    normalized.push("Ctrl".to_string());
                }
            }
            "SHIFT" => {
                modifiers |= HK_MOD_SHIFT;
                if !normalized.iter().any(|x| x == "Shift") {
                    normalized.push("Shift".to_string());
                }
            }
            "ALT" => {
                modifiers |= HK_MOD_ALT;
                if !normalized.iter().any(|x| x == "Alt") {
                    normalized.push("Alt".to_string());
                }
            }
            "WIN" | "META" | "CMD" | "SUPER" => {
                modifiers |= HK_MOD_WIN;
                if !normalized.iter().any(|x| x == "Win") {
                    normalized.push("Win".to_string());
                }
            }
            _ => {
                if vk.is_some() {
                    return Err(format!("hotkey invalid: multiple key parts ({part})"));
                }
                vk = parse_vk(&p);
                if vk.is_none() {
                    return Err(format!("hotkey invalid key: {part}"));
                }
                normalized.push(part.to_ascii_uppercase());
            }
        }
    }

    let key = vk.ok_or_else(|| "hotkey missing key".to_string())?;
    if modifiers == HK_MOD_NOREPEAT {
        return Err("hotkey requires at least one modifier (Ctrl/Alt/Shift/Win)".to_string());
    }

    Ok(HotkeySpec {
        modifiers,
        vk: key,
        label: normalized.join("+"),
    })
}

#[cfg(target_os = "windows")]
fn apply_hotkey_on_thread(spec: &HotkeySpec, active: &mut Option<HotkeySpec>) -> bool {
    unsafe {
        if active.is_some() {
            let _ = UnregisterHotKey(std::ptr::null_mut(), HOTKEY_ID);
        }
        let ok = RegisterHotKey(
            std::ptr::null_mut(),
            HOTKEY_ID,
            spec.modifiers as HOT_KEY_MODIFIERS,
            spec.vk,
        );
        if ok != 0 {
            *active = Some(spec.clone());
            set_current_hotkey_label(Some(spec.label.clone()));
            true
        } else {
            *active = None;
            set_current_hotkey_label(None);
            false
        }
    }
}

#[cfg(target_os = "windows")]
fn start_hotkey_thread(app: tauri::AppHandle) -> Result<(), String> {
    std::thread::Builder::new()
        .name("latexsnipper-hotkey".to_string())
        .spawn(move || unsafe {
            let mut msg: MSG = std::mem::zeroed();
            PeekMessageW(&mut msg, std::ptr::null_mut(), 0, 0, PM_NOREMOVE);
            let tid = GetCurrentThreadId();
            HOTKEY_THREAD_ID.store(tid, Ordering::SeqCst);
            let _ = app.emit(
                "hotkey-status",
                json!({"ready": true, "thread_id": tid, "registered": false}),
            );

            let mut active: Option<HotkeySpec> = None;
            if let Ok(mut guard) = pending_spec_slot().lock() {
                if let Some(spec) = guard.take() {
                    let ok = apply_hotkey_on_thread(&spec, &mut active);
                    let _ = app.emit(
                        "hotkey-status",
                        json!({"registered": ok, "shortcut": spec.label, "error": if ok {""} else {"register failed"}}),
                    );
                }
            }

            loop {
                let ret = GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0);
                if ret <= 0 {
                    break;
                }
                match msg.message {
                    WM_HOTKEY => {
                        if msg.wParam as i32 == HOTKEY_ID {
                            let label = active
                                .as_ref()
                                .map(|h| h.label.clone())
                                .unwrap_or_else(|| "".to_string());
                            let _ = app.emit("global-hotkey-triggered", json!({"shortcut": label}));
                        }
                    }
                    HOTKEY_MSG_RELOAD => {
                        if let Ok(mut guard) = pending_spec_slot().lock() {
                            if let Some(spec) = guard.take() {
                                let ok = apply_hotkey_on_thread(&spec, &mut active);
                                let _ = app.emit(
                                    "hotkey-status",
                                    json!({"registered": ok, "shortcut": spec.label, "error": if ok {""} else {"register failed"}}),
                                );
                            }
                        }
                    }
                    HOTKEY_MSG_STOP => {
                        break;
                    }
                    _ => {
                        TranslateMessage(&msg);
                        DispatchMessageW(&msg);
                    }
                }
            }

            if active.is_some() {
                let _ = UnregisterHotKey(std::ptr::null_mut(), HOTKEY_ID);
            }
            set_current_hotkey_label(None);
            HOTKEY_THREAD_ID.store(0, Ordering::SeqCst);
            let _ = app.emit("hotkey-status", json!({"ready": false, "registered": false}));
        })
        .map(|_| ())
        .map_err(|e| format!("start hotkey thread failed: {e}"))
}

#[cfg(not(target_os = "windows"))]
fn start_hotkey_thread(_app: tauri::AppHandle) -> Result<(), String> {
    Err("global hotkey currently supported on Windows only".to_string())
}

#[cfg(target_os = "windows")]
fn post_hotkey_thread_message(message: u32) -> Result<(), String> {
    let tid = HOTKEY_THREAD_ID.load(Ordering::SeqCst);
    if tid == 0 {
        return Err("hotkey thread not running".to_string());
    }
    unsafe {
        let ok = PostThreadMessageW(tid, message, 0, 0);
        if ok == 0 {
            return Err("post hotkey message failed".to_string());
        }
    }
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn post_hotkey_thread_message(_message: u32) -> Result<(), String> {
    Err("global hotkey currently supported on Windows only".to_string())
}

#[cfg(target_os = "windows")]
#[allow(dead_code)]
fn key_input(vk: u16, flags: u32) -> INPUT {
    INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: vk,
                wScan: 0,
                dwFlags: flags,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    }
}

#[cfg(target_os = "windows")]
#[allow(dead_code)]
fn trigger_system_snipping_overlay() -> Result<u32, String> {
    let seq_before = unsafe { GetClipboardSequenceNumber() };
    let inputs = [
        key_input(VK_LWIN, 0),
        key_input(VK_SHIFT, 0),
        key_input(0x53, 0), // 'S'
        key_input(0x53, KEYEVENTF_KEYUP),
        key_input(VK_SHIFT, KEYEVENTF_KEYUP),
        key_input(VK_LWIN, KEYEVENTF_KEYUP),
    ];
    let sent = unsafe {
        SendInput(
            inputs.len() as u32,
            inputs.as_ptr(),
            std::mem::size_of::<INPUT>() as i32,
        )
    };
    if sent != inputs.len() as u32 {
        return Err("failed to trigger snipping overlay".to_string());
    }
    Ok(seq_before)
}

#[cfg(target_os = "windows")]
#[allow(dead_code)]
fn save_hbitmap_to_temp(hbitmap: HBITMAP) -> Result<CaptureFileResult, String> {
    unsafe {
        let mut bm: BITMAP = std::mem::zeroed();
        let got = GetObjectW(
            hbitmap as HGDIOBJ,
            std::mem::size_of::<BITMAP>() as i32,
            &mut bm as *mut _ as *mut core::ffi::c_void,
        );
        if got == 0 {
            return Err("GetObjectW(hbitmap) failed".to_string());
        }
        let width = bm.bmWidth;
        let height = bm.bmHeight;
        if width <= 0 || height <= 0 {
            return Err("clipboard bitmap has invalid size".to_string());
        }

        let hdc = CreateCompatibleDC(std::ptr::null_mut());
        if hdc.is_null() {
            return Err("CreateCompatibleDC failed".to_string());
        }
        let mut bmi: BITMAPINFO = std::mem::zeroed();
        bmi.bmiHeader = BITMAPINFOHEADER {
            biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: width,
            biHeight: -height,
            biPlanes: 1,
            biBitCount: 32,
            biCompression: BI_RGB,
            biSizeImage: (width as u32)
                .saturating_mul(height as u32)
                .saturating_mul(4),
            biXPelsPerMeter: 0,
            biYPelsPerMeter: 0,
            biClrUsed: 0,
            biClrImportant: 0,
        };
        let byte_len = (width as usize)
            .saturating_mul(height as usize)
            .saturating_mul(4);
        let mut pixels = vec![0u8; byte_len];
        let lines = GetDIBits(
            hdc,
            hbitmap,
            0,
            height as u32,
            pixels.as_mut_ptr() as *mut core::ffi::c_void,
            &mut bmi,
            DIB_RGB_COLORS,
        );
        let result = if lines > 0 {
            let mut path = std::env::temp_dir();
            let ts = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis();
            path.push(format!(
                "latexsnipper_capture_region_{}_{}.bmp",
                std::process::id(),
                ts
            ));
            write_bmp_32bpp(&path, width, height, &pixels).map(|_| CaptureFileResult {
                path: path.to_string_lossy().to_string(),
                width,
                height,
            })
        } else {
            Err("GetDIBits(clipboard) failed".to_string())
        };
        let _ = DeleteDC(hdc);
        result
    }
}

#[cfg(target_os = "windows")]
#[allow(dead_code)]
fn try_read_clipboard_bitmap_to_temp() -> Result<Option<CaptureFileResult>, String> {
    unsafe {
        if OpenClipboard(std::ptr::null_mut()) == 0 {
            return Ok(None);
        }
        let mut out: Result<Option<CaptureFileResult>, String> = Ok(None);
        if IsClipboardFormatAvailable(CF_BITMAP as u32) != 0 {
            let handle = GetClipboardData(CF_BITMAP as u32);
            if !handle.is_null() {
                let hbmp = handle as HBITMAP;
                out = save_hbitmap_to_temp(hbmp).map(Some);
            }
        }
        let _ = CloseClipboard();
        out
    }
}

#[cfg(target_os = "windows")]
#[allow(dead_code)]
fn capture_region_with_system_overlay() -> Result<CaptureFileResult, String> {
    let seq_before = trigger_system_snipping_overlay()?;
    let mut last_seq = seq_before;
    let deadline = Instant::now() + Duration::from_secs(45);
    let mut last_err: Option<String> = None;

    while Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(120));
        let seq = unsafe { GetClipboardSequenceNumber() };
        if seq == last_seq {
            continue;
        }
        last_seq = seq;
        match try_read_clipboard_bitmap_to_temp() {
            Ok(Some(file)) => return Ok(file),
            Ok(None) => continue,
            Err(e) => {
                last_err = Some(e);
                continue;
            }
        }
    }

    Err(last_err
        .unwrap_or_else(|| "region capture timeout or cancelled (no clipboard image)".to_string()))
}

#[derive(Debug, Deserialize)]
struct PyCaptureResult {
    ok: bool,
    #[serde(default)]
    path: Option<String>,
    #[serde(default)]
    width: Option<i32>,
    #[serde(default)]
    height: Option<i32>,
    #[serde(default)]
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct PyCaptureResultBase64 {
    ok: bool,
    #[serde(default)]
    image_b64: Option<String>,
    #[serde(default)]
    width: Option<i32>,
    #[serde(default)]
    height: Option<i32>,
    #[serde(default)]
    error: Option<String>,
}

#[cfg(target_os = "windows")]
fn capture_region_with_python_overlay() -> Result<CaptureFileResult, String> {
    let repo_root = find_repo_root().ok_or_else(|| {
        "repo root not found (missing src/backend/daemon_server.py)".to_string()
    })?;
    let src_root = repo_root.join("src");
    let pyexe = resolve_python_exe(&repo_root).ok_or_else(|| {
        "python311 not found; set LATEXSNIPPER_PYEXE or prepare src/deps/python311/python.exe"
            .to_string()
    })?;

    let script = r#"
import json, os, sys, tempfile
src = sys.argv[1]
if src and src not in sys.path:
    sys.path.insert(0, src)

from PyQt6.QtWidgets import QApplication
from backend.capture_overlay import ScreenCaptureOverlay

app = QApplication.instance() or QApplication(sys.argv)
overlay = ScreenCaptureOverlay()
result = {"ok": False, "error": "cancelled"}

def _done(pix):
    global result
    try:
        if pix is None or pix.isNull():
            result = {"ok": False, "error": "cancelled"}
        else:
            fd, path = tempfile.mkstemp(prefix="latexsnipper_capture_region_", suffix=".png")
            os.close(fd)
            if pix.save(path, "PNG"):
                result = {
                    "ok": True,
                    "path": path,
                    "width": int(pix.width()),
                    "height": int(pix.height()),
                }
            else:
                result = {"ok": False, "error": "save failed"}
    except Exception as ex:
        result = {"ok": False, "error": str(ex)}
    finally:
        try:
            overlay.close()
        except Exception:
            pass
        app.quit()

overlay.selection_done.connect(_done)
overlay.showFullScreen()
overlay.raise_()
overlay.activateWindow()
app.exec()
print("JSON:" + json.dumps(result, ensure_ascii=False))
"#;

    let mut cmd = Command::new(&pyexe);
    cmd.arg("-c")
        .arg(script)
        .arg(src_root.to_string_lossy().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .current_dir(&src_root);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let out = cmd
        .output()
        .map_err(|e| format!("spawn overlay capture failed (py={}): {e}", pyexe.display()))?;

    let stdout = String::from_utf8_lossy(&out.stdout).to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).to_string();
    if !out.status.success() {
        return Err(format!(
            "overlay capture process failed (code={:?}): {}",
            out.status.code(),
            if stderr.trim().is_empty() {
                stdout.trim().to_string()
            } else {
                stderr.trim().to_string()
            }
        ));
    }

    let payload_line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with("JSON:"))
        .ok_or_else(|| {
            format!(
                "overlay capture returned no JSON payload; stdout={} stderr={}",
                stdout.trim(),
                stderr.trim()
            )
        })?;
    let payload = payload_line
        .trim_start()
        .strip_prefix("JSON:")
        .ok_or_else(|| "invalid capture payload prefix".to_string())?;
    let parsed: PyCaptureResult =
        serde_json::from_str(payload).map_err(|e| format!("parse capture payload failed: {e}"))?;
    if !parsed.ok {
        return Err(parsed
            .error
            .unwrap_or_else(|| "region capture cancelled".to_string()));
    }
    let path = parsed.path.unwrap_or_default();
    if path.trim().is_empty() {
        return Err("capture succeeded but file path is empty".to_string());
    }
    Ok(CaptureFileResult {
        path,
        width: parsed.width.unwrap_or_default(),
        height: parsed.height.unwrap_or_default(),
    })
}

#[cfg(target_os = "windows")]
fn capture_region_with_python_overlay_base64() -> Result<CaptureBase64Result, String> {
    let repo_root = find_repo_root().ok_or_else(|| {
        "repo root not found (missing src/backend/daemon_server.py)".to_string()
    })?;
    let src_root = repo_root.join("src");
    let pyexe = resolve_python_exe(&repo_root).ok_or_else(|| {
        "python311 not found; set LATEXSNIPPER_PYEXE or prepare src/deps/python311/python.exe"
            .to_string()
    })?;

    let script = r#"
import base64, json, sys
src = sys.argv[1]
if src and src not in sys.path:
    sys.path.insert(0, src)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
from backend.capture_overlay import ScreenCaptureOverlay

app = QApplication.instance() or QApplication(sys.argv)
overlay = ScreenCaptureOverlay()
result = {"ok": False, "error": "cancelled"}

def _done(pix):
    global result
    try:
        if pix is None or pix.isNull():
            result = {"ok": False, "error": "cancelled"}
        else:
            ba = QByteArray()
            buf = QBuffer(ba)
            ok = buf.open(QIODevice.OpenModeFlag.WriteOnly)
            if not ok:
                result = {"ok": False, "error": "buffer open failed"}
            elif pix.save(buf, "PNG"):
                data = bytes(ba)
                result = {
                    "ok": True,
                    "image_b64": base64.b64encode(data).decode("ascii"),
                    "width": int(pix.width()),
                    "height": int(pix.height()),
                }
            else:
                result = {"ok": False, "error": "png encode failed"}
            try:
                buf.close()
            except Exception:
                pass
    except Exception as ex:
        result = {"ok": False, "error": str(ex)}
    finally:
        try:
            overlay.close()
        except Exception:
            pass
        app.quit()

overlay.selection_done.connect(_done)
overlay.showFullScreen()
overlay.raise_()
overlay.activateWindow()
app.exec()
print("JSON:" + json.dumps(result, ensure_ascii=False))
"#;

    let mut cmd = Command::new(&pyexe);
    cmd.arg("-c")
        .arg(script)
        .arg(src_root.to_string_lossy().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .current_dir(&src_root);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let out = cmd
        .output()
        .map_err(|e| format!("spawn overlay capture failed (py={}): {e}", pyexe.display()))?;

    let stdout = String::from_utf8_lossy(&out.stdout).to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).to_string();
    if !out.status.success() {
        return Err(format!(
            "overlay capture process failed (code={:?}): {}",
            out.status.code(),
            if stderr.trim().is_empty() {
                stdout.trim().to_string()
            } else {
                stderr.trim().to_string()
            }
        ));
    }

    let payload_line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with("JSON:"))
        .ok_or_else(|| {
            format!(
                "overlay capture returned no JSON payload; stdout={} stderr={}",
                stdout.trim(),
                stderr.trim()
            )
        })?;
    let payload = payload_line
        .trim_start()
        .strip_prefix("JSON:")
        .ok_or_else(|| "invalid capture payload prefix".to_string())?;
    let parsed: PyCaptureResultBase64 =
        serde_json::from_str(payload).map_err(|e| format!("parse capture payload failed: {e}"))?;
    if !parsed.ok {
        return Err(parsed
            .error
            .unwrap_or_else(|| "region capture cancelled".to_string()));
    }

    let image_b64 = parsed.image_b64.unwrap_or_default();
    if image_b64.trim().is_empty() {
        return Err("capture succeeded but image_b64 is empty".to_string());
    }
    Ok(CaptureBase64Result {
        image_b64,
        width: parsed.width.unwrap_or_default(),
        height: parsed.height.unwrap_or_default(),
        format: "png".to_string(),
    })
}

#[cfg(target_os = "windows")]
fn screen_capture_to_temp_bmp() -> Result<CaptureFileResult, String> {
    unsafe {
        let left = GetSystemMetrics(SM_XVIRTUALSCREEN);
        let top = GetSystemMetrics(SM_YVIRTUALSCREEN);
        let mut width = GetSystemMetrics(SM_CXVIRTUALSCREEN);
        let mut height = GetSystemMetrics(SM_CYVIRTUALSCREEN);
        if width <= 0 || height <= 0 {
            width = GetSystemMetrics(SM_CXSCREEN);
            height = GetSystemMetrics(SM_CYSCREEN);
        }
        if width <= 0 || height <= 0 {
            return Err("invalid screen size".to_string());
        }

        let hdc_screen: HDC = GetDC(std::ptr::null_mut());
        if hdc_screen.is_null() {
            return Err("GetDC failed".to_string());
        }
        let hdc_mem: HDC = CreateCompatibleDC(hdc_screen);
        if hdc_mem.is_null() {
            let _ = ReleaseDC(std::ptr::null_mut(), hdc_screen);
            return Err("CreateCompatibleDC failed".to_string());
        }
        let hbitmap: HBITMAP = CreateCompatibleBitmap(hdc_screen, width, height);
        if hbitmap.is_null() {
            let _ = DeleteDC(hdc_mem);
            let _ = ReleaseDC(std::ptr::null_mut(), hdc_screen);
            return Err("CreateCompatibleBitmap failed".to_string());
        }
        let old_obj: HGDIOBJ = SelectObject(hdc_mem, hbitmap as HGDIOBJ);
        let result = if BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, SRCCOPY) != 0 {
            let mut bmi: BITMAPINFO = std::mem::zeroed();
            bmi.bmiHeader = BITMAPINFOHEADER {
                biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                biWidth: width,
                biHeight: -height,
                biPlanes: 1,
                biBitCount: 32,
                biCompression: BI_RGB,
                biSizeImage: (width as u32)
                    .saturating_mul(height as u32)
                    .saturating_mul(4),
                biXPelsPerMeter: 0,
                biYPelsPerMeter: 0,
                biClrUsed: 0,
                biClrImportant: 0,
            };

            let byte_len = (width as usize)
                .saturating_mul(height as usize)
                .saturating_mul(4);
            let mut pixels = vec![0u8; byte_len];
            let lines = GetDIBits(
                hdc_mem,
                hbitmap,
                0,
                height as u32,
                pixels.as_mut_ptr() as *mut core::ffi::c_void,
                &mut bmi,
                DIB_RGB_COLORS,
            );

            if lines > 0 {
                let mut path = std::env::temp_dir();
                let ts = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_millis();
                path.push(format!(
                    "latexsnipper_capture_{}_{}.bmp",
                    std::process::id(),
                    ts
                ));

                write_bmp_32bpp(&path, width, height, &pixels).map(|_| CaptureFileResult {
                    path: path.to_string_lossy().to_string(),
                    width,
                    height,
                })
            } else {
                Err("GetDIBits failed".to_string())
            }
        } else {
            Err("BitBlt failed".to_string())
        };

        if !old_obj.is_null() {
            let _ = SelectObject(hdc_mem, old_obj);
        }
        let _ = DeleteObject(hbitmap as HGDIOBJ);
        let _ = DeleteDC(hdc_mem);
        let _ = ReleaseDC(std::ptr::null_mut(), hdc_screen);
        result
    }
}

fn write_bmp_32bpp(
    path: &std::path::Path,
    width: i32,
    height: i32,
    pixels: &[u8],
) -> Result<(), String> {
    if width <= 0 || height <= 0 {
        return Err("invalid bmp size".to_string());
    }
    let mut f = File::create(path).map_err(|e| format!("create bmp failed: {e}"))?;
    let image_size = pixels.len() as u32;
    let file_size = 14u32 + 40u32 + image_size;

    // BITMAPFILEHEADER (14 bytes)
    f.write_all(&0x4D42u16.to_le_bytes())
        .map_err(|e| format!("write bmp header failed: {e}"))?;
    f.write_all(&file_size.to_le_bytes())
        .map_err(|e| format!("write bmp size failed: {e}"))?;
    f.write_all(&0u16.to_le_bytes())
        .and_then(|_| f.write_all(&0u16.to_le_bytes()))
        .map_err(|e| format!("write bmp reserved failed: {e}"))?;
    f.write_all(&54u32.to_le_bytes())
        .map_err(|e| format!("write bmp offset failed: {e}"))?;

    // BITMAPINFOHEADER (40 bytes)
    f.write_all(&40u32.to_le_bytes())
        .map_err(|e| format!("write dib size failed: {e}"))?;
    f.write_all(&width.to_le_bytes())
        .map_err(|e| format!("write dib width failed: {e}"))?;
    f.write_all(&(-height).to_le_bytes())
        .map_err(|e| format!("write dib height failed: {e}"))?;
    f.write_all(&1u16.to_le_bytes())
        .map_err(|e| format!("write dib planes failed: {e}"))?;
    f.write_all(&32u16.to_le_bytes())
        .map_err(|e| format!("write dib bpp failed: {e}"))?;
    f.write_all(&0u32.to_le_bytes())
        .map_err(|e| format!("write dib compression failed: {e}"))?;
    f.write_all(&image_size.to_le_bytes())
        .map_err(|e| format!("write dib image size failed: {e}"))?;
    f.write_all(&0i32.to_le_bytes())
        .and_then(|_| f.write_all(&0i32.to_le_bytes()))
        .map_err(|e| format!("write dib ppm failed: {e}"))?;
    f.write_all(&0u32.to_le_bytes())
        .and_then(|_| f.write_all(&0u32.to_le_bytes()))
        .map_err(|e| format!("write dib color table failed: {e}"))?;

    f.write_all(pixels)
        .map_err(|e| format!("write bmp pixels failed: {e}"))?;
    Ok(())
}

#[tauri::command]
pub fn load_rpc_contract(contract_path: Option<String>) -> Result<ContractSummary, String> {
    let (path, c) = contract_for_path(contract_path)?;
    Ok(to_summary(&path, &c))
}

#[tauri::command]
pub fn daemon_health_handshake(input: HandshakeInput) -> Result<HealthHandshakeResult, String> {
    let (_, c) = contract_for_path(input.contract_path)?;
    health_handshake(&input.endpoint, &c)
}

#[tauri::command]
pub fn daemon_task_submit(input: TaskSubmitInput) -> Result<TaskSubmitResult, String> {
    submit_task(&input.endpoint, &input.kind, input.params)
}

#[tauri::command]
pub fn daemon_task_status(input: TaskStatusInput) -> Result<TaskSnapshot, String> {
    get_task_status(&input.endpoint, &input.task_id)
}

#[tauri::command]
pub fn daemon_task_poll(input: TaskPollInput) -> Result<TaskSnapshot, String> {
    poll_task(
        &input.endpoint,
        &input.task_id,
        input.options.unwrap_or(PollOptions {
            poll_interval_ms: Some(200),
            timeout_ms: Some(600_000),
        }),
    )
}

#[tauri::command]
pub fn daemon_task_submit_and_poll(input: TaskSubmitAndPollInput) -> Result<TaskSnapshot, String> {
    submit_and_poll(
        &input.endpoint,
        &input.kind,
        input.params,
        input.options.unwrap_or(PollOptions {
            poll_interval_ms: Some(200),
            timeout_ms: Some(600_000),
        }),
    )
}

#[tauri::command]
pub fn daemon_task_cancel(input: TaskStatusInput) -> Result<bool, String> {
    cancel_task(&input.endpoint, &input.task_id)
}

#[tauri::command]
pub fn apply_window_effects(
    window: tauri::WebviewWindow,
    input: Option<WindowEffectsInput>,
) -> Result<String, String> {
    let mode = input
        .and_then(|x| x.mode)
        .unwrap_or_else(|| "auto".to_string());
    window_effects::apply_mode(&window, &mode)
}

#[tauri::command]
pub fn set_window_compact_mode(
    window: tauri::WebviewWindow,
    input: Option<WindowCompactModeInput>,
) -> Result<bool, String> {
    let compact = input.map(|x| x.compact).unwrap_or(false);
    let (width, height) = if compact { (210.0, 250.0) } else { (1100.0, 760.0) };
    window
        .set_size(tauri::Size::Logical(tauri::LogicalSize::new(width, height)))
        .map_err(|e| format!("set window size failed: {e}"))?;
    window
        .set_resizable(!compact)
        .map_err(|e| format!("set resizable failed: {e}"))?;
    window
        .set_maximizable(!compact)
        .map_err(|e| format!("set maximizable failed: {e}"))?;
    window
        .set_minimizable(!compact)
        .map_err(|e| format!("set minimizable failed: {e}"))?;
    window
        .set_always_on_top(compact)
        .map_err(|e| format!("set always-on-top failed: {e}"))?;
    if compact {
        let _ = window.set_position(tauri::Position::Logical(tauri::LogicalPosition::new(
            120.0, 96.0,
        )));
    } else {
        let _ = window.center();
    }
    Ok(compact)
}

fn find_repo_root_from(start: &Path) -> Option<PathBuf> {
    let mut cur = Some(start);
    while let Some(p) = cur {
        if p.join("src").join("backend").join("daemon_server.py").exists() {
            return Some(p.to_path_buf());
        }
        cur = p.parent();
    }
    None
}

fn find_repo_root() -> Option<PathBuf> {
    if let Ok(cwd) = std::env::current_dir() {
        if let Some(p) = find_repo_root_from(&cwd) {
            return Some(p);
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            if let Some(p) = find_repo_root_from(parent) {
                return Some(p);
            }
        }
    }
    None
}

fn resolve_python_exe(repo_root: &Path) -> Option<PathBuf> {
    if let Ok(v) = std::env::var("LATEXSNIPPER_PYEXE") {
        let p = PathBuf::from(v.trim());
        if p.exists() {
            return Some(p);
        }
    }
    let candidates = [
        repo_root.join("src").join("deps").join("python311").join("python.exe"),
        repo_root.join("deps").join("python311").join("python.exe"),
    ];
    candidates.into_iter().find(|p| p.exists())
}

fn user_home_dir() -> PathBuf {
    if let Ok(v) = std::env::var("USERPROFILE") {
        let p = PathBuf::from(v.trim());
        if p.exists() {
            return p;
        }
    }
    if let Ok(v) = std::env::var("HOME") {
        let p = PathBuf::from(v.trim());
        if p.exists() {
            return p;
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn runtime_config_path() -> PathBuf {
    user_home_dir()
        .join(".latexsnipper")
        .join("LaTeXSnipper_config.json")
}

fn read_install_base_dir_from_runtime_config() -> Option<PathBuf> {
    let cfg = runtime_config_path();
    let txt = fs::read_to_string(cfg).ok()?;
    let v: Value = serde_json::from_str(&txt).ok()?;
    let raw = v.get("install_base_dir")?.as_str()?.trim();
    if raw.is_empty() {
        return None;
    }
    Some(PathBuf::from(raw))
}

fn write_install_base_dir_to_runtime_config(install_base_dir: &Path) -> Result<(), String> {
    let cfg = runtime_config_path();
    if let Some(parent) = cfg.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("create config dir failed: {e}"))?;
    }

    let mut doc = if cfg.exists() {
        let old = fs::read_to_string(&cfg).unwrap_or_default();
        serde_json::from_str::<Value>(&old).unwrap_or_else(|_| json!({}))
    } else {
        json!({})
    };
    if !doc.is_object() {
        doc = json!({});
    }
    if let Some(obj) = doc.as_object_mut() {
        obj.insert(
            "install_base_dir".to_string(),
            Value::String(install_base_dir.display().to_string()),
        );
    }
    fs::write(
        &cfg,
        serde_json::to_string_pretty(&doc)
            .map_err(|e| format!("serialize runtime config failed: {e}"))?,
    )
    .map_err(|e| format!("write runtime config failed: {e}"))?;
    Ok(())
}

fn resolve_install_base_dir(repo_root: &Path) -> PathBuf {
    if let Some(p) = read_install_base_dir_from_runtime_config() {
        return p;
    }
    repo_root.join("src").join("deps")
}

fn runtime_cache_dir() -> PathBuf {
    if let Ok(v) = std::env::var("APPDATA") {
        return PathBuf::from(v.trim()).join("pix2text");
    }
    user_home_dir().join(".cache").join("pix2text")
}

fn read_deps_state_layers(path: &Path) -> (Vec<String>, Vec<String>) {
    if !path.exists() {
        return (Vec::new(), Vec::new());
    }
    let text = match fs::read_to_string(path) {
        Ok(v) => v,
        Err(_) => return (Vec::new(), Vec::new()),
    };
    let doc: Value = match serde_json::from_str(&text) {
        Ok(v) => v,
        Err(_) => return (Vec::new(), Vec::new()),
    };
    let mut installed = doc
        .get("installed_layers")
        .and_then(|x| x.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.trim().to_uppercase()))
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let mut failed = doc
        .get("failed_layers")
        .and_then(|x| x.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.trim().to_uppercase()))
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    installed.sort();
    installed.dedup();
    failed.sort();
    failed.dedup();
    (installed, failed)
}

fn query_gpu_usage_nvidia() -> Option<(f32, u64, u64, String)> {
    let mut cmd = Command::new("nvidia-smi");
    cmd.args([
        "--query-gpu=utilization.gpu,memory.used,memory.total,name",
        "--format=csv,noheader,nounits",
    ])
    .stdin(Stdio::null())
    .stdout(Stdio::piped())
    .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let out = cmd.output().ok()?;
    if !out.status.success() {
        return None;
    }
    let txt = String::from_utf8_lossy(&out.stdout);
    let line = txt.lines().find(|x| !x.trim().is_empty())?.trim();
    let parts = line.split(',').map(|x| x.trim()).collect::<Vec<_>>();
    if parts.len() < 4 {
        return None;
    }
    let gpu = parts[0].parse::<f32>().ok()?;
    let mem_used = parts[1].parse::<u64>().ok()?;
    let mem_total = parts[2].parse::<u64>().ok()?;
    let name = parts[3].to_string();
    Some((gpu, mem_used, mem_total, name))
}

fn endpoint_addr(endpoint: &DaemonEndpoint) -> Result<std::net::SocketAddr, String> {
    let host = endpoint.host.trim();
    let raw = format!("{}:{}", if host.is_empty() { "127.0.0.1" } else { host }, endpoint.port);
    let mut addrs = raw
        .to_socket_addrs()
        .map_err(|e| format!("resolve daemon addr failed: {e}"))?;
    addrs
        .next()
        .ok_or_else(|| format!("resolve daemon addr returned none: {raw}"))
}

fn wait_port_open(endpoint: &DaemonEndpoint, timeout_ms: u64) -> bool {
    let addr = match endpoint_addr(endpoint) {
        Ok(v) => v,
        Err(_) => return false,
    };
    let deadline = Instant::now() + Duration::from_millis(timeout_ms.max(200));
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(240)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(120));
    }
    false
}

#[tauri::command]
pub fn daemon_bootstrap_local(input: DaemonBootstrapInput) -> Result<DaemonBootstrapResult, String> {
    let endpoint = input.endpoint;
    if endpoint.port == 0 {
        return Err("invalid daemon port: 0".to_string());
    }

    if wait_port_open(&endpoint, 300) {
        return Ok(DaemonBootstrapResult {
            ok: true,
            pid: 0,
            message: "daemon already reachable".to_string(),
            endpoint: format!("{}:{}", endpoint.host, endpoint.port),
        });
    }

    let repo_root = find_repo_root().ok_or_else(|| {
        "repo root not found (missing src/backend/daemon_server.py)".to_string()
    })?;
    let src_root = repo_root.join("src");
    let daemon_script = src_root.join("backend").join("daemon_server.py");
    if !daemon_script.exists() {
        return Err(format!(
            "daemon module not found: {}",
            daemon_script.display()
        ));
    }
    let pyexe = resolve_python_exe(&repo_root).ok_or_else(|| {
        "python311 not found; set LATEXSNIPPER_PYEXE or prepare src/deps/python311/python.exe".to_string()
    })?;
    let host = if endpoint.host.trim().is_empty() {
        "127.0.0.1".to_string()
    } else {
        endpoint.host.trim().to_string()
    };

    let mut cmd = Command::new(&pyexe);
    cmd.arg("-m")
        .arg("backend.daemon_server")
        .arg("--host")
        .arg(&host)
        .arg("--port")
        .arg(endpoint.port.to_string())
        .arg("--token")
        .arg(&endpoint.token)
        .arg("--model")
        .arg(input.model.unwrap_or_else(|| "pix2text".to_string()))
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONLEGACYWINDOWSSTDIO", "0")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .current_dir(&src_root);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x00000008;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NO_WINDOW);
    }

    let child = cmd
        .spawn()
        .map_err(|e| format!("spawn daemon failed (py={}): {e}", pyexe.display()))?;
    let pid = child.id();
    drop(child);

    Ok(DaemonBootstrapResult {
        ok: true,
        pid,
        message: format!(
            "daemon started (pid={pid}) using {}",
            pyexe.display()
        ),
        endpoint: format!("{}:{}", host, endpoint.port),
    })
}

#[tauri::command]
pub fn daemon_shutdown(input: DaemonShutdownInput) -> Result<bool, String> {
    shutdown_daemon(&input.endpoint)
}

#[tauri::command]
pub fn register_capture_hotkey(
    app: tauri::AppHandle,
    input: HotkeyRegisterInput,
) -> Result<HotkeyStatus, String> {
    let spec = parse_hotkey_shortcut(&input.shortcut)?;
    if let Ok(mut guard) = pending_spec_slot().lock() {
        *guard = Some(spec.clone());
    }

    let tid = HOTKEY_THREAD_ID.load(Ordering::SeqCst);
    if tid == 0 {
        start_hotkey_thread(app)?;
        // wait a short while for thread queue init
        for _ in 0..20 {
            if HOTKEY_THREAD_ID.load(Ordering::SeqCst) != 0 {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(15));
        }
    } else {
        post_hotkey_thread_message(HOTKEY_MSG_RELOAD)?;
    }

    Ok(HotkeyStatus {
        registered: HOTKEY_THREAD_ID.load(Ordering::SeqCst) != 0,
        shortcut: spec.label,
    })
}

#[tauri::command]
pub fn unregister_capture_hotkey() -> Result<HotkeyStatus, String> {
    let tid = HOTKEY_THREAD_ID.load(Ordering::SeqCst);
    if tid != 0 {
        post_hotkey_thread_message(HOTKEY_MSG_STOP)?;
    }
    set_current_hotkey_label(None);
    Ok(HotkeyStatus {
        registered: false,
        shortcut: "".to_string(),
    })
}

#[tauri::command]
pub fn get_capture_hotkey_status() -> Result<HotkeyStatus, String> {
    let tid = HOTKEY_THREAD_ID.load(Ordering::SeqCst);
    Ok(HotkeyStatus {
        registered: tid != 0,
        shortcut: get_current_hotkey_label(),
    })
}

#[tauri::command]
pub fn capture_screen_to_temp() -> Result<CaptureFileResult, String> {
    #[cfg(target_os = "windows")]
    {
        return screen_capture_to_temp_bmp();
    }
    #[cfg(not(target_os = "windows"))]
    {
        Err("screen capture currently supported on Windows only".to_string())
    }
}

#[tauri::command]
pub fn capture_region_to_temp() -> Result<CaptureFileResult, String> {
    #[cfg(target_os = "windows")]
    {
        return capture_region_with_python_overlay();
    }
    #[cfg(not(target_os = "windows"))]
    {
        Err("region capture currently supported on Windows only".to_string())
    }
}

#[tauri::command]
pub fn capture_region_to_base64() -> Result<CaptureBase64Result, String> {
    #[cfg(target_os = "windows")]
    {
        return capture_region_with_python_overlay_base64();
    }
    #[cfg(not(target_os = "windows"))]
    {
        Err("region capture currently supported on Windows only".to_string())
    }
}

#[tauri::command]
pub fn pick_file(input: Option<PickFileInput>) -> Result<Option<String>, String> {
    let kind = input
        .as_ref()
        .and_then(|x| x.kind.as_ref())
        .map(|x| x.trim().to_ascii_lowercase())
        .unwrap_or_default();

    if kind.as_str() == "folder" || kind.as_str() == "dir" || kind.as_str() == "directory" {
        let out = rfd::FileDialog::new().pick_folder();
        return Ok(out.map(|p| p.display().to_string()));
    }

    let mut dlg = rfd::FileDialog::new();
    match kind.as_str() {
        "image" => {
            dlg = dlg.add_filter("Image", &["png", "jpg", "jpeg", "bmp", "webp", "tif", "tiff"]);
        }
        "pdf" => {
            dlg = dlg.add_filter("PDF", &["pdf"]);
        }
        "python" => {
            dlg = dlg.add_filter("Python", &["exe", "bat", "cmd"]);
        }
        _ => {}
    }
    Ok(dlg.pick_file().map(|p| p.display().to_string()))
}

#[tauri::command]
pub fn open_path(path: String) -> Result<bool, String> {
    let p = PathBuf::from(path.trim());
    if p.as_os_str().is_empty() {
        return Err("path is empty".to_string());
    }
    if !p.exists() {
        return Err(format!("path not found: {}", p.display()));
    }
    let mut cmd = Command::new("explorer");
    cmd.arg(p.as_os_str())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x00000008;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NO_WINDOW);
    }
    cmd.spawn()
        .map_err(|e| format!("open path failed: {e}"))
        .map(|_| true)
}

#[tauri::command]
pub fn get_runtime_env_config() -> Result<RuntimeEnvConfig, String> {
    let repo_root = find_repo_root().ok_or_else(|| {
        "repo root not found (missing src/backend/daemon_server.py)".to_string()
    })?;
    let install_base_dir = resolve_install_base_dir(&repo_root);
    let cfg_path = runtime_config_path();
    let py = install_base_dir.join("python311").join("python.exe");
    let py_fallback = resolve_python_exe(&repo_root).unwrap_or(py.clone());
    let deps_state = install_base_dir.join(".deps_state.json");
    let (installed_layers, failed_layers) = read_deps_state_layers(&deps_state);
    Ok(RuntimeEnvConfig {
        config_path: cfg_path.display().to_string(),
        install_base_dir: install_base_dir.display().to_string(),
        python_exe: py_fallback.display().to_string(),
        cache_dir: runtime_cache_dir().display().to_string(),
        deps_state_path: deps_state.display().to_string(),
        installed_layers,
        failed_layers,
    })
}

#[tauri::command]
pub fn set_runtime_env_config(input: SetRuntimeEnvConfigInput) -> Result<bool, String> {
    let base = PathBuf::from(input.install_base_dir.trim());
    if base.as_os_str().is_empty() {
        return Err("install_base_dir is empty".to_string());
    }
    fs::create_dir_all(&base).map_err(|e| format!("create install_base_dir failed: {e}"))?;
    write_install_base_dir_to_runtime_config(&base)?;
    Ok(true)
}

#[tauri::command]
pub fn launch_dependency_wizard(
    input: Option<LaunchDependencyWizardInput>,
) -> Result<LaunchDependencyWizardResult, String> {
    let repo_root = find_repo_root().ok_or_else(|| {
        "repo root not found (missing src/backend/daemon_server.py)".to_string()
    })?;
    let src_root = repo_root.join("src");
    let chosen_base = input
        .as_ref()
        .and_then(|x| x.install_base_dir.as_ref())
        .map(|x| PathBuf::from(x.trim()))
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| resolve_install_base_dir(&repo_root));
    fs::create_dir_all(&chosen_base)
        .map_err(|e| format!("create install_base_dir failed: {e}"))?;
    write_install_base_dir_to_runtime_config(&chosen_base)?;

    let pyexe = input
        .as_ref()
        .and_then(|x| x.python_exe.as_ref())
        .map(|x| PathBuf::from(x.trim()))
        .filter(|p| p.exists())
        .or_else(|| resolve_python_exe(&repo_root))
        .ok_or_else(|| {
            "python311 not found; set LATEXSNIPPER_PYEXE or prepare src/deps/python311/python.exe"
                .to_string()
        })?;

    let script = r#"
import sys
src = sys.argv[1]
if src and src not in sys.path:
    sys.path.insert(0, src)
from PyQt6.QtWidgets import QApplication
import deps_bootstrap as db
app = QApplication.instance() or QApplication(sys.argv)
ok = bool(db.show_dependency_wizard(always_show_ui=True))
print("WIZARD_RESULT:" + ("ok" if ok else "cancel"))
"#;

    let mut cmd = Command::new(&pyexe);
    cmd.arg("-c")
        .arg(script)
        .arg(src_root.to_string_lossy().to_string())
        .env("LATEXSNIPPER_DEPS_DIR", chosen_base.to_string_lossy().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .current_dir(&src_root);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x00000008;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NO_WINDOW);
    }

    let child = cmd
        .spawn()
        .map_err(|e| format!("launch dependency wizard failed: {e}"))?;
    let pid = child.id();
    drop(child);

    Ok(LaunchDependencyWizardResult {
        ok: true,
        pid,
        message: format!("dependency wizard started (pid={pid})"),
    })
}

#[tauri::command]
pub fn get_system_usage() -> Result<SystemUsage, String> {
    let (cpu_percent, mem_used_mb, mem_total_mb, mem_percent) = {
        let mut guard = system_monitor()
            .lock()
            .map_err(|_| "system monitor lock poisoned".to_string())?;
        guard.refresh_cpu_usage();
        guard.refresh_memory();
        let cpu = guard.global_cpu_usage();
        let used = guard.used_memory() / 1024 / 1024;
        let total = guard.total_memory() / 1024 / 1024;
        let mem_pct = if total > 0 {
            ((used as f64 / total as f64) * 100.0) as f32
        } else {
            0.0
        };
        (cpu, used, total, mem_pct)
    };

    let (gpu_percent, gpu_memory_used_mb, gpu_memory_total_mb, gpu_name, gpu_source) =
        if let Some((g, mu, mt, name)) = query_gpu_usage_nvidia() {
            (Some(g), Some(mu), Some(mt), Some(name), "nvidia-smi".to_string())
        } else {
            (None, None, None, None, "unavailable".to_string())
        };

    Ok(SystemUsage {
        cpu_percent,
        memory_used_mb: mem_used_mb,
        memory_total_mb: mem_total_mb,
        memory_percent: mem_percent,
        gpu_percent,
        gpu_memory_used_mb,
        gpu_memory_total_mb,
        gpu_name,
        gpu_source,
    })
}

#[tauri::command]
pub fn save_text_file(input: SaveTextFileInput) -> Result<Option<String>, String> {
    let content = input.content;
    if content.trim().is_empty() {
        return Err("content is empty".to_string());
    }
    let mut dlg = rfd::FileDialog::new();
    if let Some(name) = input.suggested_name.as_ref().map(|x| x.trim()).filter(|x| !x.is_empty()) {
        dlg = dlg.set_file_name(name);
        let lower = name.to_ascii_lowercase();
        if lower.ends_with(".md") {
            dlg = dlg.add_filter("Markdown", &["md"]);
        } else if lower.ends_with(".tex") {
            dlg = dlg.add_filter("LaTeX", &["tex"]);
        } else if lower.ends_with(".txt") {
            dlg = dlg.add_filter("Text", &["txt"]);
        }
    }
    let out = dlg.save_file();
    let Some(path) = out else {
        return Ok(None);
    };
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("create parent dir failed: {e}"))?;
    }
    fs::write(&path, content).map_err(|e| format!("write file failed: {e}"))?;
    Ok(Some(path.display().to_string()))
}

#[tauri::command]
pub fn open_external_url(url: String) -> Result<bool, String> {
    let u = url.trim();
    if u.is_empty() {
        return Err("url is empty".to_string());
    }
    #[cfg(target_os = "windows")]
    {
        let mut cmd = Command::new("cmd");
        cmd.args(["/C", "start", "", u])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x00000008;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NO_WINDOW);
        cmd.spawn()
            .map_err(|e| format!("open url failed: {e}"))
            .map(|_| true)
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(u)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("open url failed: {e}"))
            .map(|_| true)
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(u)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("open url failed: {e}"))
            .map(|_| true)
    }
}

#[tauri::command]
pub fn get_app_info(app: tauri::AppHandle) -> Result<AppInfo, String> {
    let pkg = app.package_info();
    Ok(AppInfo {
        name: pkg.name.clone(),
        version: pkg.version.to_string(),
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        profile: if cfg!(debug_assertions) {
            "debug".to_string()
        } else {
            "release".to_string()
        },
    })
}
