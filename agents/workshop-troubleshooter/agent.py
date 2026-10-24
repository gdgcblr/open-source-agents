"""
Google ADK Agent Definition: Workshop & Meeting Troubleshooter Co-Pilot.
Built following the 'COLLAB' (Coordinator + Sub-agents) pattern presented at GDG Bangalore.

Architecture:
- Root Agent (Coordinator): Handles natural language triage and delegates to specialized sub-agents.
- Auth Specialist: Diagnoses Google Login, OAuth 2.0, SSO, token expiration.
- Network Specialist: Diagnoses firewall, proxy, and DNS connectivity to workshop endpoints.
- Remediation Specialist: Generates exact copy-paste shell commands for Windows, Linux, and Mac.
- Escalation Specialist: Submits structured tickets to human instructors when permissions/IAM block progress.
"""

import os
from google.adk.agents.llm_agent import Agent
try:
    from .tools import (
        diagnose_login_issue,
        check_service_connectivity,
        validate_credential_format,
        get_safe_remediation_commands,
        create_instructor_ticket,
        search_internet_solutions,
        deep_troubleshoot_investigation,
    )
except ImportError:
    from tools import (
        diagnose_login_issue,
        check_service_connectivity,
        validate_credential_format,
        get_safe_remediation_commands,
        create_instructor_ticket,
        search_internet_solutions,
        deep_troubleshoot_investigation,
    )

# Model configuration: uses environment variable or defaults to gemini-3.8-flash (or gemini-2.5-flash)
DEFAULT_MODEL = os.getenv("ADK_MODEL", "gemini-3.8-flash")

# ---------------------------------------------------------------------------
# 1. SPECIALIZED SUB-AGENTS (Collaborative Multi-Agent Pattern)
# ---------------------------------------------------------------------------
auth_specialist = Agent(
    model=DEFAULT_MODEL,
    name="auth_specialist",
    description="Specialist in Google Account login failures, OAuth redirect URI mismatch, expired tokens, and 403 access issues.",
    instruction=(
        "You are TShoot Auth Specialist. "
        "Diagnose login failures, Google account errors, and permission issues using the diagnose_login_issue "
        "and validate_credential_format tools. Provide clear, numbered steps to fix the problem without jargon."
    ),
    tools=[diagnose_login_issue, validate_credential_format],
)

network_specialist = Agent(
    model=DEFAULT_MODEL,
    name="network_specialist",
    description="Specialist in internet connectivity, corporate proxy blockers, DNS resolution, and Google API reachability.",
    instruction=(
        "You diagnose attendee network issues in virtual calls. Use the check_service_connectivity tool "
        "to test socket reachability to accounts.google.com, Google GenAI APIs, and GitHub. "
        "If corporate VPN or proxy is detected, advise on proxy environment flags or mobile hotspot bypass."
    ),
    tools=[check_service_connectivity],
)

web_search_specialist = Agent(
    model=DEFAULT_MODEL,
    name="web_search_specialist",
    description="Specialist in searching the web and developer forums (StackOverflow, GitHub Issues, documentation) for programming errors.",
    instruction=(
        "You are TShoot Web Search Specialist. When an attendee encounters errors outside the standard Google suite, "
        "or selects 'Others', use the search_internet_solutions tool to fetch solutions from developer forums and documentation. "
        "Provide verified root causes, copy-paste snippets, and source references."
    ),
    tools=[search_internet_solutions],
)

deep_investigator_specialist = Agent(
    model=DEFAULT_MODEL,
    name="deep_investigator_specialist",
    description="Specialist in deep-dive troubleshooting when initial steps do not resolve the issue.",
    instruction=(
        "You are TShoot Deep Investigator. When an attendee reports that previous steps failed to unblock them, "
        "use deep_troubleshoot_investigation to inspect environment layers, cache corruptions, runtime locks, and produce "
        "unblocking bypasses until the issue is solved."
    ),
    tools=[deep_troubleshoot_investigation],
)

remediation_specialist = Agent(
    model=DEFAULT_MODEL,
    name="remediation_specialist",
    description="Generates exact shell commands and terminal fixes for Windows PowerShell, macOS, and Linux.",
    instruction=(
        "You provide exact, safe, and copy-pasteable terminal commands to resolve developer environment issues. "
        "Use the get_safe_remediation_commands tool to supply tested snippets for port conflicts, Python venvs, and gcloud CLI."
    ),
    tools=[get_safe_remediation_commands],
)

escalation_specialist = Agent(
    model=DEFAULT_MODEL,
    name="escalation_specialist",
    description="Escalates unresolved blockers or administrative tasks (like IAM role grants) to the human workshop instructor.",
    instruction=(
        "When an attendee's problem cannot be solved autonomously (e.g., they need Google Cloud IAM permission granted by the instructor), "
        "use create_instructor_ticket to persist the issue in the database and generate a concise snippet for Google Meet or Teams chat."
    ),
    tools=[create_instructor_ticket],
)

# ---------------------------------------------------------------------------
# 2. COORDINATOR (ROOT AGENT)
# ---------------------------------------------------------------------------
root_agent = Agent(
    model=DEFAULT_MODEL,
    name="tshoot_coordinator",
    description="TShoot: Autonomous Technical Troubleshooting Agent for Google Meet and Teams workshops.",
    instruction=(
        "You are TShoot, the Autonomous Workshop & Meeting Troubleshooter. Your mission is to unblock attendees "
        "quickly and accurately. "
        "1. Analyze the attendee's error message, symptom, or uploaded screenshot. "
        "2. If it is a Google Account / OAuth error, coordinate with auth_specialist. "
        "3. If it is network or proxy related, coordinate with network_specialist. "
        "4. If it is a general, rare, or 'Others' category error, delegate to web_search_specialist to fetch solutions from the internet. "
        "5. If previous fixes failed, delegate to deep_investigator_specialist to dig deeper until the issue is solved. "
        "6. Provide clean, actionable step-by-step resolution without fluff."
    ),
    sub_agents=[
        auth_specialist,
        network_specialist,
        web_search_specialist,
        deep_investigator_specialist,
        remediation_specialist,
        escalation_specialist,
    ],
    tools=[
        diagnose_login_issue,
        check_service_connectivity,
        validate_credential_format,
        get_safe_remediation_commands,
        create_instructor_ticket,
        search_internet_solutions,
        deep_troubleshoot_investigation,
    ],
)
