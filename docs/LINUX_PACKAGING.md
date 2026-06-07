# Linux Packaging Guide - Debian/Ubuntu

## Overview

The app provides native `.deb` packages for Debian-based distributions (Ubuntu, Debian, Linux Mint, Pop!_OS, etc.) with proper Electron sandbox configuration. No `--no-sandbox` flags required!

**Current Approach (v0.1.10+)**: Linux uses system Python + venv for a smaller package size (~250MB vs 2.5GB with PyInstaller bundle). The app automatically sets up and repairs the Python environment on first run.

## Package Types

### 1. Debian Package (`.deb`) - Recommended for Most Users

**Benefits:**
-  Native system integration (package manager, menu entries, file associations)
-  Automatic updates via `apt upgrade` (when using APT repo)
-  Proper sandbox permissions set automatically
-  Clean uninstall with `apt remove`
-  Respects system conventions (`/opt` install location)

**Installation:**
```bash
# Download the .deb
wget https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/download/v0.1.7/RAG-Assistant-0.1.7-linux-amd64.deb

# Install
sudo apt install ./RAG-Assistant-0.1.7-linux-amd64.deb

# Or use dpkg
sudo dpkg -i RAG-Assistant-0.1.7-linux-amd64.deb
sudo apt-get install -f  # Install dependencies if needed
```

**Launch:**
```bash
# From application menu (shows as "RAG Assistant for Zotero")
# OR from terminal:
rag-assistant
```

### 2. AppImage - Portable Alternative

**Benefits:**
-  No installation required
-  Run from anywhere (USB drive, Downloads folder, etc.)
-  No root/sudo needed

**Usage:**
```bash
# Download
wget https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/download/v0.1.7/RAG-Assistant-0.1.7-linux-x64.AppImage

# Make executable
chmod +x RAG-Assistant-0.1.7-linux-x64.AppImage

# Run (sandbox should work automatically)
./RAG-Assistant-0.1.7-linux-x64.AppImage
```

**Note:** On modern Debian/Ubuntu, the sandbox should work without `--no-sandbox`. If you encounter issues, see troubleshooting below.

## System Requirements

### Kernel Configuration (Usually Default)

The Electron/Chromium sandbox requires **unprivileged user namespaces** to be enabled:

```bash
# Check if enabled (should return 1 or not exist)
sysctl kernel.unprivileged_userns_clone

# If it returns 0, enable it:
sudo sysctl kernel.unprivileged_userns_clone=1

# Make permanent:
echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/00-local-userns.conf
sudo sysctl --system
```

**This is the default on:**
- Ubuntu 18.04+
- Debian 10 (Buster)+
- Linux Mint 19+
- Pop!_OS 20.04+
- Most modern distributions

### Dependencies

The `.deb` package automatically installs these dependencies:
- `libnotify4` - Desktop notifications
- `libnss3` - Network security services
- `libxss1` - Screen saver extension
- `libasound2` - Audio support
- `libxtst6` - X11 testing extensions
- `libappindicator1` - System tray support
- `gconf2`, `gconf-service` - Configuration system

## How the Sandbox Works

### What Happens During Installation

1. **Package extracts to `/opt/RAGAssistant/`**
   - Main binary: `/opt/RAGAssistant/rag-assistant`
   - Sandbox helper: `/opt/RAGAssistant/chrome-sandbox`
   - Resources and Python bundle included

2. **Post-install script runs automatically** (`linux-postinstall.sh`)
   - Sets `chrome-sandbox` ownership to `root:root`
   - Sets permissions to `4755` (setuid root)
   - This allows unprivileged users to use the sandbox

3. **Desktop entry registered**
   - Shows in application menu under "Office"
   - Uses proper app name and icon
   - No special flags needed

### Verifying Sandbox Configuration

```bash
# Check chrome-sandbox permissions
ls -la "/opt/RAGAssistant/chrome-sandbox"
# Should show: -rwsr-xr-x 1 root root

# Test sandbox initialization
rag-assistant --version
# Should NOT show "Running without sandbox" warnings
```

## Building `.deb` Packages

### Prerequisites

```bash
# Install build dependencies
npm install

# Create Python bundle (required!)
./scripts/bundle-python-pyinstaller.sh
```

### Build Command

