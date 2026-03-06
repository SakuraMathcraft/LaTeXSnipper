use crate::contract::{load_contract, to_summary, ContractSummary, RpcContract};
use crate::rpc_client::{
    cancel_task, get_task_status, health_handshake, poll_task, shutdown_daemon, submit_and_poll,
    submit_task, DaemonEndpoint, HealthHandshakeResult, PollOptions, TaskSnapshot, TaskSubmitResult,
};
use crate::window_effects;
use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;
use base64::Engine as _;
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
use windows_sys::Win32::Foundation::{
    ERROR_CLASS_ALREADY_EXISTS, GetLastError, HWND, LPARAM, LRESULT, POINT, WPARAM,
};
#[cfg(target_os = "windows")]
use windows_sys::Win32::Graphics::Gdi::{
    BeginPaint, BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, CreatePen, DeleteDC,
    DeleteObject, EndPaint, GetDC, GetDIBits, GetStockObject, IntersectClipRect, InvalidateRect,
    LineTo, MoveToEx, ReleaseDC, RestoreDC, SaveDC, ScreenToClient, SelectObject, SetBkMode,
    SetTextColor, StretchDIBits, TextOutW, UpdateWindow, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
    DIB_RGB_COLORS, HBITMAP, HDC, HGDIOBJ, HOLLOW_BRUSH, PAINTSTRUCT, PS_SOLID, SRCCOPY,
    TRANSPARENT,
};
#[cfg(target_os = "windows")]
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
#[cfg(target_os = "windows")]
use windows_sys::Win32::System::Threading::GetCurrentThreadId;
#[cfg(target_os = "windows")]
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
    RegisterHotKey, ReleaseCapture, SetCapture, SetFocus, UnregisterHotKey, HOT_KEY_MODIFIERS,
    VK_ESCAPE,
};
#[cfg(target_os = "windows")]
use windows_sys::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetCursorPos, GetMessageW,
    GetSystemMetrics, GetWindowLongPtrW, IsWindow, PeekMessageW, PostThreadMessageW, RegisterClassW,
    SetCursor, SetForegroundWindow, SetWindowLongPtrW, ShowWindow, TranslateMessage, CREATESTRUCTW,
    CS_HREDRAW, CS_VREDRAW, GWLP_USERDATA, MSG, PM_NOREMOVE, PM_REMOVE, SM_CXSCREEN,
    SM_CXVIRTUALSCREEN, SM_CYSCREEN, SM_CYVIRTUALSCREEN, SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN,
    SW_SHOW, WM_DESTROY, WM_ERASEBKGND, WM_HOTKEY, WM_KEYDOWN, WM_LBUTTONDOWN, WM_LBUTTONUP,
    WM_MOUSEMOVE, WM_NCCREATE, WM_PAINT, WM_QUIT, WM_RBUTTONDOWN, WM_SETCURSOR, WM_SIZE,
    WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP, WNDCLASSW,
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

#[cfg(target_os = "windows")]
#[derive(Debug, Clone)]
struct CaptureOverlaySelection {
    x_ratio: f64,
    y_ratio: f64,
    width_ratio: f64,
    height_ratio: f64,
}

#[cfg(target_os = "windows")]
#[derive(Debug, Clone)]
struct ScreenCaptureRaw {
    left: i32,
    top: i32,
    width: i32,
    height: i32,
    pixels: Vec<u8>,
}

#[cfg(target_os = "windows")]
#[derive(Debug)]
struct NativeCaptureOverlayContext {
    image_width: i32,
    image_height: i32,
    view_width: i32,
    view_height: i32,
    pixels_ptr: *const u8,
    pixels_len: usize,
    dark_pixels_ptr: *const u8,
    dark_pixels_len: usize,
    dragging: bool,
    start_x: i32,
    start_y: i32,
    cur_x: i32,
    cur_y: i32,
    has_cursor: bool,
    result: Option<CaptureOverlaySelection>,
    cancelled: bool,
    done: bool,
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
const NATIVE_CAPTURE_OVERLAY_CLASS: &str = "LaTeXSnipperNativeCaptureOverlay";

#[cfg(target_os = "windows")]
fn virtual_screen_bounds() -> Result<(i32, i32, i32, i32), String> {
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
        Ok((left, top, width, height))
    }
}

