# Profile System Quick Start Guide

## What are Profiles?

Profiles allow you to maintain separate workspaces within RAG Assistant for Zotero. Each profile has its own:
- Settings (API keys, model preferences, etc.)
- Chat history and sessions
- Document embeddings (vector database)

## Using Profiles

### Creating a New Profile

1. Open the Settings page (gear icon)
2. In the "Profile" section at the top, click the "+ New" button
3. Enter a name for your profile (e.g., "Work", "Personal", "Research")
4. Click "Create"
5. Your new profile is created with default settings

### Switching Profiles

1. Open the Settings page
2. Select a different profile from the "Profile" dropdown
3. Confirm the switch (note: this will reload the application)
4. The app reloads with the selected profile's data

**Important**: Switching profiles reloads the application. Any unsaved work will be lost.

### Managing Profiles

#### Via Settings UI
- **View Active Profile**: The current profile is shown in the dropdown
- **Create Profile**: Click "+ New" button
- **Switch Profile**: Select from dropdown, confirm reload
- **Cancel Create**: Click "Cancel" to close the create form

#### Via API (Advanced Users)
```bash
# List all profiles
curl http://localhost:8000/profiles

# Create a profile
curl -X POST http://localhost:8000/profiles \
  -H "Content-Type: application/json" \
  -d '{"id": "my-profile", "name": "My Profile", "description": "Optional description"}'

# Get profile details
curl http://localhost:8000/profiles/my-profile

# Update profile
curl -X PUT http://localhost:8000/profiles/my-profile \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Name", "description": "Updated description"}'

# Switch active profile
curl -X POST http://localhost:8000/profiles/my-profile/activate

# Delete profile (not active)
curl -X DELETE http://localhost:8000/profiles/my-profile

# Delete active profile (requires force)
curl -X DELETE "http://localhost:8000/profiles/my-profile?force=true"
```

## Use Cases

### Multiple Work Contexts
- **Work Profile**: Use your company's API keys, keep work-related chats
- **Personal Profile**: Use personal API keys, keep personal research separate
- **Research Profile**: Dedicated to academic research with specific model settings

### Testing and Development
- **Production Profile**: Stable, production settings
- **Testing Profile**: Experimental settings and models
- **Development Profile**: Local models, development API keys

### Collaboration
- **Export a profile** (coming soon) to share settings and sessions with colleagues
- **Import a profile** (coming soon) to adopt a colleague's configuration

## Data Storage

All profile data is stored locally on your computer at:
```
~/.zotero-llm/profiles/
```

Each profile has its own folder with:
- `profile.json` - Metadata (name, description, timestamps)
- `settings.json` - Settings (API keys, models, etc.)
- `sessions.json` - Chat history
- `chroma/` - Vector database for document embeddings

## Best Practices

1. **Use Descriptive Names**: Name profiles clearly (e.g., "Client-ProjectX", "Personal-Reading")
2. **Regular Backups**: Keep backups of important profiles (export feature coming soon)
3. **Separate Sensitive Data**: Use different profiles for work and personal to keep data isolated
4. **Test Changes**: Create a test profile before making major settings changes

## Troubleshooting

### Profile Won't Switch
- **Symptom**: Clicking a profile does nothing
- **Solution**: Check browser console for errors, ensure backend is running

### Settings Not Saving
- **Symptom**: Settings reset after profile switch
- **Solution**: Ensure you clicked "Save Settings" before switching profiles

### Default Profile Missing
- **Symptom**: No profiles shown on first run
- **Solution**: The "default" profile should be created automatically. If not, restart the backend.

### Can't Delete Active Profile
- **Symptom**: Delete button doesn't work for current profile
- **Solution**: Switch to a different profile first, or use the API with `force=true`

## Future Features

- **Import/Export**: Share profiles via ZIP files
- **Profile Templates**: Quick start with pre-configured profiles
- **Profile Statistics**: See storage size, message count, etc.
- **Bulk Operations**: Manage multiple profiles at once
- **Automatic Backups**: Schedule regular profile backups

## Migration from Single-Profile Setup

If you were using the plugin before profiles were added:

1. Your existing settings are automatically migrated to a "default" profile
2. Your chat history is preserved in the default profile
3. Your vector database is moved to the default profile
4. Everything continues to work as before
5. You can now create additional profiles as needed

No manual migration is required!
