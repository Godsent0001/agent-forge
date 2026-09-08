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

    let args: Vec<String> = env::args().skip(1).collect();

    // Replace this launcher process with Python on Windows.
    // Forward all CLI args (such as dynamic port) to main.py.
    let mut cmd = Command::new(&python);
    cmd.arg(&main_py);
    for arg in args {
        cmd.arg(arg);
    }

    let status = cmd
        .current_dir(&runtime_dir)
        .status()
        .expect("Failed to start Python runtime");

    exit(status.code().unwrap_or(1));
}