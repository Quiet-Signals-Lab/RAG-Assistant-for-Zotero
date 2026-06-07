# Auto-Update System

This document describes the automatic update system implemented in RAG Assistant for Zotero.

## Overview

The application uses Electron's `electron-updater` module to provide seamless automatic updates from GitHub Releases. Users can check for updates, download them, and install them directly from the Settings page.

## Multi-Architecture Support (macOS)

For macOS, the app supports both Intel (x64) and Apple Silicon (arm64) architectures:
- Each architecture has its own PyInstaller backend bundle
- GitHub Actions builds both architectures separately on `macos-13` (Intel) and `macos-14` (ARM)
- The workflow merges update manifests to ensure electron-updater can find the correct architecture
- Users automatically receive updates matching their system architecture

### How It Works

1. **Separate Builds**: Each architecture is built on its native runner to ensure correct binary architecture
2. **Manifest Merging**: After builds complete, `scripts/merge-mac-yml.js` combines both `latest-mac.yml` files
3. **Smart Downloads**: electron-updater reads the merged manifest and downloads the appropriate architecture based on `process.arch`

This ensures that:
- Intel Mac users get x64 binaries (no "error -86" spawn failures)
- Apple Silicon users get native arm64 binaries (optimal performance)
- Auto-updates work correctly for both architectures

## Architecture

### Components

1. **Main Process (electron/main.ts)**
   - Configures `electron-updater` with GitHub as the update provider
   - Handles update lifecycle events (checking, available, downloading, downloaded)
   - Provides IPC handlers for renderer to trigger update actions
   - Automatically checks for updates on startup and periodically (every 4 hours)

2. **Preload Script (electron/preload.ts)**
   - Exposes secure update APIs to the renderer process via `contextBridge`
   - Provides event listeners for update status changes
   - Provides action methods (check, download, install)

3. **React Hook (frontend/src/hooks/useAppUpdater.ts)**
   - Encapsulates update state management
   - Provides a clean React interface for update functionality
   - Tracks update status, progress, and errors

4. **Settings UI (frontend/src/pages/Settings.tsx)**
   - Displays current version and update status
   - Shows download progress with visual progress bar
   - Provides buttons for checking, downloading, and installing updates
   - Only visible when running in Electron environment

## Update Flow

### 1. Checking for Updates

**Automatic:**
- On app startup (after 10 second delay)
- Every 4 hours while app is running

**Manual:**
- User clicks "Check for Updates" button in Settings

### 2. Update Available

When an update is found:
- User is notified in Settings page
- Update version is displayed
- **Manual download required**: User must click "Download from GitHub Releases" button to go to the releases page

### 3. Manual Update Installation

**Automatic downloads are disabled for all platforms** to avoid potential installation errors. When an update is available:
- Click "Download from GitHub Releases" button in Settings
- Download the appropriate installer for your platform:
  - **macOS**: `.dmg` or `.zip` file
  - **Windows**: `.exe` installer or `.zip` file
  - **Linux**: `.AppImage` or `.deb` package
- Run the installer to update the application
- Restart the app to use the new version

## Configuration

### electron-builder (package.json)

```json
{
  "build": {
    "publish": [
      {
        "provider": "github",
        "owner": "Quiet-Signals-Lab",
        "repo": "RAG-Assistant-for-Zotero",
        "releaseType": "release"
      }
    ]
  }
}
```

### Main Process Settings

```typescript
autoUpdater.autoDownload = false;        // Auto-download is disabled for all platforms
autoUpdater.autoInstallOnAppQuit = true; // Not used since auto-download is disabled
```

**Note:** Automatic downloads are disabled to prevent installation errors. Users must manually download updates from GitHub Releases when notified.

## Publishing Updates

### Prerequisites

1. **GitHub Personal Access Token**
   - Required for publishing to GitHub Releases
   - Set as environment variable: `GH_TOKEN=your_token_here`
   - Token needs `repo` scope for private repos, or `public_repo` for public repos

2. **Version Bump**
   - Update version in `package.json`
   - Follow semantic versioning (MAJOR.MINOR.PATCH)

### Publishing Process

#### Option 1: Using npm scripts

```bash
# Publish for current platform
npm run publish

# Publish for specific platforms
npm run publish:mac
npm run publish:win
npm run publish:linux
```

#### Option 2: Manual electron-builder

```bash
# Build and publish for all platforms
npm run build
GH_TOKEN=your_token electron-builder -mwl --publish always

# Or for specific platform
GH_TOKEN=your_token electron-builder --mac --publish always
```

### What Gets Published

- Application installers (.dmg, .exe, .AppImage, etc.)
- Update metadata files (latest.yml, latest-mac.yml, etc.)
- Checksums for verification
- Release notes (from GitHub release or CHANGELOG.md)

## Release Best Practices

1. **Version Control**
   - Tag releases in git: `git tag v1.0.0 && git push origin v1.0.0`
   - Keep version in sync between package.json and git tags

2. **Release Notes**
   - Write clear, user-friendly release notes
   - List new features, improvements, and bug fixes
   - Mention any breaking changes or migration steps

