import base64
import hashlib
import json
import os
import uuid

from cryptography.fernet import Fernet
from PyQt5.QtCore import QStandardPaths

from snekbooru_linux.common.constants import DEFAULT_AI_MODEL, DEFAULT_HOTKEYS

# Initialize as an empty placeholder. It will be populated after the app is created.
SETTINGS = {}

# --------------------------- Encrypted Storage --------------------------- #
def _get_hardware_id():
    """
    Generates a machine-specific ID. This is a simple, non-invasive way to get a
    consistent ID for a machine.
    """
    try:
        # getnode() is a good candidate as it's based on the MAC address
        mac = uuid.getnode() 
        # On some systems, getnode() can fail or return a random number.
        # We'll add a fallback.
        if (mac >> 40) % 2:
            # This is a random MAC address, not a good key. Fallback.
            raise ValueError("Random MAC address")
        return str(mac)
    except Exception:
        # Fallback for systems where getnode() is unreliable.
        # This is less unique but better than nothing.
        return "snekbooru_fallback_uuid"

def _get_encryption_key():
    """
    Generates a machine-specific key for obfuscation. This means the settings
    file will not be portable between different computers.
    """
    # Use SHA256 to get a 32-byte key, which is what Fernet needs.
    key = hashlib.sha256(_get_hardware_id().encode('utf-8', 'ignore')).digest()
    return base64.urlsafe_b64encode(key)

def _get_storage_path():
    """Returns the path to the encrypted data file in the standard app data location."""
    path = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, "user.dat")

def get_app_data_dir():
    """Returns the app data directory path. On Linux, uses Qt's standard paths."""
    return QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)

def get_database_file_path(db_name):
    """Returns the path to a database file in the app data directory.
    
    Args:
        db_name: Database file name (e.g., 'favorites.db', 'local_library.db')
    
    Returns:
        Path to the database file in the app data directory
    """
    return os.path.join(get_app_data_dir(), db_name)

_ENCRYPTION_KEY = _get_encryption_key()
_STORAGE_PATH = _get_storage_path()

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
    """Encrypts and saves the main data file."""
    fernet = Fernet(_ENCRYPTION_KEY)
    json_data = json.dumps(data, indent=2).encode('utf-8')
    encrypted_data = fernet.encrypt(json_data)
    with open(_STORAGE_PATH, "wb") as f:
        f.write(encrypted_data)

def _migrate_downloaded_images():
    """Migrate downloaded images from nested data folders if they exist.
    This handles cases where files may be in the old app data location structure."""
    import shutil
    try:
        old_data_dir = os.path.join(get_app_data_dir(), "Snekbooru", "data")
        new_data_dir = os.path.join(get_app_data_dir(), "data")
        
        if os.path.exists(old_data_dir):
            os.makedirs(new_data_dir, exist_ok=True)
            
            # Load current downloads metadata
            downloads_data = load_encrypted_data().get("downloads_data", {})
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
                                else:
                                    # Create minimal entry for orphaned files
                                    _, ext = os.path.splitext(filename)
                                    downloads_data[file_hash] = {
                                        "local_path": new_file_path,
                                        "file_ext": ext.lstrip('.')
                                    }
                
                if files_migrated > 0:
                    # Save updated downloads metadata
                    all_data = load_encrypted_data()
                    all_data["downloads_data"] = downloads_data
                    save_encrypted_data(all_data)
                    print(f"[config] Migrated {files_migrated} files from {old_data_dir} to {new_data_dir}")
                    
                    # Try to remove the old directory if it's empty
                    try:
                        if not os.listdir(old_data_dir):
                            os.rmdir(old_data_dir)
                    except:
                        pass  # Directory not empty, that's OK
            except Exception as e:
                print(f"[config] Error during file migration (non-fatal): {e}")
    except Exception as e:
        print(f"[config] Image migration check failed (non-fatal): {e}")

_migrate_downloaded_images()

# --------------------------- Settings IO --------------------------- #
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
        # Default to a "data" subfolder inside the standard app data location
        "download_dir": os.path.join(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation), "data"),
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

    #
