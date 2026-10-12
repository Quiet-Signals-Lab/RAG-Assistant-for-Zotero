# backend/main.py
# uvicorn backend.main:app --reload

import os
import re
import sys
import logging

# Force UTF-8 on stdout/stderr so print() of non-ASCII content (emoji, CJK
# model paths / PDF text) doesn't crash indexing on CJK Windows, where the
# console defaults to a legacy code page (cp932/gbk). See issues #37, #61.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError):
        pass  # non-reconfigurable stream (already wrapped / redirected)

# Suppress gRPC verbose error logging BEFORE any imports
# (known issue with google-generativeai package)
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GRPC_TRACE'] = ''
os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'

# One logging configuration for the whole backend. Electron captures stdout
# and writes it to the user data folder; uvicorn adds its own handlers for
# its own loggers and leaves the root logger alone.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logging.getLogger('grpc').setLevel(logging.CRITICAL)
logging.getLogger('google.auth').setLevel(logging.WARNING)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Body, HTTPException, Request
from fastapi.responses import PlainTextResponse
from typing import Optional
from backend.zoteroitem import ZoteroItem
from backend.external_api_utils import fetch_semantic_scholar_data
from backend.pdf import PDF
from fastapi.middleware.cors import CORSMiddleware
from backend.interface import ZoteroChatbot
from backend.vector_db import ChromaClient
from backend.embed_utils import get_embedding
from backend.profile_manager import ProfileManager
from backend.metadata_version import check_metadata_compatibility
from backend.metadata_migration import MetadataMigration
import datetime
import platform
import subprocess
import warnings
from pathlib import Path

logger = logging.getLogger(__name__)

# Suppress resource_tracker warnings from loky/scikit-learn
# These are harmless cleanup warnings from parallel processing in sentence-transformers
warnings.filterwarnings("ignore", category=UserWarning, module="resource_tracker")

# Set at startup (see lifespan) so importing this module has no side effects.
profile_manager: ProfileManager = None  # type: ignore[assignment]
chatbot: ZoteroChatbot = None  # type: ignore[assignment]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global profile_manager, chatbot
    profile_manager = ProfileManager()
    logger.info("ProfileManager initialized at: %s", profile_manager.BASE_DIR)
    active_profile = profile_manager.get_active_profile()
    if not active_profile:
        raise RuntimeError("Failed to initialize profile system")
    logger.info("Active profile: %s - %s", active_profile['id'], active_profile['name'])
    chatbot = initialize_chatbot()
    yield


app = FastAPI(lifespan=lifespan)


def _fail(e: Exception, status: int = 500) -> HTTPException:
    """Log an endpoint failure and turn it into an HTTP error for the client.

    Endpoints used to answer 200 with {"error": ...}; half the UI never
    checked for it and treated failures as success.
    """
    if status >= 500:
        logger.exception(str(e))
    else:
        logger.warning(str(e))
    return HTTPException(status_code=status, detail=str(e))


