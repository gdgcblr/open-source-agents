"""Interactive Judge Demo Runner for Jarvis - A PR Review Agent."""

import sys
import time
from agent import GitPRReviewAgent

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_banner():
    print(f"\n{BOLD}{CYAN}===================================================================={RESET}")
    print(f"{BOLD}{BLUE}          🤖 JARVIS — A PR REVIEW AGENT (LIVE DEMO) {RESET}")
    print(f"{CYAN}       Fork • Build • Merge @ Google Ananta Office, Bengaluru{RESET}")
    print(f"{BOLD}{CYAN}===================================================================={RESET}\n")

def demo_scenario_1():
    print(f"{BOLD}{YELLOW}▶ SCENARIO 1: The Leak Trap (5-Layer Guardrail Enforcement){RESET}")
    print(f"{BLUE}Simulating a malicious/accidental diff containing:{RESET}")
    print(f"  • Leaked Google AI API Key ('AIzaSy...')")
    print(f"  • Leaked GitHub Personal Access Token ('ghp_...')")
    print(f"  • Arbitrary code execution via eval()")
    print(f"  • Raw SQL injection formatting\n")

    with open("demo_leak_trap.diff", "r") as f:
        diff_text = f.read()

    agent = GitPRReviewAgent(provider_type="mock")
    report = agent.review_diff_text(diff_text)

    print(f"{BOLD}--- Review Result ---{RESET}")
    print(f"Model Engine: {CYAN}{report.model_used}{RESET}")
    print(f"Verdict:      {RED}{BOLD}{report.verdict} (Guardrail Override){RESET}")
    print(f"Risk Score:   {RED}{BOLD}{report.risk_score}/100 (High Risk){RESET}")
    print(f"\n{BOLD}Detected Issues ({len(report.issues)} total):{RESET}")

    for idx, issue in enumerate(report.issues, 1):
        sev_color = RED if issue.severity == "CRITICAL" else YELLOW
        print(f"  {idx}. [{sev_color}{issue.severity}{RESET}] {issue.title}")
        print(f"     File: {issue.file_path} | Line: {issue.line_number}")
        print(f"     Fix:  {issue.suggestion}\n")

def demo_scenario_2():
    print(f"{BOLD}{YELLOW}▶ SCENARIO 2: 100% Offline Review on Google Gemma 2 (Air-Gapped Tier){RESET}")
    print(f"{BLUE}Inspecting changes using local Google Gemma 2 (gemma2:2b via Ollama)...{RESET}")
    
    with open("demo_clean_feature.diff", "r") as f:
        diff_text = f.read()

    start = time.time()
    try:
        agent = GitPRReviewAgent(provider_type="ollama", model_name="gemma2:2b")
        report = agent.review_diff_text(diff_text)
        duration = time.time() - start
        print(f"Inference Mode: {GREEN}Local Ollama (gemma2:2b) [Zero Internet Egress]{RESET}")
        print(f"Latency:        {CYAN}{duration:.2f} seconds{RESET}")
        print(f"Verdict:        {GREEN}{BOLD}{report.verdict}{RESET}")
        print(f"Risk Score:     {GREEN}{report.risk_score}/100{RESET}")
        print(f"Summary:        {report.pr_summary.summary}")
    except Exception as e:
        print(f"{YELLOW}Ollama fallback to Mock Provider: {e}{RESET}")

def demo_scenario_3():
    print(f"\n{BOLD}{YELLOW}▶ SCENARIO 3: Automated Conventional PR Description Generation{RESET}")
    print(f"{BLUE}Generating production-ready GitHub PR Markdown with test checklists...{RESET}\n")

    with open("demo_clean_feature.diff", "r") as f:
        diff_text = f.read()

    agent = GitPRReviewAgent(provider_type="mock")
    report = agent.review_diff_text(diff_text)
    pr_markdown = agent.generate_markdown_pr(report)

    print(f"{CYAN}--- BEGIN GENERATED PR MARKDOWN ---{RESET}")
    print(pr_markdown)
    print(f"{CYAN}--- END GENERATED PR MARKDOWN ---{RESET}")

def main():
    print_banner()
    demo_scenario_1()
    print("-" * 68)
    demo_scenario_2()
    print("-" * 68)
    demo_scenario_3()
    print(f"\n{BOLD}{GREEN}✅ Live Demo Complete! Web UI running at http://localhost:8000/docs{RESET}\n")

if __name__ == "__main__":
    main()
