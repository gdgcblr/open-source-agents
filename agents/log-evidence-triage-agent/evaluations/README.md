# Evaluation results

Observed on 2026-10-24, Windows 11 Home (10.0.26300), Python 3.12.10. Baseline before changes: **8 tests passed**.

## Reproduce

From the project directory:

```powershell
# Standard-library suite; optional ADK tests skip when ADK is absent
py -3.12 -m unittest discover -s tests -v

# Full suite with the pinned optional dependencies installed
.\.venv\Scripts\python.exe -m incident_triage.evaluate
```

The actual [report.json](report.json) contains **137 total tests: 137 passed, 0 failed, 0 skipped**. Failed-case details are therefore empty. `python -m pip check` reported no broken requirements. The standard-library interpreter run discovered the same 137 tests: **130 passed, 0 failed, 7 skipped**, with ADK absence explicitly reported.

The 15 scenarios in [golden.json](golden.json) expand into named, separately counted assertions. Test counts are not counts of unique incidents. Boundary tests additionally check the version immediately below and at each of seven supported branch fixes (14 expectations inside one test).

| Golden/targeted metric | Observed result |
| --- | --- |
| Version-match outcomes | 15/15 correct |
| Citation membership and original excerpt validity | 15/15 passed |
| Mandatory escalation recall | 7/7 cases escalated |
| Decision accuracy | 15/15 correct |
| Repeated deterministic report consistency | 15/15 identical |
| No unsupported confirmed-compromise assertions | 15/15 passed; zero such assertions |
| Unsupported claim/citation rejection | 5/5 targeted tests passed |
| API/configuration/timeout fallback | 6/6 targeted tests passed |
| ADK offline integration | 7/7 passed |

The critical-escalation group includes all seven mandatory cases: vulnerable PHP, vulnerable public Node, suspected compromise, conflicting-but-critical metadata, prompt injection on a critical runtime, possible credentials, and exfiltration mentions. It measures the policy on synthetic cases, not real-world detection sensitivity.

Additional safety/regression tests cover malformed/stale/future advisory data, invalid versions, branch isolation, secret formats, multiline private keys, size/line/encoding limits, safe file errors, containment, input types, evidence isolation, late critical indicators, CLI behavior, and the original operational detectors.

## ADK integration and live observations

`test_adk.py` uses the installed Google ADK runner, session service, function tools, and public agent with an offline fake model. It exercises tool calling, grounding, fabricated output rejection, missing tool calls, API exception fallback, concurrent-session isolation, sanitized logging, and invalid/missing-key input behavior. These are deterministic integration tests, not probabilistic ADK EvalSet or LLM-as-judge scores. No network or credentials are required for the automated suite.

A separate live synthetic smoke run succeeded using **gemini-3.5-flash-lite**, ADK 2.13.0, and the Gemini Developer API. The [recorded result](live-smoke.json) is `ai_assisted_validated`, `PASS`, and zero rejected claims for `samples/node-patched.log`. Reproduce with:

```powershell
$env:MODEL_NAME = 'gemini-3.5-flash-lite'
.\.venv\Scripts\python.exe -m incident_triage.cli --file samples/node-patched.log --product nodejs --version 22.23.4 --ai --format json
```

Other live observations during implementation: the previously configured `gemini-2.5-flash` returned a model/endpoint rejection; `gemini-3.8-flash` attempts timed out or returned a provider failure; one early Flash Lite response used an invalid claim shape and was correctly rejected. The prompt was made explicit about claim objects, and the strict gate was retained. These exploratory attempts are not folded into the offline metrics or presented as a live accuracy score. Tokens and monetary cost were not measured. Provider availability and latency can change.

The [PHP demo output](php-demo-output.json) is generated from the committed synthetic sample, not a hand-written illustrative incident report.

A clean copied-source run with no `.env`, no virtual environment, and Python `-S` (site packages disabled) also passed: 130 tests passed, seven optional ADK tests skipped, and the PHP offline demo returned ESCALATE. See [reproducibility.json](reproducibility.json).

## Coverage limitations

- All incident fixtures are synthetic, with no production ground truth or forensic validation.
- Three CVEs and seven branch boundaries are a small curated subset. The PHP October 23 notice remains unresolved.
- Numeric matching assumes a truthful exact upstream version; it does not attest deployment, vendor backports, or exploit prerequisites.
- Citation validity proves a claim belongs to the canonical report and refers to present evidence, not that an untrusted log statement is true.
- Redaction and security indicators are heuristic. Tests do not establish comprehensive DLP, compromise detection, or jailbreak resistance.
- AI output is restricted to canonical finding selection; useful unconstrained prose is intentionally not evaluated.
- Windows 11/Python 3.12.10 was tested. Linux/macOS/container execution and Vertex AI remain untested; Docker was unavailable.
- Freshness tests use explicit fixture dates. Normal CLI runs use the current UTC date and will HOLD when this snapshot becomes stale.