#[cfg(target_os = "windows")]
fn capture_virtual_screen_raw() -> Result<ScreenCaptureRaw, String> {
    let (left, top, width, height) = virtual_screen_bounds()?;
    unsafe {
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
                Ok(ScreenCaptureRaw {
                    left,
                    top,
                    width,
                    height,
                    pixels,
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

#[cfg(target_os = "windows")]
fn clamp_ratio(v: f64) -> f64 {
    if v.is_finite() {
        v.clamp(0.0, 1.0)
    } else {
        0.0
    }
}

#[cfg(target_os = "windows")]
fn to_wide_null(text: &str) -> Vec<u16> {
    let mut out = text.encode_utf16().collect::<Vec<u16>>();
    out.push(0);
    out
}

#[cfg(target_os = "windows")]
fn lparam_x(lparam: LPARAM) -> i32 {
    ((lparam as u32 & 0xffff) as i16) as i32
}

#[cfg(target_os = "windows")]
fn lparam_y(lparam: LPARAM) -> i32 {
    (((lparam as u32 >> 16) & 0xffff) as i16) as i32
}

#[cfg(target_os = "windows")]
fn clamp_client_pos(v: i32, max: i32) -> i32 {
    let upper = max.saturating_sub(1).max(0);
    v.clamp(0, upper)
}

#[cfg(target_os = "windows")]
unsafe fn overlay_ctx_mut(hwnd: HWND) -> Option<&'static mut NativeCaptureOverlayContext> {
    let ptr = GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *mut NativeCaptureOverlayContext;
    if ptr.is_null() {
        None
    } else {
        Some(&mut *ptr)
    }
}

#[cfg(target_os = "windows")]
unsafe extern "system" fn native_capture_overlay_wndproc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_NCCREATE => {
            let cs = lparam as *const CREATESTRUCTW;
            if cs.is_null() {
                return 0;
            }
            let ctx_ptr = (*cs).lpCreateParams as *mut NativeCaptureOverlayContext;
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, ctx_ptr as isize);
            return 1;
        }
        WM_ERASEBKGND => return 1,
        WM_SETCURSOR => {
            SetCursor(std::ptr::null_mut());
            return 1;
        }
        WM_SIZE => {
            if let Some(ctx) = overlay_ctx_mut(hwnd) {
                let w = (lparam as u32 & 0xffff) as i32;
                let h = ((lparam as u32 >> 16) & 0xffff) as i32;
                if w > 0 {
                    ctx.view_width = w;
                }
                if h > 0 {
                    ctx.view_height = h;
                }
                ctx.cur_x = clamp_client_pos(ctx.cur_x, ctx.view_width);
                ctx.cur_y = clamp_client_pos(ctx.cur_y, ctx.view_height);
            }
            return 0;
        }
        WM_KEYDOWN => {
            if (wparam as u16) == VK_ESCAPE {
                if let Some(ctx) = overlay_ctx_mut(hwnd) {
                    ctx.cancelled = true;
                    ctx.done = true;
                }
                DestroyWindow(hwnd);
                return 0;
            }
        }
        WM_RBUTTONDOWN => {
            if let Some(ctx) = overlay_ctx_mut(hwnd) {
                ctx.cancelled = true;
                ctx.done = true;
            }
            DestroyWindow(hwnd);
            return 0;
        }
        WM_LBUTTONDOWN => {
            if let Some(ctx) = overlay_ctx_mut(hwnd) {
                let x = clamp_client_pos(lparam_x(lparam), ctx.view_width);
                let y = clamp_client_pos(lparam_y(lparam), ctx.view_height);
                ctx.dragging = true;
                ctx.start_x = x;
                ctx.start_y = y;
                ctx.cur_x = x;
                ctx.cur_y = y;
                ctx.has_cursor = true;
                SetCapture(hwnd);
                InvalidateRect(hwnd, std::ptr::null(), 0);
            }
            return 0;
        }
        WM_MOUSEMOVE => {
            if let Some(ctx) = overlay_ctx_mut(hwnd) {
                let x = clamp_client_pos(lparam_x(lparam), ctx.view_width);
                let y = clamp_client_pos(lparam_y(lparam), ctx.view_height);
                ctx.cur_x = x;
                ctx.cur_y = y;
                ctx.has_cursor = true;
                InvalidateRect(hwnd, std::ptr::null(), 0);
            }
            return 0;
        }
        WM_LBUTTONUP => {
            if let Some(ctx) = overlay_ctx_mut(hwnd) {
                let x = clamp_client_pos(lparam_x(lparam), ctx.view_width);
                let y = clamp_client_pos(lparam_y(lparam), ctx.view_height);
                ctx.cur_x = x;
                ctx.cur_y = y;
                ctx.has_cursor = true;
                if ctx.dragging {
                    ctx.dragging = false;
                    ReleaseCapture();
                    let left = ctx.start_x.min(ctx.cur_x);
                    let top = ctx.start_y.min(ctx.cur_y);
                    let w = (ctx.cur_x - ctx.start_x).abs();
                    let h = (ctx.cur_y - ctx.start_y).abs();
                    if w >= 2 && h >= 2 && ctx.view_width > 0 && ctx.view_height > 0 {
                        ctx.result = Some(CaptureOverlaySelection {
                            x_ratio: clamp_ratio(left as f64 / ctx.view_width as f64),
                            y_ratio: clamp_ratio(top as f64 / ctx.view_height as f64),
                            width_ratio: clamp_ratio(w as f64 / ctx.view_width as f64),
                            height_ratio: clamp_ratio(h as f64 / ctx.view_height as f64),
                        });
                        ctx.cancelled = false;
                    } else {
                        ctx.cancelled = true;
                    }
                    ctx.done = true;
                    DestroyWindow(hwnd);
                }
            }
            return 0;
        }
        WM_PAINT => {
            let mut ps: PAINTSTRUCT = std::mem::zeroed();
            let hdc = BeginPaint(hwnd, &mut ps);
            if !hdc.is_null() {
                if let Some(ctx) = overlay_ctx_mut(hwnd) {
                    if !ctx.dark_pixels_ptr.is_null() && ctx.image_width > 0 && ctx.image_height > 0 {
                        let expected = (ctx.image_width as usize)
                            .saturating_mul(ctx.image_height as usize)
                            .saturating_mul(4);
                        if ctx.dark_pixels_len >= expected {
                            let mut bmi: BITMAPINFO = std::mem::zeroed();
                            bmi.bmiHeader = BITMAPINFOHEADER {
                                biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                                biWidth: ctx.image_width,
                                biHeight: -ctx.image_height,
                                biPlanes: 1,
                                biBitCount: 32,
                                biCompression: BI_RGB,
                                biSizeImage: (ctx.image_width as u32)
                                    .saturating_mul(ctx.image_height as u32)
                                    .saturating_mul(4),
                                biXPelsPerMeter: 0,
                                biYPelsPerMeter: 0,
                                biClrUsed: 0,
                                biClrImportant: 0,
                            };
                            let _ = StretchDIBits(
                                hdc,
                                0,
                                0,
                                ctx.view_width,
                                ctx.view_height,
                                0,
                                0,
                                ctx.image_width,
                                ctx.image_height,
                                ctx.dark_pixels_ptr as *const core::ffi::c_void,
                                &bmi,
                                DIB_RGB_COLORS,
                                SRCCOPY,
                            );

                            if ctx.dragging && !ctx.pixels_ptr.is_null() && ctx.pixels_len >= expected {
                                let left = ctx.start_x.min(ctx.cur_x);
                                let top = ctx.start_y.min(ctx.cur_y);
                                let right = ctx.start_x.max(ctx.cur_x);
                                let bottom = ctx.start_y.max(ctx.cur_y);
                                let w = (right - left).max(0);
                                let h = (bottom - top).max(0);
                                if w > 0 && h > 0 && ctx.view_width > 0 && ctx.view_height > 0 {
                                    let saved = SaveDC(hdc);
                                    if saved > 0 {
                                        let _ = IntersectClipRect(hdc, left, top, right, bottom);
                                        let _ = StretchDIBits(
                                            hdc,
                                            0,
                                            0,
                                            ctx.view_width,
                                            ctx.view_height,
                                            0,
                                            0,
                                            ctx.image_width,
                                            ctx.image_height,
                                            ctx.pixels_ptr as *const core::ffi::c_void,
                                            &bmi,
                                            DIB_RGB_COLORS,
                                            SRCCOPY,
                                        );
                                        let _ = RestoreDC(hdc, saved);
                                    }
                                }
                            }
                        }
                    }

                    if ctx.has_cursor {
                        let arm = 14;
                        let x0 = (ctx.cur_x - arm).max(0);
                        let x1 = (ctx.cur_x + arm).min(ctx.view_width.saturating_sub(1));
                        let y0 = (ctx.cur_y - arm).max(0);
                        let y1 = (ctx.cur_y + arm).min(ctx.view_height.saturating_sub(1));
                        let pen_b = CreatePen(PS_SOLID, 3, 0x000000);
                        if !pen_b.is_null() {
                            let old = SelectObject(hdc, pen_b as HGDIOBJ);
                            let _ = MoveToEx(hdc, x0, ctx.cur_y, std::ptr::null_mut());
                            let _ = LineTo(hdc, x1, ctx.cur_y);
                            let _ = MoveToEx(hdc, ctx.cur_x, y0, std::ptr::null_mut());
                            let _ = LineTo(hdc, ctx.cur_x, y1);
                            let _ = SelectObject(hdc, old);
                            let _ = DeleteObject(pen_b as HGDIOBJ);
                        }
                        let pen_w = CreatePen(PS_SOLID, 1, 0x00FFFFFF);
                        if !pen_w.is_null() {
                            let old = SelectObject(hdc, pen_w as HGDIOBJ);
                            let _ = MoveToEx(hdc, x0, ctx.cur_y, std::ptr::null_mut());
                            let _ = LineTo(hdc, x1, ctx.cur_y);
                            let _ = MoveToEx(hdc, ctx.cur_x, y0, std::ptr::null_mut());
                            let _ = LineTo(hdc, ctx.cur_x, y1);
                            let _ = SelectObject(hdc, old);
                            let _ = DeleteObject(pen_w as HGDIOBJ);
                        }
                    }

                    if ctx.dragging {
                        let left = ctx.start_x.min(ctx.cur_x);
                        let top = ctx.start_y.min(ctx.cur_y);
                        let right = ctx.start_x.max(ctx.cur_x);
                        let bottom = ctx.start_y.max(ctx.cur_y);
                        let w = right - left;
                        let h = bottom - top;
                        let _ = SelectObject(hdc, GetStockObject(HOLLOW_BRUSH) as HGDIOBJ);

                        let pen_b = CreatePen(PS_SOLID, 3, 0x000000);
                        if !pen_b.is_null() {
                            let old = SelectObject(hdc, pen_b as HGDIOBJ);
                            let _ = MoveToEx(hdc, left, top, std::ptr::null_mut());
                            let _ = LineTo(hdc, right, top);
                            let _ = LineTo(hdc, right, bottom);
                            let _ = LineTo(hdc, left, bottom);
                            let _ = LineTo(hdc, left, top);
                            let _ = SelectObject(hdc, old);
                            let _ = DeleteObject(pen_b as HGDIOBJ);
                        }

                        let pen_w = CreatePen(PS_SOLID, 1, 0x00FFFFFF);
                        if !pen_w.is_null() {
                            let old = SelectObject(hdc, pen_w as HGDIOBJ);
                            let _ = MoveToEx(hdc, left, top, std::ptr::null_mut());
                            let _ = LineTo(hdc, right, top);
                            let _ = LineTo(hdc, right, bottom);
                            let _ = LineTo(hdc, left, bottom);
                            let _ = LineTo(hdc, left, top);
                            let _ = SelectObject(hdc, old);
                            let _ = DeleteObject(pen_w as HGDIOBJ);
                        }

                        if w > 0 && h > 0 {
                            let text = format!("{w} x {h} | ({left}, {top})");
                            let text_w = to_wide_null(&text);
                            let tx = (left + 8).clamp(6, (ctx.view_width - 240).max(6));
                            let mut ty = if top > 30 { top - 24 } else { bottom + 8 };
                            ty = ty.clamp(6, (ctx.view_height - 24).max(6));
                            let _ = SetBkMode(hdc, TRANSPARENT as i32);
                            let _ = SetTextColor(hdc, 0x00FFFFFF);
                            let _ = TextOutW(
                                hdc,
                                tx,
                                ty,
                                text_w.as_ptr(),
                                (text_w.len().saturating_sub(1)) as i32,
                            );
                        }
                    }
                }
            }
            EndPaint(hwnd, &ps);
            return 0;
        }
        WM_DESTROY => {
            if let Some(ctx) = overlay_ctx_mut(hwnd) {
                if !ctx.done {
                    ctx.cancelled = true;
                    ctx.done = true;
                }
            }
            return 0;
        }
        _ => {}
    }
    DefWindowProcW(hwnd, msg, wparam, lparam)
}

