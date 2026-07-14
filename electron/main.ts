/**
 * Electron Main Process
 * 
 * Responsibilities:
 * - Create and manage the browser window
 * - Spawn and manage the Python backend process
 * - Handle IPC communication between renderer and backend
 * - Manage application lifecycle (startup, shutdown, updates)
 */

import { app, BrowserWindow, ipcMain, dialog, session } from 'electron';
import type { OnHeadersReceivedListenerDetails, HeadersReceivedResponse } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { autoUpdater } from 'electron-updater';
import axios from 'axios';

// Configuration
// Detect development vs production mode
// app.isPackaged is the most reliable way - it's false during development, true when packaged
const IS_DEV = !app.isPackaged;
let BACKEND_PORT = 8000;
let BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_DEV_URL = 'http://localhost:5173';

// Global references
let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;
let authToken: string | null = null;
let isInitializing = true; // Prevent premature quit during startup
let isShuttingDown = false; // FIX: Prevent duplicate shutdown attempts
let updateDownloaded = false;
let updateInfo: { version: string; releaseNotes?: string } | null = null;
let splashWindow: BrowserWindow | null = null; // Splash screen shown during startup

/**
 * Handle command-line arguments for Linux compatibility
 * This allows users to work around GPU/sandbox issues on problematic systems
 */
if (process.platform === 'linux') {
  // Parse command-line arguments
  const args = process.argv.slice(1);
  
  console.log('Checking command-line arguments for Linux compatibility flags...');
  
  // Check for sandbox-related flags
  if (args.includes('--no-sandbox') || args.includes('--disable-sandbox')) {
    console.log('  \u2713 Disabling sandbox (user requested)');
    app.commandLine.appendSwitch('no-sandbox');
  }
  
  // Check for GPU-related flags
  if (args.includes('--disable-gpu')) {
    console.log('  \u2713 Disabling GPU acceleration (user requested)');
    app.commandLine.appendSwitch('disable-gpu');
  }
  
  if (args.includes('--disable-gpu-sandbox')) {
    console.log('  \u2713 Disabling GPU sandbox only (user requested)');
    app.commandLine.appendSwitch('disable-gpu-sandbox');
  }
  
  // Check for software rendering
  if (args.includes('--disable-software-rasterizer')) {
    console.log('  \u2713 Disabling software rasterizer (user requested)');
    app.commandLine.appendSwitch('disable-software-rasterizer');
  }
  
  // Ozone platform (Wayland/X11)
  const ozoneIndex = args.findIndex(arg => arg.startsWith('--ozone-platform='));
  if (ozoneIndex >= 0) {
    const platform = args[ozoneIndex].split('=')[1];
    console.log(`  \u2713 Setting Ozone platform: ${platform}`);
    app.commandLine.appendSwitch('ozone-platform', platform);
  }
  
  // GL implementation
  const glIndex = args.findIndex(arg => arg.startsWith('--use-gl='));
  if (glIndex >= 0) {
    const gl = args[glIndex].split('=')[1];
    console.log(`  \u2713 Setting GL implementation: ${gl}`);
    app.commandLine.appendSwitch('use-gl', gl);
  }
  
  // If no special flags provided, apply sensible Linux defaults
  if (!args.some(arg => arg.includes('sandbox') || arg.includes('gpu') || arg.includes('ozone') || arg.includes('gl'))) {
    console.log('  \u2713 Applying default Linux compatibility settings:');
    // Disable sandboxes by default on Linux (AppArmor can block child processes)
    console.log('    - Disabling sandboxes (prevents AppArmor blocking child processes)');
    app.commandLine.appendSwitch('no-sandbox');
    app.commandLine.appendSwitch('disable-setuid-sandbox');
    app.commandLine.appendSwitch('disable-gpu-sandbox');
    
    // Disable dev-shm usage (prevents shared memory errors on some systems)
    console.log('    - Disabling /dev/shm usage (prevents shared memory errors)');
    app.commandLine.appendSwitch('disable-dev-shm-usage');
    
    // Disable GPU acceleration for Remote Desktop compatibility
    console.log('    - Disabling GPU acceleration (improves Remote Desktop compatibility)');
    app.commandLine.appendSwitch('disable-gpu');
  }
}

/**
 * Generate a random authentication token for backend communication
 */
function generateAuthToken(): string {
  return require('crypto').randomBytes(32).toString('hex');
}

/**
 * Create a loading window to show progress during long operations
 */
