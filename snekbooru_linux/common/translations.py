import json
import os

from snekbooru_linux.common.helpers import get_resource_path
from snekbooru_linux.core.config import SETTINGS

TRANSLATIONS = {"en": {}}
SUPPORTED_LANGUAGES = {"en": "English"}

def load_translations():
    """Loads all .sneklang files from the lngpcks directory."""
    global TRANSLATIONS, SUPPORTED_LANGUAGES
    lang_dir = get_resource_path("snekbooru_linux/lngpcks")
    
    if not os.path.isdir(lang_dir):
        print(f"Language directory not found: {lang_dir}")
        return

    for filename in os.listdir(lang_dir):
        if filename.endswith(".sneklang"):
            lang_code = filename.split('.')[0]
            filepath = os.path.join(lang_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    TRANSLATIONS[lang_code] = data
                    native_name = data.get("_lang_name_native", lang_code)
                    english_name = data.get("_lang_name_english", lang_code.capitalize())
                    SUPPORTED_LANGUAGES[lang_code] = f"{native_name} ({english_name})"
                    print(f"Loaded language: {english_name}")
            except Exception as e:
                print(f"Failed to load language file {filename}: {e}")

    all_keys = set()
    for lang_code, trans_dict in TRANSLATIONS.items():
        if lang_code != 'en':
            all_keys.update(trans_dict.keys())
    for key in all_keys:
        if key not in TRANSLATIONS['en']:
            TRANSLATIONS['en'][key] = key

def _tr(text, *args, **kwargs):
    """Translates a given text string to the currently selected language."""
    if not SETTINGS:
        return text.format(*args, **kwargs) if args or kwargs else text
    lang = SETTINGS.get("language", "en")
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS.get("en", {}))
    translated = lang_dict.get(text, text)
    try:
        return translated.format(*args, **kwargs) if args or kwargs else translated
    except (KeyError, IndexError):
        return text.format(*args, **kwargs) if args or kwargs else text