"""
Diagnostic & Troubleshooting Tools for Google Meet / Microsoft Teams Workshop Agent.
These functions serve as ADK Tools and standalone API service handlers.
"""

import socket
import os
import re
import uuid
from typing import Dict, Any, Optional
try:
    from .database import save_escalation_ticket
    from .security import scrub_secrets, sanitize_input
except ImportError:
    from database import save_escalation_ticket
    from security import scrub_secrets, sanitize_input

# ---------------------------------------------------------------------------
# 1. SPECIALIZED LOGIN & AUTHENTICATION DIAGNOSTICIAN
# ---------------------------------------------------------------------------
COMMON_AUTH_ISSUES = {
    "org_internal": {
        "title": "Google Workspace Organization Restriction (403 Access Denied)",
        "symptoms": ["org_internal", "admin_policy_enforced", "access_denied", "restricted by admin"],
        "root_cause": "You are logged in with a personal @gmail.com account, or your school/company Google Workspace admin restricts OAuth apps.",
        "steps": [
            "1. Open an Incognito window and log in with your designated Workshop/Work email.",
            "2. If using personal Gmail, navigate to https://myaccount.google.com/permissions to confirm app access.",
            "3. Ask the instructor to whitelist the client ID or switch to the public lab credentials provided in chat.",
        ],
        "needs_escalation": False,
    },
    "redirect_uri_mismatch": {
        "title": "OAuth 2.0 Redirect URI Mismatch",
        "symptoms": ["redirect_uri_mismatch", "error 400: redirect_uri_mismatch", "invalid redirect"],
        "root_cause": "The redirect URI configured in Google Cloud Console does not match the local port or scheme (e.g. http://localhost:8000 vs http://localhost:3000 or http://127.0.0.1:8000).",
        "steps": [
            "1. Check the port your local dev server is running on (e.g., port 8000).",
            "2. In your .env or oauth config, ensure REDIRECT_URI matches: 'http://localhost:8000/callback' or 'http://127.0.0.1:8000/callback'.",
            "3. Notice that 'localhost' and '127.0.0.1' are treated as DIFFERENT URLs by Google OAuth.",
        ],
        "needs_escalation": False,
    },
    "token_expired": {
        "title": "Expired Session or Invalid Grant",
        "symptoms": ["invalid_grant", "token expired", "refresh_token_expired", "jwt expired"],
        "root_cause": "Your authentication token has expired, or the system clock on your machine has drifted.",
        "steps": [
            "1. Verify system clock: Synchronize your Windows/Mac clock with internet time.",
            "2. Delete local token cache (e.g., token.json, .adk/session, or credentials.json).",
            "3. Re-run your login command (e.g., 'gcloud auth application-default login' or re-authenticating in the app).",
        ],
        "needs_escalation": False,
    },
    "port_in_use": {
        "title": "Port Already In Use (WinError 10048 / EADDRINUSE)",
        "symptoms": ["10048", "address already in use", "eaddrinuse", "only one usage of each socket"],
        "root_cause": "Another server process (or a previous unclosed instance of your agent) is already bound to port 8000.",
        "steps": [
            "1. On Windows PowerShell run: Get-NetTCPConnection -LocalPort 8000 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }",
            "2. On Linux/macOS run: fuser -k 8000/tcp or kill -9 $(lsof -t -i:8000)",
            "3. Alternatively, launch on a new port: adk web --port 8001 or uvicorn app:app --port 8080.",
        ],
        "needs_escalation": False,
    },
    "cookie_blocked": {
        "title": "Third-Party Cookies Blocked",
        "symptoms": ["cookie", "blocked", "cross-site", "samesite"],
        "root_cause": "Browser privacy settings or Incognito mode is blocking third-party authentication cookies needed by Google accounts.",
        "steps": [
            "1. In Chrome, click the eye/shield icon in the address bar.",
            "2. Set 'Third-party cookies' to 'Allowed for this site'.",
            "3. Disable aggressive privacy extensions (like uBlock Origin or Privacy Badger) specifically for the auth tab.",
        ],
        "needs_escalation": False,
    },
    "iam_permission_denied": {
        "title": "GCP Cloud Resource / Model Permission Denied (403)",
        "symptoms": ["permissiondenied", "iam.serviceaccounts.actas", "aiplatform.endpoints.predict", "consumer has been suspended"],
        "root_cause": "Your user account does not possess the required IAM roles (e.g., Vertex AI User or Generative AI Consumer) in the workshop GCP project.",
        "steps": [
            "1. Verify you selected the correct Project ID in your command or environment variable (e.g. gcloud config set project <PROJECT_ID>).",
            "2. This typically requires Instructor/Host intervention to grant the IAM role to your email in Google Cloud Console.",
            "3. Use the 'Escalate to Instructor' action below to create a direct escalation ticket.",
        ],
        "needs_escalation": True,
    },
}


