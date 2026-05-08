import base64
import hashlib
import json
import os
import uuid

from cryptography.fernet import Fernet
from PyQt5.QtCore import QStandardPaths

from snekbooru.common.constants import DEFAULT_AI_MODEL, DEFAULT_HOTKEYS

# Initialize as an empty placeholder. It will be populated after the app is created.
SETTINGS = {}

def _get_hardware_id():
    """
    Generates a machine-specific ID. Tries multiple methods to ensure stability
    across app versions and obfuscation.
    """
    # 1. Try to get a stable machine ID from environment or system
    try:
        # On Windows, we can use the machine GUID
        if os.name == 'nt':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            if guid: return str(guid)
    except Exception:
        pass

    # 2. Fallback to a stable hardware identifier
    try:
        import subprocess
        if os.name == 'nt':
            # Get CPU serial or similar stable ID via WMIC
            cmd = "wmic csproduct get uuid"
            uuid_str = subprocess.check_output(cmd, shell=True).decode().split('\n')[1].strip()
            if uuid_str: return uuid_str
    except Exception:
        pass

    # 3. Last resort: getnode()
    try:
        mac = uuid.getnode()
        if not ((mac >> 40) % 2):
            return str(mac)
    except Exception:
        pass

    return "snekbooru_stable_fallback_v2"

def _get_encryption_key():
    """
    Generates a machine-specific key. We now try to make this as stable as possible
    to avoid data loss between app versions.
    """
    hw_id = _get_hardware_id()
    # Use SHA256 to get a 32-byte key
    key = hashlib.sha256(hw_id.encode('utf-8', 'ignore')).digest()
    return base64.urlsafe_b64encode(key)

def _get_storage_path():
    """Returns the path to the encrypted data file in a stable, version-independent location.
    Uses a hardcoded path under LOCALAPPDATA to ensure cross-version compatibility.
    QStandardPaths.AppLocalDataLocation changes based on app name/org which breaks
    when the binary is obfuscated or renamed between versions."""
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    else:
        base = os.environ.get('XDG_DATA_HOME', os.path.join(os.path.expanduser('~'), '.local', 'share'))
    path = os.path.join(base, 'Snekbooru')
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, "user.dat")

def get_app_data_dir():
    """Returns the stable app data directory path that's version/obfuscation-independent.
    This should be used for all app data including downloads, themes, fonts, etc."""
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    else:
        base = os.environ.get('XDG_DATA_HOME', os.path.join(os.path.expanduser('~'), '.local', 'share'))
    path = os.path.join(base, 'Snekbooru')
    os.makedirs(path, exist_ok=True)
    return path

def get_database_file_path(db_name):
    """Returns the path to a database file in the stable app data directory.
    
    Args:
        db_name: Database file name (e.g., 'favorites.db', 'local_library.db')
    
    Returns:
        Path to the database file in the stable app data directory
    """
    return os.path.join(get_app_data_dir(), db_name)

_ENCRYPTION_KEY = _get_encryption_key()
_STORAGE_PATH = _get_storage_path()

