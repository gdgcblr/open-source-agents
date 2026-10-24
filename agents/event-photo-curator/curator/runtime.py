"""Read-only setup checks, without loading a model or sending photos."""
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .faces import MODELS


def runtime_status():
    try:
        ram = round(os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / 1024**3)
    except (OSError, ValueError):
        ram = None
    try:
        with urlopen('http://127.0.0.1:11434/api/tags', timeout=2) as response:
            installed = json.load(response).get('models', [])
        models = [m['name'] for m in installed]
        available = True
    except (URLError, TimeoutError, ValueError, KeyError):
        models, available = [], False
    return {'ollama_running': available, 'installed_models': models, 'ram_gb': ram,
            'default_model': 'gemma4:e2b-it-q4_K_M',
            'default_model_ready': 'gemma4:e2b-it-q4_K_M' in models,
            'face_models_ready': all((Path.cwd() / '.cache/models' / v[0]).is_file() for v in MODELS.values()),
            'cloud_fallback': False}
