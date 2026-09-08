// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

mod keychain;

#[derive(Clone)]
struct BackendPort(std::sync::Arc<std::sync::Mutex<Option<u16>>>);

#[tauri::command]
async fn get_backend_port(state: tauri::State<'_, BackendPort>) -> Result<u16, String> {
    let port_arc = state.0.clone();
    for _ in 0..100 {
        if let Ok(guard) = port_arc.lock() {
            if let Some(port) = *guard {
                return Ok(port);
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }
    // Fallback if not announced in time
    Ok(8756)
}

fn main() {
    let port_state = BackendPort(std::sync::Arc::new(std::sync::Mutex::new(None)));

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(port_state.clone())
        .invoke_handler(tauri::generate_handler![
            keychain::save_api_key,
            keychain::get_api_key,
            keychain::delete_api_key,
            get_backend_port
        ])
        .setup(move |app| {
            let shell = app.shell();

            // "python-runtime" resolves to the externalBin entry declared in
            // tauri.conf.json. Tauri appends the target triple automatically
            // when it looks for the binary (see README for exact naming).
            let sidecar_command = shell
                .sidecar("python-runtime")
                .expect("failed to create python-runtime sidecar command");

            let (mut rx, child) = sidecar_command
                .spawn()
                .expect("failed to spawn python-runtime sidecar");

            let port_arc_clone = port_state.0.clone();

            // Forward sidecar stdout/stderr and capture AGENTFORGE_READY:<port>
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            let text = String::from_utf8_lossy(&line);
                            println!("[python-runtime] {}", text);
                            if text.contains("AGENTFORGE_READY:") {
                                if let Some(part) = text.split("AGENTFORGE_READY:").nth(1) {
                                    let port_str = part.trim().split_whitespace().next().unwrap_or("");
                                    if let Ok(parsed_port) = port_str.parse::<u16>() {
                                        if let Ok(mut guard) = port_arc_clone.lock() {
                                            *guard = Some(parsed_port);
                                            println!("[tauri] Captured Python runtime dynamic port: {}", parsed_port);
                                        }
                                    }
                                }
                            }
                        }
                        CommandEvent::Stderr(line) => {
                            let text = String::from_utf8_lossy(&line);
                            eprintln!("[python-runtime:err] {}", text);
                            if text.contains("AGENTFORGE_READY:") {
                                if let Some(part) = text.split("AGENTFORGE_READY:").nth(1) {
                                    let port_str = part.trim().split_whitespace().next().unwrap_or("");
                                    if let Ok(parsed_port) = port_str.parse::<u16>() {
                                        if let Ok(mut guard) = port_arc_clone.lock() {
                                            *guard = Some(parsed_port);
                                            println!("[tauri] Captured Python runtime dynamic port: {}", parsed_port);
                                        }
                                    }
                                }
                            }
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[python-runtime] exited: {:?}", payload);
                        }
                        _ => {}
                    }
                }
            });

            // Store the child handle so Tauri maintains ownership and doesn't drop/kill it on setup end
            app.manage(std::sync::Mutex::new(Some(child)));

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window
                    .app_handle()
                    .try_state::<std::sync::Mutex<Option<tauri_plugin_shell::process::CommandChild>>>()
                {
                    if let Some(child) = state.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
