#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Node.js/npm is required." >&2; exit 1; }

(
  cd python-runtime
  uv sync --frozen --group dev
  uv run --with pyinstaller python -m PyInstaller --clean --noconfirm python-runtime.spec
)

npm ci
npm run build:icon
npm run build
npx electron-builder
echo "AgentForge installer build completed. See dist-electron/."
