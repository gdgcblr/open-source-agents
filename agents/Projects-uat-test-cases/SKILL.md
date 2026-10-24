---
name: uat-test-generator
description: Generate comprehensive end-to-end (E2E) and user acceptance testing (UAT) test cases from hardened product requirements documents or PRDs. Use when translating product requirements and acceptance criteria into executable test scenarios.
---
# E2E & UAT Test Case Generator

Generate rigorous, production-ready end-to-end (E2E) and user acceptance test (UAT) cases directly from hardened product requirements and acceptance criteria.

## When to Use

Use this skill when:
- Operating immediately after the `requirements-hardener` agent to create testing suites from newly finalized requirements.
- Reviewing a product requirements document (PRD) or feature specification to design end-to-end user flows, positive/negative validation paths, and UAT scenarios.

## Guardrails & Operating Principles

1. **No Assumptions**: If user roles, environment prerequisites, or specific integration conditions are ambiguous, ask clarifying questions before generating the test plan.
2. **User Approval Required**: Present the drafted test suite and request explicit user approval before saving or publishing the final test cases.
3. **Traceability**: Every test case must map back directly to a specific requirement ID or feature scope from the hardened requirements document.
4. **Tabular Output Only**: Output MUST strictly be provided in a tabular format (Markdown table or Excel file).

## Core Workflow

1. **Requirement & Criteria Mapping**: Analyze the detailed requirements, user scenarios, and acceptance criteria from the hardened PRD.
2. **Test Scenario Design**: Design comprehensive test scenarios covering happy paths, alternative/negative flows, and integration flows.
3. **Test Case Structuring**: Format the test cases as a table with the exact mandated columns.

## Output Format

Present your test suite strictly in a **tabular format** (Markdown table or generated Excel spreadsheet) containing the following columns:

| The Requirements ID | PASS/FAIL Drop down | Scenario | Detailed Steps | Evidence | Comments |
|---|---|---|---|---|---|
| REQ-01 | [ PASS \| FAIL ] | Scenario description... | 1. Step one<br>2. Step two | [Pending Attachment] | Execution notes... |