function createLoadingWindow(message: string = 'Loading...'): BrowserWindow {
  const loadingWindow = new BrowserWindow({
    width: 400,
    height: 200,
    frame: false,
    transparent: false,
    resizable: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    },
    show: false
  });

  // Create simple HTML content for loading window
  const loadingHtml = `
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          margin: 0;
          padding: 0;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          height: 100vh;
        }
        .spinner {
          border: 4px solid rgba(255, 255, 255, 0.3);
          border-top: 4px solid white;
          border-radius: 50%;
          width: 40px;
          height: 40px;
          animation: spin 1s linear infinite;
          margin-bottom: 20px;
        }
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        .message {
          font-size: 16px;
          text-align: center;
          padding: 0 20px;
        }
        .progress {
          font-size: 14px;
          opacity: 0.8;
          margin-top: 10px;
        }
      </style>
    </head>
    <body>
      <div class="spinner"></div>
      <div class="message" id="message">${message}</div>
      <div class="progress" id="progress"></div>
    </body>
    </html>
  `;

  loadingWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(loadingHtml)}`);
  loadingWindow.once('ready-to-show', () => {
    loadingWindow.show();
  });

  return loadingWindow;
}

/**
 * Update loading window message
 */
function updateLoadingWindow(loadingWindow: BrowserWindow | null, message: string, progress?: number): void {
  if (!loadingWindow || loadingWindow.isDestroyed()) return;
  
  const progressText = progress !== undefined ? `${progress}%` : '';
  loadingWindow.webContents.executeJavaScript(`
    document.getElementById('message').textContent = ${JSON.stringify(message)};
    document.getElementById('progress').textContent = ${JSON.stringify(progressText)};
  `).catch(() => {});
}

/**
 * Check if a port is available
 */
function isPortAvailable(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const net = require('net');
    const server = net.createServer();
    
    server.once('error', (err: any) => {
      if (err.code === 'EADDRINUSE') {
        resolve(false);
      } else {
        resolve(false);
      }
    });
    
    server.once('listening', () => {
      server.close();
      resolve(true);
    });
    
    server.listen(port, '127.0.0.1');
  });
}

/**
 * Find an available port starting from the preferred port
 */
async function findAvailablePort(preferredPort: number = 8000, maxTries: number = 10): Promise<number | null> {
  for (let i = 0; i < maxTries; i++) {
    const port = preferredPort + i;
    const available = await isPortAvailable(port);
    if (available) {
      return port;
    }
    console.log(`Port ${port} is in use, trying next...`);
  }
  return null;
}

/**
 * Kill any existing backend processes that might be stuck
 * This prevents "address already in use" errors
 */
async function killExistingBackendProcesses(): Promise<void> {
  console.log('Checking for existing backend processes...');
  
  try {
    if (process.platform === 'darwin' || process.platform === 'linux') {
      // Find processes using port 8000-8010
      for (let port = 8000; port <= 8010; port++) {
        try {
          const { execSync } = require('child_process');
          // Use lsof to find process using the port
          const result = execSync(`lsof -ti:${port} 2>/dev/null || true`, { encoding: 'utf-8' });
          const pids = result.trim().split('\n').filter((pid: string) => pid && pid !== '');
          
          if (pids.length > 0) {
            console.log(`Found ${pids.length} process(es) using port ${port}: ${pids.join(', ')}`);
            for (const pid of pids) {
              try {
                // Check if it's our backend process
                const procInfo = execSync(`ps -p ${pid} -o command= 2>/dev/null || true`, { encoding: 'utf-8' });
                if (procInfo.includes('backend_server') || procInfo.includes('uvicorn') || procInfo.includes('zotero-rag')) {
                  console.log(`  Killing backend process ${pid}...`);
                  execSync(`kill -9 ${pid} 2>/dev/null || true`);
                  console.log(`  ✓ Killed process ${pid}`);
                }
              } catch (e) {
                // Process might have already exited
              }
            }
          }
        } catch (e) {
          // lsof failed or no process found, continue
        }
      }
    } else if (process.platform === 'win32') {
      // Windows: Use netstat to find PIDs on our ports, then verify they are our
      // backend process before killing (to avoid killing unrelated servers).
      const { execSync } = require('child_process');
      const appProcessNames = ['backend_server', 'uvicorn', 'zotero-rag', 'python'];

      for (let port = 8000; port <= 8010; port++) {
        try {
          const result = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf-8' });
          const lines = result.split('\n');
          const pids = new Set<string>();
          
          for (const line of lines) {
            const parts = line.trim().split(/\s+/);
            const pid = parts[parts.length - 1];
            if (pid && pid !== '0' && !isNaN(Number(pid))) {
              pids.add(pid);
            }
          }
          
          if (pids.size > 0) {
            console.log(`Found ${pids.size} process(es) using port ${port}: ${Array.from(pids).join(', ')}`);
            for (const pid of pids) {
              try {
                // Verify it's our process before killing
                const taskInfo = execSync(`tasklist /FI "PID eq ${pid}" /FO CSV /NH`, { encoding: 'utf-8' }).toLowerCase();
                const isOurProcess = appProcessNames.some(name => taskInfo.includes(name));
                if (!isOurProcess) {
                  console.log(`  ⚠ Skipping PID ${pid} — not a known backend process`);
                  continue;
                }
                execSync(`taskkill /F /PID ${pid}`);
                console.log(`  ✓ Killed process ${pid}`);
              } catch (e) {
                // Process might have already exited
              }
            }
          }
        } catch (e) {
          // No process found on this port
        }
      }
    }
    console.log('✓ Cleanup complete');
  } catch (error) {
    console.warn('Warning: Error during process cleanup:', error);
    // Non-fatal, continue with startup
  }
}

/**
 * Check if Python 3 is available
 */
async function checkPythonAvailability(pythonCmd: string): Promise<{ available: boolean; version?: string; error?: string }> {
  return new Promise((resolve) => {
    const proc = spawn(pythonCmd, ['--version']);
    let output = '';

    proc.stdout?.on('data', (data) => {
      output += data.toString();
    });

    proc.stderr?.on('data', (data) => {
      output += data.toString();
    });

    proc.on('close', (code) => {
      if (code === 0 && output.includes('Python 3.')) {
        const versionMatch = output.match(/Python (\d+\.\d+\.\d+)/);
        resolve({ available: true, version: versionMatch?.[1] });
      } else {
        resolve({ available: false, error: 'Python 3 not found' });
      }
    });

    proc.on('error', () => {
      resolve({ available: false, error: `Command '${pythonCmd}' not found` });
    });

    setTimeout(() => {
      proc.kill();
      resolve({ available: false, error: 'Python check timed out' });
    }, 5000);
  });
}

/**
 * Find the bundled Python interpreter (production only)
 * Returns the full path to the bundled Python 3 interpreter
 * Supports both traditional venv bundles and PyInstaller executables
 */
async function findBundledPython(): Promise<{ path: string; version?: string; source: string; isPyInstaller?: boolean } | null> {
  const resourcesPath = process.resourcesPath;
  
  // First check for PyInstaller bundle (preferred method)
  const pyInstallerPaths = [
    // macOS/Linux - PyInstaller backend executable
    path.join(resourcesPath, 'python', 'backend_server'),
    path.join(resourcesPath, 'python', 'backend_server.exe'), // Windows
  ];
  
  console.log('Looking for PyInstaller bundled backend...');
  for (const execPath of pyInstallerPaths) {
    console.log(`  Checking: ${execPath}`);
    if (fs.existsSync(execPath)) {
      // Check if it's a real file (not a symlink to system Python)
      const stats = fs.lstatSync(execPath);
      if (stats.isSymbolicLink()) {
        console.warn(`  ✗ Found but it's a symlink (invalid bundle)`);
        continue;
      }
      
      console.log(`  ✓ Found PyInstaller bundle at ${execPath}`);
      return {
        path: execPath,
        version: 'PyInstaller bundle',
        source: 'bundled-pyinstaller',
        isPyInstaller: true
      };
    } else {
      console.log(`  ✗ Not found`);
    }
  }
  
  // Fallback: Check for traditional venv-style Python bundle
  const bundledPythonPaths = [
    // Linux/macOS - Standard locations for bundled Python
    path.join(resourcesPath, 'python', 'bin', 'python3'),
    path.join(resourcesPath, 'python', 'bin', 'python'),
    // Windows
    path.join(resourcesPath, 'python', 'Scripts', 'python.exe'),
    path.join(resourcesPath, 'python', 'python.exe'),
  ];
  
  console.log('Looking for traditional venv-style bundled Python interpreter...');
  for (const pythonPath of bundledPythonPaths) {
    console.log(`  Checking: ${pythonPath}`);
    if (fs.existsSync(pythonPath)) {
      // Check if it's a symlink (which would be invalid for distribution)
      const stats = fs.lstatSync(pythonPath);
      if (stats.isSymbolicLink()) {
        const linkTarget = fs.readlinkSync(pythonPath);
        // If it's an absolute symlink outside our bundle, it's invalid
        if (path.isAbsolute(linkTarget) && !linkTarget.startsWith(resourcesPath)) {
          console.warn(`  ✗ Found but it's an invalid symlink to: ${linkTarget}`);
          continue;
        }
      }
      
      console.log(`  ✓ Found bundled Python at ${pythonPath}`);
      // Verify it's a working Python 3 interpreter
      const result = await checkPythonAvailability(pythonPath);
      if (result.available) {
        console.log(`  ✓ Verified Python ${result.version}`);
        return {
          path: pythonPath,
          version: result.version,
          source: 'bundled-venv',
          isPyInstaller: false
        };
      } else {
        console.warn(`  ✗ Found file but not a working Python: ${result.error}`);
      }
    } else {
      console.log(`  ✗ Not found`);
    }
  }
  
  return null;
}

/**
 * Find the best Python interpreter to use (development only)
 * Returns the full path to a working Python 3 interpreter
 */
async function findSystemPython(): Promise<{ path: string; version?: string; source: string } | null> {
  const candidates: { path: string; source: string }[] = [];
  
  // Add system Python candidates
  // On Linux/macOS, prefer python3 over python
  if (process.platform !== 'win32') {
    candidates.push(
      { path: 'python3', source: 'system' },
      { path: 'python', source: 'system' },
      { path: '/usr/bin/python3', source: 'system' },
      { path: '/usr/local/bin/python3', source: 'system' }
    );
  } else {
    candidates.push(
      { path: 'python', source: 'system' },
      { path: 'python3', source: 'system' }
    );
  }
  
  // Test each candidate
  console.log('Looking for system Python interpreter...');
  for (const candidate of candidates) {
    console.log(`  Testing: ${candidate.path}`);
    const result = await checkPythonAvailability(candidate.path);
    
    if (result.available) {
      console.log(`  ✓ Found working Python ${result.version} at ${candidate.path}`);
      return {
        path: candidate.path,
        version: result.version,
        source: candidate.source
      };
    } else {
      console.log(`  ✗ ${candidate.path}: ${result.error}`);
    }
  }
  
  return null;
}

/**
 * Setup Linux virtual environment on first run
 * Creates venv in ~/.config/rag-assistant/venv and installs dependencies
 */
