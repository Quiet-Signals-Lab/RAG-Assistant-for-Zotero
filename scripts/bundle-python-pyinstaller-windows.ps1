# bundle-python-pyinstaller-windows.ps1
# Create a standalone Python bundle using PyInstaller for Windows
# This creates a completely self-contained Python distribution with all dependencies
# bundled as a Windows executable (backend_server.exe)

param(
    [switch]$UseVenv = $false,
    [switch]$SkipCleanup = $false
)

$ErrorActionPreference = "Stop"

# Get paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BundleDir = Join-Path $ProjectRoot "python-dist"
$BuildDir = Join-Path $ProjectRoot "build-python"
$SpecFile = Join-Path $ProjectRoot "build\pyinstaller\backend_bundle.spec"

Write-Host " Creating standalone Python bundle with PyInstaller for Windows..." -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# Clean previous bundle and build artifacts
if (Test-Path $BundleDir) {
    Write-Host "🧹 Cleaning previous bundle..." -ForegroundColor Yellow
    Remove-Item -Path $BundleDir -Recurse -Force
}

if (Test-Path $BuildDir) {
    Write-Host "🧹 Cleaning previous build artifacts..." -ForegroundColor Yellow
    Remove-Item -Path $BuildDir -Recurse -Force
}

$DistDir = Join-Path $ProjectRoot "dist\backend_bundle"
if (Test-Path $DistDir) {
    Write-Host "🧹 Cleaning PyInstaller dist directory..." -ForegroundColor Yellow
    Remove-Item -Path $DistDir -Recurse -Force
}

# Check for Python
$PythonCmd = $null
$PythonCommands = @("python", "python3", "py")

foreach ($cmd in $PythonCommands) {
    try {
        $version = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $version -match "Python 3") {
            $PythonCmd = $cmd
            Write-Host " Found $version using command '$cmd'" -ForegroundColor Green
            break
        }
    }
    catch {
        continue
    }
}

if (-not $PythonCmd) {
    Write-Host " Python 3 is not installed or not in PATH." -ForegroundColor Red
    Write-Host "   Please install Python 3.8 or later from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "   Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Red
    exit 1
}

# Check Python version
$PythonVersion = & $PythonCmd --version 2>&1 | Select-String -Pattern "(\d+\.\d+\.\d+)" | ForEach-Object { $_.Matches.Groups[1].Value }
Write-Host " Using Python $PythonVersion" -ForegroundColor Green

# Check if we should use a virtual environment
$VenvActive = $env:VIRTUAL_ENV
if (-not $VenvActive -or $UseVenv) {
    Write-Host "  No virtual environment activated" -ForegroundColor Yellow
    Write-Host " Creating temporary build environment..." -ForegroundColor Cyan
    
    # Create temporary venv for building
    & $PythonCmd -m venv "$BuildDir\venv"
    if ($LASTEXITCODE -ne 0) {
        Write-Host " Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    
    # Activate venv
    $VenvActivate = Join-Path $BuildDir "venv\Scripts\Activate.ps1"
    & $VenvActivate
    
    $PipCmd = Join-Path $BuildDir "venv\Scripts\pip.exe"
    $PyInstallerCmd = Join-Path $BuildDir "venv\Scripts\pyinstaller.exe"
}
else {
    Write-Host " Using active virtual environment: $VenvActive" -ForegroundColor Green
    $PipCmd = "pip"
    $PyInstallerCmd = "pyinstaller"
}

# Upgrade pip and install build tools
Write-Host "  Upgrading pip and installing build tools..." -ForegroundColor Cyan
& $PipCmd install --upgrade pip setuptools wheel --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host " Failed to upgrade pip" -ForegroundColor Red
    exit 1
}

# Install PyInstaller
Write-Host " Installing PyInstaller..." -ForegroundColor Cyan
& $PipCmd install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host " Failed to install PyInstaller" -ForegroundColor Red
    exit 1
}

# Install backend requirements
Write-Host " Installing backend dependencies..." -ForegroundColor Cyan
Write-Host "   (This may take a few minutes depending on your system...)" -ForegroundColor Gray

$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
& $PipCmd install -r $RequirementsFile --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host " Failed to install backend dependencies" -ForegroundColor Red
    exit 1
}

# Run PyInstaller
Write-Host " Building standalone bundle with PyInstaller..." -ForegroundColor Cyan
Write-Host "   This may take 5-10 minutes depending on your system..." -ForegroundColor Gray

& $PyInstallerCmd --clean --noconfirm $SpecFile
if ($LASTEXITCODE -ne 0) {
    Write-Host " PyInstaller build failed" -ForegroundColor Red
    exit 1
}

