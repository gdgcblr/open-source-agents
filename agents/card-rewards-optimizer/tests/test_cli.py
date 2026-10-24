import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def run_cli(*args):
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    env["NO_DOTENV"] = "1"            # ensure a real .env on disk can't leak a key in
    return subprocess.run([sys.executable, "main.py", *args],
                          capture_output=True, text=True, cwd=BASE, env=env)


def test_expiry_runs_without_key():
    r = run_cli("expiry")
    assert r.returncode == 0
    assert "expire" in r.stdout.lower()


def test_optimize_category_degrades_to_table_without_key():
    r = run_cli("optimize", "--category", "cash")
    assert r.returncode == 0
    assert "HDFC Infinia" in r.stdout
    assert "not financial advice" in r.stdout


def test_optimize_goal_without_key_explains_and_shows_all():
    r = run_cli("optimize", "--goal", "flight to Singapore")
    assert r.returncode == 0
    assert "GEMINI_API_KEY" in r.stdout    # tells the user why narration is off


def test_chat_without_key_exits_with_guidance():
    r = run_cli("chat")
    assert r.returncode == 2
    assert "GEMINI_API_KEY" in r.stderr
