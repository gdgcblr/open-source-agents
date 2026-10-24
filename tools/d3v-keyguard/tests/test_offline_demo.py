import asyncio
import importlib.util
from pathlib import Path


def test_offline_adk_demo_never_leaks(capsys):
    path = Path(__file__).resolve().parents[1] / "examples" / "offline_adk_demo.py"
    spec = importlib.util.spec_from_file_location("offline_adk_demo", path)
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    asyncio.run(demo.main())
    out = capsys.readouterr().out
    assert "call_api received the real key        : True" in out
    assert "vault locked by the lock_vault tool   : True" in out
    assert "plaintext in any model request        : False" in out
    assert "plaintext in persisted session history: False" in out
    assert "plaintext in vault file on disk       : False" in out
    assert '"result": "200 OK from https://api.example.com/v1/me; sent Authorization: Bearer [REDACTED:' in out
    assert demo.API_KEY not in out.split("3) Verification:")[0]
