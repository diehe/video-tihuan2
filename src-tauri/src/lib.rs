use std::sync::Mutex;

use tauri::{Manager, Runtime, WindowEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
struct EngineState {
    child: Mutex<Option<CommandChild>>,
}

#[tauri::command]
fn default_backend_url() -> String {
    "http://127.0.0.1:8765".to_string()
}

#[tauri::command]
fn start_engine<R: Runtime>(
    app: tauri::AppHandle<R>,
    state: tauri::State<'_, EngineState>,
) -> Result<(), String> {
    spawn_engine(&app, state.inner())
}

fn spawn_engine<R: Runtime>(app: &tauri::AppHandle<R>, state: &EngineState) -> Result<(), String> {
    if state.child.lock().map_err(|error| error.to_string())?.is_some() {
        return Ok(());
    }
    let sidecar = app
        .shell()
        .sidecar("video-tihuan-engine")
        .map_err(|error| error.to_string())?;
    let (_receiver, child) = sidecar
        .args(["--host", "127.0.0.1", "--port", "8765"])
        .spawn()
        .map_err(|error| error.to_string())?;
    *state.child.lock().map_err(|error| error.to_string())? = Some(child);
    Ok(())
}

fn stop_engine(state: &EngineState) {
    if let Ok(mut child) = state.child.lock() {
        if let Some(child) = child.take() {
            let _ = child.kill();
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(EngineState::default())
        .invoke_handler(tauri::generate_handler![default_backend_url, start_engine])
        .setup(|app| {
            let handle = app.handle().clone();
            let state = app.state::<EngineState>();
            let _ = spawn_engine(&handle, state.inner());
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::Destroyed) {
                stop_engine(window.state::<EngineState>().inner());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