async function setupLinuxVenv(onProgress?: (message: string, progress?: number) => void): Promise<{ pythonPath: string; venvPath: string } | null> {
  const os = require('os');
  const configDir = path.join(os.homedir(), '.config', 'rag-assistant');
  const venvPath = path.join(configDir, 'venv');
  const pythonBin = path.join(venvPath, 'bin', 'python3');
  
  // Check if venv already exists and is valid
  if (fs.existsSync(pythonBin)) {
    console.log(`Found existing venv at: ${venvPath}`);
    
    // Verify uvicorn is installed (critical dependency check)
    const hasUvicorn = await new Promise<boolean>((resolve) => {
      const proc = spawn(pythonBin, ['-m', 'uvicorn', '--version']);
      proc.on('close', (code) => resolve(code === 0));
      proc.on('error', () => resolve(false));
      setTimeout(() => { proc.kill(); resolve(false); }, 3000);
    });
    
    if (hasUvicorn) {
      console.log(`✓ Linux venv valid with all dependencies at: ${venvPath}`);
      return { pythonPath: pythonBin, venvPath };
    } else {
      console.warn('WARNING: Existing venv missing dependencies (uvicorn not found)');
      console.log('Reinstalling dependencies...');
      
      // Try to repair by reinstalling dependencies
      try {
        const requirementsPath = path.join(process.resourcesPath, 'requirements.txt');
        if (fs.existsSync(requirementsPath)) {
          onProgress?.('Updating Python dependencies...', 50);
          const pipBin = path.join(venvPath, 'bin', 'pip');
          await new Promise<void>((resolve, reject) => {
            const proc = spawn(pipBin, ['install', '--no-cache-dir', '-r', requirementsPath]);
            proc.stdout?.on('data', (data) => console.log(data.toString()));
            proc.stderr?.on('data', (data) => console.error(data.toString()));
            proc.on('close', (code) => code === 0 ? resolve() : reject(new Error('Dependency install failed')));
            proc.on('error', reject);
          });
          console.log('✓ Dependencies reinstalled successfully');
          onProgress?.('Dependencies updated!', 100);
          return { pythonPath: pythonBin, venvPath };
        }
      } catch (error) {
        console.error('✗ Failed to repair venv:', error);
        console.log('Will recreate venv from scratch...');
        // Fall through to recreate venv
      }
    }
  }
  
  console.log('================================================================================');
  console.log('Linux: First run setup - creating virtual environment');
  console.log('================================================================================');
  
  // Find system Python
  const systemPython = await findSystemPython();
  if (!systemPython) {
    console.error('✗ System Python 3.8+ not found');
    console.error('Please install: sudo apt install python3 python3-pip python3-venv');
    if (mainWindow) {
      dialog.showErrorBox(
        'Python Required',
        'Python 3.8 or later is required.\n\nPlease install:\nsudo apt install python3 python3-pip python3-venv\n\nThen restart the application.'
      );
    }
    return null;
  }
  
  try {
    // Create config directory
    onProgress?.('Creating configuration directory...', 10);
    fs.mkdirSync(configDir, { recursive: true });
    console.log(`✓ Created config directory: ${configDir}`);
    
    // Create virtual environment
    onProgress?.('Creating Python virtual environment...', 20);
    console.log(`Creating venv with ${systemPython.path}...`);
    await new Promise<void>((resolve, reject) => {
      const proc = spawn(systemPython.path, ['-m', 'venv', venvPath]);
      let stderr = '';
      
      proc.stderr?.on('data', (data) => { stderr += data.toString(); });
      
      proc.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error(`venv creation failed: ${stderr}`));
      });
      
      proc.on('error', reject);
    });
    console.log('✓ Virtual environment created');
    
    // Upgrade pip
    onProgress?.('Upgrading pip...', 40);
    console.log('Upgrading pip...');
    await new Promise<void>((resolve, reject) => {
      const pipBin = path.join(venvPath, 'bin', 'pip');
      const proc = spawn(pipBin, ['install', '--upgrade', 'pip']);
      
      proc.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error('pip upgrade failed'));
      });
      
      proc.on('error', reject);
    });
    console.log('✓ pip upgraded');
    
    // Install dependencies
    onProgress?.('Installing Python dependencies (this may take 2-5 minutes)...', 50);
    console.log('Installing dependencies from requirements.txt...');
    const requirementsPath = path.join(process.resourcesPath, 'requirements.txt');
    
    if (!fs.existsSync(requirementsPath)) {
      throw new Error(`requirements.txt not found at: ${requirementsPath}`);
    }
    
    await new Promise<void>((resolve, reject) => {
      const pipBin = path.join(venvPath, 'bin', 'pip');
      const proc = spawn(pipBin, ['install', '--no-cache-dir', '-r', requirementsPath]);
      let lastOutput = '';
      
      proc.stdout?.on('data', (data) => {
        lastOutput = data.toString();
        console.log(lastOutput);
        
        // Parse progress from pip output
        const match = lastOutput.match(/Downloading.*\((\d+)\/(\d+)\)/);
        if (match) {
          const current = parseInt(match[1]);
          const total = parseInt(match[2]);
          const progress = 50 + Math.floor((current / total) * 40);
          onProgress?.(`Installing dependencies (${current}/${total})...`, progress);
        }
      });
      
      proc.stderr?.on('data', (data) => { console.error(data.toString()); });
      
      proc.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error('Dependency installation failed'));
      });
      
      proc.on('error', reject);
    });
    
    onProgress?.('Setup complete!', 100);
    console.log('✓ Dependencies installed successfully');
    console.log('================================================================================');
    
    return { pythonPath: pythonBin, venvPath };
  } catch (error) {
    console.error('✗ Linux venv setup failed:', error);
    
    // Provide detailed error message
    const errorMsg = error instanceof Error ? error.message : String(error);
    let userMessage = 'Failed to set up Python environment.\n\n';
    
    // Provide specific guidance based on error
    if (errorMsg.includes('venv creation failed') || errorMsg.includes('No module named venv')) {
      userMessage += 'Python venv module is missing.\n\n' +
        'Install it with:\n' +
        '  sudo apt install python3-venv\n\n';
    } else if (errorMsg.includes('pip upgrade failed') || errorMsg.includes('Dependency installation failed')) {
      userMessage += 'Failed to install required Python packages.\n\n' +
        'This may be due to:\n' +
        '  - Network connectivity issues\n' +
        '  - Missing build tools\n\n' +
        'Try installing build essentials:\n' +
        '  sudo apt install build-essential python3-dev\n\n';
    } else {
      userMessage += 'Please ensure Python 3.8+ is installed:\n' +
        '  sudo apt install python3 python3-pip python3-venv\n\n';
    }
    
    userMessage += `Error details: ${errorMsg}\n\n` +
      'Check the console logs for more information.';
    
    dialog.showErrorBox('Python Environment Setup Failed', userMessage);
    return null;
  }
}

/**
 * Get the path to the Python backend
 * In dev: use the source directory with system Python
 * In production: use the packaged backend with bundled PyInstaller executable (all platforms)
 */
async function getBackendPath(): Promise<{ command: string; args: string[]; cwd: string; pythonInfo?: { version?: string; source: string } } | null> {
  if (IS_DEV) {
    // Development: run uvicorn directly from source using system Python
    // In dev, __dirname is typically dist/electron/, so go up two levels to project root
    const projectRoot = path.resolve(__dirname, '..', '..');
    
    console.log('Development mode: finding Python interpreter...');
    const pythonInfo = await findSystemPython();
    
    if (!pythonInfo) {
      console.error('✗ No Python 3 interpreter found on system');
      console.error('Please install Python 3.8+ for development');
      return null;
    }
    
    console.log(`Using system Python: ${pythonInfo.path} (${pythonInfo.version || 'unknown version'})`);
    
    return {
      command: pythonInfo.path,
      args: ['-m', 'uvicorn', 'backend.main:app', '--port', BACKEND_PORT.toString()],
      cwd: projectRoot,
      pythonInfo
    };
  } else {
    // Production
    const resourcesPath = process.resourcesPath;
    
    // Linux: Use venv approach (smaller packages, uses system Python)
    if (process.platform === 'linux') {
      console.log('Production mode (Linux): Setting up virtual environment...');
      
      // Create loading window for venv setup
      let loadingWindow: BrowserWindow | null = null;
      try {
        loadingWindow = createLoadingWindow('Checking Python environment...');
      } catch (e) {
        console.warn('Failed to create loading window:', e);
      }
      
      const venvSetup = await setupLinuxVenv((message: string, progress?: number) => {
        console.log(`[Setup Progress] ${message} ${progress !== undefined ? `(${progress}%)` : ''}`);
        updateLoadingWindow(loadingWindow, message, progress);
      });
      
      // Close loading window
      if (loadingWindow && !loadingWindow.isDestroyed()) {
        loadingWindow.close();
        loadingWindow = null;
      }
      
      if (!venvSetup) {
        console.error('================================================================================');
        console.error('✗ FATAL: Failed to set up Linux virtual environment');
        console.error('================================================================================');
        console.error('  Please ensure Python 3.8+ is installed:');
        console.error('    sudo apt install python3 python3-pip python3-venv');
        console.error('================================================================================');
        
        // Show detailed error dialog
        dialog.showErrorBox(
          'Python Environment Setup Failed',
          'Failed to set up the Python environment required to run this application.\n\n' +
          'Required: Python 3.8 or later with venv support\n\n' +
          'Please install:\n' +
          '  sudo apt install python3 python3-pip python3-venv\n\n' +
          'Then restart the application.\n\n' +
          'If Python is already installed, check the console logs for specific errors.'
        );
        return null;
      }
      
      console.log(`Using Linux venv: ${venvSetup.pythonPath}`);
      
      // SOLUTION: Use shell wrapper to fully detach backend from Electron process tree
      // This avoids Chromium restrictions that kill child Python processes during imports
      const wrapperPath = path.join(resourcesPath, 'start-backend.sh');
      if (fs.existsSync(wrapperPath)) {
        console.log(`🔧 Using detached shell wrapper: ${wrapperPath}`);
        return {
          command: wrapperPath,
          args: [venvSetup.pythonPath, '-m', 'uvicorn', 'backend.main:app', '--port', BACKEND_PORT.toString()],
          cwd: resourcesPath,
          pythonInfo: { version: 'venv', source: 'linux-venv-detached' }
        };
      }
      
      // TEMPORARY DEBUG: Use wrapper script to diagnose spawn issues
      const debugWrapperPath = path.join(resourcesPath, 'uvicorn_wrapper.py');
      if (fs.existsSync(debugWrapperPath)) {
        console.log(`🔍 DEBUG: Using wrapper script at ${debugWrapperPath}`);
        return {
          command: venvSetup.pythonPath,
          args: [debugWrapperPath],
          cwd: resourcesPath,
          pythonInfo: { version: 'venv', source: 'linux-venv' }
        };
      }
      
      return {
        command: venvSetup.pythonPath,
        args: ['-m', 'uvicorn', 'backend.main:app', '--port', BACKEND_PORT.toString()],
        cwd: resourcesPath,
        pythonInfo: { version: 'venv', source: 'linux-venv' }
      };
    }
    
    // Windows/macOS: Use bundled PyInstaller executable
    console.log('Production mode: looking for bundled Python interpreter...');
    const pythonInfo = await findBundledPython();
    
    if (!pythonInfo) {
      console.error('================================================================================');
      console.error('✗ FATAL: Bundled Python interpreter not found');
      console.error('================================================================================');
      console.error(`  Resources path: ${resourcesPath}`);
      console.error(`  Expected Python locations (PyInstaller):`);
      console.error(`    - ${path.join(resourcesPath, 'python', 'backend_server')}`);
      console.error(`  Expected Python locations (venv fallback):`);
      console.error(`    - ${path.join(resourcesPath, 'python', 'bin', 'python3')}`);
      console.error(`    - ${path.join(resourcesPath, 'python', 'bin', 'python')}`);
      if (process.platform === 'win32') {
        console.error(`    - ${path.join(resourcesPath, 'python', 'Scripts', 'python.exe')}`);
        console.error(`    - ${path.join(resourcesPath, 'python', 'python.exe')}`);
      }
      console.error('');
      console.error('  This is a packaging error. The application should be self-contained.');
      console.error('  Please contact support or reinstall the application.');
      console.error('================================================================================');
      return null;
    }
    
    console.log(`Using bundled Python: ${pythonInfo.path} (${pythonInfo.version || 'unknown version'})`);
    
    // PyInstaller bundles are standalone executables that don't need uvicorn arguments
    if (pythonInfo.isPyInstaller) {
      console.log('Using PyInstaller bundle - running standalone backend executable');
      return {
        command: pythonInfo.path,
        args: ['--port', BACKEND_PORT.toString()],
        cwd: resourcesPath,
        pythonInfo
      };
    } else {
      // Traditional venv-style bundle
      console.log('Using venv-style bundle - running uvicorn with Python interpreter');
      return {
        command: pythonInfo.path,
        args: ['-m', 'uvicorn', 'backend.main:app', '--port', BACKEND_PORT.toString()],
        cwd: resourcesPath,
        pythonInfo
      };
    }
  }
}