# Auto-migrate data from old QStandardPaths location if it exists
def _migrate_old_data():
    """Check for data at the old Qt-based storage path and migrate if needed.
    This handles migration from:
    - Old AppLocalDataLocation paths (when app name/version changed)
    - Old theme/font directories
    - Old download directories
    """
    import shutil
    if os.path.exists(_STORAGE_PATH):
        pass  # New path already has data, but continue to migrate other files
    else:
        try:
            # Try to find data at the old location(s) using Qt
            old_path = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
            old_file = os.path.join(old_path, "user.dat")
            if os.path.exists(old_file):
                shutil.copy2(old_file, _STORAGE_PATH)
                print(f"[config] Migrated encrypted data from {old_file} to {_STORAGE_PATH}")
        except Exception:
            pass # Be quiet if old path doesn't exist or migration fails
    
    # Migrate theme files from old Qt path
    try:
        old_app_data = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        old_themes_dir = os.path.join(old_app_data, "themes")
        new_themes_dir = os.path.join(get_app_data_dir(), "themes")
        
        if os.path.exists(old_themes_dir) and not os.path.exists(new_themes_dir):
            shutil.copytree(old_themes_dir, new_themes_dir)
            print(f"[config] Migrated themes from {old_themes_dir} to {new_themes_dir}")
    except Exception as e:
        pass  # Non-fatal
    
    # Migrate font files from old Qt path
    try:
        old_app_data = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        old_fonts_dir = os.path.join(old_app_data, "fonts")
        new_fonts_dir = os.path.join(get_app_data_dir(), "fonts")
        
        if os.path.exists(old_fonts_dir) and not os.path.exists(new_fonts_dir):
            shutil.copytree(old_fonts_dir, new_fonts_dir)
            print(f"[config] Migrated fonts from {old_fonts_dir} to {new_fonts_dir}")
    except Exception as e:
        pass  # Non-fatal
    
    # Migrate database files from nested Qt path (LOCALAPPDATA\Snekbooru\Snekbooru\)
    # Qt creates this nested structure when setOrganizationName/setApplicationName are used
    try:
        nested_app_data = os.path.join(get_app_data_dir(), "Snekbooru")
        if os.path.exists(nested_app_data):
            # Migrate favorites.db
            old_favorites_db = os.path.join(nested_app_data, "favorites.db")
            new_favorites_db = os.path.join(get_app_data_dir(), "favorites.db")
            if os.path.exists(old_favorites_db) and not os.path.exists(new_favorites_db):
                shutil.move(old_favorites_db, new_favorites_db)
                print(f"[config] Migrated favorites.db from {old_favorites_db} to {new_favorites_db}")
            
            # Migrate local_library.db
            old_library_db = os.path.join(nested_app_data, "local_library.db")
            new_library_db = os.path.join(get_app_data_dir(), "local_library.db")
            if os.path.exists(old_library_db) and not os.path.exists(new_library_db):
                shutil.move(old_library_db, new_library_db)
                print(f"[config] Migrated local_library.db from {old_library_db} to {new_library_db}")
            
            # Migrate downloaded images from nested data folder
            old_data_dir = os.path.join(nested_app_data, "data")
            new_data_dir = os.path.join(get_app_data_dir(), "data")
            if os.path.exists(old_data_dir):
                os.makedirs(new_data_dir, exist_ok=True)
                
                # Load current downloads metadata
                try:
                    all_data = load_encrypted_data()
                    downloads_data = all_data.get("downloads_data", {})
                except NameError:
                    # If this runs before functions are defined (though it shouldn't anymore)
                    downloads_data = {}
                except Exception:
                    downloads_data = {}
                files_migrated = 0
                
                try:
                    # Find all files in the old data directory
                    for filename in os.listdir(old_data_dir):
                        old_file_path = os.path.join(old_data_dir, filename)
                        if os.path.isfile(old_file_path):
                            new_file_path = os.path.join(new_data_dir, filename)
                            
                            # Only migrate if not already in new location
                            if not os.path.exists(new_file_path):
                                # Check if this is a thumbnail file (ends with _thumb.jpg)
                                if filename.endswith("_thumb.jpg"):
                                    file_hash = filename[:-10]  # Remove _thumb.jpg
                                else:
                                    # Extract file hash (filename without extension)
                                    file_hash = os.path.splitext(filename)[0]
                                
                                # Move the file
                                shutil.move(old_file_path, new_file_path)
                                files_migrated += 1
                                
                                # Update downloads_data with new path if this is not a thumbnail
                                if not filename.endswith("_thumb.jpg"):
                                    if file_hash in downloads_data:
                                        downloads_data[file_hash]["local_path"] = new_file_path
                                        if "id" not in downloads_data[file_hash]:
                                            downloads_data[file_hash]["id"] = file_hash
                                    else:
                                        # Create minimal entry for orphaned files
                                        _, ext = os.path.splitext(filename)
                                        downloads_data[file_hash] = {
                                            "id": file_hash,
                                            "local_path": new_file_path,
                                            "file_ext": ext.lstrip('.')
                                        }
                    
                    if files_migrated > 0:
                        # Save updated downloads metadata
                        try:
                            all_data = load_encrypted_data()
                            all_data["downloads_data"] = downloads_data
                            save_encrypted_data(all_data)
                            print(f"[config] Migrated {files_migrated} files from {old_data_dir} to {new_data_dir}")
                        except Exception:
                            pass
                        
                        # Try to remove the old directory if it's empty
                        try:
                            if not os.listdir(old_data_dir):
                                os.rmdir(old_data_dir)
                        except:
                            pass  # Directory not empty, that's OK
                except Exception as e:
                    print(f"[config] Error during file migration (non-fatal): {e}")
    except Exception:
        pass