#[cfg(target_os = "windows")]
fn run_native_capture_overlay_selection(raw: &ScreenCaptureRaw) -> Result<CaptureOverlaySelection, String> {
    if raw.width <= 0 || raw.height <= 0 {
        return Err("invalid screen size for overlay".to_string());
    }

    let mut dark_pixels = raw.pixels.clone();
    for px in dark_pixels.chunks_exact_mut(4) {
        px[0] = ((px[0] as u16 * 38) / 100) as u8;
        px[1] = ((px[1] as u16 * 38) / 100) as u8;
        px[2] = ((px[2] as u16 * 38) / 100) as u8;
    }

    unsafe {
        let class_name = to_wide_null(NATIVE_CAPTURE_OVERLAY_CLASS);
        let title = to_wide_null("Capture Overlay");
        let hinstance = GetModuleHandleW(std::ptr::null());
        let mut wc: WNDCLASSW = std::mem::zeroed();
        wc.style = CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc = Some(native_capture_overlay_wndproc);
        wc.hInstance = hinstance;
        wc.hCursor = std::ptr::null_mut();
        wc.lpszClassName = class_name.as_ptr();
        let reg = RegisterClassW(&wc);
        if reg == 0 {
            let err = GetLastError();
            if err != ERROR_CLASS_ALREADY_EXISTS {
                return Err(format!("register native overlay class failed: {err}"));
            }
        }

        let ctx_ptr = Box::into_raw(Box::new(NativeCaptureOverlayContext {
            image_width: raw.width,
            image_height: raw.height,
            view_width: raw.width,
            view_height: raw.height,
            pixels_ptr: raw.pixels.as_ptr(),
            pixels_len: raw.pixels.len(),
            dark_pixels_ptr: dark_pixels.as_ptr(),
            dark_pixels_len: dark_pixels.len(),
            dragging: false,
            start_x: 0,
            start_y: 0,
            cur_x: 0,
            cur_y: 0,
            has_cursor: false,
            result: None,
            cancelled: false,
            done: false,
        }));

        let hwnd = CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            class_name.as_ptr(),
            title.as_ptr(),
            WS_POPUP,
            raw.left,
            raw.top,
            raw.width,
            raw.height,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            hinstance,
            ctx_ptr as *mut core::ffi::c_void,
        );
        if hwnd.is_null() {
            let _ = Box::from_raw(ctx_ptr);
            return Err("create native capture overlay window failed".to_string());
        }

        let mut pt: POINT = std::mem::zeroed();
        if GetCursorPos(&mut pt) != 0 {
            let _ = ScreenToClient(hwnd, &mut pt);
            let ctx = &mut *ctx_ptr;
            ctx.cur_x = clamp_client_pos(pt.x, ctx.view_width);
            ctx.cur_y = clamp_client_pos(pt.y, ctx.view_height);
            ctx.has_cursor = true;
        }

        ShowWindow(hwnd, SW_SHOW);
        UpdateWindow(hwnd);
        SetForegroundWindow(hwnd);
        SetFocus(hwnd);
        InvalidateRect(hwnd, std::ptr::null(), 0);

        let started = Instant::now();
        loop {
            let mut msg: MSG = std::mem::zeroed();
            while PeekMessageW(&mut msg, std::ptr::null_mut(), 0, 0, PM_REMOVE) != 0 {
                if msg.message == WM_QUIT {
                    (*ctx_ptr).done = true;
                    break;
                }
                TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
            if (*ctx_ptr).done {
                break;
            }
            if started.elapsed() > Duration::from_secs(120) {
                (*ctx_ptr).cancelled = true;
                (*ctx_ptr).done = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(8));
        }

        if IsWindow(hwnd) != 0 {
            DestroyWindow(hwnd);
        }
        let ctx = Box::from_raw(ctx_ptr);
        if let Some(sel) = ctx.result {
            return Ok(sel);
        }
        if ctx.cancelled {
            return Err("region capture cancelled".to_string());
        }
        Err("region capture failed".to_string())
    }
}