/**
 * Check if the backend is ready by polling the health endpoint
 * @param maxRetries - Maximum number of health check attempts
 * @param delayMs - Delay between attempts
 * @param modelDownloadInProgress - Callback to check if model download is happening (extends timeout)
 */
async function waitForBackend(maxRetries = 30, delayMs = 1000, modelDownloadInProgress?: () => boolean): Promise<boolean> {
  console.log(`Waiting for backend to be ready (checking ${BACKEND_URL}/health)...`);
  
  let attempts = 0;
  const startTime = Date.now();
  
  while (attempts < maxRetries) {
    try {
      // Use generous timeout as connections can be slower on first startup
      // especially with indexing or slow disk I/O
      const timeout = 3000;
      const response = await axios.get(`${BACKEND_URL}/health`, { timeout });
      
      if (response.status === 200) {
        const healthData = response.data;
        console.log('Backend health check response:', JSON.stringify(healthData, null, 2));
        
        if (healthData.status === 'healthy') {
          console.log('✓ Backend is ready and healthy!');
          return true;
        } else if (healthData.status === 'degraded') {
          console.warn('WARNING: Backend is running but degraded:', healthData.components);
          // Still return true for degraded - app can function with warnings
          return true;
        } else {
          console.error('✗ Backend unhealthy:', healthData);
          // Continue retrying for unhealthy status
        }
      }
    } catch (error) {
      // Backend not ready yet - only log every 5 attempts to reduce noise
      if ((attempts + 1) % 5 === 0) {
        console.log(`  Attempt ${attempts + 1}/${maxRetries}: Backend not responding yet...`);
      }
      
      // If model download is in progress, don't count against max retries
      // This prevents timeout during lengthy first-run model downloads
      if (modelDownloadInProgress && modelDownloadInProgress()) {
        const elapsedSeconds = Math.round((Date.now() - startTime) / 1000);
        console.log(`  Model download in progress (${elapsedSeconds}s elapsed) - extending timeout...`);
        // Don't increment attempts counter, but still wait
      } else {
        attempts++;
      }
      
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }
  
  console.error(`✗ Backend failed to start within ${maxRetries * delayMs / 1000}s timeout`);
  console.error('Troubleshooting tips:');
  console.error('  1. Check if Python executable exists at the expected path');
  console.error('  2. Review backend process logs above for errors');
  console.error('  3. Verify backend dependencies are properly bundled');
  console.error(`  4. Try accessing ${BACKEND_URL}/health in a browser`);
  return false;
}

/**
 * Spawn the Python backend process
 */
async function startBackend(): Promise<boolean> {
  // Create splash window immediately for visual feedback
  splashWindow = createLoadingWindow('Starting RAG Assistant...');
  
  // Kill any existing backend processes before starting
  await killExistingBackendProcesses();
  
  // Find an available port
  console.log(`Checking port availability (preferred: ${BACKEND_PORT})...`);
  updateLoadingWindow(splashWindow, 'Checking port availability...');
  const availablePort = await findAvailablePort(BACKEND_PORT);
  if (!availablePort) {
    console.error('================================================================================');
    console.error('✗ FATAL: Could not find an available port for backend');
    console.error('  Ports 8000-8010 are all in use');
    console.error('================================================================================');
    
    dialog.showErrorBox(
      'No Available Port',
      'Could not find an available port to start the backend service.\n\n' +
      'Ports 8000-8010 are all in use. Please close other applications and try again.'
    );
    return false;
  }
  
  if (availablePort !== BACKEND_PORT) {
    console.log(`Port ${BACKEND_PORT} unavailable, using port ${availablePort}`);
    BACKEND_PORT = availablePort;
    BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
  } else {
    console.log(`✓ Port ${BACKEND_PORT} is available`);
  }
  
  const backendConfig = await getBackendPath();
  
  if (!backendConfig) {
    console.error('================================================================================');
    console.error('✗ FATAL: Could not find Python interpreter');
    console.error('================================================================================');
    
    if (IS_DEV) {
      // Development mode: guide user to install Python
      const platform = process.platform;
      let instructions = 'Please install Python 3.8 or later.';
      
      if (platform === 'linux') {
        instructions = 'Please install Python 3:\n\n' +
          'Ubuntu/Debian: sudo apt install python3\n' +
          'Fedora/RHEL: sudo dnf install python3\n' +
          'Arch: sudo pacman -S python';
      } else if (platform === 'darwin') {
        instructions = 'Please install Python 3:\n\n' +
          'Using Homebrew: brew install python3\n' +
          'Or download from: https://www.python.org/downloads/';
      } else if (platform === 'win32') {
        instructions = 'Please install Python 3 from:\nhttps://www.python.org/downloads/\n\n' +
          'Make sure to check "Add Python to PATH" during installation.';
      }
      
      dialog.showErrorBox(
        'Python Not Found',
        `The application requires Python 3 to run the backend service.\n\n${instructions}`
      );
    } else {
      // Production mode: this is a packaging error
      dialog.showErrorBox(
        'Application Installation Error',
        `The bundled Python interpreter is missing from this installation.\n\n` +
        `This is a packaging error. The application should be self-contained and not require Python to be installed on your system.\n\n` +
        `Please try:\n` +
        `1. Reinstalling the application\n` +
        `2. Downloading a fresh copy from the official source\n` +
        `3. Contacting support if the problem persists\n\n` +
        `Expected Python location:\n${path.join(process.resourcesPath, 'python', 'bin', 'python3')}`
      );
    }
    return false;
  }
  
  const { command, args, cwd, pythonInfo } = backendConfig;
  
  console.log('================================================================================');
  console.log('Starting backend...');
  console.log(`  Python: ${command}`);
  if (pythonInfo) {
    console.log(`  Version: ${pythonInfo.version || 'unknown'}`);
    console.log(`  Source: ${pythonInfo.source}`);
  }
  console.log(`  Args: ${args.join(' ')}`);
  console.log(`  Working directory: ${cwd}`);
  console.log('================================================================================');
  
  // Validate backend structure (in production)
  if (!IS_DEV) {
    console.log('================================================================================');
    console.log('Backend Structure Validation:');
    console.log(`  - Resources path: ${process.resourcesPath}`);
    console.log(`  - Python command: ${command}`);
    console.log(`  - Python source: ${pythonInfo?.source || 'unknown'}`);
    
    // Only check if Python exists if it's a full path (bundled or absolute system path)
    const isPythonFullPath = path.isAbsolute(command) || command.includes(path.sep);
    if (isPythonFullPath) {
      console.log(`  - Python exists: ${fs.existsSync(command)}`);
    } else {
      console.log(`  - Python command (will use PATH): ${command}`);
    }
    
    console.log(`  - Backend directory: ${cwd}`);
    console.log(`  - Backend exists: ${fs.existsSync(cwd)}`);
    
    // List Resources directory
    try {
      const resourceContents = fs.readdirSync(process.resourcesPath);
      console.log(`  - Resources contents: ${resourceContents.filter(f => !f.endsWith('.lproj')).join(', ')}`);
      
      if (fs.existsSync(path.join(process.resourcesPath, 'python'))) {
        const pythonBinPath = path.join(process.resourcesPath, 'python', 'bin');
        if (fs.existsSync(pythonBinPath)) {
          const pythonBinContents = fs.readdirSync(pythonBinPath);
          console.log(`  - python/bin/ contents: ${pythonBinContents.slice(0, 10).join(', ')}${pythonBinContents.length > 10 ? '...' : ''}`);
        }
      }
      
      const backendDir = path.join(process.resourcesPath, 'backend');
      if (fs.existsSync(backendDir)) {
        const backendContents = fs.readdirSync(backendDir);
        console.log(`  - backend/ contents: ${backendContents.join(', ')}`);
      }
    } catch (e) {
      console.error(`  - Error listing directories: ${e}`);
    }
    
    // Validate Python executable (only if it's a full path)
    if (isPythonFullPath && !fs.existsSync(command)) {
      console.error('✗ WARNING: Bundled Python executable not found, using system Python');
      console.error(`  Expected bundled Python at: ${command}`);
    }
    
    // Validate backend directory
    if (!fs.existsSync(cwd)) {
      console.error('✗ FATAL: Backend directory not found');
      console.error('================================================================================');
      
      dialog.showErrorBox(
        'Backend Missing - Source Not Found',
        `The backend source directory is missing.\n\nExpected: ${cwd}\n\nSee console logs for directory structure details.`
      );
      return false;
    }
    
    // Validate main.py exists
    const mainPyPath = path.join(cwd, 'backend', 'main.py');
    if (!fs.existsSync(mainPyPath)) {
      console.error(`✗ FATAL: Backend main.py not found at: ${mainPyPath}`);
      console.error('================================================================================');
      
      dialog.showErrorBox(
        'Backend Missing - main.py Not Found',
        `The backend entry point is missing.\n\nExpected: ${mainPyPath}\n\nSee console logs for directory structure details.`
      );
      return false;
    }
    
    console.log('✓ Backend structure validation passed');
    console.log('================================================================================');
  }
  
  try {
    // Store backend output for diagnostics
    let backendOutput: string[] = [];
    let backendErrors: string[] = [];
    
    // Track model download progress
    let modelDownloadInProgress = false;
    let lastModelDownloadTime = 0;
    let currentDownloadFile = '';
    let currentDownloadProgress = 0;
    
    // Enhanced environment for backend process
    const backendEnv = {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8',
      // Ensure Python can find the bundled libraries in production
      ...((!IS_DEV && process.platform === 'darwin') ? {
        DYLD_LIBRARY_PATH: path.join(process.resourcesPath, 'python', 'lib')
      } : {}),
      // CRITICAL FIX: Unset Electron sandbox variables that get inherited by child processes
      // This prevents the Python backend from being killed by Electron's sandbox
      ELECTRON_RUN_AS_NODE: undefined,
      ELECTRON_NO_ASAR: undefined,
      // Pass auth token to backend if needed in future
      // AUTH_TOKEN: authToken
    };
    
    console.log('Backend environment:');
    console.log(`  - PYTHONUNBUFFERED: ${backendEnv.PYTHONUNBUFFERED}`);
    console.log(`  - PYTHONIOENCODING: ${backendEnv.PYTHONIOENCODING}`);
    if (backendEnv.DYLD_LIBRARY_PATH) {
      console.log(`  - DYLD_LIBRARY_PATH: ${backendEnv.DYLD_LIBRARY_PATH}`);
    }
    console.log('Spawning process...');
    
    // Spawn in a new process group so we can kill all child processes
    // EXPERIMENTAL FIX: Try different stdio configuration for Linux production
    // Piped stdio might be failing when Electron runs from asar
    const useLogFiles = process.platform === 'linux' && app.isPackaged;
    
    const spawnOptions: any = {
      cwd,
      stdio: useLogFiles 
        ? ['ignore', 'inherit', 'inherit'] // Write directly to console (for debugging)
        : ['ignore', 'pipe', 'pipe'], // Explicitly pipe stdout and stderr
      env: backendEnv
    };
    
    // On Unix, create a new process group (detached but we keep reference)
    if (process.platform !== 'win32') {
      spawnOptions.detached = false; // Keep attached but in new group
      // By default on Unix, spawn creates new process group when shell: false
    }
    
    if (useLogFiles) {
      console.log('⚠️  Using inherit stdio for debugging - backend output will appear in console');
    }
    
    console.log('================================================================================');
    console.log('SPAWN DEBUG INFO:');
    console.log(`  Command: ${command}`);
    console.log(`  Args: ${JSON.stringify(args)}`);
    console.log(`  CWD: ${cwd}`);
    console.log(`  CWD exists: ${fs.existsSync(cwd)}`);
    console.log(`  Command exists: ${fs.existsSync(command)}`);
    console.log(`  Command is executable: ${fs.existsSync(command) ? (fs.statSync(command).mode & 0o111) !== 0 : 'N/A'}`);
    console.log(`  Process UID: ${process.getuid ? process.getuid() : 'N/A'}`);
    console.log(`  Process GID: ${process.getgid ? process.getgid() : 'N/A'}`);
    console.log(`  Stdio config: ${JSON.stringify(spawnOptions.stdio)}`);
    console.log(`  Detached: ${spawnOptions.detached}`);
    console.log(`  Using file logging: ${useLogFiles}`);
    console.log('================================================================================');
    
    backendProcess = spawn(command, args, spawnOptions);
    
    console.log(`✓ Process spawned with PID: ${backendProcess.pid}`);
    
    // Immediately check if process is still alive
    setTimeout(() => {
      if (backendProcess) {
        console.log(`[100ms check] Process alive: ${backendProcess.exitCode === null}, PID: ${backendProcess.pid}`);
      }
    }, 100);
    
    setTimeout(() => {
      if (backendProcess) {
        console.log(`[500ms check] Process alive: ${backendProcess.exitCode === null}, PID: ${backendProcess.pid}`);
      }
    }, 500);
    
    setTimeout(() => {
      if (backendProcess) {
        console.log(`[1000ms check] Process alive: ${backendProcess.exitCode === null}, PID: ${backendProcess.pid}`);
      }
    }, 1000);
    
    // Log backend output with timestamps
    // Only set up stdout/stderr handlers if we're using pipe mode
    if (!useLogFiles) {
      backendProcess.stdout?.on('data', (data) => {
        const output = data.toString().trim();
        backendOutput.push(output);
        const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
        console.log(`[Backend ${timestamp}] ${output}`);
      });
      
      backendProcess.stderr?.on('data', (data) => {
        const output = data.toString().trim();
        backendErrors.push(output);
        const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
        
        // Parse model download progress (tqdm format: "filename: XX%|####...")
        const downloadMatch = output.match(/^([\w\.\-]+):\s+(\d+)%\|/);
        if (downloadMatch) {
          const filename = downloadMatch[1];
          const progress = parseInt(downloadMatch[2]);
          
          modelDownloadInProgress = true;
          lastModelDownloadTime = Date.now();
          currentDownloadFile = filename;
          currentDownloadProgress = progress;
          
          // Update splash window with download progress
          const message = `Downloading AI model: ${filename}`;
          console.log(`[Model Download ${timestamp}] ${filename}: ${progress}%`);
          updateLoadingWindow(splashWindow, message, progress);
        }
        // Check if download just started (0% or initial)
        else if (output.match(/^([\w\.\-]+):\s+0%|^(config\.json|model\.safetensors|tokenizer)/)) {
          modelDownloadInProgress = true;
          lastModelDownloadTime = Date.now();
          updateLoadingWindow(splashWindow, 'Initializing AI model download...');
        }
        
        // Some stderr output is just warnings, not fatal errors
        if (output.includes('WARNING') || output.includes('DeprecationWarning')) {
          console.warn(`[Backend Warning ${timestamp}] ${output}`);
        } else {
          console.error(`[Backend Error ${timestamp}] ${output}`);
        }
      });
    } else {
      console.log('Backend stdio inherited - output will appear directly in console');
    }
    
    backendProcess.on('error', (error) => {
      console.error('================================================================================');
      console.error('✗ FATAL: Failed to spawn backend process');
      console.error(`  Error: ${error.message}`);
      console.error(`  Error code: ${(error as any).code}`);
      console.error(`  Error errno: ${(error as any).errno}`);
      console.error(`  Error syscall: ${(error as any).syscall}`);
      console.error(`  Command: ${command} ${args.join(' ')}`);
      console.error(`  Working directory: ${cwd}`);
      console.error(`  Stack: ${error.stack}`);
      console.error('================================================================================');
      
      dialog.showErrorBox(
        'Backend Process Failed',
        `Failed to start backend process: ${error.message}\n\nCommand: ${command}\nSee console logs for details.`
      );
    });
    
    backendProcess.on('exit', (code, signal) => {
      const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
      console.log('================================================================================');
      console.log(`[Backend ${timestamp}] Process exited`);
      console.log(`  Exit code: ${code}`);
      console.log(`  Signal: ${signal}`);
      console.log(`  Stdout lines captured: ${backendOutput.length}`);
      console.log(`  Stderr lines captured: ${backendErrors.length}`);
      console.log('================================================================================');
      
      // Log final output if process crashed
      if (code !== 0 && code !== null) {
        console.error('Backend crash diagnostics:');
        console.error(`  Last 20 stdout lines:\n    ${backendOutput.slice(-20).join('\n    ')}`);
        console.error(`  Last 20 stderr lines:\n    ${backendErrors.slice(-20).join('\n    ')}`);
      }
      
      // Even if exit was clean, log what we got if very little output
      if (backendOutput.length === 0 && backendErrors.length === 0 && !useLogFiles) {
        console.error('⚠️  WARNING: Process exited without producing any stdout/stderr output!');
        console.error('  This suggests the process died immediately after fork, possibly due to:');
        console.error('    - Missing library dependencies');
        console.error('    - Permission/security restrictions');
        console.error('    - Stdio pipe setup issues');
        console.error('    - Kernel OOM killer');
        console.error('  Recommendation: Check if Python process can be started manually:');
        console.error(`    cd ${cwd} && ${command} ${args.join(' ')}`);
      }
      
      backendProcess = null;
      
      // If backend crashes unexpectedly after startup, notify user
      if (code !== 0 && code !== null && mainWindow && !mainWindow.isDestroyed()) {
        const recentErrors = backendErrors.slice(-5).join('\n').substring(0, 300);
        dialog.showErrorBox(
          'Backend Crashed',
          `The backend process exited unexpectedly (exit code: ${code}).\n\n` +
          `This may be due to:\n` +
          `  - Missing Python dependencies\n` +
          `  - Corrupted virtual environment\n` +
          `  - File permission issues\n\n` +
          `Check the console logs for details.\n\n` +
          `Recent errors:\n${recentErrors}`
        );
      }
    });
    
    // For detached launches (shell wrapper), skip early exit check
    // The wrapper exits with code 0 immediately, which is expected
    const isDetachedLaunch = pythonInfo?.source === 'linux-venv-detached';
    
    if (isDetachedLaunch) {
      console.log('✓ Using detached launch - skipping process exit check, going straight to health check...');
    } else {
      console.log('Waiting for immediate startup errors...');
      
      // Wait a moment for immediate errors
      // Windows + PyInstaller needs more time for extraction before the process is stable
      const startupWaitMs = process.platform === 'win32' ? 3000 : 1500;
      await new Promise(resolve => setTimeout(resolve, startupWaitMs));
      
      const processExited = !backendProcess || backendProcess.killed || backendProcess.exitCode !== null;
      
      // Check if process died immediately
      if (processExited) {
        console.error('================================================================================');
        console.error('✗ FATAL: Backend process died immediately');
        console.error(`  Exit code: ${backendProcess?.exitCode}`);
        console.error(`  Signal: ${backendProcess?.signalCode}`);
        console.error(`  Killed: ${backendProcess?.killed}`);
        console.error(`  Output (${backendOutput.length} lines):\n    ${backendOutput.join('\n    ')}`);
        console.error(`  Errors (${backendErrors.length} lines):\n    ${backendErrors.join('\n    ')}`);
        console.error('================================================================================');
        
        // Provide helpful error message to user
        let errorSummary = 'The backend process failed to start.\n\n';
        
        // Try to identify the issue from stderr
        const stderrText = backendErrors.join('\n').toLowerCase();
        if (stderrText.includes('modulenotfounderror') || stderrText.includes('no module named')) {
          errorSummary += 'Issue: Missing Python dependencies\n\n' +
            'On Linux, dependencies should be automatically installed.\n' +
            'Try removing the virtual environment and restarting:\n\n' +
            '  rm -rf ~/.config/rag-assistant/venv\n\n';
        } else if (stderrText.includes('permission denied') || stderrText.includes('errno 13')) {
          errorSummary += 'Issue: File permission problem\n\n' +
            'Check that the application has permission to:\n' +
            '  - Read/execute Python files\n' +
            '  - Write to ~/.config/rag-assistant/\n\n';
        } else if (stderrText.includes('address already in use') || stderrText.includes('errno 98')) {
          errorSummary += 'Issue: Port 8000 is already in use\n\n' +
            'Another application is using the required port.\n' +
            'Try closing other applications and restarting.\n\n';
        } else {
          errorSummary += 'Review the error output below and console logs.\n\n';
        }
        
        errorSummary += `Error output:\n${backendErrors.slice(0, 10).join('\n').substring(0, 500)}`;
        
        // Close splash window before showing error dialog
        if (splashWindow && !splashWindow.isDestroyed()) {
          splashWindow.close();
          splashWindow = null;
        }
        
        dialog.showErrorBox('Backend Startup Failed', errorSummary);
        return false;
      }
    }
    
    console.log('✓ Process check passed, checking health endpoint...');
    updateLoadingWindow(splashWindow, 'Starting backend service...');
    
    // Function to check if model download is still happening
    // Consider download active if we saw progress in last 30 seconds
    const isModelDownloading = () => {
      const timeSinceLastProgress = Date.now() - lastModelDownloadTime;
      return modelDownloadInProgress && timeSinceLastProgress < 30000;
    };
    
    // Wait for backend to be ready with retry logic
    // Use generous timeouts as initialization can be slow (especially on first run with indexing)
    // The model download callback will extend timeout indefinitely while downloads are active
    let isReady = await waitForBackend(30, 1000, isModelDownloading);  // Pass download check
    if (!isReady) {
      console.log('Initial startup phase incomplete, continuing with longer intervals (3000ms)...');
      updateLoadingWindow(splashWindow, 'Continuing initialization...');
      isReady = await waitForBackend(20, 3000, isModelDownloading);  // Pass download check
      
      // If still not ready, dump comprehensive diagnostics
      if (!isReady) {
        console.error('================================================================================');
        console.error('✗ FATAL: Backend failed to become ready');
        console.error('Final diagnostics:');
        console.error(`  Process alive: ${backendProcess && !backendProcess.killed && backendProcess.exitCode === null}`);
        console.error(`  PID: ${backendProcess?.pid}`);
        console.error(`  Exit code: ${backendProcess?.exitCode}`);
        console.error(`  All stdout (${backendOutput.length} lines):\n    ${backendOutput.join('\n    ')}`);
        console.error(`  All stderr (${backendErrors.length} lines):\n    ${backendErrors.join('\n    ')}`);
        console.error('================================================================================');
        
        // Show helpful error to user
        const allErrors = backendErrors.join('\n');
        let errorMessage = 'The backend service failed to start within the timeout period.\n\n';
        
        if (backendProcess && !backendProcess.killed && backendProcess.exitCode === null) {
          errorMessage += 'The process is still running but not responding.\n\n' +
            'Possible causes:\n' +
            '  - Backend is stuck during initialization\n' +
            '  - Firewall blocking localhost connections\n' +
            '  - Database or file system issues\n\n';
        } else {
          errorMessage += 'The process has stopped or crashed.\n\n';
        }
        
        errorMessage += `Recent errors:\n${allErrors.substring(allErrors.length - 400)}`;
        
        // Close splash window before showing error dialog
        if (splashWindow && !splashWindow.isDestroyed()) {
          splashWindow.close();
          splashWindow = null;
        }
        
        dialog.showErrorBox('Backend Failed to Start', errorMessage);
      }
    }
    
    if (isReady) {
      console.log('✓ Backend is ready!');
      updateLoadingWindow(splashWindow, 'Backend ready! Loading application...');
    }
    
    return isReady;
    
  } catch (error) {
    console.error('================================================================================');
    console.error('✗ EXCEPTION in startBackend:');
    console.error(error);
    console.error('================================================================================');
    
    // Close splash window on error
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
    
    return false;
  }
}

/**
 * Stop the backend process gracefully
 */
async function stopBackend(): Promise<void> {
  if (!backendProcess) {
    console.log('No backend process to stop');
    return;
  }
  
  console.log('Stopping backend process...');
  
  const pid = backendProcess.pid;
  
  if (!pid) {
    console.log('Backend process has no PID, clearing reference');
    backendProcess = null;
    return;
  }
  
  try {
    // First, try graceful shutdown via HTTP if backend is responsive
    try {
      console.log('Attempting graceful shutdown via /shutdown endpoint...');
      await axios.post(`${BACKEND_URL}/shutdown`, {}, { timeout: 1000 });
      console.log('✓ Graceful shutdown signal sent');
      
      // Wait a bit for graceful shutdown
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      // Check if process exited
      if (backendProcess && backendProcess.exitCode !== null) {
        console.log('✓ Backend exited gracefully');
        backendProcess = null;
        return;
      }
    } catch (e) {
      console.log('Graceful shutdown failed, proceeding with SIGTERM...');
    }
    
    // Kill entire process tree (Python spawns child processes like ChromaDB)
    if (process.platform === 'win32') {
      // Windows: use taskkill to kill process tree
      const { execSync } = require('child_process');
      console.log('Sending SIGTERM via taskkill...');
      execSync(`taskkill /pid ${pid.toString()} /T /F`, { timeout: 3000 });
    } else {
      // Unix: kill process group (negative PID kills the group)
      console.log('Sending SIGTERM to process group...');
      process.kill(-pid, 'SIGTERM');
      
      // Wait for graceful shutdown
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      // Force kill if still running
      try {
        if (backendProcess && backendProcess.exitCode === null) {
          console.log('Backend still running, sending SIGKILL...');
          process.kill(-pid, 'SIGKILL');
        }
      } catch (e) {
        // Process already dead
        console.log('Process already terminated');
      }
    }
    
    console.log('✓ Backend process tree killed');
    
    // FIX: Port check with retry and exponential backoff
    let portReleased = false;
    const maxAttempts = 6;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const delay = Math.min(500 * Math.pow(2, attempt), 2000); // 500ms, 1s, 2s, 2s...
      await new Promise(resolve => setTimeout(resolve, delay));
      
      portReleased = await isPortAvailable(BACKEND_PORT);
      if (portReleased) {
        console.log(`✓ Port ${BACKEND_PORT} successfully released after ${attempt + 1} attempts`);
        break;
      }
      console.log(`  Port check attempt ${attempt + 1}/${maxAttempts}...`);
    }
    
    if (!portReleased) {
      console.error(`✗ Port ${BACKEND_PORT} still in use after ${maxAttempts} attempts`);
    }
    
  } catch (error) {
    console.error('Error during backend shutdown:', error);
    
    // Fallback: force kill
    try {
      if (backendProcess) {
        backendProcess.kill('SIGKILL');
        console.log('✓ Force killed backend process');
      }
    } catch (e) {
      console.error('Could not force kill:', e);
    }
  } finally {
    backendProcess = null;
  }
}

