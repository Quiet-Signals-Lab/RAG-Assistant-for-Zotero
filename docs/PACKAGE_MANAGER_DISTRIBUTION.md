# Package Manager Distribution Guide

This guide walks through setting up Homebrew Tap (macOS/Linux) and Winget (Windows) distribution for RAG-Assistant-for-Zotero.

## Table of Contents
- [Homebrew Tap Setup](#homebrew-tap-setup)
- [Winget Submission](#winget-submission)
- [Maintenance and Updates](#maintenance-and-updates)

---

## Homebrew Tap Setup

### 1. Create GitHub Repository

On GitHub.com, create a new public repository:
- **Name**: `homebrew-rag-assistant-for-zotero`
- **Description**: Homebrew tap for RAG-Assistant-for-Zotero
- **Visibility**: Public
- **Initialize**: Add README

### 2. Clone and Set Up Locally

```bash
cd ~/Projects
git clone https://github.com/Quiet-Signals-Lab/homebrew-rag-assistant-for-zotero.git
cd homebrew-rag-assistant-for-zotero
mkdir Casks
```

### 3. Create the Cask File

Create `Casks/rag-assistant-for-zotero.rb`:

```ruby
cask "rag-assistant-for-zotero" do
  version "0.4.5"
  sha256 :no_check # TODO: Add SHA256 once you verify the download URL
  
  url "https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/download/v#{version}/RAG.Assistant-#{version}-universal.dmg"
  name "RAG Assistant for Zotero"
  desc "AI-powered research assistant for your Zotero library"
  homepage "https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero"
  
  livecheck do
    url :url
    strategy :github_latest
  end
  
  app "RAG Assistant.app"
  
  zap trash: [
    "~/Library/Application Support/rag-assistant",
    "~/Library/Preferences/com.electron.rag-assistant.plist",
    "~/Library/Saved Application State/com.electron.rag-assistant.savedState",
  ]
end
```

### 4. Add README

Create `README.md`:

```markdown
# Homebrew Tap for RAG-Assistant-for-Zotero

AI-powered research assistant for your Zotero library.

## Installation

\`\`\`bash
brew tap Quiet-Signals-Lab/rag-assistant-for-zotero
brew install --cask rag-assistant-for-zotero
\`\`\`

## Updating

\`\`\`bash
brew upgrade rag-assistant-for-zotero
\`\`\`

## Uninstalling

\`\`\`bash
brew uninstall --cask rag-assistant-for-zotero
\`\`\`

## More Information

Visit the [main repository](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero) for documentation and support.
```

### 5. Verify Release File Name

Check your actual release filename:

```bash
# Option 1: Check local releases
ls -la release/

# Option 2: Check GitHub releases page
# Visit: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases
```

Common filename patterns:
- `RAG.Assistant-#{version}-universal.dmg`
- `RAG.Assistant-#{version}.dmg`
- `RAG-Assistant-for-Zotero-#{version}.dmg`

Update the `url` line in the cask file to match your actual filename.

### 6. Calculate SHA256 Hash

```bash
# Download the release file
curl -L "https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/download/v0.4.5/RAG.Assistant-0.4.5-universal.dmg" -o test.dmg

# Calculate SHA256
shasum -a 256 test.dmg

# Example output:
# abc123def456... test.dmg

# Update the cask file with the hash
# Replace: sha256 :no_check
# With: sha256 "abc123def456..."
```

### 7. Commit and Push

```bash
git add .
git commit -m "Add RAG-Assistant-for-Zotero cask v0.4.5"
git push origin main
```

### 8. Test Installation

```bash
# Add your tap
brew tap Quiet-Signals-Lab/rag-assistant-for-zotero

# Install the cask
brew install --cask rag-assistant-for-zotero

# Verify installation
open -a "RAG Assistant"

# Uninstall for testing
brew uninstall --cask rag-assistant-for-zotero
```

### 9. Update Documentation

Add installation instructions to your main README.md:

```markdown
### Installation via Homebrew (macOS/Linux)

\`\`\`bash
brew tap Quiet-Signals-Lab/rag-assistant-for-zotero
brew install --cask rag-assistant-for-zotero
\`\`\`
```

---

## Winget Submission

### 1. Fork winget-pkgs Repository

Visit https://github.com/microsoft/winget-pkgs and click **Fork**.

### 2. Clone Your Fork

```bash
cd ~/Projects
git clone https://github.com/aahepburn/winget-pkgs.git
cd winget-pkgs
```

### 3. Create Manifest Directory

```bash
# Winget uses first letter of publisher, then full identifier
mkdir -p manifests/a/aahepburn/RAGAssistantForZotero/0.4.5
cd manifests/a/aahepburn/RAGAssistantForZotero/0.4.5
```

### 4. Create Version Manifest

Create `aahepburn.RAGAssistantForZotero.yaml`:

```yaml
PackageIdentifier: aahepburn.RAGAssistantForZotero
PackageVersion: 0.4.5
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
```

### 5. Create Locale Manifest

Create `aahepburn.RAGAssistantForZotero.locale.en-US.yaml`:

```yaml
PackageIdentifier: aahepburn.RAGAssistantForZotero
PackageVersion: 0.4.5
PackageLocale: en-US
Publisher: Alexander Hepburn
PublisherUrl: https://github.com/aahepburn
PublisherSupportUrl: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues
PackageName: RAG Assistant for Zotero
PackageUrl: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero
License: Apache-2.0
LicenseUrl: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/blob/master/LICENSE
ShortDescription: AI-powered research assistant for your Zotero library
Description: |-
  RAG-Assistant-for-Zotero is an AI-powered research assistant that helps you
  interact with your Zotero library using natural language queries. It uses
  retrieval-augmented generation (RAG) to provide intelligent responses based
  on your research papers and documents.
Tags:
  - zotero
  - ai
  - research
  - rag
  - llm
  - assistant
ManifestType: defaultLocale
ManifestVersion: 1.6.0
```

### 6. Create Installer Manifest

Create `aahepburn.RAGAssistantForZotero.installer.yaml`:

```yaml
PackageIdentifier: aahepburn.RAGAssistantForZotero
PackageVersion: 0.4.5
Platform:
  - Windows.Desktop
MinimumOSVersion: 10.0.0.0
InstallerType: nullsoft
Scope: user
InstallModes:
  - interactive
  - silent
UpgradeBehavior: install
Installers:
  - Architecture: x64
    InstallerUrl: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/download/v0.4.5/RAG.Assistant.Setup.0.4.5.exe
    InstallerSha256: PUT_HASH_HERE
ManifestType: installer
ManifestVersion: 1.6.0
```

**Note**: Update the `InstallerUrl` to match your actual Windows installer filename.

### 7. Calculate Windows Installer SHA256

```bash
# Download Windows installer
curl -L "https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/download/v0.4.5/RAG.Assistant.Setup.0.4.5.exe" -o installer.exe

# Calculate SHA256 (on Mac)
shasum -a 256 installer.exe

# On Windows PowerShell:
# Get-FileHash installer.exe -Algorithm SHA256

# Copy the hash and update InstallerSha256 in the installer manifest
```

### 8. Validate Manifests

```bash
# Check that all files exist
ls -la manifests/a/aahepburn/RAGAssistantForZotero/0.4.5/

# You should see:
# - aahepburn.RAGAssistantForZotero.yaml
# - aahepburn.RAGAssistantForZotero.locale.en-US.yaml
# - aahepburn.RAGAssistantForZotero.installer.yaml
```

### 9. Create Pull Request

```bash
# Create a new branch
git checkout -b add-rag-assistant-0.4.5

# Add your manifest files
git add manifests/a/aahepburn/RAGAssistantForZotero/

# Commit with standard message format
git commit -m "New package: aahepburn.RAGAssistantForZotero version 0.4.5"

# Push to your fork
git push origin add-rag-assistant-0.4.5
```

Then:
1. Go to https://github.com/aahepburn/winget-pkgs
2. Click "Contribute" → "Open pull request"
3. Create PR to microsoft/winget-pkgs:master

### 10. PR Review Process

- Microsoft's automated validation will run
- Reviewers will check:
  - Manifest format correctness
  - Hash verification
  - Package metadata accuracy
- Typical review time: 1-3 days
- Once merged, package becomes available within 24 hours

### 11. Test After Merge

```powershell
# Search for your package
winget search RAGAssistantForZotero

# Install
winget install aahepburn.RAGAssistantForZotero

# Upgrade (for future releases)
winget upgrade aahepburn.RAGAssistantForZotero

# Uninstall
winget uninstall aahepburn.RAGAssistantForZotero
```

---

## Maintenance and Updates

### Releasing New Versions

When you release a new version (e.g., v0.4.6):

#### Homebrew Tap Update

```bash
cd ~/Projects/homebrew-rag-assistant-for-zotero

# Edit Casks/rag-assistant-for-zotero.rb
# 1. Update version number
# 2. Calculate new SHA256
# 3. Commit and push

git add Casks/rag-assistant-for-zotero.rb
git commit -m "Update to v0.4.6"
git push origin main
```

Users will get the update automatically with:
```bash
brew update
brew upgrade rag-assistant-for-zotero
```

#### Winget Update

```bash
cd ~/Projects/winget-pkgs

# Create new version directory
mkdir -p manifests/a/aahepburn/RAGAssistantForZotero/0.4.6
cd manifests/a/aahepburn/RAGAssistantForZotero/0.4.6

# Copy previous version and update:
# 1. Version numbers
# 2. InstallerUrl
# 3. InstallerSha256

# Create PR following steps 9-10 above
```

### Automation Options

#### Homebrew Auto-Updates
Users automatically get updates with `brew upgrade`. The `livecheck` block in your cask enables automatic version detection.

#### Winget Auto-Updates
Consider using [Winget Releaser GitHub Action](https://github.com/vedantmgoyal2009/winget-releaser) to automatically submit new versions when you create GitHub releases.

Example `.github/workflows/winget-releaser.yml`:

```yaml
name: Winget Release

on:
  release:
    types: [released]

jobs:
  winget:
    runs-on: ubuntu-latest
    steps:
      - uses: vedantmgoyal2009/winget-releaser@v2
        with:
          identifier: aahepburn.RAGAssistantForZotero
          token: ${{ secrets.WINGET_TOKEN }}
```

---

## Official Homebrew Cask (Future)

To submit to official Homebrew Casks (homebrew/cask):

### Requirements
- ✅ Stable versioned releases
- ✅ Open source license
- ✅ Direct download URLs
- ⚠️ **Code-signed macOS app** (requires Apple Developer Account - $99/year)

### Code Signing Setup

1. **Enroll in Apple Developer Program**
   - Visit https://developer.apple.com
   - Cost: $99/year

2. **Get Developer ID Certificate**
   - In Xcode: Preferences → Accounts → Manage Certificates
   - Create "Developer ID Application" certificate

3. **Sign Your App**
   ```bash
   # During build process
   codesign --deep --force --verify --verbose \
     --sign "Developer ID Application: Your Name" \
     "RAG Assistant.app"
   
   # Notarize with Apple
   xcrun notarytool submit RAG-Assistant.dmg \
     --apple-id "your@email.com" \
     --password "app-specific-password" \
     --team-id "TEAM_ID"
   ```

4. **Update electron-builder Config**
   Add to package.json:
   ```json
   "build": {
     "mac": {
       "identity": "Developer ID Application: Your Name (TEAM_ID)",
       "hardenedRuntime": true,
       "gatekeeperAssess": false,
       "entitlements": "build/entitlements.mac.plist"
     }
   }
   ```

5. **Submit to Official Homebrew**
   ```bash
   # Fork homebrew/homebrew-cask
   # Add your cask to Casks/
   # Submit PR
   ```

---

## User Installation

### macOS/Linux (Homebrew)
```bash
brew tap Quiet-Signals-Lab/rag-assistant-for-zotero
brew install --cask rag-assistant-for-zotero
```

### Windows (Winget)
```powershell
winget install aahepburn.RAGAssistantForZotero
```

### Updating Main Repository Documentation

Add these instructions to your main README.md under an "Installation" section.

---

## Troubleshooting

### Homebrew Issues

**"Cask not found"**
```bash
brew untap Quiet-Signals-Lab/rag-assistant-for-zotero
brew tap Quiet-Signals-Lab/rag-assistant-for-zotero
```

**SHA256 mismatch**
- Regenerate the hash from the actual release file
- Ensure the download URL is correct

**App won't open (Gatekeeper)**
- Users can: System Preferences → Security & Privacy → "Open Anyway"
- Or right-click app → Open
- Or sign your app (see Code Signing section)

### Winget Issues

**Validation failures**
- Check YAML syntax (indentation must be spaces, not tabs)
- Verify all URLs are accessible
- Ensure SHA256 matches exactly

**Hash mismatch**
- Download the exact file from the URL in the manifest
- Recalculate hash on that file
- Update manifest

---

## Resources

- [Homebrew Cask Documentation](https://docs.brew.sh/Cask-Cookbook)
- [Winget Package Submission](https://github.com/microsoft/winget-pkgs/blob/master/AUTHORING_MANIFESTS.md)
- [Apple Code Signing Guide](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)
- [Electron Builder Code Signing](https://www.electron.build/code-signing)
