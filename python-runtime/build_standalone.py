import os
import subprocess
import sys

def main():
    python_runtime_dir = os.path.abspath(os.path.dirname(__file__))
    os.chdir(python_runtime_dir)

    print("[build_python_runtime] Building standalone python-runtime executable with PyInstaller...")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "python-runtime.spec",
    ]

    try:
        subprocess.check_call(cmd)
        print("[build_python_runtime] Build completed successfully. Output in python-runtime/dist/python-runtime")
    except subprocess.CalledProcessError as e:
        print(f"[build_python_runtime] Error during PyInstaller build: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
