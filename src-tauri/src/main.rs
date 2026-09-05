// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

mod keychain;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            keychain::save_api_key,
            keychain::get_api_key,
            keychain::delete_api_key
        ])
        .setup(|app| {
            let shell = app.shell();

            // "python-runtime" resolves to the externalBin entry declared in
            // tauri.conf.json. Tauri appends the target triple automatically
            // when it looks for the binary (see README for exact naming).
            let sidecar_command = shell
                .sidecar("python-runtime")
                .expect("failed to create python-runtime sidecar command");

            let (mut rx, mut _child) = sidecar_command
                .spawn()
                .expect("failed to spawn python-runtime sidecar");

            // Forward sidecar stdout/stderr to the Rust log so failures are
            // visible during development instead of silently dying.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[python-runtime] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[python-runtime:err] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[python-runtime] exited: {:?}", payload);
                        }
                        _ => {}
                    }
                }
            });

            // Store the child so we can kill it explicitly on window close,
            // rather than relying on the OS to clean up orphaned processes.
            app.manage(std::sync::Mutex::new(Some(_child)));

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
