# Release Plan: Version 0.2.0

**Target Release Date:** TBD  
**Release Type:** Minor version (new features)  
**Platforms:** macOS (arm64, x64), Windows (x64, ia32), Linux (x64, arm64)

## Overview

Version 0.2.0 introduces the new profile system with isolated vector databases per profile, along with Windows support and other improvements. This release will be the first to fully support all three platforms through automated GitHub Actions CI/CD.

## What's New in 0.2.0

### Major Features

- **Profile-Specific Vector Databases** ✅
  - Each profile now has its own isolated ChromaDB instance
  - No more hardcoded `user-1` paths
  - Automatic path management: `~/.zotero-llm/profiles/{profile-id}/chroma`
  - Switch profiles without reindexing - each maintains separate embeddings
  - Different embedding models per profile without conflicts

- **Full Windows Support** ✅
  - PyInstaller build scripts for Windows (`bundle-python-pyinstaller-windows.ps1`)
  - NSIS installer with Desktop and Start Menu shortcuts
  - Comprehensive Windows build documentation
  - Portable ZIP distribution option

- **Improved Profile System**
  - Better isolation between profiles
  - Cleaner settings management
  - Per-profile embedding model support

### Bug Fixes

- Fixed vector database path not respecting profile isolation
- Removed hardcoded paths that prevented multi-profile workflows

### Documentation

- Complete Windows build guide
- Windows quick reference
- Updated profile system documentation
- Build and release automation guide

## Pre-Release Checklist

### Code & Testing

- [ ] **Test profile switching with different embedding models**
  - Create 2-3 profiles
  - Use different embedding models (bge-base, all-MiniLM, instructor)
  - Index documents in each profile
  - Switch between profiles and verify correct data loads
  - Verify no cross-contamination

- [ ] **Test on all platforms**
  - [ ] macOS (Intel and Apple Silicon)
  - [ ] Windows 10/11 (x64)
  - [ ] Linux (Ubuntu 22.04+, Debian 12+)

- [ ] **Regression testing**
  - Chat functionality
  - Document indexing
  - Citation extraction
  - Settings persistence
  - Auto-updates

- [ ] **Migration testing**
  - Test upgrade from 0.1.11 → 0.2.0
  - Verify existing profiles migrate correctly
  - Check if old `user-1` data needs migration path

### Documentation

- [ ] Update `CHANGELOG.md` with all changes
- [ ] Update `README.md` if needed
- [ ] Verify all build guides are current
- [ ] Update version in docs that reference it

### Version Updates

- [ ] Update version in `package.json`: `"version": "0.2.0"`
- [ ] Update version in `frontend/package.json` if needed
- [ ] Git commit: `git commit -am "Bump version to 0.2.0"`
- [ ] Git tag: `git tag -a v0.2.0 -m "Release v0.2.0"`

## Build Process (Automated via GitHub Actions)

### Prerequisites

- [ ] GitHub repository secrets configured:
  - `GITHUB_TOKEN` (automatic)
  - Optional: Code signing certificates for macOS/Windows

### Automated Build Steps

The `.github/workflows/build-all.yml` workflow will:

1. **Trigger on tag push**: `git push origin v0.2.0`
2. **Parallel builds** on 3 runners:
   - `ubuntu-24.04` → Linux packages
   - `macos-latest` → macOS installers
   - `windows-latest` → Windows installers

3. **Build artifacts created:**
   - **macOS**: 
     - `RAG-Assistant-0.2.0-mac-arm64.dmg` (Apple Silicon)
     - `RAG-Assistant-0.2.0-mac-x64.dmg` (Intel)
     - `RAG-Assistant-0.2.0-mac-arm64.zip` (portable)
     - `RAG-Assistant-0.2.0-mac-x64.zip` (portable)
     - `latest-mac.yml` (auto-update metadata)
   
   - **Windows**:
     - `RAG-Assistant-0.2.0-win-x64.exe` (NSIS installer)
     - `RAG-Assistant-0.2.0-win-ia32.exe` (32-bit installer)
     - `RAG-Assistant-0.2.0-win-x64.zip` (portable)
     - `RAG-Assistant-0.2.0-win-ia32.zip` (portable)
     - `latest.yml` (auto-update metadata)
   
   - **Linux**:
     - `RAG-Assistant-0.2.0-linux-x64.AppImage` (universal)
     - `RAG-Assistant-0.2.0-linux-amd64.deb` (Debian/Ubuntu)
     - `RAG-Assistant-0.2.0-linux-arm64.AppImage` (ARM)
     - `latest-linux.yml` (auto-update metadata)

4. **Automatic GitHub Release**:
   - Creates release `v0.2.0`
   - Uploads all build artifacts
   - Generates release notes from commits

### Manual Build (If Needed)

If you need to build manually on specific hardware:

#### macOS

