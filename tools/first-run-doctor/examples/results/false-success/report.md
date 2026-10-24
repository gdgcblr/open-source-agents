# FirstRun Doctor report

**Verification: FAILED**

Run: `5a0dd295c2934e74afd0df7ac39a5d4c`

Execution: completed

| Check | Result | Evidence |
| --- | --- | --- |
| ENTRY: Declared Python entrypoint | pass | main.py |
| INPUT1: Declared input | pass | main.py |
| MANIFEST: Dependency manifest | info | None found; stdlib-only examples may not need one |
| EXEC: Command exit status | pass | 0 |
| A1: Fresh report.json | fail | Expected artifact missing |
| A1.1: status | skipped | Artifact missing |
| A1.2: items | skipped | Artifact missing |

## Next step

Check the code that creates the declared output and its required fields, then rerun.

## Evidence record

Contract SHA-256: `74669b9e2cdd5062dc1576fd77dbe9ae0d0825089db31cd469510f3ff44c5515`

Source SHA-256: `be91711d910a5dad373424bf02626232ac70e5f427a4d4ab92169090995e7cd3`

See the accompanying JSON for command, interpreter, timing, and bounded redacted logs.

Passing verifies only the declared checks. Trusted local code runs as the current OS user.
