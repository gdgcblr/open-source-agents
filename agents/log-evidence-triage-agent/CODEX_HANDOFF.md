# GDG Hackathon — TraceGuard AI Codex handoff

## Background

This folder contains a working starter named **TraceTriage**: a Python log analysis engine, safe log-file tool, CLI, Google ADK agent, synthetic Spring Boot log and eight offline `unittest` tests. We are extending it into **TraceGuard AI**, an evidence-grounded PHP/Node.js security incident triage agent. This is a two-hour hackathon contribution to `https://github.com/gdgcblr/open-source-agents`; final deliverable is a focused PR against upstream `main`. The project belongs under `agents/<slug>/` per the GDG repo. **Avoid renaming the folder during the MVP.** The future-facing product name in the README can be TraceGuard AI.

## Objective

User inputs: synthetic/application log text or approved local log file, runtime family (`php` or `nodejs`), exact version, and whether service is internet-facing/production. Outputs: structured evidence ledger, scoped affected/fixed advisory matching, observed symptoms versus hypotheses, unknowns, human-escalation status `PASS` / `HOLD` / `ESCALATE`, safe next checks, and a repeatable evaluation summary.

- Agent must distinguish **potential vulnerability exposure** vs **suspicious activity** vs **confirmed compromise**. Never claim compromise without sufficient corroborating evidence.
- Evidence claims need valid log line/source IDs or curated advisory ID references.
- Deterministic Python modules make advisory/version decisions, critical escalation decisions and evidence validation. Gemini via Google ADK synthesizes, explains, asks for missing evidence, and follows the rules; do not rely on LLM memory for vulnerability facts.
- Golden offline tests/evals are **non-negotiable**; a working CLI/offline demo is required even when the API key is unavailable.
- All sensitive strings are redacted best-effort and **demo logs must be synthetic**.

## Official vulnerability research sources (verify them before implementing)

1. PHP release announcements: https://www.php.net/archive/2026.php and https://www.php.net/releases/8_4_27.php ; the October 21, 2026 PHP security announcement mentions CVE-2026-109618 and CVE-2026-109619 and patched PHP 8.4.27; validate coverage for other PHP branches separately.
2. Node.js October 21, 2026 security bulletin: https://nodejs.org/en/blog/vulnerability/october-2026-security-releases ; security release lines include Node.js 22.23.4, 24.22.1, and 26.12.1. Match only documented advisories and relevant runtime lines. Do not describe a patched version as universally secure.
3. Validate all version ranges, severity, advisory IDs, date and links from sources; **do not hard-code speculative CVEs or patch ranges**. Store the subset actually implemented as versioned local records.

## Existing files to inspect first

- `incident_triage/engine.py`: deterministic log triage and redaction
- `incident_triage/tools.py`: approved-directory file input and runbook tools
- `incident_triage/agent.py`: Google ADK `root_agent`; dotenv and env-provided model
- `incident_triage/cli.py`: offline CLI
- `tests/test_engine.py`: eight offline tests
- `.env.example`, `requirements.txt`, `README.md`, `samples/spring-boot-incident.log`

Baseline (run from THIS folder):

```powershell
python -m unittest discover -s tests -v
python -m incident_triage.cli --file samples/spring-boot-incident.log
```

Previous environment showed 8/8 tests passing; **rerun locally before claiming any result**. Live ADK/Gemini has not yet been verified.

## Required engineering scope

