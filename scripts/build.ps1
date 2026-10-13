$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is required. Install it from https://docs.astral.sh/uv/" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm is required." }

Push-Location (Join-Path $Root "python-runtime")
try {
    uv sync --frozen --group dev
    uv run --with pyinstaller python -m PyInstaller --clean --noconfirm python-runtime.spec
} finally {
    Pop-Location
}

npm ci
npm run build:icon
npm run build
npx electron-builder
Write-Host "AgentForge installer build completed. See dist-electron/."
