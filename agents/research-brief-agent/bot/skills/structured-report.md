# Structured research report

Use this skill when the user asks for a research brief, memo, or report.

## Required sections (in order)

Use these exact level-2 headings in the final reply:

1. `## Executive Summary` — 3–5 sentences, decision-oriented.
2. `## Key Findings` — bullet list; each bullet cites a source (bundled filename or URL).
3. `## Evidence Table` — markdown table with columns: Claim | Source | Confidence (high/medium/low).
4. `## Risks & Uncertainties` — gaps, conflicts, or weak evidence.
5. `## Recommended Next Steps` — numbered, actionable.
6. `## Sources` — list every bundled file read and every URL fetched.

## Grounding rules

- Call `list_bundled_sources` when the user did not name a file but wants a demo.
- Call `read_bundled_source` for each bundled file you rely on.
- Call `fetch_source` only for URLs the user supplied or that appear in sources they pasted.
- Do not invent URLs or quote text you did not retrieve via tools.
- If evidence is thin, say so under Risks & Uncertainties instead of filling with generic prose.

## Tone

Professional, concise, neutral. Prefer bullets and tables over long paragraphs.
