import base64
import hashlib
import json
import os
import uuid

from cryptography.fernet import Fernet
from PyQt5.QtCore import QStandardPaths

from snekbooru.common.constants import DEFAULT_AI_MODEL, DEFAULT_HOTKEYS


SETTINGS = {}

def _get_hardware_id():
    try:
        if os.name == 'nt':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            if guid: return str(guid)
    except Exception:
        pass

    try:
        import subprocess
        if os.name == 'nt':
            cmd = ["wmic", "csproduct", "get", "uuid"]
            uuid_str = subprocess.check_output(cmd, shell=False).decode().split('\n')[1].strip()
            if uuid_str: return uuid_str
    except Exception:
        pass

    try:
        mac = uuid.getnode()
        if not ((mac >> 40) % 2):
            return str(mac)
    except Exception:
        pass

    return "snekbooru_stable_fallback_v2"

def _get_encryption_key():
    hw_id = _get_hardware_id()
    key = hashlib.sha256(hw_id.encode('utf-8', 'ignore')).digest()
    return base64.urlsafe_b64encode(key)

def _get_storage_path():
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    else:
        base = os.environ.get('XDG_DATA_HOME', os.path.join(os.path.expanduser('~'), '.local', 'share'))
    path = os.path.join(base, 'Snekbooru')
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, "user.dat")

def get_app_data_dir():
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    else:
        base = os.environ.get('XDG_DATA_HOME', os.path.join(os.path.expanduser('~'), '.local', 'share'))
    path = os.path.join(base, 'Snekbooru')
    os.makedirs(path, exist_ok=True)
    return path

def get_database_file_path(db_name):
    return os.path.join(get_app_data_dir(), db_name)

_ENCRYPTION_KEY = _get_encryption_key()
_STORAGE_PATH = _get_storage_path()

def _migrate_old_data():
    import shutil
    if os.path.exists(_STORAGE_PATH):
        pass  
    else:
        try:
            old_path = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
            old_file = os.path.join(old_path, "user.dat")
            if os.path.exists(old_file):
                shutil.copy2(old_file, _STORAGE_PATH)
                print(f"[config] Migrated encrypted data from {old_file} to {_STORAGE_PATH}")
        except Exception:
            pass 
    
    try:
        old_app_data = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        old_themes_dir = os.path.join(old_app_data, "themes")
        new_themes_dir = os.path.join(get_app_data_dir(), "themes")
        
        if os.path.exists(old_themes_dir) and not os.path.exists(new_themes_dir):
            shutil.copytree(old_themes_dir, new_themes_dir)
            print(f"[config] Migrated themes from {old_themes_dir} to {new_themes_dir}")
    except Exception as e:
        pass  
    
    try:
        old_app_data = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        old_fonts_dir = os.path.join(old_app_data, "fonts")
        new_fonts_dir = os.path.join(get_app_data_dir(), "fonts")
        
        if os.path.exists(old_fonts_dir) and not os.path.exists(new_fonts_dir):
            shutil.copytree(old_fonts_dir, new_fonts_dir)
            print(f"[config] Migrated fonts from {old_fonts_dir} to {new_fonts_dir}")
    except Exception as e:
        pass  
    
    try:
        nested_app_data = os.path.join(get_app_data_dir(), "Snekbooru")
        if os.path.exists(nested_app_data):
            old_favorites_db = os.path.join(nested_app_data, "favorites.db")
            new_favorites_db = os.path.join(get_app_data_dir(), "favorites.db")
            if os.path.exists(old_favorites_db) and not os.path.exists(new_favorites_db):
                shutil.move(old_favorites_db, new_favorites_db)
                print(f"[config] Migrated favorites.db from {old_favorites_db} to {new_favorites_db}")
            
            old_library_db = os.path.join(nested_app_data, "local_library.db")
            new_library_db = os.path.join(get_app_data_dir(), "local_library.db")
            if os.path.exists(old_library_db) and not os.path.exists(new_library_db):
                shutil.move(old_library_db, new_library_db)
                print(f"[config] Migrated local_library.db from {old_library_db} to {new_library_db}")
            
            old_data_dir = os.path.join(nested_app_data, "data")
            new_data_dir = os.path.join(get_app_data_dir(), "data")
            if os.path.exists(old_data_dir):
                os.makedirs(new_data_dir, exist_ok=True)
                
                try:
                    all_data = load_encrypted_data()
                    downloads_data = all_data.get("downloads_data", {})
                except NameError:
                    downloads_data = {}
                except Exception:
                    downloads_data = {}
                files_migrated = 0
                
                try:
                    for filename in os.listdir(old_data_dir):
                        old_file_path = os.path.join(old_data_dir, filename)
                        if os.path.isfile(old_file_path):
                            new_file_path = os.path.join(new_data_dir, filename)
                            
                            if not os.path.exists(new_file_path):
                                if filename.endswith("_thumb.jpg"):
                                    file_hash = filename[:-10]  
                                else:
                                    file_hash = os.path.splitext(filename)[0]
                                
                                shutil.move(old_file_path, new_file_path)
                                files_migrated += 1
                                
                                if not filename.endswith("_thumb.jpg"):
                                    if file_hash in downloads_data:
                                        downloads_data[file_hash]["local_path"] = new_file_path
                                        if "id" not in downloads_data[file_hash]:
                                            downloads_data[file_hash]["id"] = file_hash
                                    else:
                                        _, ext = os.path.splitext(filename)
                                        downloads_data[file_hash] = {
                                            "id": file_hash,
                                            "local_path": new_file_path,
                                            "file_ext": ext.lstrip('.')
                                        }
                    
                    if files_migrated > 0:
                        try:
                            all_data = load_encrypted_data()
                            all_data["downloads_data"] = downloads_data
                            save_encrypted_data(all_data)
                            print(f"[config] Migrated {files_migrated} files from {old_data_dir} to {new_data_dir}")
                        except Exception:
                            pass
                        
                        try:
                            if not os.listdir(old_data_dir):
                                os.rmdir(old_data_dir)
                        except:
                            pass  
                except Exception as e:
                    print(f"[config] Error during file migration (non-fatal): {e}")
    except Exception:
        pass


def load_encrypted_data():
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
    fernet = Fernet(_ENCRYPTION_KEY)
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
        "is_configured": False, 
        "original_theme": "Dark (Default)",
        "incognito_mode": False, "allow_explicit": False,
        "show_download_notification": True,
        "enable_recommendations": True, "allow_loli_shota": False,
        "allow_bestiality": False, "allow_guro": False,
        "download_dir": os.path.join(get_app_data_dir(), "data"),
        "grid_columns": 5,
        "thumbnail_size": 150,
        "language": "en",
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
        "cpu_limit": 1, 
        "ram_limit": 1, 
        "temp_cleanup_minutes": 5,
    })

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
        
        for key in ["ai_name", "ai_persona", "ai_model", "ai_allow_spicy", "ai_personality_formal_casual", "ai_personality_helpful_sassy", "ai_personality_concise_verbose", "ai_creativity"]:
            if key in loaded_settings: del loaded_settings[key]

    if "source" in loaded_settings:
        old_source = loaded_settings["source"]
        if old_source == "All":
            loaded_settings["enabled_sources"] = ["Gelbooru", "Danbooru", "Konachan", "Yandere", "Rule34", "Hypnohub", "Zerochan"]
        else:
            loaded_settings["enabled_sources"] = [old_source]
        del loaded_settings["source"]


    for key, default_value in defaults.items():
        if key not in loaded_settings:
            loaded_settings[key] = default_value

    if "ai_chat_history" in loaded_settings:
        if not loaded_settings.get("ai_chats"): 
            loaded_settings["ai_chats"] = [{"name": "Chat 1", "history": loaded_settings["ai_chat_history"]}]
            loaded_settings["ai_active_chat_index"] = 0
        del loaded_settings["ai_chat_history"] 

    return loaded_settings

def save_settings(data):
    all_data = load_encrypted_data()
    all_data["settings"] = data
    save_encrypted_data(all_data)

def load_favorites():
    all_data = load_encrypted_data()
    favorites_data = all_data.get("favorites", {})

    if favorites_data and all(isinstance(v, dict) and 'id' in v for v in favorites_data.values()):
        return {"Uncategorized": favorites_data}

    if "Uncategorized" not in favorites_data:
        favorites_data["Uncategorized"] = {}

    return favorites_data

def save_favorites(data):
    all_data = load_encrypted_data()
    all_data["favorites"] = data
    save_encrypted_data(all_data)

def load_downloads_data():
    all_data = load_encrypted_data()
    return all_data.get("downloads_data", {})

def save_downloads_data(data):
    all_data = load_encrypted_data()
    all_data["downloads_data"] = data
    save_encrypted_data(all_data)

def find_post_in_favorites(post_id, favorites_data):
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
    all_data = load_encrypted_data()
    return all_data.get("custom_boorus", [])

def save_custom_boorus(data):
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


try:
    _migrate_old_data()
except Exception as e:
    print(f"[config] Critical error during migration: {e}")
