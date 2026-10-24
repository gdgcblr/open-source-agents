# Secure Agent Harness

## Overview
Secure Agent Harness is a reference implementation for building security-first AI agents. It combines deterministic policy enforcement, risk scoring, trust-aware memory, budget controls, and tamper-evident decision logging.

# Architecture
```text
+----------------+
| User Request   |
+-------+--------+
        |
        v
+----------------+
| Context Engine |
+-------+--------+
        |
        v
+----------------+
| Risk Engine    |
+-------+--------+
        |
        v
+----------------+
| Policy Engine  |
+-------+--------+
        |
   Allow|Deny
        v
+----------------+
| Budget Planner |
+-------+--------+
        |
        v
+----------------+
| Agent Runtime  |
+-------+--------+
        |
        v
+----------------+
| Action Receipt |
+-------+--------+
        |
        v
+----------------+
| Trust Memory   |
+----------------+
```

## Sentinel Layer
- Risk Engine
- Policy Engine
- Action Receipt
- Trust Memory
- Budget Planner

## Decision Flow
```text
Request -> Context -> Risk Assessment -> Policy Validation -> Budget Check
        -> Execute -> Receipt Creation -> Trust Update -> Response
```

## Module Responsibilities
| Module | Responsibility |
|---------|---------------|
| risk_engine.py | Assess risk across impact, permissions, sensitivity, reversibility |
| policy_engine.py | Deterministic security policy enforcement |
| action_receipt.py | Tamper-evident audit records |
| trust_memory.py | Provenance-aware memory management |
| budget_planner.py | Cost governance |
| scenarios.py | Benchmark scenarios |
| runner.py | Isolated execution |
| scoring.py | Security and utility scoring |
| report.py | Markdown and JSON reports |

## Security Principles
1. Least privilege
2. Explicit authorization
3. Auditability
4. Isolation
5. Cost governance
6. Trust-aware memory

## Running
```bash
python -m secure_agent_harness.cli
pytest tests/
```
