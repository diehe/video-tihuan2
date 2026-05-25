use tauri::Runtime;
use tauri_plugin_shell::ShellExt;

#[tauri::command]
fn default_backend_url() -> String {
    "http://127.0.0.1:8765".to_string()
}

#[tauri::command]
async fn start_engine<R: Runtime>(app: tauri::AppHandle<R>) -> Result<(), String> {
    let sidecar = app
        .shell()
        .sidecar("video-tihuan-engine")
        .map_err(|error| error.to_string())?;
    let (_receiver, _child) = sidecar
        .args(["--host", "127.0.0.1", "--port", "8765"])
        .spawn()
        .map_err(|error| error.to_string())?;
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![default_backend_url, start_engine])
        .setup(|app| {
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let _ = start_engine(handle).await;
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
