# 🛠️ TShoot — Autonomous Technical Troubleshooter Agent

> An autonomous multi-agent co-pilot designed to instantly diagnose and resolve attendee roadblocks during live workshops, hackathons, and virtual training calls (Google Meet / Microsoft Teams).

---

## 📌 Problem & Purpose

During live coding workshops or hackathons with 50+ participants:
- Attendees hit unexpected roadblocks: Google login failures (Error 403), OAuth redirect mismatches, port conflicts (`WinError 10048`), corporate proxy blocks, Python version issues, or missing dependencies.
- Instructors presenting on stage cannot stop the session to troubleshoot each attendee individually in chat.
- **TShoot** acts as an autonomous technical assistant: attendees can describe their error or upload a screenshot, and TShoot provides instant step-by-step solutions, fetches internet documentation for custom errors, and runs progressive deep diagnostics until the problem is solved.

---

## ✨ Key Features

1. **Visual Screenshot Inspector**:
   - Drag & drop, browse, or directly paste (`Ctrl + V`) an error screenshot.
   - Automatically detects the error context and triggers instant diagnosis.

2. **Multi-Agent Collaboration**:
   - **Auth Specialist**: Solves Google Account 403, OAuth redirect URI mismatch, and expired tokens.
   - **Network Specialist**: Pings `accounts.google.com`, GenAI endpoints, and PyPI to detect firewall/proxy blocks.
   - **Web Search Specialist**: For the **"Others"** category, fetches solutions from developer forums (StackOverflow, GitHub Issues, official docs) with clickable source links.
   - **Deep Investigator Specialist**: Multi-tier diagnostic engine (environment variables, cache purge, socket bypass) for stubborn issues.
   - **Remediation Specialist**: Generates copy-pasteable terminal commands for Windows (PowerShell), macOS, and Linux.

3. **Interactive "Solved or Not?" Loop**:
   - Asks: *"Did this solution resolve your issue?"*
   - If not resolved, requests attendee permission to perform **Deep Autonomous Investigation** and guides them with isolated clean-slate scripts until unblocked.

4. **One-Click Chat Escalation**:
   - When human instructor action is required (e.g. granting GCP IAM roles), formats a ready-to-paste message for Google Meet or Microsoft Teams chat.

5. **Enterprise Security Hardening**:
   - **Zero Secret Leaks**: Automatically redacts API keys and bearer tokens from logs and user inputs.
   - **OWASP XSS Protection**: Strict input sanitization and HTML entity encoding.
   - **Rate Limiting**: Sliding-window rate limiter (40 requests/minute per IP) prevents abuse.
   - **Debug Disabled**: `debug=False` ensures zero internal stack traces or environment leaks.

---

## 🏗️ System Architecture

```text
[Attendee Input: Terminal Text or Screenshot (Ctrl+V)]
                       │
                       ▼
          [OWASP Security Middleware]
     (Secret Redactor + XSS Sanitizer + Rate Limiter)
                       │
                       ▼
          [TShoot Coordinator Agent]
                       │
     ┌─────────────────┼─────────────────┬────────────────┐
     ▼                 ▼                 ▼                ▼
[Auth Specialist]  [Network Spec]  [Web Search Spec]  [Deep Investigator]
 (Login & OAuth)   (Socket Pings)  (Internet Forums)   (Multi-Tier Fix)
                       │
                       ▼
  [Step-by-Step Remediation + Copy-Paste Shell Commands]
                       │
         [Did this solve your issue?]
         ├── Yes ──► Issue marked resolved 🎉
         └── No  ──► Request consent for Deep Investigation ⚙️
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.10+** (Tested on Python 3.12)
- **pip** package manager
- Web browser (Chrome, Edge, Firefox, or Safari)

### 1. Clone & Navigate to Project
```bash
git clone https://github.com/ManushGR12/open-source-agents-workshop-copilot.git
cd open-source-agents-workshop-copilot/agents/workshop-troubleshooter
```

### 2. Set Up Virtual Environment & Dependencies

- **On Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  ```

- **On macOS / Linux:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

### 3. Configure Environment Variables
```bash
cp .env.example .env
```
*(Optional: Add your `GOOGLE_API_KEY` in `.env` if you wish to use live Google Gemini model generation).*

### 4. Run the TShoot Web Application
```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000`** in your browser.

---

## 🧪 Running Security Audit

To verify the agent against the 8 OWASP security benchmarks:
```bash
python security_audit.py
```
**Result**: 8/8 Tests Passed (Grade: A+).

---

## 📂 Project Directory Structure

```text
agents/workshop-troubleshooter/
├── .env.example         # Template environment variables
├── .gitignore           # Ignores credentials, secrets, and local databases
├── requirements.txt     # Python dependencies
├── README.md            # Project documentation
├── agent.py             # Google ADK multi-agent coordinator & sub-agents
├── app.py               # Hardened FastAPI backend & API endpoints
├── tools.py             # Diagnostic tools, web search, and deep investigation
├── database.py          # Parameterized SQLite store for escalation tickets
├── security.py          # Rate limiter, secret scrubber, and OWASP headers
├── security_audit.py    # Automated 8-point security testing suite
└── static/              # Frontend web portal
    ├── index.html       # Single-page interface with screenshot upload zone
    ├── app.css          # Glassmorphic dark cyber-theme styling
    └── app.js           # Client-side multi-agent triage logic & drag-and-drop
```

---

## 👥 Authors & Acknowledgments

- **Author**: Manush G R ([@ManushGR12](https://github.com/ManushGR12))
- Built with [Google Agent Development Kit (ADK)](https://github.com/google/agent-development-kit) and FastAPI.
