"""Pytest configuration ensuring agents/autonomous-code-healer is on sys.path."""

import os
import sys

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)
