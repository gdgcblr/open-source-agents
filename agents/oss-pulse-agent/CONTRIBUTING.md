# Contributing to OSS Pulse Agent

Thank you for your interest in contributing to **OSS Pulse Agent**! We welcome contributions from developers of all skill levels.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Local Development Setup
```bash
# Fork and clone the repository
git clone https://github.com/your-username/oss-pulse-agent.git
cd oss-pulse-agent

# Create a virtual environment
python -m venv .venv

# Activate environment
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
```

### 3. Running the Test Suite
Before submitting any pull request, ensure all unit and integration tests pass:
```bash
pytest tests/ -v
```

---

## 🛠️ Code Architecture & Standards

- **Models (`models/report.py`):** Use Pydantic v2 schemas for all telemetry structures. Every finding must attach verifiable `Evidence`.
- **Tools (`tools/`):** Each tool must handle GitHub API errors gracefully, returning structured `DataCoverage` records rather than raising unhandled exceptions.
- **Scoring (`scoring/engine.py`):** Scoring algorithms must be deterministic and transparent. No AI hallucinations for numerical metrics.
- **Formatting:** We follow [PEP 8](https://peps.python.org/pep-0008/) and [Black](https://github.com/psf/black) conventions.

---

## 🤝 Pull Request Workflow

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Write clean, documented code with accompanying unit tests in `tests/`.
3. Verify tests pass locally: `pytest tests/ -v`.
4. Commit with descriptive commit messages following Conventional Commits (e.g. `feat: ...`, `fix: ...`, `docs: ...`).
5. Push to your fork and submit a Pull Request against the `main` branch.