```bash
# Build for Linux (creates both .deb and AppImage)
npm run build
npm run package:linux

# Output files in release/:
# - RAG-Assistant-0.1.7-linux-amd64.deb
# - RAG-Assistant-0.1.7-linux-arm64.deb  
# - RAG-Assistant-0.1.7-linux-x64.AppImage
# - latest-linux.yml (for auto-updates)
```

### Architecture Support

- **amd64 (x86_64):** Intel/AMD 64-bit processors (most desktops/laptops)
- **arm64 (aarch64):** ARM 64-bit (Raspberry Pi 4+, ARM servers)

## Testing the Package

### Fresh Install Test

```bash
# Install package
sudo apt install ./RAG-Assistant-0.1.7-linux-amd64.deb

# Verify files installed
dpkg -L rag-assistant

# Check sandbox helper permissions
ls -la "/opt/Zotero RAG Assistant/chrome-sandbox"

# Launch from menu or terminal
rag-assistant

# Check for sandbox warnings in output
# Should NOT see: "Running without the SUID sandbox"
```

### Upgrade Test

```bash
# Install newer version over existing
sudo apt install ./RAG-Assistant-0.1.8-linux-amd64.deb

# Verify upgrade worked
rag-assistant --version
```

### Uninstall Test

```bash
# Remove package
sudo apt remove rag-assistant

# Verify files removed
ls /opt | grep -i zotero
# Should be empty

# Check menu entry removed
# "RAG Assistant for Zotero" should not appear in app menu
```

## Troubleshooting

### "Running without the SUID sandbox" Warning

**Cause:** `chrome-sandbox` doesn't have correct permissions

**Fix:**
```bash
# Manually fix permissions
sudo chown root:root "/opt/RAGAssistant/chrome-sandbox"
sudo chmod 4755 "/opt/RAGAssistant/chrome-sandbox"
```

### "Operation not permitted" or "namespace" Errors

**Cause:** User namespaces disabled in kernel

**Fix:**
```bash
# Enable unprivileged user namespaces
sudo sysctl kernel.unprivileged_userns_clone=1

# Make permanent
echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/00-local-userns.conf
```

### App Won't Start After Install

**Check:**
1. Dependencies installed: `apt-cache policy libnotify4 libnss3 libxss1`
2. Python bundle present: `ls "/opt/RAGAssistant/resources/python/"`
3. Logs: Run `rag-assistant` from terminal to see error output

### AppImage Sandbox Issues

**Workaround (not ideal but works):**
```bash
# Only if sandbox truly doesn't work
./RAG-Assistant-0.1.7-linux-x64.AppImage --no-sandbox
```

**Better solution:** Use the `.deb` package instead for proper sandbox support.

## APT Repository (Future)

For seamless updates like Chrome/VS Code, we plan to provide an APT repository:

```bash
# Add repository (future)
curl -fsSL https://apt.zotero-rag.example.com/KEY.gpg | sudo gpg --dearmor -o /usr/share/keyrings/zotero-rag.gpg
echo "deb [signed-by=/usr/share/keyrings/zotero-rag.gpg] https://apt.zotero-rag.example.com stable main" | sudo tee /etc/apt/sources.list.d/zotero-rag.list

# Install and get automatic updates
sudo apt update
sudo apt install rag-assistant

# Future updates via:
sudo apt upgrade
```

## Best Practices

### For Users
1. **Prefer `.deb` packages** over AppImages for installed apps
2. **Keep system updated** to ensure kernel namespace support
3. **Don't modify sandbox permissions** unless instructed
4. **Report issues** with full terminal output

### For Developers
1. **Always test on clean Ubuntu/Debian VM** before releasing
2. **Verify post-install script runs** in package manager logs
3. **Check sandbox helper permissions** after install
4. **Document any special requirements** in release notes

### For Distro Packagers
1. Post-install script handles sandbox setup automatically
2. No manual intervention should be needed
3. Dependencies list covers typical Debian/Ubuntu systems
4. Desktop file follows freedesktop.org standards

## References

- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security)
- [Chromium Sandbox](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/sandboxing.md)
- [Debian Packaging Guide](https://www.debian.org/doc/manuals/maint-guide/)
- [electron-builder Linux Config](https://www.electron.build/configuration/linux)
