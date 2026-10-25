# Security — pinpoint-mcp-server

Threat model (STRIDE-lite). Test IDs are **planned**; none have run yet.

| Threat | Mitigation | Guardrail | Test (planned) | Residual risk |
| :--- | :--- | :--- | :--- | :--- |
| Prompt injection via stored conversation text | Output wrapped under `untrustedContent`; injection phrases flagged | G5 | T-GR-2, T-TOOL-4 | Heuristic flag only; a host model may still follow injected text. Hosts must treat the field as data. |
| Path traversal on export/import | Strict filename regex, forced `.json`, resolved path must stay inside dir, symlinks rejected | G6 | T-GR-3, T-TRF-3 | Race between check and open on a local attacker-controlled dir. |
| Secret leakage into storage or logs | Pattern redaction before storage; audit logs args hash only | G4, §6.8 | T-GR-1, T-AUD-1 | Pattern-based; can miss unusual secret formats. |
| DoS via huge inputs or call floods | Length clamps, capacity limits, per-minute rate limit, store size cap | G2, G3, G8 | T-GR-4, T-STO-5 | Process-wide limit only; no per-client identity. |
| Corrupted store or bad import | Atomic write, quarantine, corrupt file renamed not deleted | G12 | T-STO-2, T-STO-3, T-STO-4 | Single-writer assumption. Two processes can race. |
| Malicious import bundle | Size cap, kind check, per-record validation, quarantine | G1, G12 | T-TRF-3 | Bundle contents are kept as data; no execution. |
| stdout corruption breaks the MCP stream | stderr-only logger; static no-`console.log` test | G10 | T-OFF-2 | A future dependency could write to stdout. |
| Outbound network access | No network APIs in `src/`; static verifier | G9 | T-OFF-1 | Verifier is regex-based; dynamic `import()` is also banned to narrow it. |
| Supply chain | Two runtime dependencies; `npm audit` gate; lockfile committed | S5 | `npm run audit:deps` | Transitive dependencies of the MCP SDK and zod. |

## Responsible disclosure

Report security issues through a GitHub issue on the upstream repository (gdgcblr/open-source-agents), or contact the maintainer via GitHub. Do not post exploit details publicly before a fix.
