# Example review: gdgcblr/open-source-agents#90

A real, unedited run of PR Slop Detector against the pull request that adds PR Slop Detector to this repo. It is a self-review, kept here because it is a useful false positive: it shows how the tool behaves when a PR's code and docs *talk about* slop phrases instead of containing slop.

| | |
| :--- | :--- |
| **PR** | [gdgcblr/open-source-agents#90](https://github.com/gdgcblr/open-source-agents/pull/90): "Feat/pr slop detector" |
| **Reviewed on** | 2026-10-24 |
| **Model** | `gemma4:e2b-it-qat` via local Ollama (default backend) |
| **Machine** | Apple M2, 8 GB RAM, macOS |
| **Run time** | 5.9 min (LLM review); the heuristics pass is instant |
| **Result** | 🔴 Likely AI slop, 62/100 (**a false positive**, see [Reviewer notes](#reviewer-notes-manual-check-of-the-verdict)) |

Nothing was posted to the PR. This was a read-only, local review.

## Command used

Run from `tools/pr-slop-detector/` with the virtual environment active. Same two steps as the [redash example](redash-7882-review.md):

```bash
# 1. Fetch the PR read-only, run heuristics, and save the PR data for re-runs
GITHUB_TOKEN=$(gh auth token) python -m slop_detector \
  "https://github.com/gdgcblr/open-source-agents/pull/90" --no-llm --save-json osa_90.json

# 2. Full review (heuristics + local Gemma 4 agent) on the saved PR
python -m slop_detector --from-json osa_90.json
```

## What the agent did

Progress printed to stderr during step 2:

```
Reviewing with ollama:gemma4:e2b-it-qat ...
  [investigator] get_pr_overview()
  [investigator] get_file_diff(tools/pr-slop-detector/slop_detector/heuristics.py)
  [investigator] get_file_diff(tools/pr-slop-detector/slop_detector/agent.py)
  [investigator] get_file_diff(tools/pr-slop-detector/slop_detector/cli.py)
```

The investigator read the overview and 3 of the 22 changed files: `heuristics.py`, `agent.py` and `cli.py`. It did not open the tests, docs or fixtures. The verdict writer then produced the structured verdict below.

## Report (verbatim output)

---

## PR Slop Check: 🔴 Likely AI slop (score 62/100)

**[gdgcblr/open-source-agents#90](https://github.com/gdgcblr/open-source-agents/pull/90)** · 22 files · +2377 / -1 · by @webobite

> This PR implements a sophisticated, multi-stage agent with excellent structure, clearly separating the investigator and verdict writer roles. It features comprehensive heuristics and modern tooling like Pydantic models, demonstrating high engineering maturity. While the design is sound, questions remain regarding scoring weights and schema enforcement with local models.

> ℹ️ None of the model's findings quote text found in the PR, so its score (95) was down-weighted.

### Findings

- **[Low]** The PR implements a sophisticated, multi-stage agent designed to detect "AI slop" using a comprehensive set of deterministic heuristics. (`tools/pr-slop-detector/slop_detector/heuristics.py, Line 1`)
- **[Low]** The agent structure correctly separates the `investigator` (heuristic analysis) from the `verdict_writer` (LLM scoring), demonstrating a sound architectural pattern. (`tools/pr-slop-detector/slop_detector/agent.py, Line 1`)
- **[Low]** The CLI provides flexible options for input (PR ref, local diff, JSON file) and output (markdown/JSON), making the tool versatile. (`tools/pr-slop-detector/slop_detector/cli.py, Line 1`)

### Strengths

- Excellent Structure and Design: The PR demonstrates a high level of engineering maturity by implementing a clear, sequential agent pattern (`investigator` -> `verdict_writer`) and separating concerns (heuristics, client, models).
- Comprehensive Heuristics: The `heuristics.py` file contains a rich, well-defined set of regex patterns targeting specific slop signals (LLM phrases, placeholders, AI artifacts), which directly addresses the project's stated goal.
- Modern Tooling: The use of Pydantic models for data structure and the integration of Google ADK show a commitment to modern, structured development practices.
- Honest Limitations: The PR description explicitly lists known limitations regarding the local model's performance and the need for external API keys, which is a sign of mature development.

### Questions for the author

1. Given the complexity of the `SLOP_DEFINITION`, how is the scoring mechanism weighted to ensure that a single, low-confidence signal doesn't disproportionately flag a PR?
2. What is the exact mechanism by which the `verdict_writer` enforces the structured `LlmVerdict` schema when using a local model like Gemma 4, which may struggle with strict JSON output?
3. How does the system handle the case where the `LLM_PROVIDER` is set to `ollama` but the model name is not explicitly provided, ensuring it defaults to a known, safe model?

<details><summary>Heuristic signals (score 48/100, 2 fired)</summary>

| Signal | Weight | Evidence |
| :--- | ---: | :--- |
| Chat-assistant text pasted verbatim | +30 | PR description: "Certainly!"<br>PR description: "Here's the updated"<br>tools/pr-slop-detector/README.md: "As an AI"<br>tools/pr-slop-detector/README.md: "I hope this helps"<br>tools/pr-slop-detector/README.md: "I hope this helps" |
| Placeholder or unfinished code | +18 | tools/pr-slop-detector/slop_detector/heuristics.py:43 `raise NotImplementedError`<br>tools/pr-slop-detector/tests/fixtures/slop_pr.json:19 `TODO: implement`<br>tools/pr-slop-detector/tests/fixtures/slop_pr.json:19 `# Add your logic here`<br>tools/pr-slop-detector/tests/fixtures/slop_pr.json:19 `your_api_key_here`<br>tools/pr-slop-detector/tests/fixtures/slop_pr.json:19 `raise NotImplementedError` |

</details>

<sub>Flag threshold: 60. This is an automated triage aid, not a judgment of the contributor. AI-assisted work is welcome when it is correct, focused, and understood. A maintainer makes the final call.</sub>

---

## Reviewer notes (manual check of the verdict)

- **The verdict is wrong; the PR is not slop.** It adds a complete tool with tests, docs, a CI workflow and a worked example, and the author can explain every part of it.
- **Every heuristic hit is the tool flagging its own subject matter** (heuristic score 48, all false positives):

  | Hit | Where it really comes from |
  | :--- | :--- |
  | "Certainly!", "Here's the updated" in the PR description | The description *quotes* these as examples of slop (line 11) |
  | "As an AI", "I hope this helps" in `README.md` | The README's signal table (line 39) and its sample reports |
  | `heuristics.py:43` `raise NotImplementedError` | One of the regex patterns in `PLACEHOLDERS` |
  | `TODO: implement`, `your_api_key_here`, ... | `tests/fixtures/slop_pr.json`, a deliberately sloppy PR used as test data |

- **The model's score contradicts its own text.** Every finding is [Low] and positive, the summary praises "high engineering maturity", yet it returned `slop_score` 95. Small local models sometimes emit a score that doesn't match their reasoning.
- **The grounding guard limited the damage but not enough.** None of the findings quoted real PR text, so the model's 95 was down-weighted to 30% (`UNSUPPORTED_LLM_WEIGHT`): `0.3 × 95 + 0.7 × 48 = 62`. Because the heuristic half was already inflated to 48, that was still just over the threshold of 60.
- **Runs are not deterministic.** An earlier run on the same PR, same model, scored 🟡 40: the model returned a low score with grounded quotes, so it got full weight (0.65) and pulled the total down. Treat a single local-model run as a lead, not a ruling.
- **The questions are the useful part.** Questions 1 and 2 (how weights stop one weak signal from flagging a PR, and how the `LlmVerdict` schema is enforced on Gemma) are fair things for a reviewer to ask. Question 3 is answered in the README's configuration table: `MODEL_NAME` defaults to `gemma4:e2b-it-qat` for Ollama.

### What this run says about the tool

Phrase and placeholder checks can't yet tell *using* a slop phrase from *quoting* one. Repos whose docs, tests or detection code discuss these phrases (including this tool's own PRs) will get inflated heuristic scores. Possible fixes:

1. Skip test fixtures (`tests/fixtures/`, data files under `tests/`) for the placeholder and leakage checks, as docs and `.env.example` are already skipped for placeholders.
2. Ignore matches inside backticks, quotation marks or markdown table cells in the description and docs.
3. Ignore matches inside string literals in source files, such as regex pattern lists.
4. Treat a model score far from what its findings support (all [Low], no quotes, score 95) as a contradiction and fall back to heuristics-only.
