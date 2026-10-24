"""Pytest configuration for token-cost-calculator."""

import os
import sys

TOOL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
