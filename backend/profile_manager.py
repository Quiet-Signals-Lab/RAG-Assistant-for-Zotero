# profile_manager.py
"""
Profile Manager for Zotero LLM Plugin

Manages user profiles with isolated settings, sessions, and data storage.
Each profile has its own:
- Settings (LLM provider, embedding model, paths)
- Chat sessions history
- Vector database (separate ChromaDB instance)

Best practices:
- All data stored locally in ~/.zotero-llm/profiles/
- Profile isolation for multi-user scenarios
- Automatic profile creation and validation
- Thread-safe profile switching
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import shutil
import logging
import threading
import time

logger = logging.getLogger(__name__)


class ProfileManager:
    """Manages user profiles with isolated settings and data."""

    # Requests run on a thread pool, and Windows refuses to replace a file that is open.
    _io_lock = threading.Lock()

    @classmethod
    def _write_json(cls, path: Path, data: Any) -> None:
        """Write through a temporary file, so a crash or a full disk never costs the old file."""
        tmp = path.with_name(path.name + ".tmp")
        with cls._io_lock:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)  # settings.json holds API keys
            os.replace(tmp, path)

    @classmethod
    def _read_json(cls, path: Path) -> Any:
        """Read a JSON file. A brief error (antivirus or a sync tool holding it) is retried; one that
        lasts is raised, since treating it as "no data" would let the next save overwrite the file."""
        for attempts_left in (2, 1, 0):
            try:
                with cls._io_lock:
                    with open(path, 'r', encoding='utf-8') as f:
                        return json.load(f)
            except FileNotFoundError:
                raise
            except OSError:
                if not attempts_left:
                    raise
                time.sleep(0.1)
    
    BASE_DIR = Path.home() / ".zotero-llm"
    PROFILES_DIR = BASE_DIR / "profiles"
    ACTIVE_PROFILE_FILE = BASE_DIR / "active_profile.json"
    
    def __init__(self):
        """Initialize profile manager and ensure directory structure exists."""
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)
        self.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[ProfileManager] Initialized with BASE_DIR: {self.BASE_DIR}")
        logger.info(f"[ProfileManager] PROFILES_DIR: {self.PROFILES_DIR}")
        logger.info(f"[ProfileManager] ACTIVE_PROFILE_FILE: {self.ACTIVE_PROFILE_FILE}")
        
        # Ensure default profile exists
        if not self.list_profiles():
            logger.info("[ProfileManager] No profiles found, creating default profile")
            self.create_profile("default", "Default Profile")
            self.set_active_profile("default")
        else:
            existing_profiles = self.list_profiles()
            logger.info(f"[ProfileManager] Found {len(existing_profiles)} existing profiles: {[p['id'] for p in existing_profiles]}")
    
    def get_profile_dir(self, profile_id: str) -> Path:
        """Get the directory path for a profile."""
        return self.PROFILES_DIR / profile_id
    
    def get_profile_settings_file(self, profile_id: str) -> Path:
        """Get the settings file path for a profile."""
        return self.get_profile_dir(profile_id) / "settings.json"
    
    def get_profile_sessions_file(self, profile_id: str) -> Path:
        """Get the sessions file path for a profile."""
        return self.get_profile_dir(profile_id) / "sessions.json"
    
    def get_profile_chroma_path(self, profile_id: str) -> str:
        """Get the ChromaDB path for a profile."""
        return str(self.get_profile_dir(profile_id) / "chroma")
    
    def get_profile_metadata_file(self, profile_id: str) -> Path:
        """Get the metadata file path for a profile."""
        return self.get_profile_dir(profile_id) / "profile.json"
    
    def create_profile(self, profile_id: str, name: str, description: str = "") -> Dict[str, Any]:
        """
        Create a new profile with isolated storage.
        
        Args:
            profile_id: Unique identifier for the profile (slug-safe)
            name: Display name for the profile
            description: Optional description
            
        Returns:
            Profile metadata dictionary
            
        Raises:
            ValueError: If profile already exists or ID is invalid
        """
        # Validate profile ID (alphanumeric, hyphens, underscores only)
        if not profile_id or not all(c.isalnum() or c in '-_' for c in profile_id):
            raise ValueError("Profile ID must contain only alphanumeric characters, hyphens, and underscores")
        
        profile_dir = self.get_profile_dir(profile_id)
        
        # A folder whose profile.json is unreadable can be repaired; only that file is rewritten.
        if self.get_profile(profile_id):
            raise ValueError(f"Profile '{profile_id}' already exists")
        
        # Create profile directory structure
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "chroma").mkdir(parents=True, exist_ok=True)
        
        # Create profile metadata
        metadata = {
            "id": profile_id,
            "name": name,
            "description": description,
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "updatedAt": datetime.utcnow().isoformat() + "Z",
            "version": "1.0"
        }
        
        metadata_file = self.get_profile_metadata_file(profile_id)
        self._write_json(metadata_file, metadata)
        
        # Initialize empty settings (will use defaults)
        settings_file = self.get_profile_settings_file(profile_id)
        if not settings_file.exists():
            self._write_json(settings_file, {})
        
        # Initialize empty sessions
        sessions_file = self.get_profile_sessions_file(profile_id)
        if not sessions_file.exists():
            self._write_json(sessions_file, {"sessions": {}, "currentSessionId": None})
        
        logger.info(f"Created profile: {profile_id} ({name})")
        return metadata
    
    def list_profiles(self) -> List[Dict[str, Any]]:
        """
        List all available profiles.
        
        Returns:
            List of profile metadata dictionaries
        """
        profiles = []
        
        if not self.PROFILES_DIR.exists():
            return profiles
        
        for profile_dir in self.PROFILES_DIR.iterdir():
            if not profile_dir.is_dir():
                continue
            
            metadata_file = profile_dir / "profile.json"
            if metadata_file.exists():
                try:
                    profiles.append(self._read_json(metadata_file))
                except Exception as e:
                    logger.warning(f"Warning: Failed to load profile metadata for {profile_dir.name}: {e}")
        
        # Sort by creation date (newest first)
        profiles.sort(key=lambda p: p.get('createdAt', ''), reverse=True)
        return profiles
    
    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific profile.
        
        Args:
            profile_id: Profile identifier
            
        Returns:
            Profile metadata dictionary or None if not found
        """
        metadata_file = self.get_profile_metadata_file(profile_id)
        
        if not metadata_file.exists():
            return None
        
        try:
            return self._read_json(metadata_file)
        except Exception as e:
            logger.error(f"Error reading profile metadata: {e}")
            return None
    
    def update_profile(self, profile_id: str, name: Optional[str] = None, description: Optional[str] = None) -> bool:
        """
        Update profile metadata.
        
        Args:
            profile_id: Profile identifier
            name: New name (optional)
            description: New description (optional)
            
        Returns:
            True if successful, False otherwise
        """
        metadata = self.get_profile(profile_id)
        if not metadata:
            return False
        
        if name is not None:
            metadata["name"] = name
        if description is not None:
            metadata["description"] = description
        
        metadata["updatedAt"] = datetime.utcnow().isoformat() + "Z"
        
        metadata_file = self.get_profile_metadata_file(profile_id)
        try:
            self._write_json(metadata_file, metadata)
            return True
        except Exception as e:
            logger.error(f"Error updating profile metadata: {e}")
            return False
    
    def delete_profile(self, profile_id: str, force: bool = False) -> bool:
        """
        Delete a profile and all its data.
        
        Args:
            profile_id: Profile identifier
            force: If True, delete even if it's the active profile
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            ValueError: If trying to delete active profile without force=True
        """
        active = self.get_active_profile()
        is_active = bool(active) and active.get('id') == profile_id
        if is_active and not force:
            raise ValueError("Cannot delete active profile. Switch to another profile first or use force=True")
        if is_active and len(self.list_profiles()) < 2:
            raise ValueError("Cannot delete the only profile")
        
        profile_dir = self.get_profile_dir(profile_id)
        
        if not profile_dir.exists():
            return False
        
        try:
            shutil.rmtree(profile_dir)
            logger.info(f"Deleted profile: {profile_id}")
            
            # If this was the active profile, clear active profile
            if is_active:
                self.ACTIVE_PROFILE_FILE.unlink(missing_ok=True)
            
            return True
        except Exception as e:
            logger.error(f"Error deleting profile: {e}")
            return False
    
    def get_active_profile(self) -> Optional[Dict[str, Any]]:
        """
        Get the currently active profile.
        
        Returns:
            Profile metadata dictionary or None if no active profile
        """
        try:
            profile_id = self._read_json(self.ACTIVE_PROFILE_FILE).get('activeProfileId')
            profile = self.get_profile(profile_id) if profile_id else None
            if profile:
                return profile
            logger.warning(f"[ProfileManager] Active profile '{profile_id}' not found")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"[ProfileManager] Error reading active profile: {e}")

        # No file, or one naming a deleted profile: any profile beats refusing to start.
        profiles = self.list_profiles()
        if profiles:
            logger.info(f"[ProfileManager] Auto-selecting first profile: {profiles[0]['id']}")
            self.set_active_profile(profiles[0]['id'])
            return profiles[0]
        return None
    
    def set_active_profile(self, profile_id: str) -> bool:
        """
        Set the active profile.
        
        Args:
            profile_id: Profile identifier
            
        Returns:
            True if successful, False otherwise
        """
        # Verify profile exists
        if not self.get_profile(profile_id):
            return False
        
        try:
            self._write_json(self.ACTIVE_PROFILE_FILE, {
                "activeProfileId": profile_id,
                "switchedAt": datetime.utcnow().isoformat() + "Z"
            })
            logger.info(f"Switched to profile: {profile_id}")
            return True
        except Exception as e:
            logger.error(f"Error setting active profile: {e}")
            return False
    
    def load_profile_settings(self, profile_id: str) -> Dict[str, Any]:
        """
        Load settings for a specific profile.
        
        Args:
            profile_id: Profile identifier
            
        Returns:
            Settings dictionary (empty if not found)
        """
        settings_file = self.get_profile_settings_file(profile_id)
        
        if not settings_file.exists():
            logger.info(f"[ProfileManager] Settings file not found, returning empty dict")
            return {}
        
        try:
            return self._read_json(settings_file)
        except ValueError as e:
            # The app carries on with defaults, and the next save would overwrite this file:
            # keep it, since it may hold the only copy of the user's API keys.
            logger.error(f"Unreadable settings, moved to settings.json.bad: {e}")
            try:
                os.replace(settings_file, settings_file.with_suffix(".json.bad"))
            except OSError as move_error:
                logger.error(f"Could not move the unreadable settings aside: {move_error}")
            return {}
    
    def save_profile_settings(self, profile_id: str, settings: Dict[str, Any]) -> bool:
        """
        Save settings for a specific profile.
        
        Args:
            profile_id: Profile identifier
            settings: Settings dictionary
            
        Returns:
            True if successful, False otherwise
        """
        settings_file = self.get_profile_settings_file(profile_id)
        
        try:
            self._write_json(settings_file, settings)
            
            # Update profile metadata timestamp
            metadata = self.get_profile(profile_id)
            if metadata:
                metadata["updatedAt"] = datetime.utcnow().isoformat() + "Z"
                self._write_json(self.get_profile_metadata_file(profile_id), metadata)
            
            return True
        except Exception as e:
            logger.error(f"Error saving profile settings: {e}")
            return False
    
    def load_profile_sessions(self, profile_id: str) -> Dict[str, Any]:
        """
        Load sessions for a specific profile.
        
        Args:
            profile_id: Profile identifier
            
        Returns:
            Sessions dictionary with format: {"sessions": {}, "currentSessionId": None}
        """
        sessions_file = self.get_profile_sessions_file(profile_id)
        
        if not sessions_file.exists():
            return {"sessions": {}, "currentSessionId": None}
        
        # An unreadable file raises: answering "no sessions" would let the UI save over them.
        return self._read_json(sessions_file)
    
    def save_profile_sessions(self, profile_id: str, sessions_data: Dict[str, Any]) -> bool:
        """
        Save sessions for a specific profile.
        
        Args:
            profile_id: Profile identifier
            sessions_data: Sessions dictionary
            
        Returns:
            True if successful, False otherwise
        """
        sessions_file = self.get_profile_sessions_file(profile_id)
        
        try:
            self._write_json(sessions_file, sessions_data)
            
            # Update profile metadata timestamp
            metadata = self.get_profile(profile_id)
            if metadata:
                metadata["updatedAt"] = datetime.utcnow().isoformat() + "Z"
                self._write_json(self.get_profile_metadata_file(profile_id), metadata)
            
            return True
        except Exception as e:
            logger.error(f"Error saving profile sessions: {e}")
            return False
    
    def get_profile_desk_file(self, profile_id: str) -> Path:
        """The reference desk's pins and query log for a profile."""
        return self.get_profile_dir(profile_id) / "desk.json"

    def load_desk_state(self, profile_id: str) -> Dict[str, Any]:
        """Pins and query log; empty when the desk has not saved any yet.

        An unreadable file is moved aside (desk.json.bad) rather than left for the
        next save to overwrite, so the pins in it can still be recovered.
        """
        path = self.get_profile_desk_file(profile_id)
        try:
            data = self._read_json(path)
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return {"pins": data.get("pins") or [], "log": data.get("log") or [], "context": data.get("context") or []}
        except FileNotFoundError:
            return {"pins": [], "log": [], "context": []}
        except ValueError as e:
            logger.error(f"Unreadable desk state, moved to desk.json.bad: {e}")
            try:
                os.replace(path, path.with_suffix(".json.bad"))
            except OSError as move_error:
                logger.error(f"Could not move the unreadable desk state aside: {move_error}")
            return {"pins": [], "log": [], "context": []}

    def save_desk_state(self, profile_id: str, state: Dict[str, Any]) -> bool:
        path = self.get_profile_desk_file(profile_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_json(path, state)
            return True
        except Exception as e:
            logger.error(f"Error saving desk state: {e}")
            return False

    def export_profile(self, profile_id: str, export_path: str) -> bool:
        """
        Export a profile to a ZIP file (excluding vector database for size reasons).
        
        Args:
            profile_id: Profile identifier
            export_path: Path to save the export file
            
        Returns:
            True if successful, False otherwise
        """
        import zipfile
        
        profile_dir = self.get_profile_dir(profile_id)
        if not profile_dir.exists():
            return False
        
        try:
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add profile metadata
                zipf.write(profile_dir / "profile.json", "profile.json")
                
                # Add settings
                settings_file = profile_dir / "settings.json"
                if settings_file.exists():
                    zipf.write(settings_file, "settings.json")
                
                # Add sessions
                sessions_file = profile_dir / "sessions.json"
                if sessions_file.exists():
                    zipf.write(sessions_file, "sessions.json")
            
            logger.info(f"Exported profile to: {export_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting profile: {e}")
            return False
    
    def import_profile(self, import_path: str, new_profile_id: Optional[str] = None) -> Optional[str]:
        """
        Import a profile from a ZIP file.
        
        Args:
            import_path: Path to the import file
            new_profile_id: Optional new profile ID (generates one if not provided)
            
        Returns:
            Profile ID if successful, None otherwise
        """
        import zipfile
        import tempfile
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract to temporary directory
                with zipfile.ZipFile(import_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Read profile metadata
                metadata_path = Path(temp_dir) / "profile.json"
                if not metadata_path.exists():
                    logger.error("Error: Invalid profile export (missing profile.json)")
                    return None
                
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Generate new profile ID if not provided
                if not new_profile_id:
                    base_id = metadata.get('id', 'imported')
                    new_profile_id = base_id
                    counter = 1
                    while self.get_profile(new_profile_id):
                        new_profile_id = f"{base_id}_{counter}"
                        counter += 1
                
                # Create new profile
                self.create_profile(
                    new_profile_id,
                    f"{metadata.get('name', 'Imported Profile')} (Imported)",
                    metadata.get('description', '')
                )
                
                # Copy settings
                settings_path = Path(temp_dir) / "settings.json"
                if settings_path.exists():
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                    self.save_profile_settings(new_profile_id, settings)
                
                # Copy sessions
                sessions_path = Path(temp_dir) / "sessions.json"
                if sessions_path.exists():
                    with open(sessions_path, 'r', encoding='utf-8') as f:
                        sessions = json.load(f)
                    self.save_profile_sessions(new_profile_id, sessions)
                
                logger.info(f"Imported profile as: {new_profile_id}")
                return new_profile_id
        except Exception as e:
            logger.error(f"Error importing profile: {e}")
            return None
