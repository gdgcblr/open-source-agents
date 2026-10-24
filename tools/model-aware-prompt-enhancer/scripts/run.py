#!/usr/bin/env python3
"""Zero-install launcher used by the Claude Code plugin (hook and MCP server).

Runs the toolkit straight from this folder with the system Python, so the
plugin needs no pip install: the runtime uses only the standard library.
"""

import sys
from pathlib import Path

if sys.version_info < (3, 10):  # noqa: UP036 - runs under whatever python3 the user has
    # Fail open for the hook (exit 0, no output) and explain on stderr.
    sys.stderr.write("model-aware-prompt-enhancer needs Python 3.10 or newer\n")
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from prompt_enhancer.cli import main  # noqa: E402

sys.exit(main())
