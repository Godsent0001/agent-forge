# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

block_cipher = None

# LiteLLM loads providers dynamically; collect its package resources and hidden imports.
litellm_datas, litellm_binaries, litellm_hiddenimports = collect_all("litellm")

# tiktoken discovers encoding plugins through distribution entry-point metadata.
# PyInstaller does not reliably include this metadata or the dynamically imported
# plugin modules unless they are collected explicitly.
tiktoken_metadata = copy_metadata("tiktoken")
tiktoken_hiddenimports = collect_submodules("tiktoken") + collect_submodules("tiktoken_ext")

# yt-dlp registers its site extractors and networking handlers by dynamic import.
yt_dlp_hiddenimports = collect_submodules("yt_dlp")

# FastEmbed/ONNX Runtime are imported lazily by the local embedding provider.
fastembed_datas, fastembed_binaries, fastembed_hiddenimports = collect_all("fastembed")
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
matplotlib_datas, matplotlib_binaries, matplotlib_hiddenimports = collect_all("matplotlib")
playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all("playwright")
onnx_datas, onnx_binaries, onnx_hiddenimports = collect_all("onnxruntime")

datas = [
    ("alembic.ini", "."),
    ("alembic", "alembic"),
] + collect_data_files("alembic") + litellm_datas + tiktoken_metadata + fastembed_datas + onnx_datas + numpy_datas + matplotlib_datas + playwright_datas

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "app",
    "app.db",
    "app.graph",
    "app.models",
    "app.ws",
] + litellm_hiddenimports + tiktoken_hiddenimports + yt_dlp_hiddenimports + fastembed_hiddenimports + onnx_hiddenimports + numpy_hiddenimports + matplotlib_hiddenimports + playwright_hiddenimports + collect_submodules("app") + collect_submodules("alembic")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=litellm_binaries + fastembed_binaries + onnx_binaries + numpy_binaries + matplotlib_binaries + playwright_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="python-runtime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="python-runtime",
)
