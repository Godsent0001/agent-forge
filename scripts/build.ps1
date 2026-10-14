$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is required. Install it from https://docs.astral.sh/uv/" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm is required." }

npm ci
npm run dist
Write-Host "AgentForge installer build completed. See dist-electron/"