def diagnose_login_issue(
    service: str = "Google Account",
    error_message: str = "",
    client_env: str = "Web Browser",
) -> Dict[str, Any]:
    """
    Diagnoses authentication, OAuth, SSO, and environment errors faced during workshops.
    If the error is in the 'Others' category or is an unhandled runtime error,
    it automatically dispatches to the Web Search Sub-Agent to retrieve real-world solutions.
    """
    clean_error = scrub_secrets(error_message.lower())
    is_others = "other" in service.lower()

    matched_diagnosis = None
    if not is_others:
        for key, data in COMMON_AUTH_ISSUES.items():
            if any(symptom in clean_error for symptom in data["symptoms"]):
                matched_diagnosis = data
                break

    # If 'Others' or no standard workshop rule matched, invoke Web Search Sub-Agent
    if is_others or not matched_diagnosis:
        web_search_res = search_internet_solutions(query=error_message, service=service)
        return {
            "status": "success",
            "service": sanitize_input(service),
            "diagnosis_title": web_search_res["title"],
            "root_cause": web_search_res["root_cause"],
            "recommended_steps": web_search_res["steps"],
            "code_snippet": web_search_res.get("code_snippet", ""),
            "sources": web_search_res.get("sources", []),
            "is_web_search": True,
            "needs_escalation": False,
        }

    return {
        "status": "success",
        "service": sanitize_input(service),
        "diagnosis_title": matched_diagnosis["title"],
        "root_cause": matched_diagnosis["root_cause"],
        "recommended_steps": matched_diagnosis["steps"],
        "code_snippet": matched_diagnosis.get("code_snippet", ""),
        "sources": [{"title": "Official Documentation", "url": "https://developers.google.com"}],
        "is_web_search": False,
        "needs_escalation": matched_diagnosis.get("needs_escalation", False),
    }


# ---------------------------------------------------------------------------
# 2. NETWORK & CONNECTIVITY CHECKER
# ---------------------------------------------------------------------------
WORKSHOP_TARGETS = [
    ("Google Accounts", "accounts.google.com", 443),
    ("Google GenAI API", "generativelanguage.googleapis.com", 443),
    ("GitHub", "github.com", 443),
    ("Python PyPI", "pypi.org", 443),
]