```bash
# 1. Create Python bundle (PyInstaller)
./scripts/bundle-python-pyinstaller.sh

# 2. Build Electron app
npm run build
npm run package:mac

# Output: release/*.dmg, release/*.zip, release/latest-mac.yml
```

#### Windows

```powershell
# 1. Create Python bundle (PyInstaller)
.\scripts\bundle-python-pyinstaller-windows.bat

# 2. Build Electron app
npm run build
npm run package:win

# Output: release/*.exe, release/*.zip, release/latest.yml
```

#### Linux

```bash
# 1. Python will be installed on first run (no bundle needed)
# 2. Build Electron app
npm run build
npm run package:linux

# Output: release/*.AppImage, release/*.deb, release/latest-linux.yml
```

## Release Steps

### 1. Prepare Release Branch (Optional)

```bash
git checkout -b release/v0.2.0
# Make any last-minute changes
git commit -am "Final prep for v0.2.0"
git push origin release/v0.2.0
```

### 2. Update Version & Tag

```bash
# Ensure you're on master/main
git checkout master

# Update version in package.json (if not done)
# Edit: "version": "0.2.0"

# Commit version bump
git commit -am "Release v0.2.0"

# Create annotated tag
git tag -a v0.2.0 -m "Release v0.2.0 - Profile-specific vector databases and Windows support"

# Push commits and tags (triggers CI/CD)
git push origin master
git push origin v0.2.0
```

### 3. Monitor GitHub Actions Build

1. Go to: `https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/actions`
2. Watch "Build All Platforms" workflow
3. Verify all 3 jobs complete successfully:
   - ✅ `build-all (ubuntu-24.04)`
   - ✅ `build-all (macos-latest)`
   - ✅ `build-all (windows-latest)`
   - ✅ `create-release`

**Build time:** ~15-25 minutes total

### 4. Verify GitHub Release

1. Go to: `https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases`
2. Verify `v0.2.0` release exists
3. Check all artifacts are uploaded:
   - [ ] 4 macOS files (2 DMG, 2 ZIP)
   - [ ] 4 Windows files (2 EXE, 2 ZIP)
   - [ ] 3 Linux files (2 AppImage, 1 DEB)
   - [ ] 3 YAML files (latest-mac.yml, latest.yml, latest-linux.yml)

### 5. Edit Release Notes

GitHub auto-generates release notes, but enhance them:

```markdown
# RAG Assistant for Zotero v0.2.0

## 🎉 What's New

### Profile-Specific Vector Databases
Each profile now maintains its own isolated ChromaDB instance. Switch between profiles without reindexing!

- ✅ Automatic profile-specific paths: `~/.zotero-llm/profiles/{profile}/chroma`
- ✅ Different embedding models per profile
- ✅ No more hardcoded `user-1` paths
- ✅ Complete data isolation between profiles

### Full Windows Support
Windows users can now enjoy native installers and portable distributions!

- ✅ NSIS installer with desktop shortcuts
- ✅ PyInstaller-bundled Python backend
- ✅ Comprehensive Windows build documentation
- ✅ Portable ZIP option

## 🐛 Bug Fixes

- Fixed vector database paths not respecting profile system
- Improved profile switching reliability
- Better error handling for missing vector databases

## 📥 Installation

### macOS
Download `RAG-Assistant-0.2.0-mac-arm64.dmg` (Apple Silicon) or `RAG-Assistant-0.2.0-mac-x64.dmg` (Intel)

### Windows
Download `RAG-Assistant-0.2.0-win-x64.exe` and run the installer.

**Note:** Windows SmartScreen may warn about an unrecognized app. Click "More info" → "Run anyway". The app is safe but not code-signed.

### Linux
- **Debian/Ubuntu**: Download `RAG-Assistant-0.2.0-linux-amd64.deb` and install with `sudo apt install ./RAG-Assistant-0.2.0-linux-amd64.deb`
- **Universal**: Download `RAG-Assistant-0.2.0-linux-x64.AppImage`, make executable, and run

## 📚 Documentation

- [Windows Build Guide](docs/WINDOWS_BUILD_GUIDE.md)
- [Profile System Guide](docs/profile_system_guide.md)
- [Release Process](docs/RELEASE_PROCESS.md)

## 🔄 Upgrading from 0.1.x

The app will auto-update if you have v0.1.8+. Otherwise, download and install the new version.

**Data Migration:** Your existing profiles and vector databases will be preserved. The old `user-1` path will need to be migrated manually if you want to keep that data - see migration guide in docs.

## Full Changelog

See [CHANGELOG.md](CHANGELOG.md) for complete details.
```

### 6. Test Downloads

Download and test installers on actual hardware:

- [ ] **macOS Intel**: Download DMG, install, launch, verify profile switching
- [ ] **macOS Apple Silicon**: Same tests
- [ ] **Windows 10/11**: Download EXE, install, test profile system
- [ ] **Linux Ubuntu**: Download DEB, install, test

