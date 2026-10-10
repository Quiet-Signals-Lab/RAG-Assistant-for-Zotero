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
- Ubuntu 24.04+ (Python 3.12)
- Debian 12 (Bookworm)+ (Python 3.11)
- Linux Mint 22+, Pop!_OS 24.04+ and other Ubuntu 24.04 derivatives

Ubuntu 22.04 is not supported: its `python3` is 3.10, and the pinned numpy,
scipy and networkx need 3.11. The package declares `python3 (>= 3.11)`, so apt
refuses the install there with a clear message instead of failing on first launch.

> **Maintainer gotcha:** a Debian control file's `Description` continuation lines
> **must** each start with a single space, or `dpkg` fails with a "error parsing
> file ... control" on install. electron-builder's single-line `--description`
> produces valid output; if you ever hit this error, the cause is almost always
> stale build artifacts — `rm -rf release/ dist/ node_modules/.cache/electron-builder`
> and rebuild. Inspect a built package with `dpkg-deb -R <pkg>.deb /tmp/x`.

### Dependencies

Declared in `build.deb.depends` in `package.json`; `apt install ./<pkg>.deb` installs them:
- electron-builder's default Electron runtime set: `libgtk-3-0`, `libnotify4`,
  `libnss3`, `libxss1`, `libxtst6`, `xdg-utils` (opening PDFs and links),
  `libatspi2.0-0`, `libuuid1`, `libsecret-1-0`
- `libasound2t64 | libasound2` (renamed in Ubuntu 24.04; the real package is listed first so apt never picks an OSS compatibility shim for the virtual name) and `libgbm1`
- `python3 (>= 3.11)` and `python3-venv`: the backend runs in a venv created from
  the system Python on first launch

`dpkg -i` does not resolve dependencies; use `apt install ./<pkg>.deb`.

## How the Sandbox Works

### What Happens During Installation

1. **Files install to `/opt/RAG Assistant/`** (electron-builder uses the product
   name, space included): the `rag-assistant` binary, the `chrome-sandbox` helper,
   and `resources/` including `start-backend.sh` and `apparmor-profile`.

2. **electron-builder's default post-install script runs.** There is deliberately
   no custom script: the old one hard-coded `/opt/RAGAssistant`, silently did
   nothing after the 0.4.3 rename, and left the sandbox unconfigured. The default
   script is maintained upstream and takes its paths from the build, so it:
   - links `/usr/bin/rag-assistant` through `update-alternatives`;
   - sets `chrome-sandbox` to `4755` (setuid root) only where user namespaces are
     unavailable, and `0755` otherwise;
   - on AppArmor systems that support it (Ubuntu 24.04+), installs
     `resources/apparmor-profile` as `/etc/apparmor.d/rag-assistant`. The profile
     grants the app user namespaces, which Ubuntu 24.04 otherwise blocks
     (`kernel.apparmor_restrict_unprivileged_userns = 1`), so Chromium's
     namespace sandbox works without a setuid helper.

3. **Desktop entry registered** under Office/Education/Science.

Removal runs the default post-remove script, which unregisters the
`/usr/bin` link and unloads and deletes the AppArmor profile.

### Verifying Sandbox Configuration

```bash
# On Ubuntu 24.04+: the profile should be installed and loaded
ls -l /etc/apparmor.d/rag-assistant
sudo aa-status | grep rag-assistant

# Without user namespaces: chrome-sandbox should be setuid root
ls -la "/opt/RAG Assistant/chrome-sandbox"   # -rwsr-xr-x root root

# Launch from a terminal; there should be no "SUID sandbox helper" FATAL
rag-assistant
```

If an older install left the sandbox broken ("The SUID sandbox helper binary was
found, but is not configured correctly"), reinstalling a fixed package repairs it.
As a one-off workaround on an affected install:
`sudo chmod 4755 "/opt/RAG Assistant/chrome-sandbox"`.

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
sudo chown root:root "/opt/RAG Assistant/chrome-sandbox"
sudo chmod 4755 "/opt/RAG Assistant/chrome-sandbox"
```

### "Operation not permitted" or "namespace" Errors

**Cause:** User namespaces disabled in kernel. On Ubuntu 24.04+ the installed AppArmor profile is the intended fix (see above); check it with `sudo aa-status | grep rag-assistant` before changing kernel settings.

**Fix (other distributions):**
```bash
# Enable unprivileged user namespaces
sudo sysctl kernel.unprivileged_userns_clone=1

# Make permanent
echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/00-local-userns.conf
```

### App Won't Start After Install

**Check:**
1. Dependencies installed: `apt-cache policy libnotify4 libnss3 libxss1`
2. Python environment set up: `ls ~/.config/rag-assistant/venv/bin/python3` (created on first launch from the system `python3`, 3.11+)
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

## Troubleshooting

Unlike macOS/Windows (which bundle Python), the Linux build creates a virtual
environment at `~/.config/rag-assistant/venv` on first run and installs
dependencies there (2-5 min). Most problems are venv setup issues.

**Backend won't start (`ERR_CONNECTION_REFUSED` on `localhost:8000`)** — the venv
didn't set up. Check `python3 --version` (needs 3.11+), then reset it (recreated on next launch):

```bash
rm -rf ~/.config/rag-assistant/venv
```

**"Python venv module is missing"** (Fedora: `python3`; Arch: `python`):

```bash
sudo apt install python3-venv
```

**"Failed to install required Python packages"** — usually no internet or missing
build tools (Fedora: `gcc gcc-c++ python3-devel`):

```bash
sudo apt install build-essential python3-dev
ping pypi.org
rm -rf ~/.config/rag-assistant/venv            # then relaunch
```

**"Permission denied"**:

```bash
chmod -R u+rwX ~/.config/rag-assistant
```

**"Port 8000 already in use"**:

```bash
sudo lsof -i :8000 && kill -9 <PID>
```

**Seeing detailed errors** — launch from a terminal (`rag-assistant` or the
AppImage path) to see stdout/stderr, or press `Ctrl+Shift+I` → Console and look
for `[Backend Error]`. The backend's own output is appended to
`~/.config/rag-assistant/logs/backend.log` (previous generation in `backend.log.1`).

**Running the bundled backend manually** (advanced):

```bash
source ~/.config/rag-assistant/venv/bin/activate
python3 -m uvicorn backend.main:app --port 8000
```

For running from source as a developer, see [BUILD_CHECKLIST.md](BUILD_CHECKLIST.md).

## References

- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security)
- [Chromium Sandbox](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/sandboxing.md)
- [Debian Packaging Guide](https://www.debian.org/doc/manuals/maint-guide/)
- [electron-builder Linux Config](https://www.electron.build/configuration/linux)
