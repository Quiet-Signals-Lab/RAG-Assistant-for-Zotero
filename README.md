
# RAG Assistant for Zotero

An open‑source desktop RAG application that enables semantic search across your Zotero library. Easily discover conceptually related papers and ideas within your PDF collection using local or cloud‑based LLMs. The app provides source attribution, metadata filtering, and seamless integration with Zotero.

## What It Does

This tool indexes the PDFs in your Zotero library and uses retrieval-augmented generation (RAG) to answer questions based on their content. Every answer includes citations to the specific sources and page numbers used, making it easy to verify claims and follow up on interesting findings.

It is not a paper summariser — think of it as a library clerk. You describe whatever is on your mind, and it fetches semantically related passages across your collection to get you started, surfacing connections you might otherwise miss during a literature review.

The application can run entirely on your local machine. Your documents and queries stay private if you use local models.

## Quick Installation

The app is available on **macOS** (Apple Silicon only), **Windows**, and **Linux**. You can always download the latest installer from [Releases](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases).

Or install it from a package manager:

**macOS** (Homebrew):

```bash
brew tap Quiet-Signals-Lab/rag-assistant-for-zotero
brew install --cask rag-assistant-for-zotero
```

**Windows** (winget):

```powershell
winget install aahepburn.RAGAssistantForZotero
```

The app is not notarised on Windows and may throw a safety warning.


**Linux** (Debian/Ubuntu): download the `.deb` from [Releases](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases) and install it with `sudo apt install ./RAG-Assistant-*.deb` — Python and all dependencies are bundled.

<img width="1440" height="871" alt="Screenshot 2026-02-21 at 6 24 03 pm" src="https://github.com/user-attachments/assets/a3ef72b4-dd75-4bd9-b50d-ede5ac65cbdc" />

## Key Features

- **Hybrid search**: Combines semantic embeddings and BM25 keyword search with cross-encoder reranking for high-precision retrieval
- **Metadata filtering**: Filter by year, tags, collections, authors, or item types through natural language queries or manual controls
- **Cited answers**: Responses include references to specific documents and page numbers from your library
- **Conversational follow-ups**: Ask follow-up questions that reference previous context without repeating information
- **Source transparency**: View the exact text passages used to generate each answer
- **Privacy controls**: Run fully offline with local models, or exclude specific Zotero collections and tags from the index so they are never sent to a cloud provider
- **Multiple LLM providers**: Use local models via Ollama or LM Studio, or connect to OpenAI, Anthropic, Google, Mistral, Groq, or OpenRouter
- **Profile support**: Maintain separate workspaces with different settings, libraries, and chat histories
- **Automatic updates**: Stay up to date with the latest features and improvements
- **Cross-platform**: Available for macOS, Windows, and Linux


## Prerequisites

To use this application locally, you need:

### 1. Zotero Desktop Client

Install [Zotero](https://www.zotero.org/download/) and sync your library:
- The app reads your local Zotero database to access PDFs and metadata
- Make sure Zotero is installed and your library is synced before first launch
- Default database location:
  - **macOS:** `~/Zotero/zotero.sqlite`
  - **Windows:** `C:\Users\{username}\Zotero\zotero.sqlite`
  - **Linux:** `~/Zotero/zotero.sqlite`

### 2. Language Model (Local or Cloud)

#### Option A: Local Models (No API key needed)

Choose either LM Studio or Ollama to run models locally on your machine:

**LM Studio**: Download from [lmstudio.ai](https://lmstudio.ai), load a model, and start the local server (default port: 1234).

**Ollama**:
```bash
# macOS/Linux - Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Download a model, for example:
ollama pull llama3.2       # Lightweight, fast (1B or 3B)
ollama pull llama3.1:8b    # Good balance of speed and quality
```

**Note:** The app uses SentenceTransformers for embeddings (downloaded automatically on first use), not Ollama/LM Studio embedding models.

#### Option B: Cloud Providers (API key required)

Configure API keys in Settings for: **OpenAI**, **Anthropic**, **Google**, **Mistral**, **Groq**, or **OpenRouter**. See [Provider Setup Guide](docs/provider_guide.md) for where to get API keys.


## Configuration

### First-Time Setup

1. **Zotero Database Location**: The app needs to know where your Zotero database is located. Set this in the Settings panel or in a `.env` file:
   - macOS: `/Users/YOUR_USERNAME/Zotero/zotero.sqlite`
   - Windows: `C:\Users\YOUR_USERNAME\Zotero\zotero.sqlite`
   - Linux: `~/Zotero/zotero.sqlite`

2. **Choose an LLM Provider**:
   - **Local (No API key)**: Ollama or LM Studio - install and load a model
   - **Cloud (API key required)**: OpenAI, Anthropic, Google, Mistral, Groq, or OpenRouter - add API key in Settings
   - See [Provider Setup Guide](docs/provider_guide.md) for detailed instructions and API key locations

3. **Index Your Library**: Make sure your Zotero client is closed. Then click "Index Library" in the Library tab to process your PDFs. This creates embeddings for semantic search. Initial indexing may take a while depending on library size.

4. **Optional - Choose Embedding Model**: In Settings, select from BGE-base (default, best quality), SPECTER (scientific papers), MiniLM-L6 (balanced), or MiniLM-L3 (fastest). Different models create separate indexes.

**Note:** PDFs must contain selectable text. Scanned documents without OCR cannot be indexed.

### Using the App

The interface has three main tabs:

- **Chat**: Type questions in natural language and view conversation history
- **Sources**: Shows the bibliography for each response.
- **Evidence**: Shows the retrieved text chunks used in the response.

Click any document title in the Sources or Evidence panel to open it in Zotero or your PDF reader.

## Technical Details

How the retrieval pipeline, metadata filtering, multi-provider support, and privacy model work under the hood is documented in [docs/TECHNICAL_DETAILS.md](docs/TECHNICAL_DETAILS.md).

## Building Installers

To create distribution packages:

```bash
npm run package:mac      # macOS .dmg and .zip
npm run package:win      # Windows .exe installer
npm run package:linux    # Linux .AppImage and .deb
npm run package:all      # All platforms
```

Built packages appear in the `release/` directory.

For complete build instructions, see [docs/BUILD_CHECKLIST.md](docs/BUILD_CHECKLIST.md).

## Documentation

**[Full documentation, FAQ, and troubleshooting →](https://quietsignalslab.com/rag-assistant/)**

** [Complete Documentation Index](docs/README.md)**

**Quick Links:**
- **Users:** [Prompting Guide](docs/PROMPTING.md) · [Provider Setup](docs/provider_guide.md)
- **Developers:** [Build Checklist](docs/BUILD_CHECKLIST.md) · [Desktop App Guide](docs/DESKTOP_APP.md)
- **Platform-Specific:** [Windows Build](docs/WINDOWS_BUILD_GUIDE.md) · [Linux Packaging](docs/LINUX_PACKAGING.md)

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).

This project was licensed under Apache 2.0 through v0.5.1; releases from v0.5.2 onward are GPLv3.

## Contributing

Contributions are welcome. Please open an issue to discuss significant changes before submitting a pull request.
