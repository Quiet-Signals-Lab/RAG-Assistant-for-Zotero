# Debian Package Control File Fix

## Issues Fixed

### 1. Description Field Formatting (Primary Issue)

**Problem**: The long description in the control file was not properly formatted for Debian packages. When electron-builder's `fpm` backend wrapped the text, it didn't add the required leading space on continuation lines.

**Error**: 
```
dpkg: error parsing file '/var/lib/dpkg/tmp.ci/control' near line 14 package 'rag-assistant'
```

**Root Cause**: The `--description` flag in `package.json` contained a single long line that got wrapped by `fpm` without proper Debian control file formatting.

**Fix**: Replaced the long single-line description with explicit newlines and proper spacing:

```json
"--description=AI-powered research assistant for your Zotero library.\n Chat with your documents and get cited answers with page numbers.\n Search semantically across your research collection.\n Supports local LLMs via Ollama and cloud providers.",
```

This ensures each line in the description properly starts with a space (` `) as required by Debian policy.

### 2. Vendor Field Improvement

**Change**: Updated `vendor` field from `"aahepburn"` to `"Alexander Hepburn"` for consistency with maintainer field.

## How Debian Control Files Work

The control file has strict formatting requirements:

1. **Single-line fields**: `Package: value`
2. **Multi-line fields** (like Description):
   - First line: `Description: short summary`
   - Continuation lines: **MUST start with a single space** (` `)
   - Empty lines: represented as ` .` (space + dot)

**Valid Example**:
```
Description: AI-powered research assistant for Zotero
 Chat with your documents and get cited answers with page numbers.
 Search semantically across your research collection.
 Supports local LLMs via Ollama and cloud providers.
```

**Invalid Example** (what was happening before):
```
Description: AI-powered research assistant for Zotero
Chat with your documents and get cited answers with page numbers.
```

The second line lacks the leading space, causing dpkg to fail parsing.

## Testing the Fix

### 1. Build a New Package

```bash
# From project root
npm run package:linux
```

This will create a new `.deb` in the `release/` directory.

### 2. Extract and Verify Control File

```bash
# Create temp directory
mkdir -p /tmp/zra-test

# Extract control file (on Linux)
dpkg-deb -R release/RAG-Assistant-0.2.2-linux-amd64.deb /tmp/zra-test

# Or on macOS
ar -x release/RAG-Assistant-0.2.2-linux-amd64.deb
tar -xzf control.tar.gz -C /tmp/zra-test

# View control file
cat /tmp/zra-test/DEBIAN/control
# or
cat /tmp/zra-test/control

# Cleanup (macOS)
rm -f control.tar.gz data.tar.xz debian-binary
```

### 3. Verify Control File Format

Check that:
- [ ] `Package:` field is present
- [ ] `Version:` starts with a digit (e.g., `0.2.2`)
- [ ] `Architecture:` is valid (e.g., `amd64`)
- [ ] `Description:` first line is short summary
- [ ] All description continuation lines start with a single space
- [ ] `Maintainer:` has proper email format

### 4. Test Installation (Linux Only)

```bash
# Install the package
sudo dpkg -i release/RAG-Assistant-0.2.2-linux-amd64.deb

# If dependencies are missing
sudo apt-get install -f

# Verify installation
dpkg -l | grep rag-assistant

# Launch the app
rag-assistant
```

### 5. Validate Package with Lintian (Optional)

On a Debian/Ubuntu system:

```bash
lintian release/RAG-Assistant-0.2.2-linux-amd64.deb
```

This will show any policy violations or warnings.

## Expected Control File Output

After the fix, the control file should look like:

```
Package: rag-assistant
Version: 0.2.2
License: MIT
Vendor: Alexander Hepburn
Architecture: amd64
Maintainer: Alexander Hepburn <aahepburn@proton.me>
Installed-Size: XXXXX
Depends: libgtk-3-0, libnotify4, libxtst6, libnss3, libxss1, libasound2, libgbm1
Recommends: libappindicator3-1
Section: default
Priority: optional
Homepage: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero
Description: AI-powered research assistant for your Zotero library.
 Chat with your documents and get cited answers with page numbers.
 Search semantically across your research collection.
 Supports local LLMs via Ollama and cloud providers.
```

Note: Each line after "Description:" starts with a space.

## References

- [Debian Policy Manual - Control Files](https://www.debian.org/doc/debian-policy/ch-controlfields.html)
- [Debian Control File Syntax](https://www.debian.org/doc/debian-policy/ch-controlfields.html#syntax-of-control-files)
- [electron-builder Linux Configuration](https://www.electron.build/configuration/linux)
- [fpm Documentation](https://fpm.readthedocs.io/en/latest/)

## Troubleshooting

### If dpkg Errors Persist After Config Changes

**Important**: If you've updated the electron-builder configuration in `package.json` but still see dpkg errors, the issue is likely from stale build artifacts, not the config itself.

The electron-builder config (`description`, `synopsis`, etc.) will not create invalid multi-line Description fields - these are single-line values. If errors persist:

1. **Clean old build artifacts**:
   ```bash
   # Remove all previous builds
   rm -rf release/
   rm -rf dist/
   rm -rf python-dist-linux/
   
   # Clear electron-builder cache
   rm -rf node_modules/.cache/electron-builder
   
   # Rebuild from scratch
   npm run package:linux
   ```

2. **Check for extra `--deb-field` options**: Look in `package.json` for any custom `--deb-field` flags that might inject newlines accidentally.

3. **Verify the freshly built .deb**: Extract and inspect the control file from the new package (see testing steps above).

### General Debugging Steps

If you still get parsing errors after cleaning:

1. **Extract and inspect**: Use `dpkg-deb -R` or `ar`/`tar` to extract the package
2. **Check line endings**: Ensure Unix line endings (`LF`), not Windows (`CRLF`)
3. **Validate each field**: Compare against a working `.deb` from a known package
4. **Use sed to debug**: `sed -n '1,20p' DEBIAN/control` to see first 20 lines with exact formatting
5. **Check for hidden characters**: `cat -A DEBIAN/control` to see all characters including spaces/tabs
