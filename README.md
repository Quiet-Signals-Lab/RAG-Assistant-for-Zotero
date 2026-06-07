
# RAG Assistant for Zotero

An open‑source desktop RAG application that enables semantic search across your Zotero library. Easily discover conceptually related papers and ideas within your PDF collection using local or cloud‑based LLMs. The app provides source attribution, metadata filtering, and seamless integration with Zotero. macOS and Linux are fully supported. Windows support is limited.

## What It Does

This tool indexes the PDFs in your Zotero library and uses retrieval-augmented generation (RAG) to answer questions based on their content. Every answer includes citations to the specific sources and page numbers used, making it easy to verify claims and follow up on interesting findings.

The application can run entirely on your local machine. Your documents and queries stay private if you use local models.

## Key Features

- **Hybrid search**: Combines semantic embeddings and BM25 keyword search with cross-encoder reranking for high-precision retrieval
- **Metadata filtering**: Filter by year, tags, collections, authors, or item types through natural language queries or manual controls
- **Cited answers**: Responses include references to specific documents and page numbers from your library
- **Conversational follow-ups**: Ask follow-up questions that reference previous context without repeating information
- **Source transparency**: View the exact text passages used to generate each answer
- **Multiple LLM providers**: Use local models via Ollama or LM Studio, or connect to OpenAI, Anthropic, Google, Mistral, Groq, or OpenRouter
- **Profile support**: Maintain separate workspaces with different settings, libraries, and chat histories
- **Automatic updates**: Stay up to date with the latest features and improvements
- **Cross-platform**: Available for macOS, Windows, and Linux

<img width="1440" height="871" alt="Screenshot 2026-02-21 at 6 24 03 pm" src="https://github.com/user-attachments/assets/a3ef72b4-dd75-4bd9-b50d-ede5ac65cbdc" />


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

Choose either Ollama or LM Studio to run models locally on your machine:

**Ollama**:
```bash
# macOS/Linux - Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Download a model
ollama pull llama3.2       # Lightweight, fast (1B or 3B)
ollama pull llama3.1:8b    # Good balance of speed and quality
```

