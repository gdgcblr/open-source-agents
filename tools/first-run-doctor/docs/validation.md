# Validation

Checked on 24 October 2026: macOS 26.6.2, arm64, Python 3.11.1.
Linux and Windows were not tested. Windows execution is unsupported.

| Check | Result |
| --- | --- |
| Fresh core environment, wheel installed without runtime dependencies | Passed |
| Core suite against installed wheel, outside checkout | 27 passed; 4 optional transport tests skipped |
| Suite with optional Jev dependencies, against installed wheel | 31 passed |
| Installed wheel's offline demo, outside checkout | All four cases matched their expected outcomes |
| Ruff 0.17.2 lint and formatting | Passed |
| Gitleaks 8.30.1 project scan | No leaks found |
| Ruff security rules | One reviewed S603 finding: intentional trusted-code subprocess execution; no other findings |
| OSV query for six installed optional dependencies | No published advisories returned |

The subprocess warning is expected for this tool's purpose. Arguments are validated,
execution requires an explicit opt-in, and `shell=False` is used. This is not a
sandbox or a security certification. See [security boundaries](security.md).

## Dependency check

Versions checked through the [OSV batch API](https://google.github.io/osv.dev/post-v1-querybatch/):

```text
requests==2.34.2
python-dotenv==1.2.4
certifi==2026.10.23
charset-normalizer==3.5.2
idna==3.20
urllib3==2.8.0
```

This result covers those installed versions on that date, not every version
allowed by the manifest. Repeat checks when dependencies change. Separate Bandit
and pip-audit installation attempts timed out; Ruff security rules and the direct
OSV query supplied the completed static/dependency checks above.

## Live Jev check

One explicit request on the false-success example returned
`output_contract_failure` at confidence `0.86`; deterministic verification remained
`failed`. Provider-reported usage: 819 input tokens, 70 output tokens, cost `0.0`.
That is one observed response, not a diagnosis accuracy benchmark or future price
guarantee. Credentials and private configuration are excluded from this contribution.

## Reproduce

Follow the README installation steps, then run:

```bash
python -m unittest discover -s tests -v
first-run-doctor demo
```

The packaged examples are synthetic. [Recorded reports](../examples/results/README.md)
preserve actual checks; only interpreter paths were normalized. Tests also exercise
stale files, wrong output, preflight failures, timeouts, FIFO/symlink rejection,
bounded logs, redaction, changed expectations, and unavailable/invalid model responses.