#[cfg(target_os = "windows")]
fn crop_capture_raw_by_ratio(
    raw: &ScreenCaptureRaw,
    sel: &CaptureOverlaySelection,
) -> Result<ScreenCaptureRaw, String> {
    if raw.width <= 0 || raw.height <= 0 {
        return Err("invalid raw capture size".to_string());
    }
    let mut x0 = (clamp_ratio(sel.x_ratio) * raw.width as f64).floor() as i32;
    let mut y0 = (clamp_ratio(sel.y_ratio) * raw.height as f64).floor() as i32;
    let mut x1 = (clamp_ratio(sel.x_ratio + sel.width_ratio) * raw.width as f64).ceil() as i32;
    let mut y1 = (clamp_ratio(sel.y_ratio + sel.height_ratio) * raw.height as f64).ceil() as i32;

    x0 = x0.clamp(0, raw.width.saturating_sub(1).max(0));
    y0 = y0.clamp(0, raw.height.saturating_sub(1).max(0));
    x1 = x1.clamp(x0 + 1, raw.width.max(1));
    y1 = y1.clamp(y0 + 1, raw.height.max(1));

    let crop_w = x1 - x0;
    let crop_h = y1 - y0;
    if crop_w <= 0 || crop_h <= 0 {
        return Err("invalid capture region".to_string());
    }

    let src_stride = (raw.width as usize).saturating_mul(4);
    let row_bytes = (crop_w as usize).saturating_mul(4);
    let mut out = vec![0u8; row_bytes.saturating_mul(crop_h as usize)];
    for row in 0..crop_h as usize {
        let src_y = y0 as usize + row;
        let src_start = src_y
            .saturating_mul(src_stride)
            .saturating_add((x0 as usize).saturating_mul(4));
        let src_end = src_start.saturating_add(row_bytes);
        let dst_start = row.saturating_mul(row_bytes);
        let dst_end = dst_start.saturating_add(row_bytes);
        if src_end > raw.pixels.len() || dst_end > out.len() {
            return Err("capture crop buffer overflow".to_string());
        }
        out[dst_start..dst_end].copy_from_slice(&raw.pixels[src_start..src_end]);
    }

    Ok(ScreenCaptureRaw {
        left: raw.left + x0,
        top: raw.top + y0,
        width: crop_w,
        height: crop_h,
        pixels: out,
    })
}