**LM Studio**: Download from [lmstudio.ai](https://lmstudio.ai), load a model, and start the local server (default port: 1234).

**Note:** The app uses SentenceTransformers for embeddings (downloaded automatically on first use), not Ollama/LM Studio embedding models.

#### Option B: Cloud Providers (API key required)

Configure API keys in Settings for: **OpenAI**, **Anthropic**, **Google**, **Mistral**, **Groq**, or **OpenRouter**. See [Provider Setup Guide](docs/provider_guide.md) for where to get API keys.


## Installation

### Desktop App (Recommended)

Download the latest installer from [Releases](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases):

#### macOS

**Via Homebrew (recommended):**
```bash
brew tap Quiet-Signals-Lab/rag-assistant-for-zotero
brew install --cask rag-assistant-for-zotero
```
> Note: Since the app isn't notarized, macOS will block it on first launch. Run this command after installing: `xattr -dr com.apple.quarantine "/Applications/RAG Assistant.app"`

**Manual install:**
1. Download `RAG-Assistant-{version}-mac-arm64.dmg` (Apple Silicon) or `-mac-x64.dmg` (Intel)
2. Open the DMG file
3. Drag the app icon to the Applications folder
4. Since the app isn't signed by Apple, you will need to run this command in your Terminal first: `xattr -dr com.apple.quarantine "/Applications/RAG Assistant.app"`
5. Launch from Applications or Spotlight

**System Requirements:**

- macOS 11.0 (Big Sur) or later
- **Apple Silicon (M1/M2/M3) recommended** - Intel Mac builds may have limited support due to PyTorch compatibility

#### Windows

**Via winget (recommended):**
```powershell
winget install aahepburn.RAGAssistantForZotero
```

**Manual install:**
1. Download `RAG-Assistant-{version}-win-x64.exe`
2. Run the installer (may show SmartScreen warning on first run - click "More info" then "Run anyway")
3. Choose installation location (default: `C:\Users\{username}\AppData\Local\Programs\`)
4. Launch from Start Menu or desktop shortcut

**System Requirements:** Windows 10 or later (64-bit)

**Note:** Windows builds are now available but may show SmartScreen warnings since the app is not code-signed. See [docs/WINDOWS_BUILD_GUIDE.md](docs/WINDOWS_BUILD_GUIDE.md) for build instructions and troubleshooting.

#### Linux

First, make sure you have the necessary Python packages installed.

```bash
sudo apt install python3 python3-pip python3-venv
```

Download the `.deb` package from [Releases](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases) and install.

Or, run the following commands from the terminal:

```bash
# Download the latest .deb package (amd64)
wget https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/latest/download/RAG-Assistant-{version}-linux-amd64.deb

# Install (automatically handles dependencies)
sudo apt install ./RAG-Assistant-{version}-linux-amd64.deb

# Launch from application menu or terminal
rag-assistant
```

**System Requirements:** Debian/Ubuntu-based distributions (Ubuntu 18.04+, Debian 10+, or equivalent)

**Note:** The installer includes Python and all dependencies. No additional setup required. For other distributions, see [docs/LINUX_PACKAGING.md](docs/LINUX_PACKAGING.md).

### Run from Source (Developers)

For development or customization:

**Prerequisites:**
- Python 3.8+
- Node.js 16+
- Zotero with local library

**Setup:**
```bash
git clone https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero.git
cd RAG-Assistant-for-Zotero

# Python environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Node dependencies
npm install
cd frontend && npm install && cd ..

# Run development mode (all services)
npm run dev
```

**Note for Intel Mac Users:** As of v0.3.1, the required PyTorch version (2.6.0+) for security fixes does not provide pre-built wheels for Intel Macs (x86_64). Intel Mac users can still run the app by manually installing an older PyTorch version at their own risk:
```bash
pip install torch==2.2.2  # Last version with Intel Mac support
pip install -r requirements.txt
```
⚠️ PyTorch 2.2.2 has a known security vulnerability (CVE-2025-32434) in `torch.load()`. The app mitigates this by using safetensors format for model loading, but users should be aware of the risk.

See [docs/DESKTOP_APP.md](docs/DESKTOP_APP.md) for detailed development instructions.

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

3. **Index Your Library**: Click "Index Library" in the Library tab to process your PDFs. This creates embeddings for semantic search. Initial indexing may take a while depending on library size.

4. **Optional - Choose Embedding Model**: In Settings, select from BGE-base (default, best quality), SPECTER (scientific papers), MiniLM-L6 (balanced), or MiniLM-L3 (fastest). Different models create separate indexes.

**Note:** PDFs must contain selectable text. Scanned documents without OCR cannot be indexed.

### Using the App

The interface has three main tabs:

- **Chat**: Type questions in natural language and view conversation history
- **Library**: Index your PDFs and sync metadata from Zotero
- **Prompts**: Use academic scaffolding templates and filter results by metadata (year, tags, collections)

**Key features:**

- View citations and source passages in the Evidence Panel
- Click document titles to open in Zotero or your PDF reader
- Filter retrieved documents by publication date, tags, collections, authors, or item types
- Switch between providers and models anytime in Settings
- Create multiple profiles for different research projects (see [Profile Guide](docs/profile_system_guide.md))

## Technical Details

### System Architecture

The application implements a multi-stage retrieval pipeline designed for academic research workflows. The backend uses FastAPI with ChromaDB for vector storage, while the frontend is built with React and TypeScript. The desktop application uses Electron with auto-update capabilities.

### Retrieval Pipeline

**Query Processing.** For multi-turn conversations, the system rewrites follow-up questions into standalone queries before retrieval. This ensures that questions containing pronouns or contextual references can be properly matched against the document corpus without relying on conversation history.

**Hybrid Search.** The system combines dense vector search (using sentence transformer embeddings) with sparse BM25 keyword search. Both result sets are merged using Reciprocal Rank Fusion, which scores each document based on its rankings from both retrieval methods. This approach captures both semantic similarity and exact keyword matches, improving recall for queries that contain specific terminology or proper nouns.

**Cross-Encoder Reranking.** After initial retrieval, candidates are reranked using a cross-encoder model that processes the query and each document together. This provides more accurate relevance scoring than the initial bi-encoder embeddings, which encode queries and documents independently.

**Diversity Controls.** The final selection enforces per-document limits to prevent a single highly-relevant paper from dominating the context window. The system uses two modes: focused queries (with active filters or results concentrated in few papers) allow up to 8 snippets per paper with 10 total snippets, while broad queries cap at 3 snippets per paper with 6 total snippets.

### Metadata Filtering

The system supports two-tier metadata filtering. The first tier uses an LLM to extract structured filters from natural language queries, automatically detecting constraints on year ranges, tags, collections, item types, authors, and titles. If auto-extracted filters return no results, the system retries without filters to avoid over-restriction from misinterpretation. The second tier allows manual filter specification through the user interface.

Filter processing uses a hybrid approach due to ChromaDB's operator limitations. Numeric and equality filters run during vector search, while substring operators for tags, collections, authors, and titles are applied client-side after retrieval.

### Conversation Management

The system maintains stateful conversation sessions with distinct handling for initial and follow-up turns. The first message in a session embeds retrieved evidence directly in the user message, while subsequent messages contain only the question itself, relying on conversation history for context. This prevents redundant context accumulation and manages token budgets more efficiently. Session messages are trimmed based on the active provider's context window, keeping the most recent exchanges while ensuring the conversation fits within model limits.

### Multi-Provider Support

The application integrates with eight LLM providers through a unified interface: Ollama and LM Studio for local inference, and OpenAI, Anthropic, Google, Mistral, Groq, and OpenRouter for cloud-based models. Cloud providers with dynamic model catalogs automatically discover available models during credential validation. Provider-specific error handling distinguishes between rate limits, authentication failures, and context length errors, providing targeted user feedback for each case.

### Embedding Models

Multiple embedding models are supported, each creating a separate ChromaDB collection to avoid dimension mismatch errors. Available models include BGE-base (768 dimensions, general-purpose), SPECTER (768 dimensions, optimized for scientific documents), MiniLM-L6 (384 dimensions, balanced speed and quality), and MiniLM-L3 (384 dimensions, fastest). The default model is BGE-base. Users can switch between models without re-indexing if the corresponding collection already exists.

### Document Processing

PDFs are extracted with page-level granularity, preserving page numbers throughout the chunking process. Text is split into approximately 800-character chunks with 200-character overlap, using sentence boundaries to avoid mid-sentence cuts. Each chunk stores metadata including item ID, title, authors, year, tags, collections, item type, PDF path, and page number, enabling both filtering and citation generation.

### Implementation Notes

The system implements provider-aware dynamic retrieval limits that automatically scale based on the active model's context window. Models with larger contexts retrieve more evidence: Gemini 1.5 Pro (2M tokens) retrieves 30-50 snippets, Claude Opus (200k tokens) retrieves 24-40 snippets, while local models without known context limits use conservative defaults (6-10 snippets). The scaling uses five tiers (1.0x, 2.0x, 3.0x, 4.0x, 5.0x) and preserves the broad/focused mode distinction for diversity control.

**Privacy:**
All processing happens locally. If you use a cloud LLM provider (OpenAI, Anthropic, etc.), your queries and retrieved document chunks are sent to their API, but your full library never leaves your machine.

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

** [Complete Documentation Index](docs/README.md)**

**Quick Links:**
- **Users:** [Prompting Guide](docs/PROMPTING_QUICKSTART.md) · [Provider Setup](docs/provider_guide.md)
- **Developers:** [Build Checklist](docs/BUILD_CHECKLIST.md) · [Desktop App Guide](docs/DESKTOP_APP.md)
- **Platform-Specific:** [Windows Build](docs/WINDOWS_BUILD_GUIDE.md) · [Linux Packaging](docs/LINUX_PACKAGING.md)

## License

Apache 2.0

## Contributing

Contributions are welcome. Please open an issue to discuss significant changes before submitting a pull request.
