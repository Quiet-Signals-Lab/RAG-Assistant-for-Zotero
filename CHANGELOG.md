# Changelog

All notable changes to RAG Assistant for Zotero will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.8] - 2026-06-08

### Added
- **Configurable evidence snippet limit (discussion [#43](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/discussions/43))**: A new **Advanced** tab in Settings exposes an "Evidence snippets per query" selector. Choose from Auto (default — scaled to the active model's context window, same as before), 4, 6, 8, 10, 12, 16, 20, or 30 snippets. Setting a fixed value overrides the automatic tier-based limit while proportionally adjusting the underlying fetch and rerank parameters so the pipeline can actually reach the target. Particularly useful for local/Ollama users, where the automatic default is 6 (conservative for unknown context windows) but the model may comfortably handle more. The setting is persisted per profile. Setting a high value on a small-context model (< 16k tokens) may cause context overflow — this is documented in the UI hint.
- **Multilingual embedding model support (issue #37)**: Three new local embedding models are now available in the Library → Embedding Model selector:
  - `BAAI/bge-m3` (1024 dim, ~2.3 GB) — BGE multilingual supporting 100+ languages including Chinese, Japanese, and Korean. Natural upgrade path from the default `bge-base` (same BGE family).
  - `BAAI/bge-large-zh-v1.5` (1024 dim, ~1.3 GB) — Chinese-optimised BGE model for users with primarily Chinese-language Zotero libraries.
  - `paraphrase-multilingual-MiniLM-L12-v2` (384 dim, ~470 MB) — Lightweight multilingual option supporting 50+ languages.
  - All three models download automatically via sentence-transformers on first use. No additional Python dependencies are required.
  - **Known limitation:** The cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) is English-only and is not replaced in this release. Reranking quality on non-English text will be reduced; dense retrieval quality is unaffected.

### Fixed
- **BM25 tokenization broken for CJK text (issue #37)**: The BM25 sparse retrieval index used `text.lower().split()`, which produces whole sentences as single tokens for Chinese, Japanese, and Korean text (these scripts have no word-boundary whitespace). BM25 scores were effectively zero for all CJK queries. A `_tokenize_for_bm25()` helper now uses a compiled Unicode regex to insert spaces around every CJK character before splitting, producing character-level tokens. This is the standard approach for CJK bag-of-words retrieval and requires no additional dependency. Applied consistently to both index building (`build_bm25_index`) and query time (`query_bm25`). Existing BM25 index files will be rebuilt automatically on the next "Sync Library" run.
- **Follow-up answers regress to a new question (issue #35)**: On turn 2+, fresh retrieval evidence was silently discarded, leaving the model with no context but a system prompt that says "use only provided context". GPT-4o would respond by generating a new question instead of an answer. Evidence is now injected into every follow-up turn via `AcademicPrompts.build_hybrid_user_message`, framing it as supplementary evidence for a follow-up exchange.
- **Context history evicts first-turn evidence anchor (issue #37 / trim bug)**: `trim_messages_for_context` previously used a reverse-only iteration that could silently drop the first user+assistant exchange — the turn that carries the bulk of library evidence. Replaced with a pinned-anchor + sliding-tail algorithm: the first exchange is always retained; only middle messages are evicted when the context budget is exceeded.
- **Dynamic context budget replaces hardcoded `max_chars=12000`**: `ZoteroChatbot` now computes the character budget from the active model's declared context window (60 % of window × 4 chars/token, capped at 400 000 chars). Falls back to 24 000 chars when the model context length cannot be determined. Eliminates context overflow on small models and underutilisation on large ones.
- **Query condenser false positives on comparative questions**: `should_condense` was triggering on any short query that contained comparison keywords (`compare`, `overlap`, `versus` …). A user asking "How does Piaget compare to Vygotsky?" on turn 2+ would have their query condensed into something about the prior conversation topic. Removed the `(has_comparison AND is_short)` trigger — comparative language alone is not a dependency signal.
- **Query condenser false negatives from trailing punctuation**: Queries like "Can you elaborate on that?" never triggered anaphora detection because the word-boundary check `q.endswith(" that")` failed on `"that?"`. Query is now stripped of trailing punctuation before all word-boundary tests.
- **Query condenser condensing before any assistant response exists**: `should_condense` previously fired after only one user turn with no prior assistant reply. Guard strengthened to require at least one completed exchange (user AND assistant) before condensation is attempted.
- **Query condenser hallucination guard**: After condensation, if the content-word overlap between the original query and the condensed version is below 15 %, the condenser falls back to the original. Prevents a rare LLM hallucination from producing an off-topic retrieval query.

### Removed
- **Database Migration UI removed from Library tab**: The "Database Migration" section (version check, migrate button, status indicators) has been removed from the Library management panel. All existing libraries are already on the current metadata format; the one-time migration path is no longer needed. `MigrationProvider`, `MigrationContext`, and the migration banner have been unwired from the app shell.

### Security
- **Dependency updates** (Dependabot PRs [#29](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/pull/29)–[#36](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/pull/36), [#40](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/pull/40), [#44](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/pull/44)–[#46](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/pull/46)):
  - `starlette` 0.49.3 → 1.0.1 — fixes malformed `Host` header vulnerability; required bumping `fastapi` to 0.134.0 to support starlette 1.x
  - `fastapi` 0.121.2 → 0.134.0 — required to allow starlette ≥ 1.0
  - `axios` 1.13.2 → 1.17.0 (Electron/root)
  - `react-router` / `react-router-dom` 7.9.6 → 7.17.0 (frontend)
  - `idna` 3.11 → 3.15
  - `pillow` 12.0.0 → 12.2.0
  - `Pygments` 2.19.2 → 2.20.0
  - `python-dotenv` 1.2.1 → 1.2.2
  - `requests` 2.32.5 → 2.33.0
  - `urllib3` 2.3.0 → 2.7.0
  - Frontend dev deps (`vite`, `rollup`) patched via `npm audit fix`

## [0.4.7] - 2026-05-06

### Added
- **Source card action buttons**: Replaced icon-only buttons in the Sources panel with labelled text buttons for clarity
  - Full service names displayed: "Open PDF", "Google Scholar", "Google Books", "Semantic Scholar"
  - Google Scholar, Google Books, and Semantic Scholar buttons now display site favicons fetched via Google's favicon proxy service
  - Uses the system UI font (`system-ui, sans-serif`) at 11 px for a clean, neutral appearance
  - Favicon images hide gracefully on load failure
- **Cloud Embedding Models**: Support for OpenAI Embeddings API as an embedding backend (resolves [#27](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues/27) Feature 1)
  - New `backend/embedding_providers/` package with abstract base class and OpenAI implementation
  - Automatic batching (up to 2 048 texts per API call) with exponential-backoff retry on rate-limit errors
  - Available models: `openai:text-embedding-3-small` (1 536 dims) and `openai:text-embedding-3-large` (3 072 dims)
  - Cloud model IDs are sanitised (`:` → `-`) before use as ChromaDB collection-name suffixes
  - Privacy warning modal shown in the UI before switching to a cloud embedding model
  - OpenAI API key is passed through from provider settings at chatbot initialisation

### Fixed
- **Chat window top border**: Removed a persistent empty `<div>` wrapper in `ChatView` that created a visible strip at the top of the chat panel; the error banner container now only renders when there is an active error
- **Metadata filter extraction without a provider**: `MetadataExtractor` now extracts explicit metadata patterns (year ranges, `after YYYY`, `before YYYY`, `tagged "…"`, `in "…"`) via a regex pre-pass that runs regardless of whether an LLM provider is configured
- **Metadata migration — lazy item fetch**: `MetadataMigration._migrate_batch` now fetches Zotero item metadata on demand per unique item instead of requiring a bulk pre-fetch; avoids a crash when item objects do not support dict-style subscript access
- **Google provider — invalid API key not detected**: `InvalidArgument` exceptions thrown by `genai.list_models()` (indicating a bad API key) are no longer swallowed by the dynamic-discovery fallback; they propagate to the outer handler so `validate_credentials_and_list_models` correctly returns `valid: False`
- **LM Studio / Single-Provider — No Models Shown**: Fixed issue where users with only one provider configured (e.g. LM Studio) would see an empty model list that never populated unless a second provider was also enabled
  - Empty model lists were cached permanently; the app now retries fetching models whenever settings change
  - Switching providers now always fetches a fresh model list instead of reusing a potentially stale empty cache
  - Added a ↻ refresh button next to the Model label for manual on-demand reload
  - Fixes [#28](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues/28)
- **OpenRouter / Cloud Provider — No Models Shown**: Fixed issue where users who enabled OpenRouter (or any cloud provider) while Ollama was the default active provider would see an empty model list and receive a `ProviderConnectionError` pointing at Ollama even after disabling it
  - Backend now auto-switches `activeProviderId` to the first enabled provider when the stored active provider is disabled, both on startup and when settings are saved
  - Frontend (`ActiveModelPanel`) now auto-switches the provider dropdown to the first configured provider when the current selection is disabled or has no credentials
  - Fixes [#26](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues/26)
- **OpenRouter `list_models` empty result**: `list_models` now filters out entries with no model ID and falls through to the hardcoded fallback list when the API returns nothing useful

## [0.4.6] - 2026-04-24

### Added
- **GitHub Models Provider**: Users with a GitHub Copilot subscription can now connect via a dedicated "GitHub Models" provider (contributed by [@ComePerin](https://github.com/ComePerin))
  - Hardcodes the GitHub Models base URL — no manual endpoint configuration needed
  - Labels the credential field "GitHub Token" for clarity

### Fixed
- **ZotMoov / Linked-File PDF Paths**: Correctly resolves PDF paths for attachments stored outside the default Zotero storage directory (e.g. via ZotMoov)
  - `storage:` paths use existing stored-file logic (unchanged)
  - Absolute paths are used as-is
  - `attachments:` paths are joined with the configured storage directory
  - Fixes [#17](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/discussions/17)
- **SourcesPanel API fetch**: Fixed missing `apiFetch` import that caused the Sources panel to fail to load
- **OpenAI-Compatible Model Listing**: Added raw HTTP fallback when the OpenAI SDK cannot parse non-standard model list responses (e.g. plain arrays instead of `{"data":[...]}`)
  - Also normalises Azure ML resource-path model IDs to simple names (e.g. `azureml://…/gpt-4o/versions/2` → `gpt-4o`)

### Documentation
- Revised README with improved project description, privacy note for local model usage, and Homebrew / winget installation instructions
- Corrected Ollama installation formatting in README

## [0.4.5] - 2026-03-22

### Added
- **Custom Endpoint Support**: OpenAI-compatible providers (OpenAI, Mistral, Groq, OpenRouter) now support optional custom endpoint configuration
  - Enables Azure OpenAI, proxy servers, and custom deployments
  - Backward compatible: defaults to standard endpoints when not configured
- **Startup Progress Indicator**: Application now displays a splash screen immediately on launch with progress updates
  - Shows real-time progress during first-run AI model downloads
  - Prevents users from launching multiple instances due to apparent unresponsiveness
- **Custom PDF Storage Directory**: New optional setting to specify a custom Zotero PDF storage folder
  - Useful when PDFs are stored on a separate drive or non-default location
  - Leave blank to use the default location next to the database file
- **Semantic Scholar Search**: Added Semantic Scholar search button alongside existing Google Scholar button in the Sources panel
- **Package Manager Distribution**: Added documentation for Homebrew tap (macOS) and winget (Windows) distribution

### Changed
- **Save & Test Button**: API key testing now automatically saves settings first, eliminating "test failed because you didn't save" confusion
- **Update Notice UX**: Manual update notification now displays in reassuring green with clear messaging that profiles, embeddings, and settings persist across updates
- **Windows Startup Wait**: Increased initial process-alive check delay to 3s on Windows (vs 1.5s elsewhere) to accommodate PyInstaller self-extraction time
- **Ollama Status Indicator**: Removed the Ollama status indicator from the top navigation bar for a cleaner interface

### Fixed
- **Syncing Stuck at 0%**: Improved error detection and messaging when Zotero database is locked
  - Now shows specific message: "Database is locked — please close Zotero completely before syncing"
  - Network/process failures during sync now display a visible error message instead of silently disappearing
- **Custom Model List (OpenAI)**: Fixed bug where all curated GPT models were returned regardless of what the API actually provides
  - Model list now accurately reflects only models available on your account
  - Changing API key or base URL now clears the cached model list, triggering a fresh fetch
- **License Inclusion**: macOS DMG now includes correct Apache 2.0 license file (was incorrectly showing MIT)
- **DMG Installation Files**: Fixed macOS DMG to include Applications folder link, Installation Instructions, and LICENSE file
- **Sound Notifications**: Fixed TypeScript errors preventing sound notification settings from saving properly
- **Windows Port Cleanup**: Port cleanup on startup now verifies process name before killing, preventing accidental termination of unrelated applications on ports 8000–8010

### Removed
- **Intel Mac Builds**: Removed x64 (Intel) macOS builds - now only building for Apple Silicon (arm64)
  - Intel Macs can still run the app via Rosetta 2
- **Windows 32-bit (ia32) Builds**: Removed ia32 build targets — only x64 is supported, consistent with the 64-bit PyInstaller backend

## [0.4.3] - 2026-02-22

### Changed

- **Trademark Compliance Rebrand**: Renamed application to comply with Zotero trademark requirements
  - Display name: "RAG Assistant for Zotero"
  - Product name: "RAG Assistant"
  - Executable: `rag-assistant` (was `zotero-rag-assistant`)
  - Package name: `rag-assistant` (was `zotero-rag-assistant`)
  - Repository: `RAG-Assistant-for-Zotero` (was `Zotero-RAG-Assistant`)
  - Installer naming: `RAG-Assistant-{version}-{platform}-{arch}.{ext}`
  - **⚠️ IMPORTANT**: Existing users need to rename their app data folder (see migration instructions in release notes)

### Technical

- Updated all installer filenames across macOS, Windows, and Linux
- Updated 50+ documentation files with new naming conventions
- Updated GitHub URLs in Settings panel and documentation
- Regenerated package-lock.json to reflect package name change

## [0.4.2] - 2026-02-20

### Added

- **Provider-Aware Dynamic Retrieval Limits**: Retrieval caps now scale automatically based on active model's context window
  - Five scaling tiers: 1.0x (default/unknown), 2.0x (32k), 3.0x (100k), 4.0x (200k), 5.0x (1M+)
  - Maximizes utility of large-context models (Gemini 1.5 Pro, Claude Opus, GPT-4 Turbo)
  - Maintains conservative defaults for local models without known context limits (Ollama, LM Studio)
  - Preserves broad/focused mode distinction for diversity control
  - Example: Gemini 1.5 Pro (2M context) retrieves 30-50 snippets instead of 6-10
  - Example: Claude Opus (200k context) retrieves 24-40 snippets instead of 6-10
  - Backward compatible: Unknown context defaults to 1.0x multiplier (no change for Ollama)

### Changed

- Retrieval pipeline now queries provider for model context_length on first chat
- Updated Technical Details section in README to reflect dynamic scaling behavior

### Technical

- Added `get_active_model_context_length()` method to query provider capabilities
- Added `get_retrieval_limits(is_focused)` method with tiered scaling logic
- Comprehensive test suite with 13 tests covering all scaling tiers and edge cases

## [0.4.1] - 2026-02-20

### Fixed

- **Linux Remote Desktop Support**: Fixed renderer crashes when launching from desktop menu in Remote Desktop environments
  - Added `--disable-gpu-sandbox` flag to desktop launcher for GPU/sandbox compatibility
  - Increased backend startup timeout from 10s to 30s for slower Remote Desktop sessions
  - Improved backend process detachment using shell wrapper to avoid Chromium sandbox restrictions
  - Added automatic backend wrapper permission setup in post-install script
- **Linux Backend Startup**: Resolved backend process being killed immediately after spawn
  - Implemented detached launch mechanism with `setsid` and `nohup` in wrapper script
  - Added comprehensive backend health check with extended retry logic
  - Improved initialization flag to prevent premature app quit during startup

## [0.4.0] - 2026-02-17

### Added
- **Metadata Filtering System**: Filter retrieved chunks by publication date, tags, and collections
  - Date range filters (before/after specific years)
  - Multi-select tag and collection filters with "match any" or "match all" logic
  - Filters apply to retrieval pipeline before context is sent to LLM
- **Retrieval Fusion (RRF)**: Reciprocal Rank Fusion combines filtered semantic results with pure semantic results
  - Ensures relevant papers aren't completely excluded by overly strict filters
  - Configurable balance between filtered and unfiltered results
- **Multi-Tab Sidebar**: Reorganized interface into Chat, Library, and Prompts tabs
  - Chat tab: Conversation history with "Start New Session" button
  - Library tab: Indexing controls and metadata sync
  - Prompts tab: Academic prompt scaffolding and Scope panel
- **Scope Panel Integration**: Moved from modal to dedicated Prompts tab
  - Persistent UI for search mode and context length selection
  - Renamed "Original" mode to "Semantic only" with clearer descriptions
- **LM Studio Provider**: Official support for LM Studio local model server
  - Auto-discovery of available models via /v1/models endpoint
  - Optimized system prompts for local models
  - Configurable base URL (default: http://localhost:1234)
- **Dynamic Model Discovery**: Ollama and LM Studio automatically fetch available models
  - Real-time model list updates from provider APIs
  - Reduces configuration overhead for local model users
- **AI Reasoning Display**: View model's chain-of-thought reasoning for supported providers
  - Toggle button to show/hide reasoning panels
  - Formatted markdown rendering of reasoning steps
  - Works with OpenRouter, OpenAI o1/o3 models
- **Semantic Scholar Integration**: Automatic metadata enrichment during indexing
  - Fetches missing abstracts, publication years, and citation counts
  - Improves metadata quality for filtering and search
- **Metadata Sync Feature**: Update metadata without re-embedding
  - Syncs titles, authors, tags, collections, dates from Zotero database
  - Preserves existing embeddings and chunk data
  - Provides detailed sync statistics
- **OCR Documentation Note**: Explains why scanned PDFs without OCR cannot be indexed

### Changed
- **Settings Panel Redesign**: Reorganized into tabbed interface
  - General: API keys, base URLs, embedding model selection
  - Advanced: Temperature, context length, performance tuning
  - About: Version info, links, credits
- **ChromaDB Metadata Schema**: Upgraded to version 2
  - Tags and collections stored as pipe-separated strings
  - Year field now integer (0 for unknown dates)
  - Enables efficient metadata filtering queries
- **Metadata Migration Architecture**: Complete overhaul with pre-caching
  - Pre-loads all Zotero items at startup for O(1) lookups
  - Bidirectional sync: vector DB → Zotero and Zotero → vector DB
  - Graceful handling of missing items and orphaned embeddings
- **Linux Packaging**: Simplified to .deb files only (removed AppImage, tar.gz)
- **Application Icon**: Redesigned with Zotero brand colors
  - White background, red document stack, purple AI network
  - Matches Zotero's official color scheme

### Fixed
- **Metadata Sync Endpoint**: Fixed 500 error by adding logger initialization
- **ChromaDB Indexing**: Fixed None value rejection errors
  - Year defaults to 0, page numbers safely handled with get()
  - Prevents "failed to extract enum MetadataValue" errors
- **Profile System**: Verified isolation and persistence
  - Default profile at ~/.zotero-llm/profiles/default/ working correctly
  - Settings, sessions, vector DB properly isolated per profile
- **Linux Backend Stability**: Multiple fixes for path handling and binary compatibility
  - Improved error messages for missing Zotero database
  - Better handling of non-existent file paths
- **Sessions Context**: Fixed backend integration for chat history persistence
  - Debounced saves prevent race conditions
  - Sessions properly load on app startup

## [0.3.2] - 2026-01-30

### Changed
- **Provider Integration**: Replaced Perplexity provider with Mistral AI
  - Removed PerplexityProvider class and all Perplexity-specific code
  - Added MistralProvider with OpenAI-compatible API
  - Updated frontend, tests, and documentation
  - Available models: mistral-large-latest, mistral-medium-latest, mistral-small-latest, open-mistral-nemo, open-mixtral-8x7b
- **CI Build Process**: Updated macOS Intel builds to handle PyTorch compatibility
  - Intel Mac CI runners use torch==2.2.2 for building (last version with x64 wheels)
  - Bundled apps for Intel Macs continue to work correctly
  - Security risk isolated to CI build environment only

### Security
- **PyTorch Version**: Updated to `torch>=2.6.0` to address CVE-2025-32434
  - Fixes serious vulnerability in torch.load() function
  - **Breaking change for Intel Mac developers**: PyTorch 2.6+ does not provide x86_64 wheels
  - Intel Mac developers must manually install torch==2.2.2 (with known security risk)
  - **Intel Mac users (GUI)**: Unaffected - DMG builds continue to work normally
  - App uses safetensors format for model loading which mitigates the vulnerability
  - See README for Intel Mac development setup instructions

## [0.3.1] - 2026-01-30

### Changed
- **macOS Title Bar**: Implemented elegant frameless design with hiddenInset style
  - Removed app title text from title bar for cleaner appearance
  - Positioned traffic lights at optimal location (16×16 offset)
  - Added darker background color (#1a1a1a) for title bar area
  - Optimized navigation spacing with traffic lights (90px left padding)
  - Reduced titlebar height from 52px to 28px for minimal footprint
- **Settings Page**: Cleaned up visual appearance
  - Changed header to relative positioning (scrolls with content)
  - Removed sticky background and border for seamless look
  - Added proper spacing to avoid traffic lights overlap
- **DMG Installer**: Enhanced first-time installation experience on macOS
  - Added Installation Instructions file with prominent quarantine removal command
  - Included LICENSE.txt in DMG for transparency
  - Configured 4-item grid layout (app, Applications folder, README, LICENSE)
  - Set larger window size (600×500) with light background for better readability

### Fixed
- Drag region conflicts between title bar and interactive elements
- Navigation bar spacing issues with macOS traffic lights
- Settings header visual inconsistencies when scrolling

## [0.3.0] - 2026-01-30

### Added
- **Provider-Agnostic Architecture**: Implemented comprehensive refactoring for external API integrations
  - MessageAdapter class for format conversion (OpenAI, Anthropic, Gemini, Perplexity)
  - ParameterMapper for parameter translation across providers
  - ResponseValidator for detecting meta-responses and quality issues
- **Support & Feedback Section**: Added prominent section in Settings page with:
  - Direct link to GitHub Issues for bug reports
  - GitHub Sponsors button for project support
  - Instructions for reporting bugs (screenshots, error messages, console logs)
- **Platform Detection**: Added getPlatform() API for OS-specific features
- **Test Suite**: Created comprehensive test suite for provider adapters (13 tests passing)

### Changed
- **Manual Updates Only**: Disabled automatic downloads for all platforms to prevent installation errors
  - App still checks for updates automatically (startup + every 4 hours)
  - Users directed to GitHub Releases for manual downloads
  - Clear warning message with direct link when updates are available
- **Enhanced Logging**: Improved provider validation logging with structured warnings
- **Provider-Specific Prompts**: Added PROVIDER_OVERRIDES for Perplexity (anti-web-search) and Google (concise)
- **API Key Display**: Improved security with masked keys ("***") in Settings UI
- **Documentation**: Updated AUTO_UPDATES.md to reflect manual-only update flow

### Fixed
- **Critical Shutdown Race Conditions**:
  - Fixed before-quit race by removing app.exit(0), allowing natural quit flow
  - Made stopBackendSync actually wait for timeout before SIGKILL
  - Increased backend shutdown delay from 0.5s to 2.0s for reliable cleanup
  - Added port check retry with exponential backoff (500ms → 1s → 2s, max 6 attempts)
- **External API Integration**: Fixed issues with Google Gemini and Perplexity returning meta-responses
- **Provider Parameter Mapping**: Corrected temperature and parameter translation for all 7 providers
- **Test Failures**: Fixed parameter mapper tests and citation detection thresholds

### Technical
- Added pytest>=9.0.0 to requirements.txt
- Implemented isShuttingDown flag to prevent duplicate shutdown attempts
- Enhanced error handling for provider rate limits and context errors
- Improved process tree killing for Windows (taskkill /T) and Unix (negative PID)

## [0.2.5] - 2026-01-19

### Fixed
- Fixed architecture mismatch issue causing "error -86" spawn failures on Intel Macs
- Extended backend initialization timeout to 70 seconds (10 attempts × 1s + 20 attempts × 3s) across all platforms to prevent false-positive timeout errors
- Unified HTTP health check timeout to 3000ms for consistency
- Updated minimum macOS version to 11.0 in build configuration

### Changed
- **macOS Native Builds**: Now building separate native binaries for both architectures:
  - **x64 (Intel)**: Built on `macos-15-intel` runner - native performance on Intel Macs
  - **arm64 (Apple Silicon)**: Built on `macos-14` runner - native performance on M1/M2/M3/M4 Macs
- **Technical Implementation**: Uses GitHub Actions matrix strategy with architecture-specific runners
  - Each architecture builds natively (no cross-compilation)
  - PyInstaller produces optimized binaries for host architecture
  - Separate DMG/ZIP files for each architecture
- **Distribution**: Users download the appropriate installer for their Mac's architecture
- Added `minimumSystemVersion: 11.0` for macOS compatibility documentation

### Technical Note
Due to GitHub Actions retiring Intel Mac runners (macos-12, macos-13), we've switched to building only for Apple Silicon.
Intel Mac users will automatically run the app through Rosetta 2, which provides excellent compatibility and performance.
This is the standard approach for macOS apps as the industry transitions to Apple Silicon.

## [0.2.4] - 2026-01-06

### Changed
- Reverted Debian packaging metadata to v0.2.0 configuration to eliminate potential dpkg parsing issues
- Removed custom FPM fields from deb configuration
- Simplified maintainer and vendor metadata

### Fixed
- Updated Linux installation guidance in README to remove outdated version references and AppImage instructions

## [0.2.3] - 2026-01-06

### Fixed
- Fixed "address already in use" crash on startup when port 8000 is occupied
- Added automatic cleanup of orphaned backend processes before app startup
- Implemented dynamic port selection (8000-8010) if default port is unavailable
- Enhanced graceful shutdown with proper port release verification
- Added backend `/shutdown` endpoint for clean server termination
- Improved signal handling (SIGTERM, SIGINT) to ensure cleanup on force quit
- Backend now automatically retries with available ports if requested port is in use

## [0.2.2] - 2026-01-05

### Added
- Application icons for macOS, Windows, and Linux builds

### Fixed
- Fixed duplicate indexing operations during vector database updates
- Resolved indexing progress double-counting bug

## [0.2.1] - 2026-01-05

### Fixed
- Fixed incremental sync progress bar getting stuck at low counts
- Removed skip warnings from navbar during sync to prevent UI disruption
- Warnings still logged to backend console for diagnostics

## [0.2.0] - 2026-01-05

### Added

- **Profile-Specific Vector Databases** - Major improvement to profile isolation
  - Each profile now has its own isolated ChromaDB instance
  - Automatic profile-specific paths: `~/.zotero-llm/profiles/{profile-id}/chroma`
  - Switch between profiles without reindexing - each maintains separate embeddings
  - Support for different embedding models per profile without conflicts
  - No more shared `user-1` paths

- **Full Windows Support** - Native Windows builds and installers
  - PyInstaller build scripts for Windows (PowerShell and batch file)
  - NSIS installer with Desktop shortcut and Start Menu entry
  - Portable ZIP distribution option
  - Comprehensive Windows build documentation
  - Automated Windows builds via GitHub Actions

- **Improved GitHub Actions CI/CD**
  - Automated builds for macOS, Windows, and Linux on tag push
  - Parallel builds across all platforms
  - Automatic GitHub release creation with all artifacts
  - Build time ~15-25 minutes for all platforms

### Changed

- Vector database path now defaults to profile-specific location instead of hardcoded `user-1`
- `load_settings()` function now automatically uses profile-specific chroma path
- Settings UI displays correct profile-specific vector database path
- Removed global `CHROMA_PATH` constant dependency (now profile-managed)

### Fixed

- Vector database paths not respecting profile system
- Profiles sharing the same vector database causing data conflicts
- Inability to use different embedding models in different profiles
- Settings showing incorrect default chroma path

### Documentation

- Added comprehensive Windows build guide (`docs/WINDOWS_BUILD_GUIDE.md`)
- Added Windows quick reference (`docs/WINDOWS_BUILD_QUICKREF.md`)
- Added Windows support tracking document (`docs/WINDOWS_SUPPORT_TODO.md`)
- Added complete release plan for v0.2.0 (`docs/RELEASE_PLAN_v0.2.0.md`)
- Updated profile system documentation with vector database isolation details

### Migration Notes

- **Existing Users**: Old vector database at `~/.zotero-llm/chroma/user-1` will not be automatically migrated
- **To Keep Old Data**: Manually copy `~/.zotero-llm/chroma/user-1` to `~/.zotero-llm/profiles/default/chroma`
- **Fresh Start**: Just create a new profile and re-index your library

## [0.1.10] - 2025-12-31

### Fixed

- **Memory Leak** - Fixed orphaned backend processes on app quit
  - Process tree cleanup kills Python backend and ChromaDB child processes
  - Unix: Uses negative PID to kill entire process group
  - Windows: Uses `taskkill /T` for tree termination
  - Prevents memory accumulation from repeated app launches

### Changed

- **Linux Packaging** - Reverted to venv approach (from PyInstaller bundle)
  - PyInstaller bundle exceeded GitHub's 2GB file size limit (2.5GB DEB)
  - Linux now uses system Python + venv with auto-setup and repair logic
  - Validates uvicorn installation and auto-repairs if missing
  - Mac/Windows still use PyInstaller bundles (self-contained)
  - Smaller Linux DEB (~250MB vs 2.5GB)

## [0.1.9] - 2025-12-16

### Fixed

- **Linux Backend Startup** - Bundled PyInstaller executable for Linux (like Mac/Windows)
  - Eliminates dependency on system Python and manual venv setup
  - Fixes "No module named uvicorn" errors on Linux installations
  - More reliable: self-contained executable with all dependencies
  - Larger DEB file size (~150MB more) but eliminates installation issues

### Changed

- **Linux Packaging** - Now uses PyInstaller bundle instead of system Python + venv
  - Consistent backend deployment across all platforms
  - Simplified Linux installation (no Python prerequisites)
  - Auto-repair logic removed (no longer needed with bundled approach)

## [0.1.8] - 2025-12-16

### Added

- **2025 Academic Prompting System** - Major upgrade to AI response quality
  - Citation-aware RAG prompting with mandatory inline citations [N]
  - Chain-of-thought reasoning for transparent logic
  - Improved generation parameters (temp=0.35, top_p=0.9, top_k=50)
  - Explicit handling of uncertainty and research gaps
  - Structured responses: Direct answer → Evidence → Synthesis → Limitations
  - New `AcademicPrompts` module with comprehensive prompt templates
  - New `AcademicGenerationParams` with research-backed parameter sets

### Changed

- **System Prompt** - Enhanced from 54 to ~400 words with comprehensive academic guidelines
  - Detailed citation requirements with examples
  - Explicit responsibilities and quality gates
  - Chain-of-thought reasoning instructions
- **Generation Parameters** - Optimized for academic content synthesis:
  - Temperature: 0.3 → 0.35 (reduces repetition, maintains factuality)
  - Max tokens: 512 → 600 (allows detailed academic responses)
  - Top-k: 40 → 50 (better vocabulary diversity)
  - Repeat penalty: 1.1 → 1.15 (prevents citation repetition)
- **All LLM Providers** - Updated defaults for better academic output:
  - Ollama: Enhanced top_k and repeat_penalty
  - OpenAI: Added frequency_penalty, optimized top_p
  - Anthropic: Added top_k parameter
  - Perplexity, Groq, OpenRouter: Enhanced sampling parameters

### Improved

- **Citation Accuracy** - Expected ~60% reduction in citation mismatches (based on CiteFix research)
- **Response Quality** - More natural academic writing with proper grounding
- **Transparency** - Clear distinction between findings, synthesis, and gaps
- **Repetition Control** - Eliminated citation and concept repetition in long responses
- **Uncertainty Handling** - Explicit "I don't know" when evidence is insufficient

### Documentation

- Added `docs/ACADEMIC_PROMPTING_2025.md` - Comprehensive implementation guide
- Added `docs/PROMPTING_QUICKSTART.md` - User migration guide

### Technical Notes

- Based on 2025 research: CiteFix (ACL 2025), Perplexity Academic Mode, RAG evaluation frameworks
- All changes are backward compatible - no breaking changes
- No re-indexing required - works with existing vector databases
- Pure Python code changes - no dependency updates needed

## [0.1.7] - 2025-12-08

### Fixed

- **Linux Installation Path** - Removed spaces from productName to fix Electron zygote spawn issues
  - Changed from `/opt/Zotero RAG Assistant/` to `/opt/RAGAssistant/` (updated in later version)
  - Fixes "failed to execvp" and zygote_host_impl_linux.cc errors on launch
  - Fixed postinstall script to correctly set chrome-sandbox permissions
- **Security** - Removed vulnerable icon generation dependencies
  - Removed `electron-icon-maker`, `icon-gen`, `svg2png`, `phantomjs-prebuilt`
  - Using electron-builder's built-in icon generation
  - Zero npm audit vulnerabilities

### Changed

- **Product Name** - Changed to simplify naming (updated to "RAG Assistant" in later version)

## [0.1.6] - 2025-12-08

### Fixed

- **PyInstaller Backend Bundle** - Fixed backend startup issues in packaged Electron app
  - Changed to import FastAPI app object directly instead of string reference
  - Added PIL/Pillow to bundled dependencies (required by sentence-transformers)
  - Backend now starts correctly in production builds
- **Debian Package Dependencies** - Removed obsolete packages from `.deb` dependencies
  - Removed `gconf2`, `gconf-service`, `libappindicator1` (no longer available in modern repos)
  - Added `libgtk-3-0`, `libgbm1` (required Electron runtime libraries)
  - Fixes "unmet dependencies" errors during `apt` installation on Ubuntu 22.04+

## [0.1.6] - 2025-12-08

### Fixed

- **macOS DMG Installation** - Added Applications folder shortcut for easy drag-and-drop installation
- **Auto-Updates** - Fixed missing `latest-mac.yml`, `latest.yml`, and `latest-linux.yml` files
  - macOS: Enabled `writeUpdateInfo: true` for DMG
  - Windows: Added `differentialPackage: true` for delta updates
  - Linux: Proper auto-update metadata generation
- **Python Bundling** - Migrated from venv symlinks to PyInstaller for truly portable bundles
  - No more "Python interpreter missing" errors
  - Self-contained executable includes all dependencies
  - Works without system Python installation

### Added

- **Native Linux .deb packages** for Debian/Ubuntu with proper sandbox configuration
  - Automatic chrome-sandbox setup via post-install script
  - No `--no-sandbox` flag needed
  - System integration via package manager
  - Support for both amd64 and arm64 architectures
- **PyInstaller-based Python bundling** for all platforms
  - Complete standalone backend executable
  - No symlinks to system Python
  - Truly relocatable application bundle
- **Comprehensive Linux packaging documentation** (docs/LINUX_PACKAGING.md)
- **PyInstaller build guide** (docs/PYINSTALLER_BUNDLE_GUIDE.md)

### Changed

- **Documentation cleanup** - Consolidated and removed redundant docs
  - Installation instructions now in README for all platforms
  - Merged auto-update documentation into single comprehensive guide
  - Removed 12 redundant/outdated documentation files
  - Clear separation of user vs developer documentation

## [0.1.3] - 2025-12-02

### Fixed

- **Linux AppImage Python detection** - Fixed "Python Not Found" errors on Linux systems
  - Now correctly detects `python3` command (standard on modern Linux distros)
  - Tries bundled Python first, falls back to system Python gracefully
  - Added multiple fallback paths: `python3`, `python`, `/usr/bin/python3`, etc.
  - Shows platform-specific installation instructions if Python is missing
- **Development mode backend conflict** - Fixed port 8000 conflict in dev mode
  - Electron no longer tries to start its own backend in development
  - Uses the backend started by `npm run dev:backend` instead
- **Working directory resolution** - Fixed backend module import errors in dev mode
  - Correctly resolves project root directory on all platforms
  - Backend can now find Python modules in development and production

### Added

- Comprehensive Python detection system with smart fallback logic
- Platform-specific error messages for missing Python installations
- Detailed logging for Python detection and backend startup process
- New documentation:
  - `docs/PYTHON_DETECTION.md` - Technical architecture
  - `docs/LINUX_PYTHON_GUIDE.md` - User guide for Linux
  - `docs/BUILD_CHECKLIST.md` - Build and testing procedures
  - `docs/PYTHON_DETECTION_FLOW.txt` - Visual flow diagram

## [0.1.0] - 2024-12-02

### Added - Desktop App Release 

- **Native desktop application** using Electron for macOS, Windows, and Linux
- **Automatic updates** via GitHub Releases - future versions install automatically
- **Bundled backend** - no need to install Python or dependencies manually
- **Cross-platform installers**:
  - macOS: DMG installer (Universal: Intel + Apple Silicon)
  - Windows: NSIS installer with auto-updates
  - Linux: AppImage (portable) and DEB packages
- **One-command development** - `npm run dev` runs everything
- **Professional packaging** with code signing support
- **Comprehensive documentation** for development and deployment

### Changed

- Backend now supports HEAD requests for health checks
- Development workflow simplified with concurrent script execution
- Repository structure reorganized for desktop app

### Fixed

- Backend process management and cleanup on app quit
- IPC communication security with context isolation
- TypeScript compilation errors in Electron code

## Previous Versions (Web App)

### [0.0.x] - Pre-Desktop Era

Previous versions were web-based only, requiring manual setup of Python backend and Node.js frontend.

See git history for details: https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/commits/master

---

## Release Notes Format

### Added
- New features

### Changed
- Changes in existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security improvements
