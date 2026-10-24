"""Pytest fixtures for MergeReady tests."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest


@pytest.fixture
def defective_agent_dir(tmp_path: Path) -> Path:
    """Constructs a defective agent directory in a temporary path at runtime.

    Guarantees no committed API keys, binary SQLite files, or dangerous Unicode
    characters exist in the git repository.
    """
    proj = tmp_path / "agents" / "bad-agent"
    proj.mkdir(parents=True)

    # 1. README with unedited template residue ([Project Name])
    (proj / "README.md").write_text(
        "# [Project Name]\n\n"
        "## Overview\n"
        "Defective agent implementation for testing validation heuristics.\n\n"
        "## Configuration & Environment Variables\n"
        "| Variable Name | Required | Default | Description |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| `API_KEY` | Yes | - | Primary model API key |\n\n"
        "## How to Run\n"
        "```bash\n"
        "python bad_agent.py\n"
        "```\n\n"
        "## License\n"
        "MIT\n",
        encoding="utf-8",
    )

    # 2. .env.example with placeholder
    (proj / ".env.example").write_text(
        "API_KEY=your_gemini_api_key_here\n",
        encoding="utf-8",
    )

    # 3. .gitignore
    (proj / ".gitignore").write_text(
        ".venv/\n",
        encoding="utf-8",
    )

    # 4. requirements.txt missing pyyaml
    (proj / "requirements.txt").write_text(
        "requests==2.31.0\n",
        encoding="utf-8",
    )

    # 5. .env containing real secret (constructed from harmless string fragments at runtime)
    secret_key = "AIza" + "Sy" + "D9a8b7c6d5e4f3g2h1j0k9l8m7n6b5v4c"
    (proj / ".env").write_text(
        f"API_KEY={secret_key}\n",
        encoding="utf-8",
    )

    # 6. bad_agent.py with runtime-constructed secrets, Trojan bidi, tag characters, loops, and subprocess
    bidi_char = chr(0x202E)  # RIGHT-TO-LEFT OVERRIDE
    tag_h = chr(0xE0048)     # Tag 'H'
    tag_i = chr(0xE0049)     # Tag 'I'

    source_code = (
        '"""Defective agent fixture constructed dynamically at test runtime."""\n\n'
        'import os\n'
        'import subprocess\n'
        'import yaml  # Undeclared import (violates R01)\n\n'
        f'HARDCODED_API_KEY = "{secret_key}"  # Violates S01\n\n'
        'BACKDOOR_TOKEN = os.getenv("SECRET_BACKDOOR_KEY")  # Violates E01\n\n'
        f'SUSPICIOUS_PROMPT = "Normal looking prompt{bidi_char} reversed text {tag_h}{tag_i}"  # Violates A02\n\n'
        'class MockModelClient:\n'
        '    def chat(self, prompt: str) -> str:\n'
        '        return f"Response to {prompt}"\n\n'
        'def run_agent() -> None:\n'
        '    client = MockModelClient()\n'
        '    # Unbounded while loop around model call with no exit condition (violates A01)\n'
        '    while True:\n'
        '        resp = client.chat("infinite cycle")\n'
        '    # Undisclosed subprocess execution (violates A03)\n'
        '    subprocess.run(["echo", "running command"])\n\n'
        'if __name__ == "__main__":\n'
        '    run_agent()\n'
    )
    (proj / "bad_agent.py").write_text(source_code, encoding="utf-8")

    # 7. Create a temporary SQLite database file at runtime (violates S02)
    db_path = proj / "local_cache.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE cache (key TEXT, val TEXT);")
    conn.commit()
    conn.close()

    return proj
