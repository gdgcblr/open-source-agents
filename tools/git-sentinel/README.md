# GitSentinel: Autonomous Pre-Commit Secret Triage & Auto-Remediation Agent

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

**GitSentinel** is an autonomous DevSecOps agent that intercepts secret leaks in Git pre-commit hooks, eliminates false positives with semantic context, and **autonomously remediates vulnerabilities** by migrating credentials to `.env` and rewriting code.

---

## ⚡ Why GitSentinel (Standout Capabilities)

Traditional secret scanners (like basic regex scripts) generate excessive false alarms on test fixtures, miss custom high-entropy credentials, and force developers to manually fix their code. 

GitSentinel introduces a **Quad-Layer Autonomous Architecture**:

1. **High-Confidence Regex + Shannon Entropy:**
   - Detects AWS, GitHub, OpenAI (`sk-proj-`), Anthropic, Google Gemini, Slack, Stripe, and Private RSA/SSH keys.
   - Calculates mathematical **Shannon Entropy ($H \ge 3.8$)** to catch unlabelled proprietary tokens and hex/base64 hashes without needing a known prefix.
2. **Multi-Line Split & Base64 De-obfuscation:**
   - Reassembles secrets fragmented across adjacent diff lines (Python implicit string concat, `+`, and `\` continuations).
   - Decodes inline Base64 string literals and scans the payload against all provider patterns.
3. **Context & AST-Aware Mock Triage:**
   - Understands test fixtures, mock suites, and dummy placeholders (e.g. `test_*.py`, `conftest.py`, `dummy_key`), avoiding disruptive false-positive blocks.
4. **3-Tier Intelligence Hierarchy:**
   - **Tier 1 — Gemini Cloud AI:** Batched structured JSON semantic triage via `gemini-2.5-flash` / `gemini-1.5-flash`.
   - **Tier 2 — Local Ollama LLM:** Stdlib-only (`urllib` + `json`) offline fallback, pings Ollama in 1.5 s — never blocks commits if Ollama is not running.
   - **Tier 3 — Shannon Entropy + AST Heuristics:** Zero-dependency deterministic analysis always available.

---

## 🏗️ Architecture Flow

```
                     [ Git Staged Diff / Source File ]
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │ 1. Tri-Layer Detection Engine                           │
       │    • Multi-Provider Regex (OpenAI sk-proj-, Claude, AWS)│
       │    • Shannon Entropy Calculator (H >= 3.8)              │
       │    • AST & Filepath Test/Mock Heuristics                │
       └─────────────────────────────────────────────────────────┘
                                    │ (Matches found)
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │ 2. Batched Google Gemini AI Triage                      │
       │    • Single round-trip structured evaluation            │
       │    • Distinguishes mock/doc fixtures from live tokens   │
       │    • Proposes idiomatic ENV names                       │
       └─────────────────────────────────────────────────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               │                                         │
               ▼                                         ▼
  [ Test Fixture / Safe ]                 [ Authentic Credential Leak ]
               │                                         │
               ▼                                         ▼
         (Pass Commit)                         ┌───────────────────┐
                                               │ Autonomous Auto-  │
                                               │ Remediation Agent │
                                               └───────────────────┘
                                                         │
                                        ┌────────────────┴────────────────┐
                                        ▼                                 ▼
                             [ Interactive Terminal ]           [ CI / --fix Flag ]
                             • Extracts to .env                 • Rewrites source AST
                             • Adds .env to .gitignore          • Auto-stages in Git
```

---

## 🚀 Quickstart

### 1. Installation
```bash
cd tools/git-sentinel
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Setup (Optional)
```bash
cp .env.example .env
```
Add your Gemini API key (optional — GitSentinel runs in offline entropy/heuristic mode if unset):
```env
GEMINI_API_KEY=AIzaSy...
```

---

## 💻 Usage

### 1. Run Interactive Synthetic Demo
Test modern OpenAI `sk-proj-`, AWS keys, dummy test tokens, and entropy detection:
```bash
python main.py --demo
```

### 2. Test Autonomous Remediation
Demonstrate auto-fixing mock leaks in memory:
```bash
python main.py --demo --fix
```

### 3. Audit Current Staged Git Changes
Inspect changes queued with `git add`:
```bash
python main.py --staged
```

### 4. Auto-Remediate Real Staged Leaks
Automatically extract hardcoded secrets into `.env`, rewrite code to use `os.environ.get(...)`, and stage:
```bash
python main.py --staged --fix
```

### 5. Structured JSON Output for CI/CD
Generate machine-readable JSON for automated audit gates and GitHub Actions:
```bash
python main.py --demo --json
```

### 6. Install Pre-Commit Hook
Install GitSentinel directly into your repository's `.git/hooks/pre-commit`:
```bash
python main.py --install-hook
```

### 7. Run Edge-Case Unit Tests
Verify detection, collision prevention, AST analysis, and redaction logic against the automated test suite:
```bash
python -m unittest tests/test_edge_cases.py
```

---

## 📦 Pre-Commit Hook Integration

Add GitSentinel to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: git-sentinel
        name: GitSentinel Secret Audit
        entry: python tools/git-sentinel/main.py --staged
        language: system
        stages: [pre-commit]
```

---

## 🛡️ Example Report Output

```text
╭─────────────────────────────────────────────────────────────────────╮
│ GitSentinel - Autonomous Secret Leak & Pre-Commit Remediation Agent │
╰─────────────────────────────────────────────────────────────────────╯
Running built-in synthetic leak test (live regex + Shannon entropy + test triage)...
! Detected 4 potential credential token(s) or high-entropy string(s).

                       GitSentinel Security Audit Report                        
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Location              ┃ Pattern  ┃ Severity ┃ Entropy ┃ Masked    ┃ Status / Remediation        ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ config/database.py:10 │ OpenAI   │   HIGH   │     3.6 │ sk-...381 │ Hardcoded credential        │
│                       │ API Key  │          │         │           │ Action: Extract to .env     │
├───────────────────────┼──────────┼──────────┼─────────┼───────────┼─────────────────────────────┤
│ config/database.py:11 │ AWS Key  │SAFE/MOCK │     3.7 │ AKI...PLE │ Test fixture detected. Safe.│
├───────────────────────┼──────────┼──────────┼─────────┼───────────┼─────────────────────────────┤
│ config/database.py:12 │ OpenAI   │SAFE/MOCK │     3.8 │ sk-...000 │ Test fixture detected. Safe.│
├───────────────────────┼──────────┼──────────┼─────────┼───────────┼─────────────────────────────┤
│ config/database.py:13 │ Generic  │   HIGH   │     3.4 │ d41...98a │ Hardcoded credential        │
│                       │ Secret   │          │         │           │ Action: Extract to .env     │
└───────────────────────┴──────────┴──────────┴─────────┴───────────┴─────────────────────────────┘
Commit rejected: High-severity credentials found. Pass `--fix` to auto-remediate.
```

---

## ⚠️ Known Limitations

1. **Binary & Compiled Blobs:** GitSentinel inspects UTF-8 unified text diffs. Secrets packaged inside compiled binaries, `.wasm` modules, or compressed archives are intentionally skipped.
2. **Multi-Line Split Secrets:** Credentials broken across multiple lines or dynamically constructed at runtime via complex string concatenation/base64 decoding cannot be deterministically inferred from unified diff hunks alone.
3. **Offline / Fallback Heuristic Mode:** In restricted-network environments or when `GEMINI_API_KEY` is omitted, GitSentinel operates in local heuristic mode (using Shannon entropy and AST heuristics). While fast and zero-cost, it lacks deep contextual semantic reasoning provided by Gemini.
