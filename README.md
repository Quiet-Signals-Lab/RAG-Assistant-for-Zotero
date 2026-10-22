
# RAG Assistant for Zotero

[![Latest version](https://img.shields.io/github/v/release/Quiet-Signals-Lab/RAG-Assistant-for-Zotero?label=version)](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/latest)
[![Downloads](https://img.shields.io/badge/downloads-2%2C000%2B-blue)](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases)
[![License: GPL-3.0](https://img.shields.io/github/license/Quiet-Signals-Lab/RAG-Assistant-for-Zotero)](LICENSE)

<a href="https://buymeacoffee.com/aahepburn"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="40"></a>

A reference desk for your Zotero library using semantic search of the contents of your entire PDF collection. Ask for a topic, a title, or an author and year, and the desk returns a ranked bibliography of the items in your library that bear on it, with the passages that matched, open at the page.

<img width="1398" height="813" alt="Screenshot 2026-10-13 at 7 47 24 PM" src="https://github.com/user-attachments/assets/ab2ec234-2b0d-458b-9f8e-858e077c2ffc" />


## What It Does

The app indexes the full text of the PDFs in your Zotero library and searches it by meaning and by keyword. The desk has three panes:

- **Ask**: the query desk. What you type is read for its limits (years, authors, tags, collections, kinds of item, exclusions), shown as chips you can remove. Your searches collect in a query log so you can retrace the trail.
- **Browse**: the bibliography. Items ranked by their best passage, each with a full reference, the sentence that matched and its page. Relevance is shown as strong, good, weak or see also, never as a percentage.
- **Verify**: the evidence. Every passage that matched the selected item, with your terms marked, one click from the PDF at that page in Zotero.

The design borrows from library science rather than from chat: Cutter's catalogue objectives (find the item you name, show what the library has on a subject), Ranganathan's laws, Taylor's reference interview and Bates' berrypicking. It does the catalogue's job, not the librarian's: it points you to sources and leaves the reading and the judging to you.

**Language models are optional.** The desk ranks, quotes and cites with no model at all. If you set one up, a local model on your computer or a cloud provider, the *desk clerk* uses it for small, checked jobs: reading harder queries, a one-line note on each item that must be supported by its passages, next searches drawn from your own tags, and names for groups of results. Anything that fails a check falls back to the desk's own work.

**Want an answer written?** The chat is one click away (the Search | Chat switch in the header, or Settings → General → Interface): a model answers from passages in your library, citing each by number. From search, "Chat about these" opens a chat on the items you found.

The application can run entirely on your computer. With no model or a local one, your documents and queries never leave it.

## Quick Installation

The app is available on **macOS** (Apple Silicon, macOS 13 or later), **Windows**, and **Linux**. You can always download the latest installer from [Releases](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases).

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


## Key Features

- **A ranked bibliography, not an answer**: hybrid semantic and keyword search with cross-encoder reranking, ranked by item, with the matching sentence and page under every reference
- **Evidence at the page**: matched passages with your terms marked; open the PDF in Zotero's reader at that page, or show the item in Zotero
- **Queries read for their limits**: "courier strikes since 2015, not about Deliveroo" or "Berlant's books on affect" set years, authors, tags, collections, item types and exclusions from your library's own names, as chips you can remove
- **Known items**: a DOI, ISBN, arXiv id, quoted title, or author and year pins that item above the list, with "search inside this"
- **Group and narrow**: group the list by decade, kind of item, collection, first author, journal, or theme; narrow to the busiest decade or collection; set the top results aside to see what else there is; "more like this" from any item
- **References and citations**: what an item cites and what cites it, from Semantic Scholar, with the works already in your library marked (only the item's DOI or title is sent, and only when you ask)
- **Export**: copy APA references, or save the list as BibTeX, RIS, or a pathfinder (a Markdown subject guide with extracts and your pinned passages)
- **Pins and query log**: keep passages across searches, per profile
- **A language model (optional)**: reads limits out of your query, suggests next searches and names theme groups; measured on small local models. What it read from your query is shown under the search box
- **Privacy controls**: run fully offline, or exclude Zotero collections and tags from the index so they are never searched or sent anywhere
- **Model providers**: local models via Ollama or LM Studio, or OpenAI, Anthropic, Google, Mistral, Groq or OpenRouter
- **Profiles, automatic updates, macOS, Windows and Linux**

### What the reference desk will never do

- Answer your question for you, or write a summary across papers.
- Send your PDFs anywhere. If you allow the desk clerk to use a cloud model, your query and the passages a job needs go to that provider; with a local model or none, nothing leaves your computer.
- Write to your Zotero database. It is only ever read.
- Require an account or an API key.

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

### 2. Language Model (optional)

The reference desk works without one. A model adds query readings, next searches and theme names, and is needed for chat. For the clerk, a small local model is enough: Qwen3-4B-Instruct-2507 is the model the desk was measured with ([results](docs/DESK_CLERK.md#measurement)).

#### Option A: Local Models (No API key needed)

Choose either LM Studio or Ollama to run models locally on your machine:

**LM Studio**: Download from [lmstudio.ai](https://lmstudio.ai), load a model, and start the local server (default port: 1234).

**Ollama**:
```bash
# macOS/Linux - Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Download a model, for example Qwen3 4B (instruct):
ollama pull qwen3:4b-instruct
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

2. **Index Your Library**: Make sure your Zotero client is closed. Then open the library from the desk's rail and click "Index Library" to process your PDFs. This creates embeddings for semantic search. Initial indexing may take a while depending on library size.

3. **Optional - Choose a Model**: for the language model jobs or chat.
   - **Local (No API key)**: Ollama or LM Studio - install and load a model
   - **Cloud (API key required)**: OpenAI, Anthropic, Google, Mistral, Groq, or OpenRouter - add API key in Settings
   - See [Provider Setup Guide](docs/provider_guide.md) for detailed instructions and API key locations

4. **Optional - Choose Embedding Model**: In Settings, select from BGE-base (default, best quality), SPECTER (scientific papers), MiniLM-L6 (balanced), or MiniLM-L3 (fastest). Different models create separate indexes.

**Note:** PDFs must contain selectable text. Scanned documents without OCR cannot be indexed.

### Using the App

Type what you are looking for in the query desk and press Enter. Choose an entry in the bibliography to see its passages in the evidence pane; press `p` to pin a passage, `o` to open the PDF, `/` to return to the query. On a narrow window the panes become Ask, Browse and Verify.

The rail on the left switches between the desk, the library (indexing and exclusions), the desk clerk (model and jobs) and About.

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
- **Users:** [Provider Setup](docs/provider_guide.md) · [How the chat prompts a model](docs/PROMPTING.md)
- **Design:** [The reference desk](docs/REFERENCE_DESK_PLAN.md) · [The desk clerk: small models](docs/DESK_CLERK.md) · [Roadmap](docs/REFDESK_ROADMAP.md)
- **Developers:** [Build Checklist](docs/BUILD_CHECKLIST.md) · [Desktop App Guide](docs/DESKTOP_APP.md)
- **Platform-Specific:** [Windows Build](docs/WINDOWS_BUILD_GUIDE.md) · [Linux Packaging](docs/LINUX_PACKAGING.md)

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).

References are formatted by [citeproc-js](https://github.com/Juris-M/citeproc-js) (CPAL 1.0 / AGPL) with styles from the [Citation Style Language project](https://citationstyles.org/) (`frontend/src/assets/csl`, CC BY-SA 3.0): APA 7th, Chicago 18th, and the en-US locale. Styles installed in your Zotero are read from its styles folder.

This project was licensed under Apache 2.0 through v0.5.1; releases from v0.5.2 onward are GPLv3.

## Contributing

Contributions are welcome. Please open an issue to discuss significant changes before submitting a pull request.