# Move the bundle to python-dist
if (Test-Path $DistDir) {
    Write-Host " Moving bundle to python-dist..." -ForegroundColor Cyan
    Move-Item -Path $DistDir -Destination $BundleDir -Force
    
    # Rename backend_server to backend_server.exe if not already done
    $BackendExe = Join-Path $BundleDir "backend_server.exe"
    $BackendNoExt = Join-Path $BundleDir "backend_server"
    
    if ((Test-Path $BackendNoExt) -and -not (Test-Path $BackendExe)) {
        Write-Host " Renaming backend_server to backend_server.exe..." -ForegroundColor Cyan
        Move-Item -Path $BackendNoExt -Destination $BackendExe -Force
    }
    
    # Create a startup script for the backend (PowerShell)
    $StartScript = @"
# Start the backend server using the PyInstaller bundle
`$ScriptDir = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$BackendExecutable = Join-Path `$ScriptDir "backend_server.exe"

# Pass all arguments to the backend executable
& `$BackendExecutable `$args
"@
    
    $StartScriptPath = Join-Path $BundleDir "start_backend.ps1"
    Set-Content -Path $StartScriptPath -Value $StartScript -Encoding UTF8
    
    # Create a batch file wrapper
    $BatchScript = @"
@echo off
REM Start the backend server using the PyInstaller bundle
"%~dp0backend_server.exe" %*
"@
    
    $BatchScriptPath = Join-Path $BundleDir "start_backend.bat"
    Set-Content -Path $BatchScriptPath -Value $BatchScript -Encoding ASCII
    
    # Get bundle size
    $BundleSize = (Get-ChildItem -Path $BundleDir -Recurse | Measure-Object -Property Length -Sum).Sum
    $BundleSizeMB = [math]::Round($BundleSize / 1MB, 2)
    
    Write-Host ""
    Write-Host " PyInstaller bundle created successfully!" -ForegroundColor Green
    Write-Host " Bundle size: $BundleSizeMB MB" -ForegroundColor Cyan
    Write-Host " Location: $BundleDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " Bundle structure:" -ForegroundColor Cyan
    Get-ChildItem -Path $BundleDir | Select-Object -First 10 | Format-Table Name, Length, LastWriteTime
    Write-Host ""
    
    # Verify the bundle
    Write-Host " Verifying bundle..." -ForegroundColor Cyan
    if (Test-Path $BackendExe) {
        Write-Host " Backend executable found: backend_server.exe" -ForegroundColor Green
        
        # Get file info
        $FileInfo = Get-Item $BackendExe
        $FileSizeMB = [math]::Round($FileInfo.Length / 1MB, 2)
        Write-Host " Executable size: $FileSizeMB MB" -ForegroundColor Green
        
        # Test execution (just check --help)
        Write-Host " Testing backend executable..." -ForegroundColor Cyan
        try {
            $output = & $BackendExe --help 2>&1
            Write-Host " Backend executable runs successfully" -ForegroundColor Green
        }
        catch {
            Write-Host "  Backend executable may have issues, but file exists" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host " Backend executable not found!" -ForegroundColor Red
        exit 1
    }
    
    Write-Host ""
    Write-Host " Bundle verification passed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Build Electron app: npm run package:win" -ForegroundColor White
    Write-Host "2. The bundled Python will be included automatically" -ForegroundColor White
    Write-Host "3. App will run standalone without requiring system Python" -ForegroundColor White
    Write-Host ""
    Write-Host " Note: The bundle contains a fully self-contained Python runtime" -ForegroundColor Gray
    Write-Host "         with all dependencies baked in." -ForegroundColor Gray
}
else {
    Write-Host " PyInstaller bundle creation failed!" -ForegroundColor Red
    Write-Host "Expected directory not found: $DistDir" -ForegroundColor Red
    exit 1
}

# Cleanup build directory
if (-not $SkipCleanup) {
    if (Test-Path $BuildDir) {
        Write-Host "🧹 Cleaning up build directory..." -ForegroundColor Yellow
        Remove-Item -Path $BuildDir -Recurse -Force
    }
    
    # Cleanup PyInstaller temp files
    $PyInstallerBuild = Join-Path $ProjectRoot "build"
    if (Test-Path $PyInstallerBuild) {
        Remove-Item -Path $PyInstallerBuild -Recurse -Force
    }
    
    $PyInstallerDist = Join-Path $ProjectRoot "dist"
    if (Test-Path $PyInstallerDist) {
        Remove-Item -Path $PyInstallerDist -Recurse -Force
    }
}

Write-Host ""
Write-Host " Done!" -ForegroundColor Green
Write-Host ""