# Call migration at the end of the file after functions are defined


def load_encrypted_data():
    """Loads and decrypts the main data file."""
    try:
        with open(_STORAGE_PATH, "rb") as f:
            encrypted_data = f.read()
        if not encrypted_data: return {}
        fernet = Fernet(_ENCRYPTION_KEY)
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception:
        return {}

def save_encrypted_data(data):
    """Encrypts and saves the main data file.
    Uses a custom default encoder to handle non-serializable objects (like Hentai)."""
    fernet = Fernet(_ENCRYPTION_KEY)
    # Use default=str to convert non-JSON-serializable objects to strings instead of crashing.
    # This is a safety net for complex objects that might end up in favorites/settings.
    json_data = json.dumps(data, indent=2, default=str).encode('utf-8')
    encrypted_data = fernet.encrypt(json_data)
    with open(_STORAGE_PATH, "wb") as f:
        f.write(encrypted_data)

def load_settings():
    all_data = load_encrypted_data()
    loaded_settings = all_data.get("settings", {})
    defaults = {
        "enabled_sources": ["Gelbooru"],
        "gelbooru": {"user_id": "", "api_key": ""},
        "danbooru": {"login": "", "api_key": ""},
        "rule34": {"user_id": "", "api_key": ""},
        "preferred_tags": "",
        "blacklisted_tags": "",
        "active_theme": "Dark (Default)",
        "is_configured": False, # New flag for first-run setup
        "original_theme": "Dark (Default)",
        "incognito_mode": False, "allow_explicit": False,
        "show_download_notification": True,
        "enable_recommendations": True, "allow_loli_shota": False,
        "allow_bestiality": False, "allow_guro": False,
        # Use stable app data path instead of Qt's AppLocalDataLocation to ensure cross-version compatibility
        "download_dir": os.path.join(get_app_data_dir(), "data"),
        "grid_columns": 5,
        "thumbnail_size": 150,
        "language": "en",
        # AI settings are now nested
        "ai_api_key": "",
        "ai_endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "ai_provider": "OpenRouter",
        "gemini_api_key": "",
        "ai_presets": [{
            "name": "SnekAI",
            "persona": "You are SnekAI, a friendly and slightly mischievous snake-themed AI assistant for the Snekbooru application. You are knowledgeable about anime, art, and imageboards. You are helpful and engaging. You can roleplay, but you must adhere to safety guidelines, avoiding the promotion of illegal acts or dangerous content. Erotic roleplay is permissible within these boundaries.",
            "model": DEFAULT_AI_MODEL,
            "allow_spicy": True,
            "formal_casual": 50,
            "helpful_sassy": 20,
            "concise_verbose": 50,
            "creativity": 80,
        }, {
            "name": "Snekai (Gemini)",
            "persona": "You are Snekai, a friendly snake-themed AI assistant powered by Google's Gemini. You are knowledgeable about anime, art, and imageboards. You are helpful, engaging, and witty. You provide thoughtful responses while maintaining a playful personality.",
            "model": "gemini-2.5-pro",
            "provider": "Google Gemini (Experimental)",
            "allow_spicy": True,
            "formal_casual": 45,
            "helpful_sassy": 25,
            "concise_verbose": 55,
            "creativity": 75,
        }],
        "ai_active_preset_index": 0,
        "ai_chats": [{"name": "Default Chat", "history": []}],
        "ai_active_chat_index": 0,
        "hotkeys": DEFAULT_HOTKEYS.copy()
    }
    defaults.update({
        "window_mode": "Windowed",
        "window_size_preset": "1600x900",
        "custom_window_width": 1820,
        "custom_window_height": 1080,
        "auto_scale_grid": False,
        "potato_mode": False,
        "cpu_limit": 1, # Disabled
        "ram_limit": 1, # Disabled
        "temp_cleanup_minutes": 5,
    })

    # Migration for AI presets
    if "ai_persona" in loaded_settings:
        default_preset = {
            "name": loaded_settings.get("ai_name", "SnekAI"),
            "persona": loaded_settings.get("ai_persona", defaults["ai_presets"][0]["persona"]),
            "model": loaded_settings.get("ai_model", defaults["ai_presets"][0]["model"]),
            "allow_spicy": loaded_settings.get("ai_allow_spicy", True),
            "formal_casual": loaded_settings.get("ai_personality_formal_casual", 50),
            "helpful_sassy": loaded_settings.get("ai_personality_helpful_sassy", 20),
            "concise_verbose": loaded_settings.get("ai_personality_concise_verbose", 50),
            "creativity": loaded_settings.get("ai_creativity", 80),
        }
        loaded_settings["ai_presets"] = [default_preset]
        loaded_settings["ai_active_preset_index"] = 0
        
        # Clean up old keys
        for key in ["ai_name", "ai_persona", "ai_model", "ai_allow_spicy", "ai_personality_formal_casual", "ai_personality_helpful_sassy", "ai_personality_concise_verbose", "ai_creativity"]:
            if key in loaded_settings: del loaded_settings[key]

    # Migration from old "source" string to "enabled_sources" list
    if "source" in loaded_settings:
        old_source = loaded_settings["source"]
        if old_source == "All":
            # The old "All" included these specific sources
            loaded_settings["enabled_sources"] = ["Gelbooru", "Danbooru", "Konachan", "Yandere", "Rule34", "Hypnohub", "Zerochan"]
        else:
            loaded_settings["enabled_sources"] = [old_source]
        del loaded_settings["source"]


    for key, default_value in defaults.items():
        if key not in loaded_settings:
            loaded_settings[key] = default_value

    # Migration from old single chat history to new multi-chat structure
    if "ai_chat_history" in loaded_settings:
        if not loaded_settings.get("ai_chats"): # Only migrate if new structure doesn't exist
            loaded_settings["ai_chats"] = [{"name": "Chat 1", "history": loaded_settings["ai_chat_history"]}]
            loaded_settings["ai_active_chat_index"] = 0
        del loaded_settings["ai_chat_history"] # Remove old key

    return loaded_settings