# CORS setup: matches your frontend HTML server (e.g., http://localhost:8080)
app.add_middleware(
    CORSMiddleware,
    # Allow the typical dev server origins (Vite default 5173 and older 8080),
    # plus localhost variants used during development.
    allow_origins=["http://localhost:8080", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default paths - use user's home directory for cross-platform compatibility
_home = Path.home()
DB_PATH = str(_home / "Zotero" / "zotero.sqlite")
# CHROMA_PATH is now profile-specific - set per profile in load_settings()
CHROMA_PATH = None  # Legacy global, prefer profile-specific paths


def load_settings(profile_id: str = None):
    """Load settings from profile storage.
    
    Args:
        profile_id: Profile ID to load settings from. If None, uses active profile.
    """
    if profile_id is None:
        active = profile_manager.get_active_profile()
        if not active:
            raise RuntimeError("No active profile")
        profile_id = active['id']
    
    logger.debug(f"[load_settings] Loading settings for profile: {profile_id}")
    
    # Use profile-specific chroma path by default
    profile_chroma_path = profile_manager.get_profile_chroma_path(profile_id)
    logger.debug(f"[load_settings] Profile chroma path: {profile_chroma_path}")
    
    default_settings = {
        "activeProviderId": "ollama",
        "activeModel": "",
        "embeddingModel": "bge-base",
        "zoteroPath": DB_PATH,
        "chromaPath": profile_chroma_path,
        # "desk" (reference desk, the default) or "chat" (legacy chat mode)
        "interfaceMode": "desk",
        # The desk's model jobs (backend/clerk_jobs.py). Each runs only when a model is set.
        "deskReadQuery": True,   # read the request with the model before searching
        "deskReadTimeout": 8,    # seconds to wait for that reading before using the library's
        "deskNotes": True,       # one indicative note per result, after the list appears
        "deskAlsoTry": True,     # next searches chosen from the results' terms
        "deskThemes": True,      # group the results into labelled themes
        "deskClerkCloud": False, # let the clerk use a cloud provider: queries and passages are sent to it
        "providers": {
            "ollama": {
                "enabled": True,
                "credentials": {
                    "base_url": "http://localhost:11434"
                }
            },
            "lmstudio": {
                "enabled": False,
                "credentials": {
                    "base_url": "http://localhost:1234"
                }
            },
            "openai": {
                "enabled": False,
                "credentials": {
                    "api_key": ""
                }
            },
            "anthropic": {
                "enabled": False,
                "credentials": {
                    "api_key": ""
                }
            },
            "mistral": {
                "enabled": False,
                "credentials": {
                    "api_key": ""
                }
            },
            "google": {
                "enabled": False,
                "credentials": {
                    "api_key": ""
                }
            },
            "groq": {
                "enabled": False,
                "credentials": {
                    "api_key": ""
                }
            },
            "openrouter": {
                "enabled": False,
                "credentials": {
                    "api_key": ""
                }
            },
            "github_models": {
                "enabled": False,
                "credentials": {
                    "api_key": ""
                }
            }
        }
    }
    
    # Load profile-specific settings
    saved_settings = profile_manager.load_profile_settings(profile_id)
    if saved_settings:
        try:
            # Migrate old settings format if needed
            if "openaiApiKey" in saved_settings or "anthropicApiKey" in saved_settings:
                    # Old format - migrate to new
                    migrated = default_settings.copy()
                    
                    if saved_settings.get("openaiApiKey"):
                        migrated["providers"]["openai"]["credentials"]["api_key"] = saved_settings["openaiApiKey"]
                        migrated["providers"]["openai"]["enabled"] = True
                    
                    if saved_settings.get("anthropicApiKey"):
                        migrated["providers"]["anthropic"]["credentials"]["api_key"] = saved_settings["anthropicApiKey"]
                        migrated["providers"]["anthropic"]["enabled"] = True
                    
                    if saved_settings.get("zoteroPath"):
                        migrated["zoteroPath"] = saved_settings["zoteroPath"]
                    
                    if saved_settings.get("chromaPath"):
                        migrated["chromaPath"] = saved_settings["chromaPath"]
                    
                    # Migrate defaultModel
                    if saved_settings.get("defaultModel"):
                        old_model = saved_settings["defaultModel"]
                        if old_model == "ollama":
                            migrated["activeProviderId"] = "ollama"
                        elif old_model.startswith("gpt"):
                            migrated["activeProviderId"] = "openai"
                            migrated["activeModel"] = old_model
                        elif old_model.startswith("claude"):
                            migrated["activeProviderId"] = "anthropic"
                            migrated["activeModel"] = old_model
                    
                    # Save migrated settings
                    save_settings(migrated, profile_id)
                    return migrated
            else:
                # New format - merge with defaults
                merged = default_settings.copy()
                merged.update(saved_settings)
                
                # Ensure all providers exist in settings
                if "providers" in saved_settings:
                    for provider_id in default_settings["providers"]:
                        if provider_id not in merged["providers"]:
                            merged["providers"][provider_id] = default_settings["providers"][provider_id]
                
                logger.debug(f"[load_settings] Merged settings - zoteroPath: {merged.get('zoteroPath')}, chromaPath: {merged.get('chromaPath')}, embeddingModel: {merged.get('embeddingModel')}")
                return merged
        except Exception as e:
            logger.debug(f"[load_settings] Error loading settings: {e}")
            logger.debug(f"[load_settings] Returning default settings - zoteroPath: {default_settings.get('zoteroPath')}, chromaPath: {default_settings.get('chromaPath')}")
            return default_settings
    else:
        logger.debug(f"[load_settings] No saved settings, returning defaults - zoteroPath: {default_settings.get('zoteroPath')}, chromaPath: {default_settings.get('chromaPath')}")
        return default_settings


def save_settings(settings: dict, profile_id: str = None):
    """Save settings to profile storage.
    
    Args:
        settings: Settings dictionary
        profile_id: Profile ID to save to. If None, uses active profile.
    """
    if profile_id is None:
        active = profile_manager.get_active_profile()
        if not active:
            return False
        profile_id = active['id']
    
    return profile_manager.save_profile_settings(profile_id, settings)


# Instantiate the main chatbot object with provider settings
def initialize_chatbot():
    """Initialize chatbot with current profile settings."""
    active = profile_manager.get_active_profile()
    if not active:
        raise RuntimeError("No active profile")
    
    settings = load_settings(active['id'])
    
    # Extract provider credentials
    provider_credentials = {}
    for provider_id, provider_config in settings.get("providers", {}).items():
        if provider_config.get("enabled"):
            provider_credentials[provider_id] = provider_config.get("credentials", {})
    
    # Validate that activeProviderId is an enabled provider; auto-switch if not
    active_provider_id = settings.get("activeProviderId", "ollama")
    all_providers = settings.get("providers", {})
    if not all_providers.get(active_provider_id, {}).get("enabled", False):
        fallback = next(
            (pid for pid, cfg in all_providers.items() if cfg.get("enabled", False)),
            "ollama"
        )
        logger.info(f"[initialize_chatbot] Active provider '{active_provider_id}' is disabled; switching to '{fallback}'")
        active_provider_id = fallback

    # Use profile-specific chroma path if not customized
    chroma_path = settings.get("chromaPath")
    if not chroma_path:
        chroma_path = profile_manager.get_profile_chroma_path(active['id'])
    
    new_chatbot = ZoteroChatbot(
        db_path=settings.get("zoteroPath", DB_PATH),
        chroma_path=chroma_path,
        active_provider_id=active_provider_id,
        active_model=settings.get("activeModel"),
        credentials=provider_credentials,
        embedding_model_id=settings.get("embeddingModel", "bge-base"),
        storage_path=settings.get("pdfStoragePath") or None
    )

    # Propagate API credentials to the embedding dispatch layer so cloud
    # embedding providers (OpenAI, etc.) can authenticate at index and query time.
    from backend.embed_utils import set_embedding_credentials
    for provider_id, creds in provider_credentials.items():
        set_embedding_credentials(provider_id, creds)

    return new_chatbot

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _validate_profile_id(profile_id: str) -> None:
    """Reject (400) a profile_id with characters outside [a-zA-Z0-9_-]."""
    if not profile_id or not all(c.isalnum() or c in '-_' for c in profile_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid profile ID: must contain only alphanumeric characters, hyphens, and underscores",
        )


def _get_allowed_storage_dirs() -> list:
    """Return resolved directories from which PDF file access is permitted."""
    dirs = []
    storage_path = getattr(chatbot.zlib, 'storage_path', None)
    if storage_path:
        dirs.append(Path(storage_path).resolve())
    db_parent = Path(chatbot.zlib.db_path).parent
    dirs.append((db_parent / "storage").resolve())
    return dirs


def _validate_pdf_path(filepath: str) -> Path:
    """Validate a user-supplied file path for PDF access.

    Ensures the resolved path:
    - Is not empty
    - Has a .pdf suffix
    - Resolves within an allowed Zotero storage directory

    Returns the resolved Path on success; raises ValueError otherwise.
    """
    if not filepath or not filepath.strip():
        raise ValueError("File path must not be empty")
    resolved = Path(filepath).resolve()
    if resolved.suffix.lower() != '.pdf':
        raise ValueError("Only PDF files are accessible via this endpoint")
    allowed_dirs = _get_allowed_storage_dirs()
    for allowed in allowed_dirs:
        try:
            resolved.relative_to(allowed)
            return resolved
        except ValueError:
            continue
    # Linked attachments (e.g. ZotMoov) live outside the storage folder. They
    # were accepted at indexing time, so a path the index knows is trusted too.
    if chatbot.chroma.has_pdf_path(filepath) or chatbot.chroma.has_pdf_path(str(resolved)):
        return resolved
    raise ValueError("Access denied: file is outside the Zotero storage directory")


@app.get("/")
def read_root():
    """Health check endpoint for Zotero LLM backend."""
    return {"msg": "Welcome to Zotero LLM Plugin backend"}

@app.head("/")
def read_root_head():
    """Health check endpoint (HEAD) for Zotero LLM backend."""
    return {"msg": "Welcome to Zotero LLM Plugin backend"}

@app.get("/health")
def health_check_simple():
    """Simple health check endpoint for application startup verification."""
    return {"status": "healthy"}

@app.get("/api/health")
def health_check():
    """
    Detailed health check endpoint that validates all critical components.
    Returns structured health information for diagnostics.
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.datetime.now().isoformat(),
            "components": {}
        }
        
        # Check profile system
        try:
            active = profile_manager.get_active_profile()
            health_status["components"]["profile_manager"] = {
                "status": "ok",
                "active_profile": active["id"] if active else None
            }
        except Exception as e:
            health_status["components"]["profile_manager"] = {
                "status": "error",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # Check the Zotero database the active profile is configured to use
        try:
            db_path = load_settings().get("zoteroPath") or DB_PATH
            db_exists = os.path.exists(db_path)
            health_status["components"]["database"] = {
                "status": "ok" if db_exists else "warning",
                "path": db_path,
                "exists": db_exists
            }
            if not db_exists:
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "error",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }

@app.post("/shutdown")
async def shutdown():
    """
    Graceful shutdown endpoint.
    Allows Electron to cleanly shut down the backend server.
    """
    import signal
    import threading
    
    def delayed_shutdown():
        """Shutdown after a brief delay to allow response to be sent"""
        import time
        time.sleep(2.0)  # long enough for the response to be sent and uvicorn to clean up
        os.kill(os.getpid(), signal.SIGTERM)
    
    # Start shutdown in background thread
    thread = threading.Thread(target=delayed_shutdown, daemon=True)
    thread.start()
    
    return {"status": "shutting_down", "message": "Server will shutdown in 2 seconds"}

@app.get("/api/pdfsample")
def pdf_sample(
    filename: str = Query(..., description="Path to PDF file, e.g. backend/sample_pdfs/test_article.pdf"),
    max_chars: Optional[int] = Query(2000, description="Maximum number of characters to extract"),
):
    """Extracts sample text from a PDF for testing purposes."""
    try:
        safe_path = _validate_pdf_path(filename)
        pdf = PDF(filepath=str(safe_path))
        text = pdf.extract_text(max_chars=max_chars)
        return {"sample": text}
    except ValueError as e:
        raise _fail(e, 400)
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)

@app.get("/api/item_metadata")
def get_item_metadata(
    filename: str = Query(..., description="Path to PDF or metadata file"),
):
    """Retrieves metadata from the ZoteroItem class."""
    try:
        safe_path = _validate_pdf_path(filename)
        item = ZoteroItem(filepath=str(safe_path))
        title = item.get_title()
        author = item.get_author()
        return {"title": title,
                "author": author}
    except ValueError as e:
        raise _fail(e, 400)
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)

@app.get("/api/search_items")
def search_items(
    authors: Optional[str] = Query("", description="Comma separated authors"),
    titles: Optional[str] = Query("", description="Comma separated titles"),
    dates: Optional[str] = Query("", description="Comma separated dates")
):
    """Query the Zotero library using authors, titles, and dates."""
    try:
        authors_list = [a.strip() for a in authors.split(",") if a.strip()]
        titles_list = [t.strip() for t in titles.split(",") if t.strip()]
        dates_list = [d.strip() for d in dates.split(",") if d.strip()]
        results = chatbot.zlib.search_parent_items(authors=authors_list, titles=titles_list, dates=dates_list)
        return {"results": list(results)}  # Convert set to list for JSON serialization
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)

@app.post("/api/external/semantic_scholar")
def lookup_semantic_scholar(payload: dict = Body(...)):
    """
    Look up paper metadata on Semantic Scholar.
    
    Request body:
        {
            "doi": "10.xxx/xxx",      // Optional - preferred method
            "title": "Paper title",   // Optional - fallback
            "authors": "Author names" // Optional - helps with matching
        }
    
    Returns:
        {
            "success": true/false,
            "data": {
                "title": str,
                "abstract": str,
                "year": int,
                "authors": [str],
                "citation_count": int,
                "citations": [dict],
                "references": [dict],
                "url": str,
                "doi": str
            },
            "error": str (if success=false)
        }
    """
    try:
        result = fetch_semantic_scholar_data(
            doi=payload.get('doi'),
            title=payload.get('title'),
            authors=payload.get('authors')
        )
        
        if result:
            return {"success": True, "data": result}
        else:
            return {
                "success": False,
                "error": "Paper not found on Semantic Scholar"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/index_library")
def index_library(payload: dict = Body(default={"incremental": True})):
    """Index Zotero parent items and PDFs in the vector database.
    
    Args:
        payload: JSON with optional "incremental" boolean (default: True)
                 - True: Only index new items not already in the database
                 - False: Full reindex of all items
    """
    try:
        incremental = payload.get("incremental", True)
        settings = load_settings()
        chatbot.start_indexing(
            incremental=incremental,
            excluded_collections=settings.get("excludedCollections", []) or [],
            excluded_tags=settings.get("excludedTags", []) or [],
            excluded_item_types=settings.get("excludedItemTypes", []) or [],
        )
        mode = "incremental" if incremental else "full"
        return {"msg": f"Indexing started ({mode} mode)."}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/index_cancel")
def index_cancel():
    """Cancel a running indexing job."""
    try:
        chatbot.cancel_indexing()
        return {"msg": "Cancellation signaled."}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/exclusions/purge")
def purge_exclusions():
    """Remove already-indexed items matching the saved exclusion rules from the
    vector store, so exclusions take effect immediately without a reindex."""
    try:
        s = load_settings()
        result = chatbot.purge_excluded_items(
            excluded_collections=s.get("excludedCollections", []) or [],
            excluded_tags=s.get("excludedTags", []) or [],
            excluded_item_types=s.get("excludedItemTypes", []) or [],
        )
        return {"success": True, **result}
    except Exception as e:
        raise _fail(e)

@app.get("/api/chat")
def chat(query: str, item_ids: Optional[str] = Query("", description="Comma separated Zotero item IDs to scope search")):
    try:
        filter_ids = [id_.strip() for id_ in item_ids.split(",") if id_.strip()]
        payload = chatbot.chat(query, filter_item_ids=filter_ids if filter_ids else None)
        return payload
    except Exception as e:
        raise _fail(e)


@app.post("/api/chat")
def chat_post(payload: dict = Body(...)):
    """POST-style chat endpoint that accepts JSON body: 
    {
        "query": "...", 
        "item_ids": ["id1","id2"], 
        "session_id": "...",
        "use_metadata_filters": true/false,
        "manual_filters": {
            "year_min": 2020,
            "year_max": 2023,
            "tags": ["NLP", "ML"],
            "collections": ["Research"]
        },
        "use_rrf": true/false
    }
    
    This mirrors the GET `/chat` endpoint but is easier for clients that send JSON.
    Supports stateful conversations via session_id and metadata filtering.
    """
    try:
        query = payload.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' in request body")

        item_ids = payload.get("item_ids") or []
        # Accept either a list of ids or a comma-separated string
        if isinstance(item_ids, str):
            filter_ids = [id_.strip() for id_ in item_ids.split(",") if id_.strip()]
        elif isinstance(item_ids, list):
            filter_ids = [str(id_).strip() for id_ in item_ids if str(id_).strip()]
        else:
            filter_ids = []

        # Extract session_id for stateful conversation
        session_id = payload.get("session_id")
        
        # Extract metadata filtering options
        use_metadata_filters = payload.get("use_metadata_filters", False)
        manual_filters = payload.get("manual_filters")
        use_rrf = payload.get("use_rrf", True)
        # 0 = auto (dynamic, model-based); > 0 = user-specified evidence snippet cap
        max_sources = int(payload.get("max_sources", 0) or 0)

        payload_out = chatbot.chat(
            query, 
            filter_item_ids=filter_ids if filter_ids else None,
            session_id=session_id,
            use_metadata_filters=use_metadata_filters,
            manual_filters=manual_filters,
            use_rrf=use_rrf,
            max_sources=max_sources,
        )
        return payload_out
    except HTTPException:
        raise
    except Exception as e:
        raise _retrieval_failure(e)


def _retrieval_failure(e: Exception) -> HTTPException:
    """Turn a search failure into an HTTP error, explaining the one users can fix themselves."""
    if "embedding with dimension" in str(e).lower():
        return _fail(RuntimeError(
            "Database configuration error: embedding dimension mismatch. Your database was "
            "created with a different embedding model. Delete the vector database and "
            f"re-index your library. ({e})"
        ))
    return _fail(e)


def _clean_filters(raw) -> Optional[dict]:
    """Validate scope filters from the client. Unknown keys are dropped; bad values are a 400."""
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="'manual_filters' must be an object")
    clean = {}
    for key in ("year_min", "year_max"):
        value = raw.get(key)
        if value in (None, ""):
            continue
        try:
            clean[key] = int(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"'{key}' must be a year")
    for key in ("tags", "collections", "item_types", "exclude"):
        values = raw.get(key) or []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            raise HTTPException(status_code=400, detail=f"'{key}' must be a list")
        values = [str(v).strip() for v in values if str(v).strip()]
        if values:
            clean[key] = values
    for key in ("author", "title"):
        value = str(raw.get(key) or "").strip()
        if value:
            clean[key] = value
    return clean or None


@app.post("/api/search")
def search(payload: dict = Body(...)):
    """Reference desk search: a ranked bibliography with evidence.

    Body: {"query": str, "manual_filters"?: {year_min, year_max, tags, collections,
    item_types, author, title, exclude}, "use_metadata_filters"?: bool (read scope
    from the query, default true), "item_ids"?: [str] (search only these),
    "exclude_item_ids"?: [str] (set these aside)}. A model reads the query only when
    the desk settings allow it and the library reader leaves something unread.
    """
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Type what you are looking for.")
    if len(query) > 2000:
        raise HTTPException(status_code=400, detail="The query is too long. Keep it under 2,000 characters.")
    manual_filters = _clean_filters(payload.get("manual_filters"))
    item_ids = _id_list(payload.get("item_ids"))
    exclude_ids = _id_list(payload.get("exclude_item_ids"))
    settings = load_settings()
    _clerk_settings(settings)
    try:
        return chatbot.search(
            query,
            manual_filters=manual_filters,
            use_metadata_filters=bool(payload.get("use_metadata_filters", True)),
            filter_item_ids=item_ids or None,
            exclude_item_ids=exclude_ids or None,
            read_with_model=bool(settings.get("deskReadQuery", True)),
            read_timeout=float(settings.get("deskReadTimeout", 8) or 8),
        )
    except Exception as e:
        raise _retrieval_failure(e)


def _clerk_settings(settings: dict) -> None:
    """The clerk may use a cloud provider only when the reader allowed it for the desk:
    a key set up for legacy chat is not consent to send passages on every search."""
    chatbot.clerk.allow_cloud = bool(settings.get("deskClerkCloud", False))


def _id_list(raw) -> list:
    if isinstance(raw, str):
        raw = raw.split(",")
    return [str(i).strip() for i in raw if str(i).strip()] if isinstance(raw, list) else []


@app.post("/api/annotate")
async def annotate(request: Request, payload: dict = Body(...)):
    """Stream the clerk's work on a result list as newline-delimited JSON.

    Body: {"query": str, "items": [{item_id, title, tags, band, passages: [{page, text}]}]}.
    Which jobs run follows the desk settings. The stream stops, and work not yet
    started is cancelled, when the client goes away (a new search replaces it).
    The body must be sent as JSON: a page in a browser could otherwise post here
    without a CORS check and spend the reader's model quota.
    """
    import asyncio
    import concurrent.futures
    import json as _json
    from fastapi.responses import StreamingResponse

    query = str(payload.get("query") or "").strip()
    items = payload.get("items")
    if not query or not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Send the query and the items to annotate.")
    items = [
        {
            "item_id": str(it.get("item_id")),
            "title": str(it.get("title") or "")[:500],
            "tags": [str(t) for t in (it.get("tags") if isinstance(it.get("tags"), list) else [])][:30],
            "band": str(it.get("band") or ""),
            "passages": [
                {"page": p.get("page") if isinstance(p.get("page"), int) else None, "text": str(p.get("text") or "")[:2000]}
                for p in (it.get("passages") if isinstance(it.get("passages"), list) else [])[:3] if isinstance(p, dict)
            ],
        }
        for it in items[:40] if isinstance(it, dict) and it.get("item_id")
    ]
    settings = load_settings()
    _clerk_settings(settings)
    provider = chatbot.provider_manager.get_active_provider() if chatbot.provider_manager else None
    events = chatbot.annotate(
        query, items,
        notes=bool(settings.get("deskNotes", True)),
        also_try=bool(settings.get("deskAlsoTry", True)),
        themes=bool(settings.get("deskThemes", True)),
        # A local server answers one call at a time: a second worker only queues work
        # that a new search would then wait behind.
        workers=3 if getattr(provider, "requires_api_key", False) else 1,
    )

    def close(_=None):
        try:
            events.close()
        except ValueError:  # still running in the worker: close once it returns
            pass

    async def stream():
        # The stream's own worker, so a disconnect mid-call can wait for that call
        # to return before closing the generator (closing a running one raises).
        worker = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="annotate-stream")
        pending = None
        try:
            while True:
                if await request.is_disconnected():
                    break
                pending = worker.submit(next, events, None)
                event = await asyncio.wrap_future(pending)
                if event is None:
                    break
                yield _json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            if pending is not None and not pending.done():
                pending.add_done_callback(close)
            else:
                close()
            worker.shutdown(wait=False)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/api/desk/chain")
def desk_chain(payload: dict = Body(...)):
    """References and cited-by for one item, from Semantic Scholar, with the reader's own copies marked.

    Sends the item's DOI (or its title when it has none) to Semantic Scholar, and
    only when the reader asks. Body: {"item_id": str}.
    """
    import requests

    item_id = str(payload.get("item_id") or "").strip()
    if not item_id.isdigit():
        raise HTTPException(status_code=400, detail="Send the item_id of a Zotero item.")
    try:
        out = chatbot.citation_chain(item_id)
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 429:
            raise HTTPException(status_code=503, detail="Semantic Scholar is limiting requests. Try again in a minute.")
        raise HTTPException(status_code=502, detail="Semantic Scholar returned an error.")
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Could not reach Semantic Scholar. Check the connection.")
    if out is None:
        raise HTTPException(status_code=404, detail="This item is not in your Zotero library.")
    return out


@app.get("/api/desk/model")
def desk_model():
    """The model the desk's jobs would use, whether it may and can be used, and the desk's own measurements of it."""
    from backend.clerk import measured
    settings = load_settings()
    _clerk_settings(settings)
    model = chatbot.clerk.model()
    provider = chatbot.provider_manager.get_active_provider() if chatbot.provider_manager else None
    return {
        "available": chatbot.clerk.available(),
        "model": model,
        "cloud": bool(getattr(provider, "requires_api_key", False)),
        "cloud_allowed": chatbot.clerk.allow_cloud,
        "measured": measured(model) if model else None,
        "jobs": {
            "read_query": bool(settings.get("deskReadQuery", True)),
            "notes": bool(settings.get("deskNotes", True)),
            "also_try": bool(settings.get("deskAlsoTry", True)),
            "themes": bool(settings.get("deskThemes", True)),
        },
    }


@app.get("/api/index_status")
def index_status():
    """Return a simple status for indexing. Currently basic placeholder.
    You can expand this to report real progress/state from the ZoteroChatbot.
    """
    try:
        status = "indexing" if getattr(chatbot, "is_indexing", False) else "idle"
        progress = getattr(chatbot, "index_progress", None) or {}
        return {"status": status, "progress": progress}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/db_health")
def db_health():
    """Check the health and configuration of the vector database.
    Validates that embedding dimensions are consistent.
    """
    try:
        validation = chatbot.chroma.validate_embedding_dimension()
        return validation
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


def _zotero_styles_dir() -> Path:
    """Zotero keeps the CSL styles a user installs next to its database."""
    return Path(chatbot.zlib.db_path).parent / "styles"


@app.get("/api/csl/styles")
def csl_styles():
    """The CSL styles installed in Zotero, offered as drop-in styles for the desk's references."""
    folder = _zotero_styles_dir()
    styles = []
    for path in sorted(folder.glob("*.csl")) if folder.is_dir() else []:
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        except OSError:
            continue
        title = re.search(r"<title>([^<]+)</title>", head)
        styles.append({"file": path.name, "title": title.group(1).strip() if title else path.stem})
    return {"styles": styles}


@app.get("/api/csl/styles/{name}")
def csl_style(name: str):
    """One installed style's XML. The name is a bare file name; nothing outside the folder is served."""
    if name != Path(name).name or not name.endswith(".csl"):
        raise HTTPException(status_code=400, detail="Not a style file name")
    path = _zotero_styles_dir() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No such style")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="ignore"), media_type="application/xml")


@app.get("/api/index_stats")
def index_stats():
    """Get statistics about the indexed library.
    
    Returns:
        - indexed_items: Number of unique items in the database
        - total_chunks: Total number of text chunks indexed
        - zotero_items: Total number of items in Zotero library with PDFs
        - new_items: Number of items in Zotero not yet indexed
    """
    try:
        # Get indexed item IDs
        indexed_ids = chatbot.chroma.get_indexed_item_ids()

        # Get total chunks
        total_chunks = chatbot.chroma.get_document_count()

        # Get all Zotero items
        raw_items = chatbot.zlib.search_parent_items_with_pdfs()
        zotero_item_ids = {str(it['item_id']) for it in raw_items}

        # Calculate new items
        new_item_ids = zotero_item_ids - indexed_ids

        return {
            "indexed_items": len(indexed_ids),
            "total_chunks": total_chunks,
            "zotero_items": len(zotero_item_ids),
            "new_items": len(new_item_ids),
            "needs_sync": len(new_item_ids) > 0,
            "current_embedding_model": chatbot.embedding_model_id,
            "collection_name": chatbot.chroma.collection_name
        }
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/metadata/version")
def metadata_version():
    """Check the current metadata version and whether migration is needed.
    
    Returns:
        - version: Current metadata format version (0, 1, or 2)
        - migration_needed: Boolean indicating if migration is required
        - message: User-friendly description
        - can_use_filtering: Whether filtering features can be used
    """
    try:
        from backend.metadata_version import MetadataVersionManager, CURRENT_METADATA_VERSION
        
        manager = MetadataVersionManager(chatbot.chroma)
        version = manager.detect_metadata_version()
        migration_needed = manager.is_migration_needed()
        message = manager.get_migration_message()
        
        # Get sample metadata for debugging
        sample_results = chatbot.chroma.collection.get(limit=3, include=['metadatas'])
        sample_meta = []
        for meta in sample_results.get('metadatas', [])[:3]:
            sample_meta.append({
                'year': meta.get('year'),
                'year_type': type(meta.get('year')).__name__,
                'has_tags': 'tags' in meta,
                'has_collections': 'collections' in meta,
            })
        
        return {
            "version": version,
            "migration_needed": migration_needed,
            "message": message,
            "can_use_filtering": version == CURRENT_METADATA_VERSION,
            "sample_metadata": sample_meta,  # For debugging
            "total_chunks": len(sample_results.get('ids', []))
        }
    except Exception as e:
        raise _fail(e)


@app.post("/api/metadata/count_filtered")
def count_filtered_items(body: dict):
    """
    Count how many items and chunks match the given filters.
    
    Used by the Scope panel to show an approximate count of filtered items.
    
    Request body:
        - year_min: Optional minimum year
        - year_max: Optional maximum year
        - tags: Optional list of tags
        - collections: Optional list of collections
        - title: Optional title substring
        - author: Optional author substring
        - item_types: Optional list of item types
    
    Returns:
        - unique_items: Number of unique items matching filters
        - total_chunks: Total number of chunks matching filters
    """
    try:
        year_min = body.get("year_min")
        year_max = body.get("year_max")
        tags = body.get("tags", [])
        collections = body.get("collections", [])
        title = body.get("title")
        author = body.get("author")
        item_types = body.get("item_types", [])
        
        counts = chatbot.chroma.count_items_matching_filters(
            year_min=year_min,
            year_max=year_max,
            tags=tags if tags else None,
            collections=collections if collections else None,
            title=title if title else None,
            author=author if author else None,
            item_types=item_types if item_types else None,
        )
        
        return counts
    except Exception as e:
        raise _fail(e)


@app.post("/api/metadata/migrate")
def metadata_migrate():
    """Migrate metadata to current format.
    
    Updates metadata in-place without re-embedding. Runs synchronously in a
    worker thread; the response carries the summary.
    
    Returns:
        - status: "started", "completed", "not_needed", or "error"
        - message: Description of the operation
        - summary: Migration statistics (if completed)
    """
    try:
        from backend.metadata_version import MetadataVersionManager
        from backend.metadata_migration import MetadataMigration
        
        # Check if migration is needed
        manager = MetadataVersionManager(chatbot.chroma)
        version = manager.detect_metadata_version()
        migration_needed = manager.is_migration_needed()
        
        if not migration_needed:
            return {
                "status": "not_needed",
                "message": "Metadata is already in current format",
                "version": version
            }
        
        migration = MetadataMigration(chatbot.chroma, chatbot.zlib)
        summary = migration.migrate_all_metadata()
        
        # Clear the cached version so next check will re-detect
        manager._cached_version = None
        
        return {
            "status": "completed",
            "message": "Migration completed successfully",
            "summary": summary
        }
    except Exception as e:
        raise _fail(e)


@app.post("/api/metadata/sync")
def metadata_sync():
    """Sync metadata from Zotero without re-embedding.
    
    Fetches current metadata from Zotero database and updates ChromaDB
    in-place without regenerating embeddings. Useful when you've updated
    titles, authors, tags, or other metadata in Zotero and want to refresh
    the indexed data.
    
    Returns:
        - status: "completed" or "error"
        - message: Description of the operation
        - summary: Sync statistics (chunks updated, time elapsed, etc.)
    """
    try:
        from backend.metadata_migration import MetadataMigration
        
        logger.info("[metadata_sync] Starting metadata sync from Zotero...")
        
        # Use the migration class to update metadata (it fetches fresh data from Zotero)
        migration = MetadataMigration(chatbot.chroma, chatbot.zlib)
        summary = migration.migrate_all_metadata()
        
        logger.info(f"[metadata_sync] Sync completed: {summary}")
        
        return {
            "status": "completed",
            "message": f"Successfully synced metadata for {summary.get('unique_items', 0)} items",
            "summary": summary
        }
    except Exception as e:
        raise _fail(e)


@app.get("/api/diagnose_unindexed")
def diagnose_unindexed():
    """Diagnose why specific items aren't being indexed.
    
    Returns detailed information about items that should be indexed but aren't.
    """
    try:
        # Get indexed item IDs
        indexed_ids = chatbot.chroma.get_indexed_item_ids()
        
        # Get all Zotero items
        raw_items = chatbot.zlib.search_parent_items_with_pdfs()
        zotero_item_ids = {str(it['item_id']) for it in raw_items}
        
        # Find unindexed items
        unindexed_ids = zotero_item_ids - indexed_ids
        
        # Get details for each unindexed item
        unindexed_items = [it for it in raw_items if str(it['item_id']) in unindexed_ids]
        
        diagnostics = []
        for item in unindexed_items:
            item_id = str(item['item_id'])
            pdf_path = item.get('pdf_path', '')
            
            diagnosis = {
                "item_id": item_id,
                "title": item.get('title', 'Unknown'),
                "pdf_path": pdf_path,
                "pdf_exists": os.path.exists(pdf_path) if pdf_path else False,
                "issues": []
            }
            
            # Check for issues
            if not pdf_path:
                diagnosis["issues"].append("No PDF path specified")
            elif not os.path.exists(pdf_path):
                diagnosis["issues"].append(f"PDF file not found at: {pdf_path}")
            else:
                # Try to extract text
                try:
                    from backend.pdf import PDF
                    pdf = PDF(pdf_path)
                    pages = pdf.extract_text_with_pages()
                    if not pages:
                        diagnosis["issues"].append("PDF has no extractable pages")
                    else:
                        text = "\\n".join([p['text'] for p in pages])
                        if not text.strip():
                            diagnosis["issues"].append("PDF pages exist but contain no text")
                        else:
                            diagnosis["text_length"] = len(text)
                            diagnosis["page_count"] = len(pages)
                            diagnosis["issues"].append("PDF appears valid - may need manual reindex")
                except Exception as e:
                    diagnosis["issues"].append(f"PDF extraction error: {str(e)}")
            
            diagnostics.append(diagnosis)
        
        return {
            "unindexed_count": len(unindexed_items),
            "indexed_count": len(indexed_ids),
            "zotero_count": len(zotero_item_ids),
            "diagnostics": diagnostics
        }
    except Exception as e:
        raise _fail(e)


@app.get("/api/embedding_collections")
def list_embedding_collections():
    """List all available embedding model collections in the database.
    Shows which embedding models have been used to index the library.
    """
    try:
        settings = load_settings()
        # Use profile-specific chroma path
        active = profile_manager.get_active_profile()
        profile_chroma_path = profile_manager.get_profile_chroma_path(active['id'])
        chroma_path = settings.get("chromaPath", profile_chroma_path)
        
        # Create a temporary ChromaDB client to list collections
        import chromadb
        from chromadb.config import Settings
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings())
        
        collections = client.list_collections()
        
        # Parse collection names to extract embedding models
        embedding_collections = []
        for col in collections:
            # Collection names follow pattern: zotero_lib_{embedding_model_id}
            # Cloud model IDs have ':' replaced with '-' in collection names.
            if col.name.startswith("zotero_lib_"):
                embedding_model_id = col.name.replace("zotero_lib_", "")
                item_count = col.count()
                current_safe = chatbot.embedding_model_id.replace(":", "-")
                embedding_collections.append({
                    "collection_name": col.name,
                    "embedding_model_id": embedding_model_id,
                    "item_count": item_count,
                    "is_current": embedding_model_id == current_safe,
                })
        
        return {
            "collections": embedding_collections,
            "current_embedding_model": chatbot.embedding_model_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/open_pdf")
def open_pdf(payload: dict = Body(...)):
    """Open a PDF file with the system's default viewer.
    Expects JSON body: {"pdf_path": "/path/to/file.pdf"}
    """
    try:
        pdf_path = payload.get("pdf_path")
        if not pdf_path:
            raise HTTPException(status_code=400, detail="Missing 'pdf_path' in request body")

        try:
            safe_path = _validate_pdf_path(pdf_path)
        except ValueError as e:
            raise _fail(e, 403)

        if not safe_path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found")

        # Open the file with the system's default application
        system = platform.system()
        if system == "Darwin":  # macOS
            subprocess.run(["open", str(safe_path)], check=True)
        elif system == "Windows":
            os.startfile(str(safe_path))
        elif system == "Linux":
            subprocess.run(["xdg-open", str(safe_path)], check=True)
        else:
            raise HTTPException(status_code=501, detail=f"Unsupported operating system: {system}")

        return {"success": True, "message": f"Opened {safe_path.name}"}
    except subprocess.CalledProcessError as e:
        raise _fail(RuntimeError(f"Failed to open PDF: {e}"))
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/embedding_models")
def list_embedding_models():
    """List all available embedding models (local and cloud)."""
    from backend.embed_utils import EMBEDDING_MODELS
    from backend.embedding_providers import CLOUD_EMBEDDING_MODELS
    try:
        local_models = [
            {"id": model_id, **config}
            for model_id, config in EMBEDDING_MODELS.items()
        ]
        cloud_models = [
            {"id": model_id, **config}
            for model_id, config in CLOUD_EMBEDDING_MODELS.items()
        ]
        return {"models": local_models + cloud_models}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/providers")
def list_providers():
    """List all available LLM providers and their metadata."""
    from backend.model_providers import get_provider_info
    try:
        providers = get_provider_info()
        return {"providers": providers}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/providers/{provider_id}/models")
def list_provider_models(provider_id: str):
    """List available models for a specific provider."""
    from backend.model_providers import get_provider
    try:
        provider = get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
        
        settings = load_settings()
        provider_config = settings.get("providers", {}).get(provider_id, {})
        credentials = provider_config.get("credentials", {})
        
        models = provider.list_models(credentials)
        
        return {
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "description": m.description,
                    "context_length": m.context_length
                }
                for m in models
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/providers/{provider_id}/validate")
def validate_provider(provider_id: str, credentials: dict = Body(...)):
    """Validate credentials for a specific provider.
    
    For providers with dynamic model discovery (Google, OpenAI, Mistral, Groq, OpenRouter),
    also returns dynamically discovered models.
    """
    from backend.model_providers import get_provider
    try:
        provider = get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
        
        # Always load credentials from stored settings for validation
        # This ensures we test the actual saved configuration, not form data
        settings = load_settings()
        provider_config = settings.get("providers", {}).get(provider_id, {})
        creds = provider_config.get("credentials", {})
        
        logger.debug("[Validation] Loading stored credentials for %s", provider_id)
        
        # For providers with dynamic discovery, use enhanced validation
        providers_with_discovery = ["google", "openai", "mistral", "groq", "openrouter", "anthropic", "github_models"]
        
        if provider_id in providers_with_discovery and hasattr(provider, 'validate_credentials_and_list_models'):
            result = provider.validate_credentials_and_list_models(creds)
            
            if result["valid"]:
                # Convert ModelInfo objects to dicts for JSON serialization
                models_dict = [
                    {
                        "id": m.id,
                        "name": m.name,
                        "description": m.description,
                        "context_length": m.context_length
                    }
                    for m in result["models"]
                ]
                
                return {
                    "valid": True,
                    "provider": provider_id,
                    "models": models_dict,
                    "message": result["message"]
                }
            else:
                return {
                    "valid": False,
                    "provider": provider_id,
                    "error": result.get("error", "Validation failed")
                }
        
        # For other providers (Anthropic, Ollama, LM Studio), use standard validation
        is_valid = provider.validate_credentials(creds)
        return {"valid": is_valid, "provider": provider_id}
    except Exception as e:
        error_msg = str(e)
        # Determine error type
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            return {"valid": False, "error": "Invalid credentials", "details": error_msg}
        elif "connection" in error_msg.lower():
            return {"valid": False, "error": "Connection failed", "details": error_msg}
        else:
            return {"valid": False, "error": error_msg}


@app.get("/api/providers/{provider_id}/status")
def provider_status(provider_id: str):
    """Check the status and availability of a specific provider."""
    from backend.model_providers import get_provider
    try:
        provider = get_provider(provider_id)
        if not provider:
            return {"status": "unknown", "error": f"Provider '{provider_id}' not found"}
        
        settings = load_settings()
        provider_config = settings.get("providers", {}).get(provider_id, {})
        
        if not provider_config.get("enabled"):
            return {
                "status": "disabled",
                "provider": provider_id,
                "message": "Provider is disabled in settings"
            }
        
        credentials = provider_config.get("credentials", {})
        
        try:
            is_valid = provider.validate_credentials(credentials)
            if is_valid:
                return {
                    "status": "available",
                    "provider": provider_id,
                    "label": provider.label
                }
            else:
                return {
                    "status": "unavailable",
                    "provider": provider_id,
                    "message": "Credentials validation failed"
                }
        except Exception as validation_error:
            return {
                "status": "error",
                "provider": provider_id,
                "message": str(validation_error)
            }
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/library/tags")
def list_library_tags():
    """
    Get all unique tags from the Zotero library.
    
    Returns:
        {
            "tags": [str] - List of tag names sorted alphabetically
        }
    """
    try:
        tags = chatbot.zlib.get_all_tags()
        return {"tags": tags}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/library/collections")
def list_library_collections():
    """
    Get all collections from the Zotero library with item counts.
    
    Returns:
        {
            "collections": [
                {"name": str, "count": int}
            ]
        }
    """
    try:
        collections = chatbot.zlib.get_all_collections()
        return {"collections": collections}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/library/item_types")
def list_library_item_types():
    """
    Get all item types from the Zotero library with counts.
    Only includes types for items with PDFs.
    
    Returns:
        {
            "item_types": [
                {"name": str, "count": int}
            ]
        }
    """
    try:
        item_types = chatbot.zlib.get_all_item_types()
        return {"item_types": item_types}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/settings")
def get_settings():
    """Get current application settings."""
    try:
        settings = load_settings()
        
        # Mask API keys for security - show only last 3 chars
        masked_settings = settings.copy()
        if "providers" in masked_settings:
            masked_providers = {}
            for provider_id, provider_config in masked_settings["providers"].items():
                masked_provider = provider_config.copy()
                if "credentials" in masked_provider:
                    masked_creds = masked_provider["credentials"].copy()
                    if "api_key" in masked_creds and masked_creds["api_key"]:
                        # Show last 3 chars, mask the rest
                        api_key = masked_creds["api_key"]
                        if len(api_key) > 3:
                            masked_creds["api_key"] = "•" * (len(api_key) - 3) + api_key[-3:]
                        else:
                            masked_creds["api_key"] = "•" * len(api_key)
                    masked_provider["credentials"] = masked_creds
                masked_providers[provider_id] = masked_provider
            masked_settings["providers"] = masked_providers
        
        return masked_settings
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/detect_api_keys")
def detect_api_keys():
    """Detect API keys from environment variables.
    
    Returns a dict of provider IDs and whether their API keys are set via environment variables.
    This helps the UI show warnings when keys are coming from environment rather than 
    being explicitly configured.
    """
    # Map of provider IDs to their common environment variable names
    env_key_mapping = {
        "openai": ["OPENAI_API_KEY", "OPENAI_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "mistral": ["MISTRAL_API_KEY"],
        "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "groq": ["GROQ_API_KEY"],
        "openrouter": ["OPENROUTER_API_KEY"],
    }
    
    detected = {}
    for provider_id, env_vars in env_key_mapping.items():
        for env_var in env_vars:
            if os.getenv(env_var):
                detected[provider_id] = {
                    "detected": True,
                    "env_var": env_var,
                }
                break
        if provider_id not in detected:
            detected[provider_id] = {"detected": False}
    
    return {"detected_keys": detected}


@app.get("/api/profiles")
def list_profiles():
    """List all available profiles."""
    try:
        profiles = profile_manager.list_profiles()
        active = profile_manager.get_active_profile()
        return {
            "profiles": profiles,
            "activeProfileId": active['id'] if active else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/profiles")
def create_profile(payload: dict = Body(...)):
    """Create a new profile.
    
    Expects JSON body: {"id": "my-profile", "name": "My Profile", "description": "Optional"}
    """
    try:
        profile_id = payload.get("id")
        name = payload.get("name")
        description = payload.get("description", "")
        
        if not profile_id or not name:
            raise HTTPException(status_code=400, detail="Missing required fields: id, name")
        
        metadata = profile_manager.create_profile(profile_id, name, description)
        return {"success": True, "profile": metadata}
    except ValueError as e:
        raise _fail(e, 400)
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: str):
    """Get metadata for a specific profile."""
    try:
        _validate_profile_id(profile_id)
        profile = profile_manager.get_profile(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
        return {"profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.put("/api/profiles/{profile_id}")
def update_profile(profile_id: str, payload: dict = Body(...)):
    """Update profile metadata.
    
    Expects JSON body: {"name": "New Name", "description": "New Description"}
    """
    try:
        _validate_profile_id(profile_id)
        name = payload.get("name")
        description = payload.get("description")
        
        success = profile_manager.update_profile(profile_id, name, description)
        if not success:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
        
        return {"success": True, "profile": profile_manager.get_profile(profile_id)}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str, force: bool = Query(False)):
    """Delete a profile and all its data."""
    try:
        _validate_profile_id(profile_id)
        success = profile_manager.delete_profile(profile_id, force=force)
        if not success:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
        return {"success": True}
    except ValueError as e:
        raise _fail(e, 400)
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/profiles/{profile_id}/activate")
def activate_profile(profile_id: str):
    """Set the active profile."""
    global chatbot
    try:
        _validate_profile_id(profile_id)
        if chatbot.is_indexing:
            raise HTTPException(status_code=409, detail="Indexing is running. Wait for it to finish or stop it before switching profiles.")
        success = profile_manager.set_active_profile(profile_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
        
        # Reinitialize chatbot with new profile
        chatbot = initialize_chatbot()
        
        return {
            "success": True,
            "activeProfile": profile_manager.get_active_profile()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


DESK_PIN_LIMIT, DESK_LOG_LIMIT = 500, 50


def _desk_state(body) -> dict:
    """Keep only the fields the desk writes, with sizes capped: the file is read back into the page."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Send an object with 'pins' and 'log'.")

    def text(value, limit):
        return str(value or "")[:limit]

    def number(value):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def scope(value):
        try:
            return _clean_filters(value) or {}
        except HTTPException:
            return {}

    pins = [
        {"id": text(p.get("id"), 300), "itemId": text(p.get("itemId"), 64), "label": text(p.get("label"), 300),
         "page": number(p.get("page")), "text": text(p.get("text"), 4000), "query": text(p.get("query"), 500),
         "at": number(p.get("at")) or 0}
        for p in (body.get("pins") or []) if isinstance(p, dict) and p.get("id")
    ][-DESK_PIN_LIMIT:]  # pins are appended: keep the newest
    log = [
        {"query": text(e.get("query"), 500), "scope": scope(e.get("scope")), "count": number(e.get("count")) or 0,
         "at": number(e.get("at")) or 0}
        for e in (body.get("log") or []) if isinstance(e, dict) and e.get("query")
    ][:DESK_LOG_LIMIT]
    return {"pins": pins, "log": log}


@app.get("/api/profiles/{profile_id}/desk")
def get_desk_state(profile_id: str):
    """The reference desk's pins and query log for a profile."""
    _validate_profile_id(profile_id)
    return profile_manager.load_desk_state(profile_id)


@app.put("/api/profiles/{profile_id}/desk")
def put_desk_state(profile_id: str, body: dict = Body(...)):
    """Replace the reference desk's pins and query log for a profile."""
    _validate_profile_id(profile_id)
    if not profile_manager.get_profile(profile_id):
        raise HTTPException(status_code=404, detail="No such profile.")
    state = _desk_state(body)
    if not profile_manager.save_desk_state(profile_id, state):
        raise HTTPException(status_code=500, detail="Could not save the desk's pins and log.")
    return state


@app.get("/api/profiles/{profile_id}/sessions")
def get_profile_sessions(profile_id: str):
    """Get sessions for a specific profile."""
    try:
        _validate_profile_id(profile_id)
        sessions_data = profile_manager.load_profile_sessions(profile_id)
        return sessions_data
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/profiles/{profile_id}/sessions")
def save_profile_sessions(profile_id: str, sessions_data: dict = Body(...)):
    """Save sessions for a specific profile."""
    try:
        _validate_profile_id(profile_id)
        success = profile_manager.save_profile_sessions(profile_id, sessions_data)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save sessions")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


@app.post("/api/settings")
def update_settings(settings: dict = Body(...)):
    """Update application settings."""
    global DB_PATH, chatbot
    try:
        current_settings = load_settings()
        if chatbot.is_indexing and settings.get("embeddingModel") not in (None, chatbot.embedding_model_id):
            raise HTTPException(status_code=409, detail="Indexing is running. Wait for it to finish or stop it before changing the embedding model.")
        
        # Deep copy to avoid mutation issues
        import copy
        updated_settings = copy.deepcopy(current_settings)
        
        # Handle masked API keys - preserve existing keys if "***" is sent
        # Process providers specially to handle credentials correctly
        if "providers" in settings:
            for provider_id, provider_config in settings.get("providers", {}).items():
                # Initialize provider if it doesn't exist
                if provider_id not in updated_settings["providers"]:
                    updated_settings["providers"][provider_id] = {
                        "enabled": False,
                        "credentials": {}
                    }
                
                # Update enabled status
                if "enabled" in provider_config:
                    updated_settings["providers"][provider_id]["enabled"] = provider_config["enabled"]
                
                # Handle credentials with masking logic
                if "credentials" in provider_config:
                    current_creds = updated_settings["providers"][provider_id].get("credentials", {})
                    new_creds = provider_config["credentials"]
                    
                    # Merge credentials, preserving masked keys
                    for key, value in new_creds.items():
                        if key == "api_key" and (value == "***" or (value and "•" in str(value))):
                            # Keep existing API key if new value is masked (either *** or contains •)
                            if "api_key" in current_creds:
                                updated_settings["providers"][provider_id]["credentials"]["api_key"] = current_creds["api_key"]
                        else:
                            # Update with new value
                            updated_settings["providers"][provider_id]["credentials"][key] = value
        
        # Update top-level settings (but not providers, already handled)
        for key, value in settings.items():
            if key != "providers":
                updated_settings[key] = value
        
        # Auto-switch activeProviderId if it refers to a disabled provider
        _active_pid = updated_settings.get("activeProviderId", "ollama")
        _updated_providers = updated_settings.get("providers", {})
        if not _updated_providers.get(_active_pid, {}).get("enabled", False):
            _fallback_pid = next(
                (pid for pid, cfg in _updated_providers.items() if cfg.get("enabled", False)),
                _active_pid
            )
            if _fallback_pid != _active_pid:
                logger.info(f"[update_settings] Active provider '{_active_pid}' is disabled; switching to '{_fallback_pid}'")
                updated_settings["activeProviderId"] = _fallback_pid
                updated_settings["activeModel"] = ""

        if save_settings(updated_settings):
            # Update global paths if they changed
            if "zoteroPath" in settings:
                DB_PATH = settings["zoteroPath"]
            
            # Reinitialize chatbot with new provider or embedding settings
            if "activeProviderId" in settings or "activeModel" in settings or "embeddingModel" in settings:
                try:
                    provider_credentials = {}
                    for pid, pconfig in updated_settings.get("providers", {}).items():
                        if pconfig.get("enabled"):
                            provider_credentials[pid] = pconfig.get("credentials", {})

                    # Keep embedding credentials in sync whenever any provider creds change
                    from backend.embed_utils import set_embedding_credentials
                    for pid, creds in provider_credentials.items():
                        set_embedding_credentials(pid, creds)

                    # Update provider settings if changed
                    if "activeProviderId" in settings or "activeModel" in settings:
                        chatbot.update_provider_settings(
                            active_provider_id=updated_settings.get("activeProviderId", "ollama"),
                            active_model=updated_settings.get("activeModel"),
                            credentials=provider_credentials
                        )
                    
                    # Update embedding model if changed - requires new ChromaClient
                    if "embeddingModel" in settings:
                        new_embedding_model = updated_settings.get("embeddingModel", "bge-base")
                        old_embedding_model = chatbot.embedding_model_id
                        if new_embedding_model != old_embedding_model:
                            logger.info(f"Switching embedding model from {old_embedding_model} to {new_embedding_model}")
                            logger.info(f"Creating new ChromaClient with collection: zotero_lib_{new_embedding_model}")
                            chatbot.embedding_model_id = new_embedding_model
                            # Reinitialize ChromaClient with new embedding model
                            # Use profile-specific path if chromaPath not customized
                            active = profile_manager.get_active_profile()
                            profile_chroma_path = profile_manager.get_profile_chroma_path(active['id'])
                            chroma_path = updated_settings.get("chromaPath", profile_chroma_path)
                            chatbot.chroma = ChromaClient(chroma_path, embedding_model_id=new_embedding_model)
                        else:
                            logger.info(f"Embedding model unchanged: {chatbot.embedding_model_id}")
                except Exception as e:
                    logger.warning(f"Warning: Failed to update chatbot settings: {e}")
            
            return {"success": True, "message": "Settings saved successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to save settings")
    except HTTPException:
        raise
    except Exception as e:
        raise _fail(e)