/**
 * Synchronous version of stopBackend for signal handlers
 */
function stopBackendSync(): void {
  if (!backendProcess || !backendProcess.pid) {
    return;
  }
  
  const pid = backendProcess.pid;
  console.log('Stopping backend process (sync)...');
  
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', pid.toString(), '/T', '/F']);
    } else {
      process.kill(-pid, 'SIGTERM');
      // FIX: Wait for SIGTERM timeout before SIGKILL
      // Use synchronous blocking wait instead of fire-and-forget setTimeout
      const startTime = Date.now();
      while (Date.now() - startTime < 500) {
        // Busy wait for 500ms to give SIGTERM time to work
      }
      try {
        process.kill(-pid, 'SIGKILL');
      } catch (e) {
        // Process already dead - good!
      }
    }
    console.log('✓ Backend process killed');
  } catch (error) {
    console.error('Error killing backend:', error);
    try {
      backendProcess?.kill('SIGKILL');
    } catch (e) {
      // Ignore
    }
  }
  
  backendProcess = null;
}

/**
 * Create the main application window
 */
function createWindow(): void {
  // Platform-specific window configuration
  const windowOptions: Electron.BrowserWindowConstructorOptions = {
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    title: 'RAG Assistant for Zotero',
    backgroundColor: '#1a1a1a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  };
  
  // macOS-specific settings
  if (process.platform === 'darwin') {
    windowOptions.titleBarStyle = 'hiddenInset'; // macOS-only feature
    windowOptions.trafficLightPosition = { x: 16, y: 16 };
  }
  // Linux-specific settings
  else if (process.platform === 'linux') {
    // Use default title bar on Linux for better compatibility
    // Some Linux desktop environments don't handle custom title bars well
    windowOptions.frame = true;
  }
  // Windows-specific settings
  else if (process.platform === 'win32') {
    // Windows uses default frame
    windowOptions.frame = true;
  }
  
  mainWindow = new BrowserWindow(windowOptions);
  
  // Load the frontend
  if (IS_DEV) {
    // Development: load from Vite dev server
    mainWindow.loadURL(FRONTEND_DEV_URL);
    // Only open DevTools in development (and only if not explicitly disabled)
    if (process.env.DISABLE_DEVTOOLS !== 'true') {
      mainWindow.webContents.openDevTools();
    }
  } else {
    // Production: load from built files
    const appPath = app.getAppPath();
    const indexPath = path.join(appPath, 'frontend', 'dist', 'index.html');
    
    console.log('================================================================================');
    console.log('Frontend Path Resolution:');
    console.log(`  - App path (getAppPath): ${appPath}`);
    console.log(`  - Resolved index.html: ${indexPath}`);
    console.log(`  - Index exists: ${fs.existsSync(indexPath)}`);
    
    // Check alternate paths to help diagnose any mismatch
    const altPaths = [
      path.join(appPath, 'dist', 'frontend', 'dist', 'index.html'),
      path.join(appPath, 'index.html'),
      path.join(appPath, 'dist', 'index.html')
    ];
    console.log('  - Alternate path checks:');
    altPaths.forEach(p => {
      console.log(`      ${p}: ${fs.existsSync(p)}`);
    });
    
    // List app directory contents for diagnostics
    try {
      const appContents = fs.readdirSync(appPath);
      console.log(`  - App directory contents: ${appContents.join(', ')}`);
      
      if (fs.existsSync(path.join(appPath, 'frontend'))) {
        const frontendContents = fs.readdirSync(path.join(appPath, 'frontend'));
        console.log(`  - frontend/ contents: ${frontendContents.join(', ')}`);
        
        if (fs.existsSync(path.join(appPath, 'frontend', 'dist'))) {
          const distContents = fs.readdirSync(path.join(appPath, 'frontend', 'dist'));
          console.log(`  - frontend/dist/ contents: ${distContents.join(', ')}`);
        }
      }
    } catch (e) {
      console.error(`  - Error listing directories: ${e}`);
    }
    console.log('================================================================================');
    
    // Validate frontend files exist
    if (!fs.existsSync(indexPath)) {
      console.error(`✗ FATAL: Frontend index.html not found at: ${indexPath}`);
      
      dialog.showErrorBox(
        'Frontend Files Missing',
        `The frontend application files are missing.\n\nExpected location: ${indexPath}\n\nSee console logs for directory structure details.`
      );
      app.quit();
      return;
    }
    
    console.log('✓ Frontend validation passed, loading window...');
    mainWindow.loadFile(indexPath);
  }
  
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  
  // Close splash window when main window is ready
  mainWindow.webContents.once('did-finish-load', () => {
    console.log('✓ Main window loaded, closing splash screen');
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
  });
  
  // Handle renderer process crashes (critical for Linux stability)
  mainWindow.webContents.on('render-process-gone', (event, details) => {
    console.error('================================================================================');
    console.error('✗ FATAL: Renderer process crashed');
    console.error(`  Reason: ${details.reason}`);
    console.error(`  Exit code: ${details.exitCode}`);
    console.error('================================================================================');
    
    const crashReasons: { [key: string]: string } = {
      'clean-exit': 'Renderer exited normally',
      'abnormal-exit': 'Renderer crashed unexpectedly',
      'killed': 'Renderer was killed (possibly by OS)',
      'crashed': 'Renderer crashed (GPU/sandbox issue)',
      'oom': 'Renderer ran out of memory',
      'launch-failed': 'Renderer failed to launch',
      'integrity-failure': 'Renderer integrity check failed'
    };
    
    const reasonText = crashReasons[details.reason] || details.reason;
    
    // Show error dialog before quitting
    dialog.showErrorBox(
      'Application Crashed',
      `The application window crashed unexpectedly.\n\n` +
      `Reason: ${reasonText}\n` +
      `Exit code: ${details.exitCode}\n\n` +
      `If this persists on Linux, try launching with:\n` +
      `  /opt/RAGAssistant/rag-assistant --disable-gpu-sandbox\n\n` +
      `Or report this issue on GitHub.`
    );
    
    // Clean shutdown
    app.quit();
  });
  
  // Handle page load failures
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.error('================================================================================');
    console.error('✗ Page failed to load');
    console.error(`  Error code: ${errorCode}`);
    console.error(`  Description: ${errorDescription}`);
    console.error(`  URL: ${validatedURL}`);
    console.error('================================================================================');
    
    // Don't quit on load failures in production (might be transient)
    if (!IS_DEV && errorCode !== -3) { // -3 is ERR_ABORTED (user navigation)
      console.warn('Attempting to reload after load failure...');
      setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.reload();
        }
      }, 2000);
    }
  });
  
  // Handle renderer becoming unresponsive
  mainWindow.on('unresponsive', () => {
    console.warn('WARNING: Renderer process is unresponsive');
    
    if (!mainWindow) return; // Safety check
    
    dialog.showMessageBox(mainWindow, {
      type: 'warning',
      title: 'Application Not Responding',
      message: 'The application is not responding. Would you like to wait or close it?',
      buttons: ['Wait', 'Close'],
      defaultId: 0
    }).then(result => {
      if (result.response === 1) {
        app.quit();
      }
    });
  });
  
  // Handle renderer becoming responsive again
  mainWindow.on('responsive', () => {
    console.log('✓ Renderer process is responsive again');
  });
  
  // Handle navigation to external links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    require('electron').shell.openExternal(url);
    return { action: 'deny' };
  });
}