#[cfg(target_os = "windows")]
fn capture_region_with_native_overlay_raw() -> Result<ScreenCaptureRaw, String> {
    let raw = capture_virtual_screen_raw()?;
    let selection = run_native_capture_overlay_selection(&raw)?;
    crop_capture_raw_by_ratio(&raw, &selection)
}

#[cfg(target_os = "windows")]
fn screen_capture_to_temp_bmp() -> Result<CaptureFileResult, String> {
    let raw = capture_virtual_screen_raw()?;
    save_capture_raw_to_temp_bmp(&raw, "latexsnipper_capture")
}

fn encode_bmp_32bpp(width: i32, height: i32, pixels: &[u8]) -> Result<Vec<u8>, String> {
    if width <= 0 || height <= 0 {
        return Err("invalid bmp size".to_string());
    }
    let expected = (width as usize)
        .saturating_mul(height as usize)
        .saturating_mul(4);
    if pixels.len() < expected {
        return Err("bmp pixels buffer too short".to_string());
    }
    let image_size = expected as u32;
    let file_size = 14u32 + 40u32 + image_size;
    let mut out = Vec::with_capacity(file_size as usize);

    // BITMAPFILEHEADER (14 bytes)
    out.extend_from_slice(&0x4D42u16.to_le_bytes());
    out.extend_from_slice(&file_size.to_le_bytes());
    out.extend_from_slice(&0u16.to_le_bytes());
    out.extend_from_slice(&0u16.to_le_bytes());
    out.extend_from_slice(&54u32.to_le_bytes());

    // BITMAPINFOHEADER (40 bytes)
    out.extend_from_slice(&40u32.to_le_bytes());
    out.extend_from_slice(&width.to_le_bytes());
    out.extend_from_slice(&(-height).to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&32u16.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&image_size.to_le_bytes());
    out.extend_from_slice(&0i32.to_le_bytes());
    out.extend_from_slice(&0i32.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&pixels[..expected]);
    Ok(out)
}

