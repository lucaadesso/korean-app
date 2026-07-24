import json
import os
from typing import Callable

LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")

# Memory cache for loaded languages
_locales_cache = {}

def load_language(lang: str) -> dict:
    if lang in _locales_cache:
        return _locales_cache[lang]
    
    file_path = os.path.join(LOCALES_DIR, f"{lang}.json")
    if not os.path.exists(file_path):
        # Fallback to Italian if not found
        if lang != "it":
            return load_language("it")
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        _locales_cache[lang] = data
        return data

def get_translator(lang: str) -> Callable[[str], str]:
    translations = load_language(lang)
    
    def t(key: str, **kwargs) -> str:
        keys = key.split('.')
        val = translations
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return key  # fallback to the key itself if not found
        
        if not isinstance(val, str):
            return key
            
        if kwargs:
            try:
                return val.format(**kwargs)
            except KeyError:
                return val
        return val

    return t
