## Context

ClaimCheck serves maintainers reviewing execution instructions, API contracts
and image metadata. Its Python CLI discovers bounded claims, checks them against
operator-selected targets, and produces evidence independently of model prose.
Google ADK adds tool selection and explanation through a native Ollama adapter.
The product must work deterministically without access to a model.

## Goals / Non-Goals

Goals: collect real observations; distinguish drift, operational errors and
unsupported checks; provide reproducible examples and a durable development workspace.
Non-goals: execute arbitrary shell scripts on the host, scan all natural-language
prose, validate every OpenAPI feature, or infer image provenance.

## Decisions

1. Deterministic discovery creates stable claim IDs. Tools alone write verdicts;
   the model receives only known claims and cannot invent new privileged actions.
   This keeps findings comparable and supports model-free CI. Model-authored
   verdicts were rejected because explanations are not executable evidence.
2. Native Ollama /api/chat converts ADK function declarations, calls and results.
   A direct adapter keeps the transport inspectable and avoids an unnecessary
   provider-routing dependency. LiteLLM and other providers are absent.
3. README commands execute without a shell in disposable Docker containers,
   against bounded read-only snapshots with common secret filenames and caches
   excluded. Filename filtering is not content-level secret detection. Host shell
   execution was rejected because audited instructions are untrusted.
4. API targets are CLI-selected; spec servers and external references never choose
   network destinations. Mutations and authenticated operations stay unverified.
   Using spec-provided servers or arbitrary reference fetching would let project
   content choose destinations outside operator approval.
5. Docker checks compare declared final-stage configuration with image inspect,
   retaining immutable image IDs. This is not a runtime-health/provenance check.
   Inspecting an existing image avoids executing its entrypoint or automatically
   building an untrusted Dockerfile; those operations need a separate policy.
6. Operational errors and unsupported claims are separate from observed failures.
   Reports retain incomplete checks rather than inventing success.
7. Full demo compares a declared Dockerfile to an intentionally stale image.
   Synthetic fixture execution on the host is limited to our bundled server;
   audited projects are never started on the host.
   Positive controls accompany planted failures so the demo cannot succeed by
   marking every claim failed. Exact totals detect missing or duplicate checks.

## Risks / Trade-offs

- Minimal network-disabled Python sandboxes cannot reproduce arbitrary setup
  workflows. Report those limits rather than granting host/network privileges.
- Models may misuse tools or stop early. Bound calls/time, preserve partial
  evidence, and fail explicitly if checks were not completed.
- Private data in ordinary source/output may evade filename exclusions. Require
  operator review and consent for remote model/API traffic.
- Docker/Desktop and model availability are operational dependencies, not hidden
  test prerequisites. Unit tests mock model transport; the full demo is separate.

## Migration Plan

Install dependencies using `make setup`, explicitly prepare the pinned sandbox
image, and run `make doctor` before Docker-dependent checks. Configure Ollama
only for agent mode; existing deterministic audits require no model service.

No existing application data needs migration. Reports are local generated files.
To roll back an installation, uninstall the package and stop any operator-managed
test server; audits do not change the selected project or image.

Keep this change unarchived for review. Main product requirements are published
in `openspec/specs/project-claims/spec.md`. Before archive, rerun `make check`
and the full fixture demo, then reconcile any specification changes.

## Open Questions

None for the supported initial scope. Additional runtimes, writable setup steps,
authenticated API probes and full image-runtime verification require separate
changes with explicit permission and acceptance criteria.