/**
 * Setup IPC handlers for communication with renderer process
 */
function setupIpcHandlers(): void {
  // Send backend configuration to renderer
  ipcMain.handle('get-backend-config', () => {
    return {
      backendUrl: BACKEND_URL,
      authToken: authToken
    };
  });
  
  // Check if backend is healthy
  ipcMain.handle('check-backend-health', async () => {
    try {
      // Use generous timeout for consistency with startup health checks
      const timeout = 3000;
      const response = await axios.get(`${BACKEND_URL}/`, { timeout });
      return { healthy: true, status: response.status };
    } catch (error) {
      return { healthy: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
  
  // Get app version
  ipcMain.handle('get-app-version', () => {
    return app.getVersion();
  });
  
  // Get platform
  ipcMain.handle('get-platform', () => {
    return process.platform; // Returns 'darwin', 'win32', 'linux', etc.
  });
  
  // Open external links
  ipcMain.handle('open-external', (event, url: string) => {
    require('electron').shell.openExternal(url);
  });
}

/**
 * Setup auto-updater for automatic updates from GitHub Releases
 */
function setupAutoUpdater(): void {
  // Configure auto-updater
  autoUpdater.autoDownload = false; // Don't auto-download, let user decide
  autoUpdater.autoInstallOnAppQuit = true; // Install on quit after download
  
  // Skip actual update checks in development, but still register the IPC
  // handlers below so the renderer's updater hook doesn't hit "No handler
  // registered for 'get-update-status'". Each handler guards IS_DEV itself.
  if (IS_DEV) {
    console.log('Auto-updater update checks disabled in development mode');
  } else {
    // Check for updates on startup (after a delay to let app fully load)
    setTimeout(() => {
      console.log('Checking for updates on startup...');
      autoUpdater.checkForUpdates().catch(err => {
        console.error('Failed to check for updates on startup:', err);
      });
    }, 10000); // Wait 10 seconds after startup

    // Check for updates periodically (every 4 hours)
    setInterval(() => {
      console.log('Periodic update check...');
      autoUpdater.checkForUpdates().catch(err => {
        console.error('Failed to check for updates periodically:', err);
      });
    }, 4 * 60 * 60 * 1000);
  }
  
  // Update event handlers
  autoUpdater.on('checking-for-update', () => {
    console.log('Checking for updates...');
    updateDownloaded = false;
    updateInfo = null;
    
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-checking');
    }
  });
  
  autoUpdater.on('update-available', (info) => {
    console.log('Update available:', info.version);
    updateInfo = {
      version: info.version,
      releaseNotes: typeof info.releaseNotes === 'string' ? info.releaseNotes : undefined
    };
    
    // Notify renderer
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-available', updateInfo);
    }
  });
  
  autoUpdater.on('update-not-available', (info) => {
    console.log('No updates available. Current version:', info.version);
    
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-not-available', {
        version: info.version
      });
    }
  });
  
  autoUpdater.on('error', (error) => {
    console.error('Auto-updater error:', error);
    
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-error', {
        message: error instanceof Error ? error.message : String(error)
      });
    }
  });
  
  autoUpdater.on('download-progress', (progress) => {
    const percent = progress.percent.toFixed(2);
    console.log(`Download progress: ${percent}% (${progress.transferred}/${progress.total} bytes)`);
    
    // Notify renderer of download progress
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-download-progress', {
        percent: progress.percent,
        transferred: progress.transferred,
        total: progress.total,
        bytesPerSecond: progress.bytesPerSecond
      });
    }
  });
  
  autoUpdater.on('update-downloaded', (info) => {
    console.log('Update downloaded and ready to install:', info.version);
    updateDownloaded = true;
    updateInfo = {
      version: info.version,
      releaseNotes: typeof info.releaseNotes === 'string' ? info.releaseNotes : undefined
    };
    
    // Notify renderer that update is ready to install
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-downloaded', updateInfo);
    }
  });
  
  // IPC handlers for update actions
  ipcMain.handle('check-for-updates', async () => {
    try {
      if (IS_DEV) {
        return {
          success: false,
          error: 'Updates are not available in development mode'
        };
      }
      
      const result = await autoUpdater.checkForUpdates();
      return {
        success: true,
        updateInfo: result?.updateInfo ? {
          version: result.updateInfo.version,
          releaseDate: result.updateInfo.releaseDate
        } : null
      };
    } catch (error) {
      console.error('Check for updates error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  });
  
  ipcMain.handle('download-update', async () => {
    try {
      if (IS_DEV) {
        return {
          success: false,
          error: 'Updates are not available in development mode'
        };
      }
      
      if (!updateInfo) {
        return {
          success: false,
          error: 'No update available to download'
        };
      }
      
      await autoUpdater.downloadUpdate();
      return { success: true };
    } catch (error) {
      console.error('Download update error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  });
  
  ipcMain.handle('install-update', () => {
    if (IS_DEV) {
      return {
        success: false,
        error: 'Updates are not available in development mode'
      };
    }
    
    if (!updateDownloaded) {
      return {
        success: false,
        error: 'No update has been downloaded yet'
      };
    }
    
    // This will quit the app and install the update
    setImmediate(() => {
      autoUpdater.quitAndInstall(false, true);
    });
    
    return { success: true };
  });
  
  ipcMain.handle('get-update-status', () => {
    return {
      updateAvailable: updateInfo !== null,
      updateDownloaded: updateDownloaded,
      updateInfo: updateInfo,
      currentVersion: app.getVersion()
    };
  });
}

/**
 * Application ready event
 */
app.on('ready', async () => {
  console.log('================================================================================');
  console.log('App is ready, starting initialization...');
  console.log('================================================================================');
  console.log('Environment Information:');
  console.log(`  - IS_DEV: ${IS_DEV}`);
  console.log(`  - app.isPackaged: ${app.isPackaged}`);
  console.log(`  - Platform: ${process.platform}`);
  console.log(`  - Architecture: ${process.arch}`);
  console.log(`  - Electron version: ${process.versions.electron}`);
  console.log(`  - Node version: ${process.versions.node}`);
  console.log(`  - App version: ${app.getVersion()}`);
  console.log(`  - App path: ${app.getAppPath()}`);
  console.log(`  - Resources path: ${process.resourcesPath}`);
  console.log(`  - User data path: ${app.getPath('userData')}`);
  console.log('================================================================================');
  
  // Configure Content Security Policy
  session.defaultSession.webRequest.onHeadersReceived(
    (details: OnHeadersReceivedListenerDetails, callback: (response: HeadersReceivedResponse) => void) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [
            IS_DEV
              ? // Development: Allow Vite dev server and HMR
                "default-src 'self' http://localhost:5173 ws://localhost:5173; " +
                "script-src 'self' http://localhost:5173 'unsafe-inline'; " +
                "style-src 'self' http://localhost:5173 'unsafe-inline'; " +
                `connect-src 'self' http://localhost:5173 ws://localhost:5173 ${BACKEND_URL} http://localhost:${BACKEND_PORT}; ` +
                "img-src 'self' data: http://localhost:5173;"
              : // Production: Strict CSP
                "default-src 'self'; " +
                "script-src 'self'; " +
                "style-src 'self' 'unsafe-inline'; " +
                `connect-src 'self' ${BACKEND_URL} http://localhost:${BACKEND_PORT}; ` +
                "img-src 'self' data:;"
          ]
        }
      });
    }
  );
  
  // Generate auth token
  authToken = generateAuthToken();
  
  // Setup IPC handlers
  setupIpcHandlers();
  
  // Setup auto-updater
  setupAutoUpdater();
  
  // In development, backend is started separately by npm run dev:backend
  // Only start backend in production mode
  if (!IS_DEV) {
    const backendStarted = await startBackend();
    
    if (!backendStarted) {
      const response = await dialog.showMessageBox({
        type: 'error',
        title: 'Backend Failed to Start',
        message: 'The backend service failed to start. The application may not work correctly.',
        buttons: ['Exit', 'Continue Anyway'],
        defaultId: 0
      });
      
      if (response.response === 0) {
        app.quit();
        return;
      }
    }
  } else {
    console.log('Development mode: Skipping backend startup (handled by npm run dev:backend)');
    console.log('Waiting for backend to be available...');
    
    // Wait for backend to be ready (started by separate process)
    const backendReady = await waitForBackend(30, 1000);
    
    if (!backendReady) {
      console.warn('WARNING: Backend not detected - make sure "npm run dev:backend" is running');
      const response = await dialog.showMessageBox({
        type: 'warning',
        title: 'Backend Not Detected',
        message: `Could not connect to backend at ${BACKEND_URL}.\n\nMake sure you're running "npm run dev" which starts the backend automatically.`,
        buttons: ['Exit', 'Continue Anyway'],
        defaultId: 1
      });
      
      if (response.response === 0) {
        app.quit();
        return;
      }
    } else {
      console.log('✓ Connected to development backend');
    }
  }
  
  // Create window
  createWindow();
  
  // Initialization complete - allow normal window-close behavior
  isInitializing = false;
});

/**
 * All windows closed event
 */
app.on('window-all-closed', () => {
  // During initialization, don't quit when loading window closes
  if (isInitializing) {
    console.log('Loading window closed during initialization - not quitting');
    return;
  }
  
  // On macOS, keep app running until explicitly quit
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

/**
 * Activate event (macOS)
 */
app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

/**
 * Before quit event - cleanup
 */
app.on('before-quit', async (event) => {
  // FIX: Race condition - remove app.exit(0) to let natural quit flow hit will-quit
  if (backendProcess && !isShuttingDown) {
    event.preventDefault();
    isShuttingDown = true;
    console.log('App is quitting, cleaning up...');
    await stopBackend();
    console.log('✓ Cleanup complete');
    // Let app quit naturally instead of forcing exit
    app.quit();
  }
});

/**
 * Handle window close - ensure cleanup
 */
app.on('will-quit', (event) => {
  if (backendProcess) {
    console.log('Emergency cleanup on will-quit...');
    stopBackendSync();
  }
});

/**
 * Handle uncaught exceptions
 */
process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error);
  stopBackendSync();
  dialog.showErrorBox('Application Error', `An unexpected error occurred: ${error.message}`);
});

/**
 * Handle unhandled promise rejections
 */
process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled promise rejection:', reason);
});

/**
 * Handle process termination signals
 */
process.on('SIGTERM', () => {
  console.log('SIGTERM received, cleaning up...');
  stopBackendSync();
  app.quit();
});

process.on('SIGINT', () => {
  console.log('SIGINT received, cleaning up...');
  stopBackendSync();
  app.quit();
});
