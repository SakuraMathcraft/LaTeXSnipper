use tauri::WebviewWindow;

#[cfg(target_os = "windows")]
fn apply_acrylic_preferred(window: &WebviewWindow) -> bool {
    use window_vibrancy::apply_acrylic;
    // 固定深色 tint，避免失焦/弹系统对话框时发白漂移。
    apply_acrylic(window, Some((10, 14, 20, 118))).is_ok() || apply_acrylic(window, None).is_ok()
}

#[cfg(target_os = "windows")]
pub fn apply_mode(window: &WebviewWindow, mode: &str) -> Result<String, String> {
    use window_vibrancy::apply_mica;

    let normalized = mode.trim().to_ascii_lowercase();
    match normalized.as_str() {
        "acrylic" => {
            if apply_acrylic_preferred(window) {
                Ok("acrylic".to_string())
            } else {
                Ok("none".to_string())
            }
        }
        "mica" => {
            if apply_mica(window, None).is_ok() {
                Ok("mica".to_string())
            } else {
                Ok("none".to_string())
            }
        }
        _ => apply_best_effort(window),
    }
}

#[cfg(target_os = "windows")]
pub fn apply_best_effort(window: &WebviewWindow) -> Result<String, String> {
    use window_vibrancy::apply_mica;

    if apply_acrylic_preferred(window) {
        return Ok("acrylic".to_string());
    }
    // 最后回退 Mica。
    if apply_mica(window, None).is_ok() {
        return Ok("mica".to_string());
    }
    Ok("none".to_string())
}

#[cfg(not(target_os = "windows"))]
pub fn apply_best_effort(_window: &WebviewWindow) -> Result<String, String> {
    Ok("none".to_string())
}

#[cfg(not(target_os = "windows"))]
pub fn apply_mode(_window: &WebviewWindow, _mode: &str) -> Result<String, String> {
    Ok("none".to_string())
}
