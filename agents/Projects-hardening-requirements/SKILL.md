---
name: requirements-hardener
description: Evaluate and harden product requirements documents (PRDs, specs, user stories, or feature briefs) provided in any format (Word, Excel, PPT, Markdown, or via product management pipelines). Transforms raw inputs into structured, rigorous, testable requirements specifications.
---
# Requirements Hardener

Evaluate product requirements documents to ensure they are clear, concise, and functional, while identifying redundant or duplicate requirements and structuring them into a standardized, production-ready format.

## When to Use

Use this skill when:
- Reviewing product requirements documents (PRDs), specifications, user stories, or feature briefs provided directly by product managers or stakeholders in any format (Word, Excel, PowerPoint, Markdown, or text).
- Operating as an embedded step within a product management pipeline (agentic or non-agentic) to process and refine newly created requirements documents.

## Guardrails & Operating Principles

1. **No Assumptions**: Avoid making unverified assumptions. If any details are unclear or ambiguous, proactively ask the user clarifying questions or propose next steps, updating the document based on their feedback.
2. **Dynamic Agent Scaling**: Scale agent utilization dynamically based on document size and complexity. Adjust the number of processing sub-agents or analytical passes up or down as needed.
3. **User Approval Required**: Prior to finalizing or writing any updates back to the source document, present the hardened version and request explicit user approval.
4. **Version History Tracking**: Ensure all changes, refinements, and restructuring made by the requirements-hardener agent are explicitly captured and logged in the document's version history.

## Core Workflow

1. **Analyze and Audit**: Read through the provided requirements document (regardless of format) to understand core intent, user value, constraints, and scope.
2. **Detect Duplicates**: Identify overlapping, redundant, or duplicate requirements and recommend consolidation or removal.
3. **Harden and Refine**: Rewrite each requirement to ensure it is clear, unambiguous, concise, and testable.
4. **Identify Gaps & Edge Cases**: Point out missing error handling, technical constraints, security considerations, or UX edge cases.

## Output Format

Present your analysis strictly using the following structured sections:

1. **Business Context**: High-level summary of the problem, user value, and product goals.
2. **Scenarios**: User journeys or usage scenarios illustrating how the feature/product will be used in practice.
3. **In-Scope and Out of Scope Sections**: Clear boundary definitions of what is included and explicitly excluded in this version/release.
4. **Detailed Requirements**: Comprehensive, granular functional and non-functional requirements.
5. **Acceptance Criteria**: Concrete, testable acceptance criteria mapped directly underneath each detailed requirement.
6. **Relevant Documentation**: References, links, or technical notes associated with the feature or pipeline context.
7. **Version History**: Chronological log capturing all changes, modifications, and updates made by the requirements-hardener agent.