fn write_bmp_32bpp(path: &std::path::Path, width: i32, height: i32, pixels: &[u8]) -> Result<(), String> {
    let bytes = encode_bmp_32bpp(width, height, pixels)?;
    let mut f = File::create(path).map_err(|e| format!("create bmp failed: {e}"))?;
    f.write_all(&bytes)
        .map_err(|e| format!("write bmp failed: {e}"))?;
    Ok(())
}

#[cfg(target_os = "windows")]
fn save_capture_raw_to_temp_bmp(raw: &ScreenCaptureRaw, prefix: &str) -> Result<CaptureFileResult, String> {
    let mut path = std::env::temp_dir();
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    path.push(format!("{}_{}_{}.bmp", prefix, std::process::id(), ts));
    write_bmp_32bpp(&path, raw.width, raw.height, &raw.pixels)?;
    Ok(CaptureFileResult {
        path: path.to_string_lossy().to_string(),
        width: raw.width,
        height: raw.height,
    })
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

fn has_daemon_marker(base: &Path) -> bool {
    base.join("src").join("backend").join("daemon_server.py").exists()
        || base.join("backend").join("daemon_server.py").exists()
}

fn normalize_path(path: &Path) -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        let raw = path.to_string_lossy().into_owned();
        if let Some(rest) = raw.strip_prefix(r"\\?\UNC\") {
            return PathBuf::from(format!(r"\\{}", rest));
        }
        if let Some(rest) = raw.strip_prefix(r"\\?\") {
            return PathBuf::from(rest);
        }
        PathBuf::from(raw)
    }
    #[cfg(not(target_os = "windows"))]
    {
        path.to_path_buf()
    }
}

fn path_to_string(path: &Path) -> String {
    normalize_path(path).display().to_string()
}

fn home_default_install_base_dir() -> PathBuf {
    user_home_dir().join(".latexsnipper").join("deps")
}

fn app_local_deps_dir() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    Some(normalize_path(&dir.join("deps")))
}

fn default_install_base_dir() -> PathBuf {
    app_local_deps_dir().unwrap_or_else(home_default_install_base_dir)
}

fn path_contains_component(path: &Path, needle: &str) -> bool {
    path.components().any(|c| {
        c.as_os_str()
            .to_string_lossy()
            .eq_ignore_ascii_case(needle)
    })
}

fn resolve_src_root(base: &Path) -> PathBuf {
    if base.join("src").join("backend").join("daemon_server.py").exists() {
        return base.join("src");
    }
    base.to_path_buf()
}

fn find_repo_root_from(start: &Path) -> Option<PathBuf> {
    let mut cur = Some(start);
    while let Some(p) = cur {
        if has_daemon_marker(p) {
            return Some(p.to_path_buf());
        }
        cur = p.parent();
    }
    None
}

fn find_repo_root() -> Option<PathBuf> {
    let mut seeds: Vec<PathBuf> = Vec::new();
    if let Ok(v) = std::env::var("LATEXSNIPPER_RESOURCE_DIR") {
        let p = PathBuf::from(v.trim());
        if !p.as_os_str().is_empty() {
            seeds.push(p);
        }
    }
    if let Ok(v) = std::env::var("LATEXSNIPPER_EXE_DIR") {
        let p = PathBuf::from(v.trim());
        if !p.as_os_str().is_empty() {
            seeds.push(p);
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        seeds.push(cwd);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            seeds.push(parent.to_path_buf());
        }
    }

    let mut candidates: Vec<PathBuf> = Vec::new();
    for seed in seeds {
        candidates.push(seed.clone());
        candidates.push(seed.join("_up_"));
        candidates.push(seed.join("_up_").join("_up_"));
        candidates.push(seed.join("_up_").join("_up_").join("_up_"));
        candidates.push(seed.join("_internal"));
        candidates.push(seed.join("resources"));
        candidates.push(seed.join("..").join("Resources"));
    }

    for c in candidates {
        if let Some(p) = find_repo_root_from(&c) {
            return Some(normalize_path(&p));
        }
    }
    None
}

