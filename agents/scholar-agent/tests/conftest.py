"""
tests/conftest.py - Pytest configuration and path resolution
"""
import sys
import os

# Ensure the parent directory (agents/scholar-agent) is in sys.path during test collection
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)