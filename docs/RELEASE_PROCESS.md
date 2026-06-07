# Release Process Guide

This guide walks you through creating a new release of the Zotero LLM Desktop App with automatic updates.

## Official Release Workflow

**⚠️ IMPORTANT: The official release workflow is "Build All Platforms" (`.github/workflows/build-all.yml`).**

This is the **only** workflow that should be used for creating releases. It:
- Builds for all three platforms (macOS, Windows, Linux) in a single workflow
- Creates platform-specific installers automatically
- Uploads artifacts and creates GitHub releases
- Ensures consistency across all platforms

**To trigger a release:**
1. Push a version tag: `git push origin v0.x.x`
2. OR manually trigger the workflow from GitHub Actions with a version number

Do not create separate or custom workflows for releases.

## Quick Release Commands

**Standard release sequence (use this for all releases):**

```bash
# 1. Update version in package.json first (manually)

# 2. Commit all changes with a clear release message
git add package.json CHANGELOG.md [any other files]
git commit -m "Release v0.x.x - Brief description of changes"

# 3. Create tag and push everything
git tag v0.x.x
git push origin master
git push origin v0.x.x

# 4. Verify workflow triggered
echo "Check status at: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/actions"
```

**Important notes:**
- Always update `package.json` version first
- Use semantic versioning (v0.2.3, v1.0.0, etc.)
- Push master and tag separately (NOT `git push origin master --tags`)
- Verify the GitHub Actions workflow completes successfully
- Check that the release was created with all platform artifacts

## Prerequisites

- [ ] Git access to the repository
- [ ] GitHub account with release permissions
- [ ] Access to all three platforms (macOS, Windows, Linux) OR CI/CD pipeline
- [ ] Code signing certificates (optional but recommended)

## Release Checklist

### 1. Prepare the Release

- [ ] Test all features thoroughly on each platform
- [ ] Update `CHANGELOG.md` with new features and fixes
- [ ] Review and close related GitHub issues
- [ ] Update version numbers

### 2. Version Numbers

Update version in `package.json`:

```json
{
  "version": "0.1.0"
}
```

**Version Scheme:** Follow [Semantic Versioning](https://semver.org/)
- **Major** (1.0.0): Breaking changes
- **Minor** (0.1.0): New features, backward compatible
- **Patch** (0.0.1): Bug fixes only

**Pre-release tags:**
- `0.1.0-alpha.1`: Early testing
- `0.1.0-beta.1`: Feature complete, testing
- `0.1.0-rc.1`: Release candidate

### 3. Verify Workflow Completion

After pushing the tag, monitor the GitHub Actions workflow:

1. **Go to Actions page:**
   ```
   https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/actions
   ```

2. **Check workflow status:**
   - All three platform builds (macOS, Windows, Linux) should complete
   - Artifacts should be uploaded
   - GitHub Release should be created automatically

3. **Verify the release:**
   ```
   https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/latest
   ```

4. **Confirm all artifacts are present:**
   - macOS: `*.dmg`, `*.zip`, `latest-mac.yml`
   - Windows: `*.exe`, `*.zip`, `latest.yml`
   - Linux: `*.AppImage`, `*.deb`, `*.tar.gz`, `latest-linux.yml`

**If the workflow fails:**
- Check the workflow logs in GitHub Actions
- Fix any issues in the code
- Delete the tag: `git tag -d v0.x.x && git push origin :refs/tags/v0.x.x`
- Re-run the release process after fixing

### 4. Test the Release

Download and test the installers from the GitHub Release:

**Test checklist:**
- [ ] App launches without errors on target platform
- [ ] Backend starts and responds
- [ ] Can index Zotero library
- [ ] Can chat with library
- [ ] Settings persist across restarts
- [ ] Auto-update check works (if previous version installed)

### 5. Verify Auto-Updates

1. Install previous version on a test machine
2. Launch the app
3. Wait for "Update Available" notification (or check manually)
4. Download and install update
5. Verify new version launches correctly

### 8. Announce Release

- [ ] Post in GitHub Discussions
- [ ] Update documentation site (if applicable)
- [ ] Social media announcement
- [ ] Email newsletter (if applicable)

## Troubleshooting the Workflow

### Workflow doesn't trigger

- Verify tag starts with `v` (e.g., `v0.2.3`, not `0.2.3`)
- Check GitHub Actions is enabled for your repository
- View workflow runs at: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/actions

### Build fails on specific platform

Check the workflow logs for that platform:
1. Go to the failed workflow run
2. Click on the failed job (macOS, Windows, or Linux)
3. Review the error messages
4. Common issues:
   - Missing dependencies
   - PyInstaller errors
   - Node module issues

### Build fails with "Module not found"

This shouldn't happen with the automated workflow, but if it does:
- Check the workflow file for correct dependency installation
- Verify `requirements.txt` and `package.json` are up to date

### Release not created automatically

- Verify the `create-release` job completed in the workflow
- Check that all platform builds succeeded
- Review the workflow logs for the release job

### Auto-update not detected

- Verify `.yml` files are uploaded
- Check version in `package.json` is greater than installed
- Check GitHub release is published (not draft)
- Look for errors in app console

### Binary too large

The app will be large (100-500 MB) due to Python dependencies. This is normal for bundled Python applications.

### Code signing errors (macOS)

Code signing is handled in the workflow. If you see warnings:
- macOS: First-time users may see Gatekeeper warnings (expected without paid certificate)
- Provide instructions for users: System Preferences → Security & Privacy → "Open Anyway"

### Windows SmartScreen warning

- Get an EV code signing certificate (expensive)
- Or accumulate reputation (users will see warning initially)
- Include instructions in README for users to click "More info" → "Run anyway"

## Beta Testing

Before public release, do a beta test:

1. Create release with `-beta.X` tag
2. Check "pre-release" checkbox
3. Share with beta testers
4. Gather feedback
5. Fix issues
6. Create stable release

## Version History Maintenance

Keep `CHANGELOG.md` updated:

```markdown
# Changelog

## [0.1.0] - 2024-12-02

### Added
- Desktop app with Electron
- Auto-update functionality
- Native installers for all platforms

### Changed
- Improved indexing performance

### Fixed
- Bug where settings weren't saved

## [0.0.1] - 2024-11-01

### Added
- Initial web app release
```

## Support

After release, monitor:
- [ ] GitHub Issues for bug reports
- [ ] GitHub Discussions for questions
- [ ] Download statistics in Release insights
- [ ] Update adoption (check server logs if applicable)

## Next Release

Plan ahead:
- Create milestone for next version
- Label issues for inclusion
- Set target date
- Communicate roadmap to users