fn python_exe_from_install_base(install_base_dir: &Path) -> PathBuf {
    normalize_path(&install_base_dir.join("python311").join("python.exe"))
}

fn resolve_python_exe(repo_root: &Path) -> PathBuf {
    let mut base =
        read_install_base_dir_from_runtime_config().unwrap_or_else(|| resolve_install_base_dir(repo_root));
    if path_contains_component(&base, "_up_") && !path_contains_component(repo_root, "_up_") {
        base = normalize_path(&repo_root.join("deps"));
        let _ = write_install_base_dir_to_runtime_config(&base);
    }
    python_exe_from_install_base(&base)
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
    Some(normalize_path(&PathBuf::from(raw)))
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
            Value::String(path_to_string(install_base_dir)),
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
        // Migrate the incorrect temporary default introduced previously:
        // keep user-custom paths untouched, only rewrite the legacy home default
        // when it still has no python311 payload.
        let legacy_home = normalize_path(&home_default_install_base_dir());
        let cur = normalize_path(&p);
        if path_contains_component(&cur, "_up_") && !path_contains_component(repo_root, "_up_") {
            let migrated = normalize_path(&repo_root.join("deps"));
            let _ = write_install_base_dir_to_runtime_config(&migrated);
            return migrated;
        }
        if cur == legacy_home && !cur.join("python311").join("python.exe").exists() {
            let migrated = if path_contains_component(repo_root, "_up_") {
                default_install_base_dir()
            } else {
                normalize_path(&repo_root.join("deps"))
            };
            let _ = write_install_base_dir_to_runtime_config(&migrated);
            return migrated;
        }
        return p;
    }
    if path_contains_component(repo_root, "_up_") {
        return default_install_base_dir();
    }
    let mut candidates = vec![
        repo_root.join("src").join("deps"),
        repo_root.join("deps"),
        repo_root.join("_internal").join("deps"),
        repo_root.join("resources").join("deps"),
    ];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("deps"));
            candidates.push(dir.join("_internal").join("deps"));
            candidates.push(dir.join("resources").join("deps"));
            candidates.push(dir.join("..").join("Resources").join("deps"));
        }
    }
    if let Some(hit) = candidates.into_iter().find(|p| p.exists()) {
        return normalize_path(&hit);
    }
    normalize_path(&repo_root.join("deps"))
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
        "app source root not found (missing backend/daemon_server.py)".to_string()
    })?;
    let src_root = resolve_src_root(&repo_root);
    let daemon_script = src_root.join("backend").join("daemon_server.py");
    if !daemon_script.exists() {
        return Err(format!(
            "daemon module not found: {}",
            daemon_script.display()
        ));
    }
    let pyexe = resolve_python_exe(&repo_root);
    if !pyexe.exists() {
        return Err(format!(
            "python311 not found at {} (expected install_base_dir\\\\python311\\\\python.exe)",
            pyexe.display()
        ));
    }
    let host = if endpoint.host.trim().is_empty() {
        "127.0.0.1".to_string()
    } else {
        endpoint.host.trim().to_string()
    };

    let mut daemon_log_path = std::env::temp_dir();
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    daemon_log_path.push(format!(
        "latexsnipper_daemon_boot_{}_{}.log",
        std::process::id(),
        ts
    ));
    let daemon_log_file = File::options()
        .create(true)
        .append(true)
        .open(&daemon_log_path)
        .map_err(|e| format!("open daemon log file failed ({}): {e}", daemon_log_path.display()))?;
    let daemon_log_file_err = daemon_log_file
        .try_clone()
        .map_err(|e| format!("clone daemon log file failed: {e}"))?;

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
        .stdout(Stdio::from(daemon_log_file))
        .stderr(Stdio::from(daemon_log_file_err))
        .current_dir(&src_root);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x00000008;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NO_WINDOW);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn daemon failed (py={}): {e}", pyexe.display()))?;
    let pid = child.id();

    let probe_deadline = Instant::now() + Duration::from_millis(1800);
    while Instant::now() < probe_deadline {
        if wait_port_open(&endpoint, 220) {
            break;
        }
        match child.try_wait() {
            Ok(Some(status)) => {
                let tail = fs::read_to_string(&daemon_log_path)
                    .ok()
                    .map(|txt| {
                        let mut lines = txt.lines().collect::<Vec<_>>();
                        if lines.len() > 20 {
                            lines = lines[lines.len() - 20..].to_vec();
                        }
                        lines.join("\n")
                    })
                    .unwrap_or_default();
                return Err(format!(
                    "daemon exited early (pid={pid}, code={:?}) using {} | log={} | tail={}",
                    status.code(),
                    pyexe.display(),
                    daemon_log_path.display(),
                    tail
                ));
            }
            Ok(None) => {}
            Err(e) => {
                return Err(format!("probe daemon process failed (pid={pid}): {e}"));
            }
        }
        std::thread::sleep(Duration::from_millis(120));
    }
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
pub fn capture_region_to_temp(app: tauri::AppHandle) -> Result<CaptureFileResult, String> {
    #[cfg(target_os = "windows")]
    {
        let _ = app;
        let raw = capture_region_with_native_overlay_raw()?;
        return save_capture_raw_to_temp_bmp(&raw, "latexsnipper_capture_region");
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = app;
        Err("region capture currently supported on Windows only".to_string())
    }
}

