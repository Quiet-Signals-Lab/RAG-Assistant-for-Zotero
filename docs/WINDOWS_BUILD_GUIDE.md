# Windows Build Guide

Complete guide for building RAG Assistant for Zotero on Windows.

## Prerequisites

### Required Software

1. **Python 3.8 or later**
   - Download from: https://www.python.org/downloads/
   -  **Important:** Check "Add Python to PATH" during installation
   - Verify installation:
     ```powershell
     python --version
     # or
     python3 --version
     # or
     py --version
     ```

2. **Node.js 16 or later**
   - Download from: https://nodejs.org/
   - Verify installation:
     ```powershell
     node --version
     npm --version
     ```

3. **Git** (for cloning the repository)
   - Download from: https://git-scm.com/download/win
   - Or use GitHub Desktop

4. **PowerShell** (usually pre-installed on Windows)
   - Verify: Open "Windows PowerShell" from Start menu

### System Requirements

- Windows 10 or later (64-bit)
- At least 4 GB RAM (8 GB recommended)
- At least 5 GB free disk space for build
- Internet connection for downloading dependencies

## Build Process

### Step 1: Clone Repository

```powershell
# Clone the repository
git clone https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero.git
cd RAG-Assistant-for-Zotero
```

### Step 2: Install Node Dependencies

```powershell
# Install Node.js dependencies (root)
npm install

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Step 3: Create Python Virtual Environment (Optional but Recommended)

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1

# If you get an execution policy error, run:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Verify activation (you should see (.venv) in your prompt)
```

### Step 4: Bundle Python Backend

This is the critical step that creates a standalone Python executable.

```powershell
# Make sure you're in the project root directory
# Run the bundle script (Option 1: Batch file - easiest)
.\scripts\bundle-python-pyinstaller-windows.bat

# Or Option 2: PowerShell directly
.\scripts\bundle-python-pyinstaller-windows.ps1
```

**What this does:**
- Creates a temporary Python environment
- Installs PyInstaller and all dependencies
- Builds a standalone `backend_server.exe`
- Bundles all Python libraries and models
- Creates `python-dist/` directory

**Expected output:**
```
 PyInstaller bundle created successfully!
 Bundle size: ~800 MB
 Location: python-dist/
 Backend executable found: backend_server.exe
```

**This step takes 5-10 minutes** depending on your system and internet speed.

**Troubleshooting:**
- If script fails with "Python not found": Add Python to PATH and restart PowerShell
- If PyInstaller fails: Make sure you have a C++ compiler installed (Visual Studio Build Tools)
- If out of memory: Close other applications and try again
- If antivirus blocks: Temporarily disable or add exception for the project folder

### Step 5: Build Electron App

```powershell
# Build TypeScript and frontend
npm run build

# Package for Windows
npm run package:win
```

**This creates:**
- `release/RAG-Assistant-{version}-win-x64.exe` - NSIS installer (64-bit)
- `release/RAG-Assistant-{version}-win-ia32.exe` - NSIS installer (32-bit)
- `release/RAG-Assistant-{version}-win-x64.zip` - Portable ZIP (64-bit)
- `release/RAG-Assistant-{version}-win-ia32.zip` - Portable ZIP (32-bit)
- `release/latest.yml` - Auto-update configuration

**Build time:** 2-5 minutes

### Step 6: Verify the Build

```powershell
# Check that files were created
Get-ChildItem release\*.exe
Get-ChildItem release\*.zip
Get-ChildItem release\latest.yml

# Verify bundle is included
Get-ChildItem python-dist\backend_server.exe
```

### Step 7: Test the Application

**Option 1: Run from build artifacts**
```powershell
# Install the NSIS installer
.\release\RAG-Assistant-{version}-win-x64.exe

# Or extract and run the portable version
Expand-Archive .\release\RAG-Assistant-{version}-win-x64.zip -DestinationPath test-install
.\test-install\RAGAssistant.exe
```

