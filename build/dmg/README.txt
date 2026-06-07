RAG Assistant for Zotero - Installation Instructions
====================================================

Thank you for downloading RAG Assistant for Zotero!

INSTALLATION
------------

1. Drag the "RAG Assistant" app icon to the "Applications" folder
2. Wait for the copy to complete
3. Eject this disk image


IMPORTANT: Remove macOS Quarantine
-----------------------------------

Since this app is not signed by Apple, you must remove the quarantine flag
before first launch. Open Terminal and run:

    xattr -dr com.apple.quarantine "/Applications/RAG Assistant.app"

Then launch the app from Applications or Spotlight.


PREREQUISITES
-------------

Before using the app, ensure you have:

1. Zotero Desktop Client installed (https://www.zotero.org/download/)
   - The app reads your local Zotero database
   - Default location: ~/Zotero/zotero.sqlite

2. Ollama installed for local LLM support (https://ollama.com/)
   - Download models: ollama pull llama3.1:8b
   - Or use cloud providers (OpenAI, Anthropic, Google) via Settings

3. Python 3.8+ (usually pre-installed on macOS)
   - The app includes a bundled Python backend


FIRST LAUNCH
------------

1. Launch the app (after removing quarantine)
2. Grant any permission requests (file access, network)
3. Optionally, check the path to your Zotero database in Settings.
5. Select your preferred embedding model.
4. In the top right corner of the main menu, press 'Sync' to start 
indexing your Zotero library.
6. Enter your API keys in Settings if using cloud LLMs. 
Not necessary for Ollama.
5. After the indexing is done, select your LLM provider and model.
6. Wait for initial indexing to complete


SYSTEM REQUIREMENTS
-------------------

- macOS 11.0 (Big Sur) or later
- 8GB RAM minimum (16GB recommended)
- 2GB free disk space for vector database


TROUBLESHOOTING
---------------

If the app doesn't launch:
- Verify you ran the quarantine removal command
- Check Console.app for error messages
- Ensure Zotero is installed with a synced library

For more help, visit:
https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues


LICENSE
-------

This software is released under the MIT License.
See LICENSE.txt for full details.


SUPPORT THE PROJECT
-------------------

If you find this tool useful, consider supporting continued development:
https://github.com/sponsors/aahepburn