3. **Testing**
   - Test the update process before publishing
   - Verify installers work on target platforms
   - Test update from previous version to new version

4. **Incremental Updates**
   - electron-updater supports differential updates on Windows
   - Users only download changed files, not entire app
   - Reduces download size and time

## Security

1. **Code Signing**
   - All releases should be code signed
   - Prevents "untrusted developer" warnings
   - Required for auto-updates on macOS

2. **HTTPS**
   - GitHub Releases uses HTTPS by default
   - Updates are verified with checksums

3. **Sandboxed API**
   - Update APIs are exposed via secure `contextBridge`
   - No direct access to Node.js or Electron APIs from renderer

## User Experience

### Update Notifications

- **Non-intrusive**: Updates don't interrupt the user
- **Manual Control**: Users must manually download and install updates from GitHub Releases
- **Clear Instructions**: Warning message with direct link to releases page
- **Platform Agnostic**: Same experience across macOS, Windows, and Linux

### Update States

1. **Idle** - No update check performed yet
2. **Checking** - Checking for updates with spinner
3. **Not Available** - Running latest version (green checkmark)
4. **Available** - Update available (yellow warning with link to GitHub Releases)
5. **Error** - Something went wrong (red, with error message)

**Note:** Download and install states are removed since automatic updates are disabled.

## Troubleshooting

### Updates Not Working

1. **Check GitHub Token**
   - Ensure `GH_TOKEN` is set when publishing
   - Verify token has correct permissions

2. **Check Release Visibility**
   - Releases must be marked as "releases" (not drafts or pre-releases)
   - For private repos, ensure token has access

3. **Check Build Artifacts**
   - Verify latest.yml (or platform-specific) is published
   - Check that artifact names match configuration

4. **Development Mode**
   - Updates are disabled in development mode
   - Test with packaged application

### Common Issues

**"No updates available" when update exists**
- Check that version in release is higher than current
- Verify update metadata files are published
- Check console for error messages

**Manual download link not working**
- Verify you have internet connection
- Try opening https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/latest directly
- Check if GitHub is accessible from your network

**Update check fails**
- Check network connection
- Verify GitHub Releases API is accessible
- Check console logs for specific error messages

## API Reference

### Electron API (window.electron)

```typescript
interface ElectronAPI {
  // Check for updates manually
  checkForUpdates(): Promise<{ 
    success: boolean; 
    updateInfo?: any; 
    error?: string 
  }>;
  
  // Download available update
  downloadUpdate(): Promise<{ 
    success: boolean; 
    error?: string 
  }>;
  
  // Install downloaded update and restart
  installUpdate(): Promise<{ 
    success: boolean; 
    error?: string 
  }>;
  
  // Get current update status
  getUpdateStatus(): Promise<{
    updateAvailable: boolean;
    updateDownloaded: boolean;
    updateInfo: UpdateInfo | null;
    currentVersion: string;
  }>;
  
  // Event listeners
  onUpdateChecking(callback: () => void): void;
  onUpdateAvailable(callback: (info: UpdateInfo) => void): void;
  onUpdateNotAvailable(callback: (info: { version: string }) => void): void;
  onUpdateDownloadProgress(callback: (progress: DownloadProgress) => void): void;
  onUpdateDownloaded(callback: (info: UpdateInfo) => void): void;
  onUpdateError(callback: (error: { message: string }) => void): void;
}
```

### React Hook (useAppUpdater)

```typescript
const {
  status,              // Current update status
  updateInfo,          // Info about available/downloaded update
  downloadProgress,    // Download progress (percent, transferred, total)
  error,              // Error message if any
  currentVersion,      // Current app version
  checkForUpdates,     // Function to check for updates
  downloadUpdate,      // Function to download update
  installUpdate,       // Function to install and restart
} = useAppUpdater();
```

## Publishing Checklist

Use this checklist when publishing a new release:

### Pre-Release
- [ ] Update version in `package.json`
- [ ] Update `CHANGELOG.md`
- [ ] Test on all target platforms
- [ ] Commit: `git commit -am "Bump version to x.x.x"`
- [ ] Tag: `git tag vx.x.x`
- [ ] Push: `git push origin master && git push origin vx.x.x`
- [ ] Set `GH_TOKEN` environment variable

### Build & Publish
- [ ] Run: `npm run publish:mac` (or :win, :linux)
- [ ] Wait for build completion
- [ ] Check console for errors

### Verify Release
- [ ] GitHub release created with correct version
- [ ] All installers uploaded (.dmg/.exe/.deb/AppImage)
- [ ] Update metadata files present (latest*.yml)
- [ ] Release notes populated

### Test
- [ ] Download and install from GitHub release
- [ ] Verify version in Settings
- [ ] Test update from previous version (if available)
- [ ] Verify settings/data preserved after update

## Related Documentation

- [Electron Updater Documentation](https://www.electron.build/auto-update)
- [electron-builder Publishing](https://www.electron.build/configuration/publish)
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github)
