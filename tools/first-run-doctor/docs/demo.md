# A 90-second demo

After installing the package, run:

```bash
first-run-doctor demo --output-dir .doctor-reports/presentation
```

Use a fresh directory name if that one already exists. This command explicitly
runs four trusted packaged examples and saves real JSON/Markdown evidence.

Expected case outcomes (not an accuracy benchmark):

| Case | What happens | Verification |
| --- | --- | --- |
| missing-config | Required `APP_MODE` is absent; target is not run. | unknown |
| false-success | Program exits zero but writes no report. | failed |
| invalid-output | Report exists but its items list is empty. | failed |
| working | Fresh report satisfies the same output assertions. | verified |

1. **0-10 seconds:** Explain: "An agent saying success does not prove its example worked."
2. **10-30:** Run the demo and open `false-success/report.md`.
3. **30-50:** Point to exit zero and the failed fresh-file check.
4. **50-65:** Show the `working` fixture's small output-writing implementation.
5. **65-80:** Open `working/report.md`: fresh artifact hash and both field assertions pass.
6. **80-90:** Compare the two runs:

```bash
first-run-doctor compare .doctor-reports/presentation/false-success/report.json .doctor-reports/presentation/working/report.json
```

The fixtures use the same command and output contract. This demonstrates a
reproducible before/after example, not proof that all real agents are reliable.

The demo is fully offline. A live Jev call can be shown separately after explicitly
configuring the optional extra and key; the presentation does not depend on it.
