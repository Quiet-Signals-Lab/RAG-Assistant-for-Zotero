# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for bundling the RAG Assistant for Zotero backend
# This creates a standalone Python distribution that includes all dependencies

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Get the project root directory
project_root = os.path.abspath(os.path.dirname(SPEC))
backend_dir = os.path.join(project_root, 'backend')

# Collect all submodules for key dependencies
hiddenimports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'pydantic',
    'pydantic_core',
    'starlette',
    'chromadb',
    'chromadb.api',
    'chromadb.config',
    'sentence_transformers',
    'torch',
    'transformers',
    'numpy',
    'sqlite3',
    'anthropic',
    'openai',
    'httpx',
    'fitz',
    'pymupdf',
    'PIL',
    'PIL.Image',
    'anyio',
    'sniffio',
    'h11',
    'click',
    'typing_extensions',
]

# Collect additional hidden imports for Chroma and sentence-transformers
hiddenimports += collect_submodules('chromadb')
hiddenimports += collect_submodules('sentence_transformers')
hiddenimports += collect_submodules('transformers')
hiddenimports += collect_submodules('torch')

# Collect data files (models, configs, etc.)
datas = []
datas += collect_data_files('chromadb')
datas += collect_data_files('sentence_transformers')
datas += collect_data_files('transformers')
datas += collect_data_files('torch')
datas += collect_data_files('tiktoken')
datas += collect_data_files('tokenizers')

# Add backend directory files
datas.append((backend_dir, 'backend'))

# Add requirements.txt for reference
datas.append((os.path.join(project_root, 'requirements.txt'), '.'))

a = Analysis(
    [os.path.join(project_root, 'backend_server_main.py')],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'tkinter',
        'jupyter',
        'notebook',
        'IPython',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend_server',
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
    name='backend_bundle',
)
