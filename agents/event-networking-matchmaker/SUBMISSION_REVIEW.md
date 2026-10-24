# Submission review

Reviewed against the fork's README, CONTRIBUTING.md and PR template at baseline `b0ad2a403b7dc731f3b5e2d5e9ba0fe07f6d4b36` on 24 October 2026. The fetched upstream and fork main branches both pointed to this commit. This is evidence of preparation, not a maintainer acceptance decision.

## Intended scope and category

Branch: `feat/event-networking-matchmaker`.

All submission files belong under `agents/event-networking-matchmaker/`. The folder is descriptive, lowercase kebab-case, and did not exist in the fetched upstream main. No root manifests, other projects, repository templates or index files are changed.

Primary fit: **AI Agents / interactive assistants**. CONTRIBUTING explicitly permits task-oriented agents and interactive assistants in `agents/`. The optional Gemini planner selects bounded `search_people` and `finish` tools; the optional MiniLM integration performs local semantic retrieval. The tested default is lexical NLP, not autonomous LLM reasoning. Do not claim a live agent/model demonstration until those optional modes are validated with a model/key.

Secondary relevance: AI-powered workflows (consented XLSX to explainable introductions) and evaluation/testing/safety patterns (retrieval checks, bounded-tool tests and consent enforcement). This is not an MCP server or a multi-agent system.

## Complete file map

All paths below are relative to the project directory.

| File/folder | Responsibility |
| --- | --- |
| `app.py` | FastAPI endpoints, authentication, imports, matching, check-ins, withdrawal and organizer actions; local CLI |
| `agent.py` | Local workflow orchestration and optional bounded Gemini tool-calling planner |
| `nlp.py` | Tokenization, aliases, phrase expansions, BM25 and optional local MiniLM encoding |
| `matching.py` | Eligibility filters, ranking, reciprocal benefits, evidence and introduction text |
| `importer.py` | XLSX validation, header mapping, consent filtering and size/row/field limits |
| `storage.py` | SQLite persistence, token hashing, imports and withdrawal suppression |
| `security.py` | Streaming request-body size limit |
| `hosted.py` | Hosted launch using provider port and exact HTTPS public origin |
| `setup_model.py` | Optional public MiniLM model download and setup check |
| `evaluate.py` | Ten synthetic retrieval cases and sequential 200-profile timing |
| `requirements.txt` | Pinned base runtime dependencies |
| `requirements-dev.txt` | Test dependencies plus base requirements |
| `requirements-semantic.txt` | Optional FastEmbed dependency |
| `constraints.txt` | Base dependency version constraints used in verification |
| `render.yaml` | Render Blueprint for a disposable fictional-data demo |
| `.env.example` | Commented configuration examples; no real keys |
| `.gitignore` | Excludes secrets, private token exports, databases, model caches, environments and editor files |
| `LICENSE` | Preserved parent MIT license |
| `static/index.html` | Attendee and organizer interface |
| `static/app.js` | Browser API calls, cards, private invitation sign-in and token export |
| `static/style.css` | Interface styling and responsive layout rules |
| `static/guide.html` | In-app organizer, attendee and privacy instructions |
| `sample/form-responses.xlsx` | Twenty synthetic rows; Adarsh is P001; eighteen consenting profiles |
| `sample/app-desktop.jpg` | Actual browser screenshot of the synthetic demonstration |
| `sample/workflow.svg` | README illustration of the before/during/after event journey |
| `tests/test_buildbuddy.py` | Import, matching, authentication, consent and workflow regressions |
| `tests/test_nlp_privacy.py` | NLP, renamed identity, cloud boundaries, host rules and privacy regressions |
| `README.md` | App overview, user journey, benefits, privacy choices and limitations |
| `DEVELOPMENT.md` | Setup, configuration, architecture, implementation, examples, tests and contribution-check summary |
| `ORGANIZER_GUIDE.md` | Form setup, import, safe token delivery, operation and retention |
| `ATTENDEE_GUIDE.md` | Sign-in, search, evidence, finding people and privacy choices |
| `DEPLOY.md` | Render configuration and email-button integration instructions |
| `PRIVACY.md` | Data boundaries, implemented protections and residual risks |
| `VERIFICATION.md` | Actual test/evaluation results and explicitly unverified features |
| `SUBMISSION_REVIEW.md` | This file map and contribution-rule assessment |

## Four contribution standards

| Standard | Evidence and qualification |
| --- | --- |
| Reproducibility | Base requirements installed in a fresh virtual environment; final 38 tests pass; pip check passes. macOS/Python 3.14.5 verified, other platforms and Render deployment not yet verified. |
| Documentation quality | Product-focused README links to DEVELOPMENT.md for setup, configuration, architecture and tests. Sample input/output, role guides, deployment instructions, model/cost assumptions and limitations remain documented. The repository requests these technical topics in README itself; this split is a deliberate presentation choice, subject to maintainer approval. |
| Security and privacy | No intended real credentials or private dataset in the Git submission. Examples contain only explicitly fictional demo/test tokens. Consent, token hashes, event isolation, withdrawal, expiring check-ins and upload bounds are tested. This is not a formal audit or a guarantee against all attacks. |
| Focused scope | Every added file lives under the one project directory; root build files and other contributors' files are untouched. |

## CONTRIBUTING workflow status

- Fork/main was fetched and verified. The local clone initially came from upstream, with the user's fork added as remote `fork`; this is operationally equivalent to a fork clone but uses different remote names (`origin` is upstream here).
- Feature branch originates from the shared upstream/fork main commit.
- Required README, `.gitignore`, `.env.example`, manifests and license are present. Technical template topics are in linked DEVELOPMENT.md rather than directly in README; maintainers may request inline sections.
- Implementation, local tests and scoped commits are prepared.
- Push to the fork, opening the upstream PR, completing its checklist, and responding to reviews remain subsequent workflow steps. A rejected push approval was not retried.
- A public evaluator URL still requires the organizer to provision and verify hosting. No live deployment, live Gemini call or MiniLM inference is claimed.

## Distinguishing features to demonstrate

1. Existing Google Form XLSX data becomes useful introductions without requiring attendees to install software.
2. Two-way relevance: what the other person can offer and what the viewer can contribute.
3. Exact profile evidence and a distinction between shared interest and expertise.
4. Expiring meeting spots connect recommendations to real-world introductions without GPS tracking.
5. Private email invitation links support pre-event matching without falsely announcing venue arrival.
6. No-key local operation, consent persistence and reproducible safety tests make the project practical to reuse.

These features support the stated criteria; they do not establish uniqueness against other entries or guarantee a competition placement.

## Reproduce the scope check

From the repository root:

```bash
git diff --name-only origin/main...HEAD
git diff --check origin/main...HEAD
git status --short
git ls-files agents/event-networking-matchmaker
```

Expected: only this project prefix in the first command, no whitespace errors, a clean worktree after committing, and no databases, `.env`, model weights, environments or private-token exports in the tracked list. Use `fork` (not `origin`) as the push remote in this checkout.
