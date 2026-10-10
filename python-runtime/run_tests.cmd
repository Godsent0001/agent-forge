@echo off
setlocal

echo === AgentForge Python runtime test runner ===

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.11 or newer is required. Check with: python --version
    exit /b 1
)

echo.
echo [1/2] Installing runtime and test dependencies...
python -m pip install -e ".[test]"
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    exit /b 1
)

echo.
echo [2/2] Running the complete Python runtime test suite...
python -m pytest tests -v
if errorlevel 1 (
    echo.
    echo TESTS FAILED. Review the first failure and traceback above.
    exit /b 1
)

echo.
echo ALL TESTS PASSED.
exit /b 0