def save_settings(data):
    all_data = load_encrypted_data()
    all_data["settings"] = data
    save_encrypted_data(all_data)

def load_favorites():
    all_data = load_encrypted_data()
    favorites_data = all_data.get("favorites", {})

    # Migration from old format (dict of posts) to new format (dict of categories)
    if favorites_data and all(isinstance(v, dict) and 'id' in v for v in favorites_data.values()):
        print("Migrating old favorites to new categorized format...")
        return {"Uncategorized": favorites_data}

    # Ensure the default "Uncategorized" category exists
    if "Uncategorized" not in favorites_data:
        favorites_data["Uncategorized"] = {}

    return favorites_data

def save_favorites(data):
    all_data = load_encrypted_data()
    all_data["favorites"] = data
    save_encrypted_data(all_data)

def load_downloads_data():
    """Loads the metadata for downloaded posts."""
    all_data = load_encrypted_data()
    # Returns a dict: {file_hash: post_data_with_local_paths}
    return all_data.get("downloads_data", {})

def save_downloads_data(data):
    """Saves the metadata for downloaded posts."""
    all_data = load_encrypted_data()
    all_data["downloads_data"] = data
    save_encrypted_data(all_data)

def find_post_in_favorites(post_id, favorites_data):
    """Finds which category a post belongs to."""
    for category, posts in favorites_data.items():
        if post_id in posts: return category
    return None

def load_search_history():
    all_data = load_encrypted_data()
    return all_data.get("search_history", [])

def save_search_history(data):
    all_data = load_encrypted_data()
    all_data["search_history"] = data
    save_encrypted_data(all_data)

def load_tag_profile():
    all_data = load_encrypted_data()
    return all_data.get("tag_profile", {})

def save_tag_profile(data):
    all_data = load_encrypted_data()
    all_data["tag_profile"] = data
    save_encrypted_data(all_data)

def load_custom_boorus():
    """Loads custom booru configurations from the data file."""
    all_data = load_encrypted_data()
    return all_data.get("custom_boorus", [])

def save_custom_boorus(data):
    """Saves custom booru configurations to the data file."""
    all_data = load_encrypted_data()
    all_data["custom_boorus"] = data
    save_encrypted_data(all_data)

def load_highscores():
    all_data = load_encrypted_data()
    return all_data.get("highscores", {})

def save_highscores(data):
    all_data = load_encrypted_data()
    all_data["highscores"] = data
    save_encrypted_data(all_data)


# Run migration now that all functions are defined
# Note to self: check if migration is succesfull post 6.0.0
try:
    _migrate_old_data()
except Exception as e:
    print(f"[config] Critical error during migration: {e}")