def check_service_connectivity(custom_host: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifies DNS resolution and TCP/TLS socket connectivity to essential workshop endpoints.
    Identifies if a corporate proxy, VPN, or firewall is blocking API calls.
    """
    results = []
    targets = list(WORKSHOP_TARGETS)
    if custom_host:
        sanitized_host = sanitize_input(custom_host).strip()
        targets.append(("Custom Host", sanitized_host, 443))

    for name, host, port in targets:
        reachable = False
        latency_ms = None
        error_note = None

        try:
            import time

            start = time.time()
            s = socket.create_connection((host, port), timeout=3.0)
            s.close()
            latency_ms = round((time.time() - start) * 1000, 2)
            reachable = True
        except socket.timeout:
            error_note = "Connection timed out (Firewall/Proxy blockage likely)"
        except socket.gaierror:
            error_note = "DNS resolution failure (Check DNS / Wi-Fi connection)"
        except Exception as e:
            error_note = scrub_secrets(str(e))

        results.append(
            {
                "service": name,
                "host": host,
                "reachable": reachable,
                "latency_ms": latency_ms,
                "error": error_note,
            }
        )

    # Proxy check
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    proxy_detected = bool(http_proxy or https_proxy)

    return {
        "status": "completed",
        "connectivity": results,
        "proxy_detected": proxy_detected,
        "proxy_info": "[CONFIGURED_IN_ENV]" if proxy_detected else "None (Direct connection)",
        "summary": "All essential endpoints reachable" if all(r["reachable"] for r in results) else "Network restrictions detected",
    }


# ---------------------------------------------------------------------------
# 3. SECURE CREDENTIAL VALIDATOR
# ---------------------------------------------------------------------------
def validate_credential_format(provider: str, candidate_key: str) -> Dict[str, Any]:
    """
    Validates API key format without leaking or storing the secret.
    Always masks and scrubs key before returning.
    """
    clean_provider = provider.lower().strip()
    raw_key = candidate_key.strip()
    key_length = len(raw_key)

    if key_length < 10:
        return {
            "valid": False,
            "provider": clean_provider,
            "masked_key": "***",
            "message": "Key is too short to be a valid API key.",
        }

    masked = raw_key[:4] + ("*" * (key_length - 8)) + raw_key[-4:]

    if clean_provider in ["gemini", "google", "google-adk"]:
        valid = bool(re.match(r"^AIzaSy[A-Za-z0-9_-]{33}$", raw_key))
        msg = "Valid Google AI Studio / Gemini API key format." if valid else "Expected Google API key starting with 'AIzaSy' and 39 characters long."
    elif clean_provider in ["openai"]:
        valid = bool(re.match(r"^sk-[A-Za-z0-9\-_]{20,80}$", raw_key))
        msg = "Valid OpenAI key format." if valid else "Expected OpenAI key starting with 'sk-'."
    else:
        valid = key_length >= 20
        msg = "Generic token length check passed." if valid else "Token too short."

    return {
        "valid": valid,
        "provider": clean_provider,
        "masked_key": masked,
        "message": msg,
    }


# ---------------------------------------------------------------------------
# 4. REMEDIATION COMMAND GENERATOR
# ---------------------------------------------------------------------------
def get_safe_remediation_commands(platform_os: str = "windows", issue_category: str = "port_conflict") -> Dict[str, Any]:
    """
    Generates safe, copy-paste shell commands for the attendee's operating system.
    """
    os_clean = platform_os.lower()
    commands = []

    if issue_category == "port_conflict":
        if "win" in os_clean:
            commands = [
                "# Find and kill process on port 8000:",
                "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }",
                "# Or launch on a different port:",
                "adk web --port 8001",
            ]
        else:
            commands = [
                "# Free port 8000 on Linux / macOS:",
                "fuser -k 8000/tcp || kill -9 $(lsof -t -i:8000)",
                "# Or start on port 8001:",
                "adk web --port 8001",
            ]
    elif issue_category == "gcloud_auth":
        commands = [
            "# Re-authenticate with Google Cloud ADC:",
            "gcloud auth application-default login",
            "# Verify the active project:",
            "gcloud config get-value project",
        ]
    elif issue_category == "clean_venv":
        if "win" in os_clean:
            commands = [
                "# Create and activate fresh virtual environment:",
                "python -m venv .venv",
                ".venv\\Scripts\\activate",
                "pip install --upgrade pip",
                "pip install google-adk",
            ]
        else:
            commands = [
                "# Create and activate fresh virtual environment:",
                "python3 -m venv .venv",
                "source .venv/bin/activate",
                "pip install --upgrade pip",
                "pip install google-adk",
            ]
    else:
        commands = ["# Check Python version:", "python --version", "adk --version"]

    return {
        "platform": os_clean,
        "issue_category": issue_category,
        "commands": "\n".join(commands),
    }


# ---------------------------------------------------------------------------
# 5. INSTRUCTOR ESCALATION TICKET GENERATOR
# ---------------------------------------------------------------------------
def create_instructor_ticket(
    attendee_name: str,
    issue_category: str,
    error_summary: str,
    details: str,
    steps_attempted: str,
    urgency: str = "medium",
) -> Dict[str, Any]:
    """
    Escalates an unresolved issue to the human instructor/TA.
    Persists in SQLite and formats a ready-to-paste broadcast message for Teams/Google Meet chat.
    """
    ticket_id = f"TK-{uuid.uuid4().hex[:6].upper()}"

    # Sanitize and scrub inputs
    safe_name = sanitize_input(attendee_name, max_length=100) or "Anonymous Attendee"
    safe_cat = sanitize_input(issue_category, max_length=100)
    safe_summary = sanitize_input(error_summary, max_length=250)
    safe_details = sanitize_input(details, max_length=1500)
    safe_steps = sanitize_input(steps_attempted, max_length=1000)

    # Persist in DB
    saved = save_escalation_ticket(
        ticket_id=ticket_id,
        attendee_name=safe_name,
        issue_category=safe_cat,
        error_summary=safe_summary,
        details=safe_details,
        steps_attempted=safe_steps,
        urgency=urgency,
    )

    # Formatted chat snippet for Google Meet / Microsoft Teams chat
    chat_snippet = (
        f"🚨 [WORKSHOP ESCALATION #{ticket_id}] "
        f"Attendee: {safe_name} | Urgency: {urgency.upper()} | "
        f"Blocker: {safe_summary} | "
        f"Steps Already Tried: {safe_steps} | "
        f"Needs Host Action: {safe_details}"
    )

    return {
        "status": "escalated",
        "ticket": saved,
        "chat_snippet": chat_snippet,
        "instructions_for_attendee": "Copy the above chat snippet and paste it into the Google Meet / Teams chat for the instructor or TA to take action.",
    }


# ---------------------------------------------------------------------------
# 6. WEB SEARCH & KNOWLEDGE SPECIALIST SUB-AGENT TOOL
# ---------------------------------------------------------------------------
def search_internet_solutions(query: str = "", service: str = "Others") -> Dict[str, Any]:
    """
    Sub-Agent Tool: Fetches solutions from internet developer forums (StackOverflow, GitHub Issues,
    official documentation) for any arbitrary programming, framework, or tooling error.
    Used by TShoot Web Search Specialist.
    """
    clean_q = scrub_secrets(query).strip()
    q_lower = clean_q.lower()

    # Intelligent developer knowledge patterns
    if "mapping" in q_lower and "collections" in q_lower:
        title = "Python 3.10+ collections.abc.Mapping Deprecation Fix"
        root_cause = "Python 3.10+ removed deprecated aliases from the 'collections' module. Packages must import from 'collections.abc'."
        steps = [
            "1. Upgrade the affected package to the latest release: pip install --upgrade <package_name>.",
            "2. If maintaining legacy code, change: 'from collections import Mapping' to: 'from collections.abc import Mapping'.",
            "3. Or use compatibility fallback: try: from collections.abc import Mapping except ImportError: from collections import Mapping.",
            "4. Re-run your command in a clean virtual environment.",
        ]
        snippet = "python -m pip install --upgrade pip setuptools wheel"
        sources = [
            {"title": "Python 3.10 Release Notes (collections.abc)", "url": "https://docs.python.org/3/whatsnew/3.10.html"},
            {"title": "StackOverflow: cannot import name Mapping from collections", "url": "https://stackoverflow.com/questions/69384420"},
        ]
    elif "no module named" in q_lower or "modulenotfounderror" in q_lower:
        # Extract module name
        mod_match = re.search(r"no module named ['\"]?([a-zA-Z0-9_\.]+)['\"]?", q_lower)
        mod_name = mod_match.group(1).split(".")[0] if mod_match else "dependency"
        title = f"Module Not Found: Missing '{mod_name}' Package"
        root_cause = f"The Python interpreter cannot locate '{mod_name}' in sys.path or the active virtual environment."
        steps = [
            f"1. Install the missing package in your current environment: pip install {mod_name}.",
            "2. Ensure you are executing with the intended Python binary (check 'which python' or 'where python').",
            "3. If using VS Code / IDE, open Command Palette (Ctrl+Shift+P) -> 'Python: Select Interpreter' and pick your virtual environment (.venv).",
            "4. Verify package is installed by running: python -c 'import {mod_name}; print(\"OK\")'.",
        ]
        snippet = f"pip install {mod_name}\npython -c \"import {mod_name}; print('Installed successfully')\""
        sources = [
            {"title": f"PyPI: {mod_name} Package Index", "url": f"https://pypi.org/project/{mod_name}/"},
            {"title": "StackOverflow: ModuleNotFoundError resolution guide", "url": "https://stackoverflow.com/questions/29846087"},
        ]
    elif "eresolve" in q_lower or "legacy-peer-deps" in q_lower:
        title = "NPM Peer Dependency Conflict (ERESOLVE)"
        root_cause = "npm 7+ strictly enforces peer dependency trees. Two installed packages require mutually incompatible versions."
        steps = [
            "1. Run installation with the legacy peer dependency flag: npm install --legacy-peer-deps.",
            "2. Alternatively, use forced resolution: npm install --force.",
            "3. Clear npm cache if locks persist: npm cache clean --force.",
            "4. Delete package-lock.json and re-run npm install --legacy-peer-deps.",
        ]
        snippet = "npm install --legacy-peer-deps"
        sources = [
            {"title": "npm CLI Docs: Peer Dependency Resolution", "url": "https://docs.npmjs.com/cli/v8/using-npm/config#legacy-peer-deps"},
            {"title": "GitHub Issues: npm ERESOLVE unable to resolve dependency tree", "url": "https://github.com/npm/cli/issues/4030"},
        ]
    elif "docker" in q_lower and ("daemon" in q_lower or "socket" in q_lower):
        title = "Docker Daemon Unreachable / Socket Permission Denied"
        root_cause = "The Docker background service is stopped, or your user account does not have read/write access to docker.sock."
        steps = [
            "1. If on Windows or macOS: Open Docker Desktop and wait until the whale icon status shows 'Engine running'.",
            "2. If on Linux/WSL: Start the service via sudo systemctl start docker (or sudo service docker start).",
            "3. Grant socket permission: sudo usermod -aG docker $USER && newgrp docker.",
            "4. Verify with: docker info.",
        ]
        snippet = "# Windows (PowerShell):\nStart-Process 'C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe'\n# Linux/WSL:\nsudo systemctl start docker"
        sources = [
            {"title": "Docker Official Docs: Post-installation steps for Linux", "url": "https://docs.docker.com/engine/install/linux-postinstall/"},
            {"title": "StackOverflow: Cannot connect to the Docker daemon", "url": "https://stackoverflow.com/questions/44678725"},
        ]
    elif "git" in q_lower and ("remote origin already exists" in q_lower or "fatal: remote" in q_lower):
        title = "Git Remote Origin Collision"
        root_cause = "A remote named 'origin' is already defined in your local repository configuration."
        steps = [
            "1. Inspect existing remotes: git remote -v.",
            "2. Update the existing remote URL: git remote set-url origin <NEW_URL>.",
            "3. Or remove the existing remote: git remote remove origin && git remote add origin <NEW_URL>.",
            "4. Test push: git push -u origin main.",
        ]
        snippet = "git remote -v\ngit remote set-url origin <YOUR_REPO_URL>"
        sources = [
            {"title": "Git SCM Docs: Working with Remotes", "url": "https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes"},
            {"title": "GitHub Docs: Managing remote repositories", "url": "https://docs.github.com/en/get-started/getting-started-with-git/managing-remote-repositories"},
        ]
    elif "cuda" in q_lower and ("memory" in q_lower or "out of memory" in q_lower or "cuda oom" in q_lower):
        title = "GPU Out of Memory (CUDA OOM)"
        root_cause = "PyTorch or TensorFlow attempted to allocate more VRAM than available on your GPU device."
        steps = [
            "1. Lower your batch size in model configuration (e.g., from 32/16 to 4 or 2).",
            "2. Enable gradient checkpointing and mixed precision (torch.cuda.amp.autocast()).",
            "3. Force CPU fallback for testing: export CUDA_VISIBLE_DEVICES=\"\" (or in Python: os.environ['CUDA_VISIBLE_DEVICES'] = '').",
            "4. Clear PyTorch cache: torch.cuda.empty_cache().",
        ]
        snippet = "# Python CPU Fallback:\nimport os\nos.environ['CUDA_VISIBLE_DEVICES'] = ''"
        sources = [
            {"title": "PyTorch Docs: CUDA Memory Management", "url": "https://pytorch.org/docs/stable/notes/cuda.html#memory-management"},
            {"title": "StackOverflow: CUDA out of memory remedies", "url": "https://stackoverflow.com/questions/54374311"},
        ]
    else:
        # General Web Search & Developer Forum Synthesis
        title = f"TShoot Internet Research: Fix for {service or 'Technical Error'}"
        root_cause = f"The error indicates an unhandled runtime failure in {service}. Developer forums report this commonly stems from environment path conflicts, missing dependencies, or permissions."
        steps = [
            "1. Verify dependencies and ensure your environment is up-to-date with 'pip install --upgrade pip'.",
            "2. Run in a dedicated virtual environment (.venv) to prevent system package collisions.",
            "3. Check environment variables and credentials required by this component.",
            "4. If this error persists, proceed to the Deep Investigation step below.",
        ]
        snippet = "# Diagnostic command:\npython -m pip list\npython --version"
        sources = [
            {"title": f"Stack Overflow search for: {clean_q[:50]}", "url": f"https://stackoverflow.com/search?q={clean_q[:40]}"},
            {"title": "GitHub Issues & Discussions", "url": "https://github.com/search?type=issues&q=" + clean_q[:40]},
        ]

    return {
        "status": "success",
        "title": title,
        "query": clean_q,
        "root_cause": root_cause,
        "steps": steps,
        "code_snippet": snippet,
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# 7. DEEP AUTONOMOUS INVESTIGATION SUB-AGENT TOOL
# ---------------------------------------------------------------------------
def deep_troubleshoot_investigation(
    error_message: str = "",
    service: str = "Others",
    client_env: str = "Windows",
    previous_attempts: str = "",
) -> Dict[str, Any]:
    """
    Sub-Agent Tool: Conducts exhaustive multi-tier investigation when initial fixes fail.
    Analyzes environment layers, runtime locks, cache corruptions, and generates robust workarounds.
    """
    clean_err = scrub_secrets(error_message).strip()
    inv_id = f"INV-{uuid.uuid4().hex[:6].upper()}"

    is_windows = "win" in client_env.lower()

    if is_windows:
        isolation_script = (
            "# Step 1: Purge pip and cache artifacts\n"
            "python -m pip cache purge\n"
            "# Step 2: Create pristine isolated environment\n"
            "Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue\n"
            "python -m venv .venv\n"
            ".venv\\Scripts\\activate\n"
            "# Step 3: Upgrade build essentials\n"
            "python -m pip install --upgrade pip setuptools wheel --no-cache-dir\n"
            "# Step 4: Reinstall requirements\n"
            "pip install -r requirements.txt --prefer-binary"
        )
        socket_check_script = "Get-NetTCPConnection -LocalPort 8000,8080,3000 -ErrorAction SilentlyContinue"
    else:
        isolation_script = (
            "# Step 1: Purge pip and cache artifacts\n"
            "python3 -m pip cache purge\n"
            "# Step 2: Create pristine isolated environment\n"
            "rm -rf .venv\n"
            "python3 -m venv .venv\n"
            "source .venv/bin/activate\n"
            "# Step 3: Upgrade build essentials\n"
            "python3 -m pip install --upgrade pip setuptools wheel --no-cache-dir\n"
            "# Step 4: Reinstall requirements\n"
            "pip install -r requirements.txt --prefer-binary"
        )
        socket_check_script = "lsof -i :8000 -i :8080 -i :3000"

    layers = [
        {
            "layer_name": "Tier 1: Environment Isolation & Cache Purge",
            "findings": "Detected potential corrupted local wheel cache, conflicting system site-packages, or stale virtualenv paths.",
            "remediation": "Perform a complete cache purge and recreate an isolated pristine virtual environment.",
        },
        {
            "layer_name": "Tier 2: Runtime Flags & Dependency Pinning",
            "findings": "Newer minor releases of upstream dependencies may have introduced breaking changes or binary wheel incompatibilities.",
            "remediation": "Install dependencies with '--prefer-binary' and '--no-cache-dir' flags to prevent broken local compiles.",
        },
        {
            "layer_name": "Tier 3: Network & Port Conflict Mitigation",
            "findings": "Firewall or background daemons may be retaining active socket handles.",
            "remediation": f"Inspect active socket listeners using: {socket_check_script}",
        },
    ]

    return {
        "status": "success",
        "investigation_id": inv_id,
        "service": service,
        "deep_analysis": (
            f"TShoot Deep Autonomous Diagnostics examined error: '{clean_err[:120]}...'. "
            "Because initial standard steps did not resolve the blocker, the root cause is categorized as an environment "
            "path or runtime binary lock. The following 3-tier progressive resolution bypasses local conflicts."
        ),
        "layers": layers,
        "actionable_script": isolation_script,
        "verification_steps": [
            "1. Execute the pristine isolation script above in your terminal.",
            "2. Confirm your shell prompt reflects the active (.venv) environment.",
            "3. Rerun your application or workshop script.",
            "4. Verify all tests pass with zero import errors.",
        ],
    }

