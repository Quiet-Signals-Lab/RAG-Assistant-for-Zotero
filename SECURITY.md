# Security and Privacy Guide

## Data Storage Overview

RAG Assistant stores data in different locations depending on how you're running it:

### Desktop App (Packaged Installer)

When using the desktop application, data is stored in two locations:

1. **Application Data** (Electron-managed, platform-specific):
   - **macOS**: `~/Library/Application Support/RAG Assistant/`
   - **Windows**: `%APPDATA%\RAG Assistant\`
   - **Linux**: `~/.config/rag-assistant/` (venv only)
   - Stores: Window state, app preferences, temporary files

2. **Profile Data** (Backend-managed, same on all platforms):
   - **All Platforms**: `~/.zotero-llm/`
   - Stores: API keys, settings, chat history, vector databases
   - This location is consistent across all platforms for the backend

### Running from Source (Development)

When running from source code, only `~/.zotero-llm/` is used for all user data.

---

## What Gets Excluded from Git

The following sensitive files and directories are excluded from version control (see `.gitignore`):

### User Data and Configuration
- `~/.zotero-llm/` - Your entire profile directory containing:
  - API keys for LLM providers
  - Local file paths specific to your machine
  - Chat history and sessions
  - Vector database indices
  - Profile settings

### Environment Files
- `.env` - Contains environment-specific configuration
- `settings.json` - User settings with API credentials
- `active_profile.json` - Current active profile

### Generated Data
- `vector_db/` - ChromaDB embeddings database
- `*.sqlite3` - Local database files
- `__pycache__/` - Python bytecode cache

## Data Storage Locations

### Profile Directory Structure
```
~/.zotero-llm/
 active_profile.json          # Current active profile
 profiles/
     default/                 # Profile ID
         profile.json         # Profile metadata
         settings.json        # Settings with API keys
         sessions.json        # Chat history
         chroma/             # Vector database
```

### What's Stored Where

**API Keys and Credentials** (`~/.zotero-llm/profiles/{profile}/settings.json`):
- OpenAI API key
- Anthropic API key
- Mistral API key
- Google API key
- Groq API key
- OpenRouter API key
- Ollama base URL

**Local Paths** (profile settings):
- Zotero database path (e.g., `/Users/you/Zotero/zotero.sqlite`)
- ChromaDB storage path
- PDF attachment locations

**Personal Data** (`~/.zotero-llm/profiles/{profile}/sessions.json`):
- Chat conversations
- Research queries
- Generated summaries
- Session metadata

**Vector Embeddings** (`~/.zotero-llm/profiles/{profile}/chroma/`):
- Embedded PDF content
- Metadata indices
- BM25 indices

## Setting Up on a New Machine

Desktop app users install the app and set the Zotero path in Settings. Source
users follow the development setup in `CONTRIBUTING.md`:

1. **Install dependencies**: `requirements.txt` in a virtual environment, then
   `npm install` at the root and in `frontend/`.

2. **Optional environment file**: `cp .env.example .env` and add provider API
   keys there if you prefer them outside the Settings page.

3. **Zotero path and profile**: set in Settings on first run; the profile
   directory is created for you.

4. **The application will auto-generate**:
   - Default settings on first run
   - Profile metadata
   - Active profile marker

5. **Configure API keys** via Settings UI after starting the app

## Best Practices

### For Developers

1. **Never commit**:
   - `.env` files with real values
   - `settings.json` with API keys
   - Any file from `~/.zotero-llm/`
   - Personal Zotero database paths

2. **Always commit**:
   - `.env.example` with placeholder values
   - Documentation about setup process
   - Default configuration templates

3. **Before committing**:
   ```bash
   git status  # Check what's staged
   git diff    # Review changes
   # Verify no sensitive data is included
   ```

### For Users

1. **Backup your data**:
   ```bash
   # Desktop app users: Backup profile data (chat history, settings, vector DB)
   tar -czf zotero-llm-backup.tar.gz ~/.zotero-llm/
   
   # Optional: Backup app preferences (if needed)
   # macOS: ~/Library/Application Support/RAG Assistant/
   # Windows: %APPDATA%\RAG Assistant\
   # Linux: ~/.config/rag-assistant/
   ```

2. **Restore from backup**:
   ```bash
   tar -xzf zotero-llm-backup.tar.gz -C ~/
   ```

3. **Switch machines**:
   - Desktop app: Just install the app on new machine, reconfigure settings
   - Don't need to copy `.zotero-llm` directory (profiles will be recreated)
   - Reconfigure API keys via Settings UI
   - Re-index library (database will be rebuilt)
   - Source users: follow the setup in `CONTRIBUTING.md` on the new machine

4. **Secure your API keys**:
   - Never share screenshots of Settings page
   - Don't commit or share `.env` or `settings.json`
   - Rotate keys if accidentally exposed

## Privacy Features

### Local-First Architecture
- All data stays on your device
- No cloud sync by default
- No telemetry or tracking
- API calls go directly to provider (not through our servers)

### Profile Isolation
- Each profile has separate:
  - Settings and API keys
  - Chat history
  - Vector database
  - Zotero library connection

### Data Control
- Delete profiles to remove all associated data
- Export chat history as JSON or Markdown
- Clear vector database without losing settings

## Sharing and Collaboration

### Safe to Share
- Source code (via Git)
- Documentation
- Feature requests and bug reports
- General configuration templates

### DO NOT Share
- Your `.zotero-llm/` directory
- API keys
- `.env` file with real values
- Settings JSON with credentials
- Chat history or sessions
- Vector database files

### Collaborative Development
If working on a team:
1. Each developer has their own `.zotero-llm/` directory
2. Share code via Git (sensitive data excluded)
3. Use `.env.example` to document required variables
4. Test with personal/test API keys
5. Never commit real credentials

## Troubleshooting

### "Profile not found" Error
Delete `~/.zotero-llm/active_profile.json` and start the app again; it recreates
the default profile.

### "Missing API key" Error
- Check Settings UI and add API keys
- Or set in `.env` file
- Verify `~/.zotero-llm/profiles/default/settings.json` exists

### After Git Pull
```bash
# Reinstall dependencies if needed
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install

# Your settings are preserved (not in Git)
# No need to reconfigure
```

### Fresh Start
```bash
# Desktop app users: Remove profile data
rm -rf ~/.zotero-llm/
# App will recreate profiles on next launch
# Reconfigure settings via UI

# Source/development users: Full reset
rm -rf ~/.zotero-llm/
# Start the app; the default profile is recreated. Reconfigure settings via UI
```

## Security Recommendations

1. **API Key Management**:
   - Use environment-specific keys (dev/prod)
   - Rotate keys periodically
   - Monitor API usage for anomalies

2. **File Permissions**:
   ```bash
   # Restrict profile directory access
   chmod 700 ~/.zotero-llm/
   ```

3. **Git Safety**:
   ```bash
   # Verify .gitignore is working
   git status --ignored
   
   # Check for accidentally tracked sensitive files
   git ls-files | grep -E '\.env$|settings\.json|\.zotero-llm'
   ```

4. **Before Publishing**:
   ```bash
   # Search for potential secrets in history
   git log -p | grep -i "api.key\|password\|secret"
   ```

## Questions?

- Check [docs/profile_system_guide.md](docs/profile_system_guide.md) for profile details
- See [docs/multi_provider_system.md](docs/multi_provider_system.md) for provider configuration
- Open an issue for security concerns
