#!/usr/bin/env python3
"""Incident Analyzer - AI-powered codebase incident diagnosis agent.

Usage:
    # One-time setup: index your codebase
    python main.py index /path/to/your/project

    # Analyze an incident
    python main.py analyze --spec /path/to/your/project/.incident-spec.json \\
        --log-file error.log --mock

    # Pipe logs directly
    cat error.log | python main.py analyze --spec .incident-spec.json --mock
"""

import sys

from incident_analyzer.cli import main

if __name__ == "__main__":
    sys.exit(main())