**Option 2: Test in development mode**
```powershell
# Start backend (in one terminal)
.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --port 8000

# Start frontend (in another terminal)
cd frontend
npm run dev

# Start Electron (in third terminal)
npm run dev:electron:only
```

## Troubleshooting

### Python Issues

**"Python not found" or "python is not recognized"**
- Python not in PATH. Reinstall Python and check "Add to PATH"
- Or manually add: Control Panel → System → Advanced → Environment Variables
- Add `C:\Users\{username}\AppData\Local\Programs\Python\Python3X` to PATH

**"No module named 'venv'"**
```powershell
# venv is included with Python 3.3+, but may need to reinstall
python -m pip install --upgrade pip
```

### PyInstaller Issues

**"Unable to find pyinstaller"**
```powershell
# Install PyInstaller globally
pip install pyinstaller
```

**"Failed to execute script" when running bundle**
- Windows Defender may be blocking. Add exception:
  - Windows Security → Virus & threat protection → Manage settings
  - Add exclusion for project folder

**"DLL load failed" errors**
- Install Visual C++ Redistributable:
  - Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe

### Build Issues

**"electron-builder not found"**
```powershell
npm install electron-builder --save-dev
```

**"Build failed" during npm run package:win**
- Clean and rebuild:
  ```powershell
  Remove-Item -Path node_modules -Recurse -Force
  Remove-Item -Path dist -Recurse -Force
  npm install
  npm run build
  npm run package:win
  ```

### Runtime Issues

**"Failed to start backend process: spawn ENOENT"**
- Python bundle missing. Re-run Step 4 (bundle script)
- Verify `python-dist/backend_server.exe` exists

**"Backend not responding"**
- Check Windows Firewall isn't blocking port 8000
- Check antivirus isn't blocking the backend executable

**Application won't start**
- Check Event Viewer for crash details:
  - Windows Logs → Application → Look for RAG Assistant errors
- Try running from command line to see errors:
  ```powershell
  cd "C:\Users\{username}\AppData\Local\Programs\RAG Assistant"
  .\RAG Assistant.exe
  ```

## Development Workflow

For active development (without packaging):

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

This allows hot-reloading and faster iteration.

## Building for Distribution

### Code Signing (Optional but Recommended)

To avoid SmartScreen warnings, sign your executables:

1. Obtain a code signing certificate ($200-400/year)
   - DigiCert, Sectigo, or other trusted CA

2. Update `package.json`:
   ```json
   "win": {
     "certificateFile": "path/to/certificate.pfx",
     "certificatePassword": "your-password",
     "publisherName": "Your Name or Company"
   }
   ```

3. Rebuild with signing:
   ```powershell
   npm run package:win
   ```

### Creating Installer Without Signing

The NSIS installer will show SmartScreen warnings. Users need to:
1. Click "More info" on SmartScreen warning
2. Click "Run anyway"

This is normal for unsigned applications.

## CI/CD with GitHub Actions (Future)

Example workflow for automated Windows builds:

```yaml
name: Build Windows

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '18'
    
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: npm install
    
    - name: Bundle Python backend
      run: .\scripts\bundle-python-pyinstaller-windows.bat
    
    - name: Build Electron app
      run: npm run package:win
    
    - name: Upload artifacts
      uses: actions/upload-artifact@v3
      with:
        name: windows-installers
        path: release/*.exe
```

## Next Steps

After successful build:
1. Test the installer on a clean Windows machine
2. Test on Windows 10 and Windows 11
3. Update README.md to mark Windows as supported
4. Create GitHub release with Windows installers
5. Update documentation with Windows-specific notes

## Resources

- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
- [Electron Builder Windows Configuration](https://www.electron.build/configuration/win)
- [NSIS Installer](https://nsis.sourceforge.io/Main_Page)
- [Windows Code Signing](https://www.electron.build/code-signing)

## Support

If you encounter issues not covered here:
1. Check existing GitHub issues
2. Create a new issue with:
   - Windows version
   - Python version
   - Error messages
   - Steps to reproduce