#[tauri::command]
pub fn capture_region_to_base64(app: tauri::AppHandle) -> Result<CaptureBase64Result, String> {
    #[cfg(target_os = "windows")]
    {
        let _ = app;
        let raw = capture_region_with_native_overlay_raw()?;
        let bmp = encode_bmp_32bpp(raw.width, raw.height, &raw.pixels)?;
        return Ok(CaptureBase64Result {
            image_b64: BASE64_STANDARD.encode(bmp),
            width: raw.width,
            height: raw.height,
            format: "bmp".to_string(),
        });
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = app;
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
    let repo_root = find_repo_root();
    let configured_base = read_install_base_dir_from_runtime_config();
    let install_base_dir = if let Some(root) = repo_root.as_ref() {
        resolve_install_base_dir(root)
    } else if let Some(base) = configured_base.clone() {
        base
    } else {
        default_install_base_dir()
    };
    fs::create_dir_all(&install_base_dir)
        .map_err(|e| format!("create install_base_dir failed: {e}"))?;
    if configured_base.is_none() {
        let _ = write_install_base_dir_to_runtime_config(&install_base_dir);
    }
    let cfg_path = runtime_config_path();
    let py_fallback = python_exe_from_install_base(&install_base_dir);
    let deps_state = install_base_dir.join(".deps_state.json");
    let (installed_layers, failed_layers) = read_deps_state_layers(&deps_state);
    Ok(RuntimeEnvConfig {
        config_path: path_to_string(&cfg_path),
        install_base_dir: path_to_string(&install_base_dir),
        python_exe: path_to_string(&py_fallback),
        cache_dir: path_to_string(&runtime_cache_dir()),
        deps_state_path: path_to_string(&deps_state),
        installed_layers,
        failed_layers,
    })
}

#[tauri::command]
pub fn set_runtime_env_config(input: SetRuntimeEnvConfigInput) -> Result<bool, String> {
    let base = normalize_path(&PathBuf::from(input.install_base_dir.trim()));
    if base.as_os_str().is_empty() {
        return Err("install_base_dir is empty".to_string());
    }
    fs::create_dir_all(&base).map_err(|e| format!("create install_base_dir failed: {e}"))?;
    write_install_base_dir_to_runtime_config(&base)?;
    Ok(true)
}

#[tauri::command]
pub fn launch_dependency_wizard(
    app: tauri::AppHandle,
    input: Option<LaunchDependencyWizardInput>,
) -> Result<LaunchDependencyWizardResult, String> {
    let repo_root = find_repo_root();
    let chosen_base = input
        .as_ref()
        .and_then(|x| x.install_base_dir.as_ref())
        .map(|x| normalize_path(&PathBuf::from(x.trim())))
        .filter(|p| !p.as_os_str().is_empty())
        .or_else(|| {
            repo_root
                .as_ref()
                .map(|root| resolve_install_base_dir(root))
        })
        .unwrap_or_else(default_install_base_dir);
    fs::create_dir_all(&chosen_base)
        .map_err(|e| format!("create install_base_dir failed: {e}"))?;
    write_install_base_dir_to_runtime_config(&chosen_base)?;

    let _legacy_python_exe_hint = input
        .as_ref()
        .and_then(|x| x.python_exe.as_ref())
        .map(|x| x.trim())
        .filter(|x| !x.is_empty());
    let py_hint = path_to_string(&python_exe_from_install_base(&chosen_base));

    let _ = app.emit(
        "open-environment-page",
        json!({
            "install_base_dir": path_to_string(&chosen_base),
            "python_exe_hint": py_hint,
        }),
    );

    Ok(LaunchDependencyWizardResult {
        ok: true,
        pid: 0,
        message: "tauri dependency manager opened".to_string(),
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
pub fn copy_text_to_clipboard(text: String) -> Result<bool, String> {
    let mut clipboard =
        arboard::Clipboard::new().map_err(|e| format!("init clipboard failed: {e}"))?;
    clipboard
        .set_text(text)
        .map_err(|e| format!("write clipboard failed: {e}"))?;
    Ok(true)
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
