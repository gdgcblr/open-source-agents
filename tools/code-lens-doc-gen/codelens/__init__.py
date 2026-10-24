"""
CodeLens Doc Gen — Automatic codebase documentation generator.

Scans a codebase, analyzes its structure, and generates categorized
documentation (User Docs & Dev Docs) using Google Gemini.
"""

import sys
import warnings

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError with spinners/emojis
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Suppress deprecation notice from third-party google.generativeai library
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

__version__ = "0.1.0"
