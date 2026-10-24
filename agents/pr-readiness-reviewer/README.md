# AgentSentinel 🛡️
> **Autonomous AI-Agent Security, Prompt Guardrail & Self-Healing Patch Engine**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-11%2F11%20passing-brightgreen.svg)](https://github.com/)
[![OWASP LLM Compliant](https://img.shields.io/badge/OWASP%20LLM-Top%2010%20Secured-cyan.svg)](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

AgentSentinel is an enterprise-grade security auditor and pre-commit/CI guardrail engine built specifically for modern AI agents, tool runtimes, and open-source agentic repositories. It moves beyond standard syntax linters to address adversarial LLM threats, prompt injections, supply-chain poisoning, and permission creep.

---

## ⚡ Core Capabilities

- **Zero-Secrets & High-Entropy Scanner**: High-fidelity detection for Google AI Studio / Gemini (`AIzaSy...`), OpenAI (`sk-proj-...`), Anthropic (`sk-ant-...`), GitHub PATs (`github_pat_...`), Slack webhooks, AWS keys, private PEM headers, and database connection strings with Shannon entropy analysis.
- **OWASP LLM01 - Prompt Injection & System Prompt Integrity**: Detects unshielded user variable interpolation into system prompts and flags known adversarial jailbreak payloads.
- **OWASP LLM06 - Excessive Agency & Dangerous Tools**: Flags exposed agent tools granting unrestricted OS command execution (`os.system`, `subprocess(shell=True)`, `eval()`, `exec()`) or unbounded filesystem deletion (`shutil.rmtree`).
- **AST Undeclared-Import Scanner**: Parses Python Abstract Syntax Trees (AST) with recursion safeguards to ensure every third-party import is explicitly declared in `requirements.txt` or `pyproject.toml`.
- **Environment Sync Verification**: Cross-references every `os.getenv` and `process.env` key across the codebase against `.env.example`.
- **Hook-Safe Git Isolation**: Validates repository working trees while overriding dangerous untrusted git hooks (`-c core.hooksPath=/dev/null -c core.fsmonitor=false`).
- **Autonomous Self-Healing Unified Diff Engine**: Automatically generates a standard unified `.patch` file that can be applied with `git apply` to instantly fix missing configuration and manifests.
- **Prompt-Shielded AI Synthesis**: Utilizes Gemini 3.8 Flash inside an isolated XML boundary to provide executive security evaluations resilient to prompt injection attacks.

---

## 🚀 Quickstart

### 1. Installation
Core scanner uses the Python standard library with zero mandatory external packages:
```bash
git clone https://github.com/your-username/agentsentinel.git
cd agentsentinel

# Optional: install google-genai for AI-powered synthesis
pip install -r requirements.txt
```

Or install as a local CLI tool:
```bash
pip install -e .
```

### 2. Run Single Agent Audit
```bash
python3 main.py --path ./my-agent --suggest-fixes --generate-patch
```

### 3. Run Repo-Wide Batch Leaderboard
Audits all agent subdirectories and prints a ranked Markdown readiness leaderboard:
```bash
python3 main.py --path ./agents --batch
```

### 4. CI/CD Mode (Exit Code 1 on Failure)
```bash
python3 main.py --path . --strict --format json
```

---

## 🛠️ CLI Options

| Argument | Description | Default |
| :--- | :--- | :--- |
| `--path <dir>` | Path to agent folder or parent repository container | `.` |
| `--batch` | Audit all subprojects under container and print leaderboard | `False` |
| `--suggest-fixes` | Output copy-pasteable remediation snippets and unified patch | `False` |
| `--generate-patch` | Write self-healing patch directly to `agent-fix.patch` | `False` |
| `--provider` | AI summary provider (`mock`, `gemini`, `ollama`) | `mock` |
| `--model` | Model name override (e.g. `gemini-3.8-flash`) | None |
| `--format` | Output format (`markdown`, `json`) | `markdown` |
| `--strict` | Exit code 1 if any finding is `NEEDS_WORK` (for CI/CD gates) | `False` |

---

## 🤖 GitHub Actions Workflow

Add `.github/workflows/agentsentinel.yml` to your repository:

```yaml
name: AgentSentinel Security Gate

on:
  pull_request:
    branches: [ main ]
  push:
    branches: [ main ]

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run AgentSentinel Audit
        run: |
          python3 main.py --path . --strict --format markdown --suggest-fixes
```

---

## 🧪 Unit Testing

Run the comprehensive unit test suite:
```bash
python3 test_main.py
```
Output:
```text
Ran 11 tests in 0.080s

OK (ALL 11 UNIT TESTS PASSING)
```

---

## ⚠️ Known Limitations

- Static file scan inspects UTF-8 text files up to 512 KB per file.
- AST parser verifies top-level module names against declared manifests (`requirements.txt`, `pyproject.toml`).
- Ollama synthesis is constrained to RFC-compliant loopback IP ranges (`127.0.0.1`, `::1`) for SSRF protection.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
