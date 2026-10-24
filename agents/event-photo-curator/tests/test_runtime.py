from io import BytesIO
import json
from urllib.error import URLError

from curator.runtime import runtime_status


def test_readiness_is_based_on_installed_models(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('curator.runtime.urlopen',lambda *a,**kw:BytesIO(json.dumps({'models':[{'name':'gemma4:e2b-it-q4_K_M'}]}).encode()))
    result=runtime_status()
    assert result['ollama_running'] and result['default_model_ready']
    assert not result['face_models_ready'] and not result['cloud_fallback']


def test_unreachable_ollama_is_not_ready(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    def unavailable(*args,**kwargs):raise URLError('not running')
    monkeypatch.setattr('curator.runtime.urlopen',unavailable)
    result=runtime_status()
    assert not result['ollama_running'] and not result['default_model_ready']
