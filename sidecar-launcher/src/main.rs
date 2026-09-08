use std::env;
use std::process::{Command, exit};

fn main() {
    let exe_dir = env::current_exe()
        .expect("Failed to locate launcher executable")
        .parent()
        .expect("Failed to locate launcher directory")
        .to_path_buf();

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

    let port = env::args().nth(1).unwrap_or_else(|| "8756".to_string());

    // Replace this launcher process with Python on Windows.
    // This makes the Python runtime the actual sidecar process,
    // so Tauri can terminate it cleanly.
    let status = Command::new(&python)
        .arg(&main_py)
        .arg(&port)
        .current_dir(&runtime_dir)
        .status()
        .expect("Failed to start Python runtime");

    exit(status.code().unwrap_or(1));
}