### 7. Test Auto-Update

If you have 0.1.11 installed:

1. Launch the app
2. Wait for "Update Available" notification
3. Click "Download Update"
4. Verify it downloads v0.2.0
5. Install and relaunch
6. Verify upgrade was successful

### 8. Publish Release

If the release was created as a draft:

1. Review all sections
2. Uncheck "Set as a pre-release" (for stable release)
3. Click "Publish release"

If it was auto-published, it's already live!

## Post-Release Tasks

### Immediate (Day 1)

- [ ] Monitor GitHub Issues for bug reports
- [ ] Check GitHub Discussions for questions
- [ ] Respond to first-day feedback
- [ ] Tweet/announce on social media (if applicable)
- [ ] Update README badges if needed

### Week 1

- [ ] Monitor download statistics
- [ ] Track auto-update adoption rate
- [ ] Create hotfix branch if critical issues found
- [ ] Update documentation based on user feedback

### Planning Next Release

- [ ] Create `v0.2.1` milestone for bug fixes
- [ ] Create `v0.3.0` milestone for next features
- [ ] Label issues accordingly
- [ ] Update project board

## Rollback Plan

If critical issues are discovered:

### Option 1: Hotfix Release (v0.2.1)

```bash
git checkout -b hotfix/v0.2.1
# Fix critical bug
git commit -am "Hotfix: Critical bug"
git tag -a v0.2.1 -m "Hotfix v0.2.1"
git push origin v0.2.1
```

### Option 2: Unpublish Release

1. Mark release as "pre-release"
2. Add warning to release notes
3. Delete release (last resort)

### Option 3: Revert to 0.1.11

Users can manually download 0.1.11 from release history.

## Known Issues / Warnings

Document any known issues:

- **Windows SmartScreen**: Expected for unsigned apps
- **Linux first-run**: May need to install Python venv on first launch
- **macOS Gatekeeper**: May need right-click → Open on first launch
- **Profile Migration**: Old `user-1` data needs manual migration

## Success Metrics

Track these after release:

- [ ] Download count per platform
- [ ] Auto-update adoption rate
- [ ] Issue reports (target: <5 critical bugs)
- [ ] GitHub stars increase
- [ ] User engagement in Discussions

## Communication Plan

### Release Announcement Channels

1. **GitHub Release** - Primary announcement (auto-generated)
2. **GitHub Discussions** - Detailed post with Q&A
3. **README.md** - Update "What's New" section
4. **Social Media** - Twitter/X, LinkedIn (if applicable)
5. **Email List** - If you have subscribers

### Sample Announcement

```
🎉 RAG Assistant for Zotero v0.2.0 is now available!

New features:
✅ Profile-specific vector databases - no more shared paths!
✅ Full Windows support with native installers
✅ Improved profile isolation and switching

Download now: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/tag/v0.2.0

Questions? Join the discussion: [link to GitHub Discussions]
```

## Timeline

| Phase | Duration | Tasks |
|-------|----------|-------|
| **Pre-Release Testing** | 3-5 days | Platform testing, regression tests, migration testing |
| **Build & Release** | 1 day | Tag, CI/CD build, edit release notes, publish |
| **Immediate Support** | 1-2 days | Monitor issues, respond to feedback |
| **Post-Release** | 1 week | Track metrics, plan hotfixes if needed |

## Checklist Summary

**Before Tag:**
- [ ] All features tested
- [ ] Version bumped in package.json
- [ ] CHANGELOG.md updated
- [ ] Documentation current
- [ ] Migration path documented

**Create Release:**
- [ ] Tag created: `git tag -a v0.2.0 -m "Release v0.2.0"`
- [ ] Tag pushed: `git push origin v0.2.0`
- [ ] GitHub Actions build completed successfully
- [ ] All artifacts uploaded to release

**After Release:**
- [ ] Release notes edited and enhanced
- [ ] Downloads tested on all platforms
- [ ] Auto-update tested
- [ ] Announcements posted
- [ ] Monitoring active for issues

## Resources

- **CI/CD Workflow**: `.github/workflows/build-all.yml`
- **Release Process**: `docs/RELEASE_PROCESS.md`
- **Build Checklist**: `docs/BUILD_CHECKLIST.md`
- **Changelog**: `CHANGELOG.md`
- **Windows Guide**: `docs/WINDOWS_BUILD_GUIDE.md`
- **Profile Guide**: `docs/profile_system_guide.md`

## Questions?

If you encounter issues during the release process:

1. Check the [RELEASE_PROCESS.md](RELEASE_PROCESS.md) guide
2. Review GitHub Actions logs for build errors
3. Test locally with manual build process
4. Document any process improvements for future releases

---

**Ready to release?** Start with the Pre-Release Checklist above! 🚀
