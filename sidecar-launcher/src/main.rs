use std::env;
use std::process::{Command, exit};

fn main() {
    let exe_dir = env::current_exe()
        .expect("Failed to locate launcher executable")
        .parent()
        .expect("Failed to locate launcher directory")
        .to_path_buf();

    // During development, Tauri places the sidecar in:
    // src-tauri/target/debug/
    // We need to walk back to the project root.
    let project_root = exe_dir
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .expect("Failed to locate project root")
        .to_path_buf();

    let runtime_dir = project_root.join("python-runtime");

    let python = runtime_dir
        .join(".venv")
        .join("Scripts")
        .join("python.exe");

    let main_py = runtime_dir.join("main.py");

    let status = Command::new(&python)
        .arg(&main_py)
        .status()
        .expect("Failed to start Python runtime");

    exit(status.code().unwrap_or(1));
}