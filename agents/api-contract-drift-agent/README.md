# API Contract & Gateway Security Drift Agent

An autonomous AI agent designed for microservice ecosystems to eliminate silent interface failures and security regressions by analyzing backend controller code against OpenAPI/Swagger specifications and API Gateway security policies.

---

## The Problem

In distributed microservice architectures, backend endpoints change rapidly. Developers rename fields, introduce enum constraints, alter HTTP verb mappings, or omit route-level authorization annotations (`@PreAuthorize`, `@RolesAllowed`) in controller code without updating the corresponding OpenAPI schemas.

This causes two major issues in production:
1. **Downstream Interface Crashes**: Consumer teams (web, mobile, partner microservices) deserialize against outdated contracts, triggering runtime NPEs and serialization errors.
2. **Security & Policy Drift**: Endpoints intended to be private or restricted to specific OAuth2/JWT scopes (e.g., `admin:write`) are accidentally exposed publicly due to missing code guards.

---

## Features

- **Schema Parity Verification**: Detects removed fields, renamed properties, altered types, missing routes, and HTTP verb mismatches.
- **API Gateway Security & Policy Drift Checker**: Audits route-level OAuth2 scopes, Bearer schemes, and role requirements against actual backend controller guards.
- **Categorized Severity**:
  - `CRITICAL`: Unguarded routes, unauthenticated sensitive data exposure.
  - `BREAKING`: Schema mismatches that crash downstream consumers.
  - `WARNING`: Undocumented fields, extra endpoints, non-breaking changes.
  - `INFO`: Cosmetic documentation discrepancies.
- **Dual Remediation Generation**: Automatically generates OpenAPI JSON patches and backend code snippets (e.g., Spring Security annotations) to fix detected drift.
- **CI/CD Ready**: Prints rich terminal summaries and writes structured `drift_report.md` reports for automated PR checks.

---

## Security & Multi-Layer Guardrails

This agent enforces strict security guardrails across three stages:

1. **Pre-Execution Scanning**:
   - **Secret Leak Prevention**: Scans input files with deterministic regex checks for leaked credentials (API keys, Bearer tokens, private keys, AWS secrets) and aborts execution before data leaves the machine.
   - **Path Traversal Defense**: Enforces path resolution bounds and limits single-file input payloads to $\le 256\text{ KB}$.
   - **Prompt Injection Defense**: Evaluates comments and descriptions for adversarial override instructions.

2. **Model Safeguards**:
   - **Prompt Isolation**: Isolates user code and spec definitions inside strict `<analyzed_artifacts>` XML delimiters.
   - **Safety Filters**: Configured with strict harm blocking thresholds.
   - **Deterministic Output**: Operates with `temperature=0.0` and structured Pydantic schema validation.

3. **Post-Execution Output Validation**:
   - **Syntax Validator**: Checks generated OpenAPI JSON patches for valid structure before writing to disk.

---

## Prerequisites

- Python 3.10+ (tested on Python 3.10, 3.11, 3.12)
- A Google Gemini API key ([Google AI Studio](https://aistudio.google.com/))

---

## Installation

```bash
cd agents/api-contract-drift-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY