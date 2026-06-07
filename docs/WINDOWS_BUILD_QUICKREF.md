# Windows Build Quick Reference

Quick commands for building RAG Assistant for Zotero on Windows.

## Prerequisites
- Python 3.8+ (with "Add to PATH" checked during install)
- Node.js 16+
- PowerShell

## One-Time Setup

```powershell
# Clone repository
git clone https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero.git
cd RAG-Assistant-for-Zotero

# Install dependencies
npm install
cd frontend
npm install
cd ..

# Create Python virtual environment (optional)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## Build Commands

```powershell
# Step 1: Bundle Python backend (required, takes 5-10 minutes)
.\scripts\bundle-python-pyinstaller-windows.bat

# Step 2: Build Electron app
npm run build
npm run package:win
```

## Output Files

Located in `release/` directory:
- `RAG-Assistant-{version}-win-x64.exe` - 64-bit installer
- `RAG-Assistant-{version}-win-ia32.exe` - 32-bit installer
- `RAG-Assistant-{version}-win-x64.zip` - Portable 64-bit
- `latest.yml` - Auto-update config

## Development Mode

```powershell
# Terminal 1: Backend
.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev

# Terminal 3: Electron
npm run build:electron
npm run dev:electron:only
```

## Common Issues

**"Python not found"**
```powershell
# Reinstall Python with "Add to PATH" checked
# Or add manually to PATH environment variable
```

**"Backend not starting"**
```powershell
# Verify bundle exists
Get-ChildItem python-dist\backend_server.exe

# If missing, re-run bundle script
.\scripts\bundle-python-pyinstaller-windows.bat
```

**"SmartScreen warning"**
```
This is normal for unsigned apps.
Click "More info" → "Run anyway"
```

**"Antivirus blocking"**
```powershell
# Add project folder to antivirus exclusions
# Windows Security → Virus & threat protection → Exclusions
```

## Clean Build

```powershell
# Remove all build artifacts
Remove-Item -Path python-dist -Recurse -Force
Remove-Item -Path dist -Recurse -Force
Remove-Item -Path node_modules -Recurse -Force
Remove-Item -Path release -Recurse -Force

# Reinstall and rebuild
npm install
.\scripts\bundle-python-pyinstaller-windows.bat
npm run build
npm run package:win
```

## Full Documentation

See [WINDOWS_BUILD_GUIDE.md](WINDOWS_BUILD_GUIDE.md) for detailed instructions and troubleshooting.
