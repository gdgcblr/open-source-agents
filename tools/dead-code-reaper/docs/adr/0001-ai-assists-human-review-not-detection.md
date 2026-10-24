# 1. AI assists human review; it never decides what is dead

Date: 2026-10-24
Status: Accepted

## Context

dead-code-reaper is submitted to a collection of AI agents and AI developer tools, so
using AI for detection would be the obvious choice. But an AI judgment that code is
unused can't be checked, and a wrong deletion breaks the user's project. Reading the
code and running the project's tests can show, with evidence, that a removal is safe.

## Decision

Dead code is found and proven by deterministic steps only: static analysis, then
deleting the code and running the project's tests. AI adds an AI note and, where it
sees one, a risk warning to each removal during human review. A risk warning makes a
removal start out kept, but the developer makes the final call. Everything works with
AI turned off.

## Consequences

- Same project and same tests give the same removals, so results are reproducible.
- AI can't cause a deletion. At most it moves a removal from ticked to kept.
- The AI part is smaller than in a typical AI tool, so the README must explain this
  choice clearly to reviewers who expect AI to do the detecting.
- AI calls are only made for removals that already passed the tests, which keeps
  their number and cost low.
