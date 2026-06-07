# Electron Desktop App

This directory contains the Electron main and preload processes that wrap the Zotero LLM Plugin as a native desktop application.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Electron Main Process                 │
│  - Window management                                     │
│  - Python backend process spawning                       │
│  - IPC communication                                     │
│  - Auto-updates                                          │
└───────────────┬─────────────────────────────────────────┘
                │
                ├─────────────────────────────────────────┐
                │                                         │
       ┌────────▼──────────┐                   ┌─────────▼────────┐
       │  Preload Script   │                   │  Python Backend  │
       │  - Context Bridge │                   │  (FastAPI)       │
       │  - Safe IPC API   │                   │  - Port 8000     │
       └────────┬──────────┘                   └─────────┬────────┘
                │                                         │
       ┌────────▼─────────────────────────────────────────▼────────┐
       │              Renderer Process (Frontend)                   │
       │  - React + TypeScript                                      │
       │  - Communicates with backend via HTTP                      │
       │  - Receives Electron APIs via window.electron              │
       └────────────────────────────────────────────────────────────┘
```

## Files

### `main.ts`
The Electron main process that:
- Creates and manages the application window
- Spawns the Python backend on startup (uvicorn in dev, packaged binary in production)
- Waits for backend to be ready before showing the window
- Handles app lifecycle events (quit, activate, etc.)
- Implements auto-update functionality using electron-updater
- Cleans up processes on shutdown

### `preload.ts`
The preload script that:
- Bridges the main process and renderer using contextBridge
- Exposes a safe API to the frontend (`window.electron`)
- Handles IPC communication between processes
- Provides auto-update event listeners

### `tsconfig.json`
TypeScript configuration for building the Electron code.

## Development Mode

In development:
- Electron loads the React dev server from `http://localhost:5173`
- Python backend runs via `uvicorn backend.main:app --reload`
- Hot reload works for both frontend and backend
- DevTools are automatically opened

```bash
# Run all services concurrently
npm run dev

# Or run individually:
npm run dev:frontend   # Vite dev server
npm run dev:backend    # Python backend
npm run dev:electron   # Electron window
```

## Production Build

In production:
- Electron loads the built frontend from `dist/frontend/dist/index.html`
- Python backend is packaged as a binary (using PyInstaller) in `extraResources/backend/`
- Backend binary is spawned on app startup
- No external dependencies needed

## Backend Integration

The main process spawns the Python backend as a child process:

**Development:**
```bash
python3 -m uvicorn backend.main:app --port 8000
```

**Production:**
```bash
./resources/backend/backend --port 8000
```

The main process:
1. Spawns the backend process
2. Polls `http://127.0.0.1:8000/` until it responds (max 30 seconds)
3. Passes the backend URL to the renderer via IPC
4. Monitors the process and shows errors if it crashes
5. Kills the process gracefully on app quit

## Auto-Updates

The app uses `electron-updater` to automatically check for and install updates from GitHub Releases.

**Update Flow:**
1. App checks for updates on startup (after 10 seconds) and every 4 hours
2. When update is available, renderer shows "Update Available" banner
3. User can download the update
4. When download completes, renderer shows "Restart to Update" banner
5. User clicks restart, app quits and installs update

**Events exposed to renderer:**
- `onUpdateAvailable(callback)` - New version available
- `onUpdateDownloadProgress(callback)` - Download progress
- `onUpdateDownloaded(callback)` - Download complete, ready to install

**Actions:**
- `downloadUpdate()` - Start downloading update
- `installUpdate()` - Quit and install (restarts app)

## IPC API

The preload script exposes these methods to the renderer via `window.electron`:

```typescript
interface ElectronAPI {
  // Backend
  getBackendConfig(): Promise<{ backendUrl: string; authToken: string | null }>
  checkBackendHealth(): Promise<{ healthy: boolean; status?: number; error?: string }>
  
  // App
  getAppVersion(): Promise<string>
  openExternal(url: string): Promise<void>
  
  // Updates
  onUpdateAvailable(callback: (info) => void): void
  onUpdateDownloadProgress(callback: (progress) => void): void
  onUpdateDownloaded(callback: (info) => void): void
  downloadUpdate(): Promise<{ success: boolean; error?: string }>
  installUpdate(): void
}
```

## Building Installers

```bash
# Build for all platforms (requires appropriate OS)
npm run package:all

# Build for specific platform
npm run package:mac     # macOS: DMG + ZIP
npm run package:win     # Windows: NSIS installer + ZIP
npm run package:linux   # Linux: AppImage + DEB + tar.gz

# Output in release/ directory
```

## Platform-Specific Notes

### macOS
- Universal builds (x64 + arm64)
- DMG installer with drag-to-Applications
- Code signing requires Apple Developer account
- Notarization required for distribution

### Windows
- NSIS installer (user-level, allows install directory choice)
- Supports both x64 and ia32
- Code signing recommended but not required
- Auto-updater works with or without code signing

### Linux
- AppImage (universal, no installation needed)
- DEB package for Debian/Ubuntu
- Supports x64 and arm64
- No code signing needed

## Packaging the Python Backend

For production builds, the Python backend needs to be packaged as a binary. This is typically done with PyInstaller:

```bash
# Install PyInstaller
pip install pyinstaller

# Create backend binary (per platform)
pyinstaller --onefile \
  --name backend \
  --add-data "backend:backend" \
  --hidden-import backend.main \
  backend/main.py

# Output in dist/backend/backend
```

The electron-builder config includes the backend directory in `extraResources`, so the binary will be bundled with the app.

**Note:** This step should be automated in your CI/CD pipeline for each platform.

## GitHub Releases & Auto-Updates

To enable auto-updates:

1. **Tag your release** with semantic versioning:
   ```bash
   git tag v0.1.0-beta.1
   git push origin v0.1.0-beta.1
   ```

2. **Build installers** for all platforms

3. **Create GitHub Release**:
   - Go to: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/new
   - Select your tag
   - Upload all build artifacts from `release/` directory
   - Include `latest-mac.yml`, `latest-linux.yml`, `latest.yml` (Windows)

4. **Users get auto-updates**:
   - App checks GitHub Releases API
   - Downloads appropriate installer for their platform
   - Shows notification when ready
   - Installs on restart

**Required files per platform:**
- **macOS**: `*.dmg`, `*.zip`, `latest-mac.yml`
- **Windows**: `*.exe`, `*.zip`, `latest.yml`
- **Linux**: `*.AppImage`, `*.deb`, `latest-linux.yml`

The `.yml` files contain version info and download URLs, generated automatically by electron-builder.

## Troubleshooting

### Backend won't start
- Check Python is installed and in PATH
- Verify requirements.txt dependencies are available
- Check backend logs in console
- Try running backend manually: `python3 -m uvicorn backend.main:app`

### Window loads blank page
- Verify frontend was built: `ls frontend/dist/index.html`
- Check console for errors
- Try running frontend dev server separately

### Auto-update not working
- Verify GitHub release is published (not draft)
- Check release artifacts are uploaded
- Ensure `.yml` files are present
- Check console for update errors

### Build fails
- Install platform-specific dependencies
- Verify all paths in electron-builder config
- Check that Python backend can be packaged
- Ensure code signing certs are valid (if signing)
