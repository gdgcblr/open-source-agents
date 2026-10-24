"""Pytest config: ensure the project root is importable so `pytest` (not just
`python -m pytest`) resolves `import portfolio` / `import engine`, and expose
shared fixtures so test modules never cross-import each other."""
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from portfolio import load_portfolio, load_rates   # noqa: E402


@pytest.fixture(scope="session")
def rates():
    return load_rates(str(BASE / "data" / "transfer_rates.yaml"))


@pytest.fixture(scope="session")
def sample_portfolio(rates):
    return load_portfolio(str(BASE / "examples" / "portfolio.yaml"), rates)