1. **Security matcher**: Structured local advisory records with publisher, publication date, affected/fixed ranges, authoritative links, runtime family, and CVE where applicable. Make matching deterministic, branch-specific, and conservative. Missing version → UNKNOWN rather than guessed fixed.
2. **Evidence ledger**: Session-scoped input and tool results with stable evidence IDs (log line, advisory). Claim-to-evidence validation, unknowns, goal completion indicator, no unnecessary long-term persistence or leaking of secrets.
3. **Escalation policy**: `ESCALATE` for configured critical internet-facing exposure, likely compromise, exfiltration indicators, or other clearly high-impact patterns; `HOLD` for missing version, contradictory/unsupported claims, non-verifiable citations; `PASS` for defensible low-risk summaries. Emit reasons and recommended human verification steps. No automatic patching, paging, external incident calls, or production writes.
4. **Credibility gate**: Structured final JSON fields; reject claims without evidence, advisory IDs not found in local records, log references not in input, and any model attempt to downgrade mandatory escalation.
5. **Evals (most important)**: Golden data + deterministic tests with expected `PASS/HOLD/ESCALATE`, expected affected/unaffected/unknown, citation grounding, redaction, conflicting data, injection-in-log resistance, invalid version handling, regression protection. Report actual number of passing tests and any known limitations. If API key available, add one small reproducible ADK eval case or smoke test and clearly separate online from offline results.
6. **Separation of concerns**: Keep `core` logic independent of CLI / ADK UI adapters. Refactor in small steps rather than rebuild.
7. **Config/deployment**: `GOOGLE_API_KEY`, `MODEL_NAME`, approved local log dir and any optional model path from env; never commit secrets. Native Windows-first Python setup. Optional small Dockerfile only if time permits; verify actual Docker behavior if claimed.
8. **Docs/open source**: Update README to show a demo, requirements, installation, expected outputs, Windows commands, constraints, sources, eval command/results. Add `GOOD_FIRST_ISSUES.md` with scoped future enhancements and a couple of clear newcomer tasks.

## Time-boxed milestones

- **M0 (5–10 min)** Inspect source/upstream guidelines, rerun baseline, decide minimal component boundaries. Note any conflict with upstream instructions.
- **M1 (20–25 min)** Implement scoped PHP/Node advisory matching and synthetic fixtures; add version matching tests.
- **M2 (20–25 min)** Add evidence ledger, mandatory human escalation, credibility validator; add negative and injection/unknown tests.
- **M3 (10–15 min)** Connect Google ADK adapter and CLI/report; keep offline flow fully usable.
- **M4 (25–30 min; reserve this)** Run offline golden evaluations and regression suite. If permitted/configured, live Gemini/ADK smoke test. Fix failing credibility/critical-escalation checks rather than expanding scope.
- **M5 (15–20 min)** README, env security, optional Docker/Linux smoke, good-first issues, PR prep; don't push without asking.

## Minimum golden cases

- PHP 8.4.26 and PHP 8.4.27 **for only the scoped October 2026 advisories**. Validate version details from PHP primary sources.
- Node 22.23.3 and 22.23.4 **for only the scoped October 2026 advisories**. Validate from Node primary source.
- Unknown/invalid version -> UNKNOWN and HOLD, not invented vulnerability status.
- Public production service with scoped critical affected runtime -> ESCALATE with authoritative source.
- Suspicious log evidence on a patched runtime -> investigate observed activity; do not pretend patched runtime proves no incident.
- Log with benign entries -> no invented root cause or compromise assertion.
- Log with embedded model instructions -> ignore instructions, analyze as data.
- Secret-bearing log -> output redaction verified.
- Contradictory evidence or invalid citation -> HOLD, no confident diagnosis.
- Agent-generated claim unsupported by logs/advisories -> blocked by validator.

## Definition of done

- Existing and added offline tests all pass locally with command + count recorded.
- Demonstrate a vulnerable PHP example with human escalation, a patched Node example with correctly scoped status, and a hallucination/unsupported-claim rejection fixture.
- README reproduces the setup on Windows, with optional Linux/Docker caveats as appropriate.
- `.env` and sensitive fixtures are excluded from git, only project folder changes staged; clean PR against upstream main after approval.
- If any milestone is unfinished, clearly disclose missing verification rather than representing it as complete.

## How Codex should work in this session

1. Start by reading `AGENTS.md`, this handoff and the existing README/tests. Run baseline tests.
2. Give a concise status and initial implementation plan; then implement the above milestones one by one. Work on files, run tests, and show concrete results rather than only describing proposed code.
3. Prefer completing the MVP and evals over adding UI/deployment extras.
4. Ask explicit approval before committing, pushing, opening a PR or making external system changes.
