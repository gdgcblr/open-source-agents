# Good first issues

Each task should stay in this agent directory, use synthetic data, and preserve the existing golden tests.

1. **Add a JSONL application fixture.** Include five synthetic structured events, document which fields are currently treated as plain text, and test line references and redaction. Do not add a parser dependency.
2. **Test additional redaction formats.** Add synthetic escaped JSON credentials and URL-encoded query secrets. Fix a demonstrated leak, retain line numbering, and verify full report output rather than only the redaction helper.
3. **Verify Linux and macOS setup.** Run clean offline and optional ADK installation/tests on one platform. Record Python/dependency versions and actual results; update the platform table only after execution.
4. **Add one Node.js advisory.** Verify a missing October bulletin CVE from the publisher, record branch-specific ranges and severity, and add below/at-fix and unsupported-branch cases. A security-aware maintainer must review provenance.
5. **Resolve the PHP follow-up notice when published.** Verify complete publisher ranges and configuration prerequisites, then replace the coverage notice only if the matcher can represent them honestly. Add a patched-but-configuration-unknown fixture.
6. **Improve offline report readability.** Add a Markdown exporter from the existing JSON schema; preserve every evidence reference, unknown, and mandatory decision. No model-generated prose or external writes.

Larger future work: signed advisory provenance, vendor backport evidence, trace-ID correlation, reviewed configuration applicability, and optional live ADK EvalSets. These need design review and are not beginner-sized changes.
