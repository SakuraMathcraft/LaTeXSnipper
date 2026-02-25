#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{Emitter, Manager};

mod commands;
mod contract;
mod rpc_client;
mod window_effects;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                if let Ok(applied) = window_effects::apply_best_effort(&window) {
                    let _ = window.emit("window-effects-applied", applied);
                }

            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::apply_window_effects,
            commands::set_window_compact_mode,
            commands::daemon_bootstrap_local,
            commands::daemon_shutdown,
            commands::load_rpc_contract,
            commands::daemon_health_handshake,
            commands::daemon_task_submit,
            commands::daemon_task_status,
            commands::daemon_task_poll,
            commands::daemon_task_submit_and_poll,
            commands::daemon_task_cancel,
            commands::get_system_usage,
            commands::get_runtime_env_config,
            commands::set_runtime_env_config,
            commands::launch_dependency_wizard,
            commands::register_capture_hotkey,
            commands::unregister_capture_hotkey,
            commands::get_capture_hotkey_status,
            commands::capture_region_to_temp,
            commands::capture_region_to_base64,
            commands::capture_screen_to_temp,
            commands::pick_file,
            commands::open_path,
            commands::save_text_file,
            commands::open_external_url,
            commands::get_app_info,
        ])
        .run(tauri::generate_context!())
        .expect("failed to run tauri app");
}
