# Security boundaries and review notes

## Intended use

FirstRun Doctor runs **trusted local Python code** as the invoking OS user.
`--execute` is an explicit execution opt-in. `demo` runs bundled trusted examples.
The tool is not a sandbox or a malware scanner. Do not use it to execute an
unreviewed contribution just because it has a `doctor.json` file.

## Controls implemented

- Command lists and `shell=False`; only local `.py` entrypoints in v0.1.
- Strict contract validation, duplicate-key rejection, relative paths, protected
  inputs, non-overlapping file artifacts, and source/artifact symlink rejection.
- Fresh working copies omit declared generated files, known credential files,
  `.env`, and environments/caches. Original output files are not removed.
- Bounded copying and verifier reads. Child stdout/stderr are drained with capped
  capture to avoid log-buffer growth/deadlocks.
- POSIX process-group termination on timeout, interruption, or completion.
- Minimal child environment; optional model credentials are not inherited.
- Known-value and pattern redaction, terminal-control removal, and escaped Markdown
  evidence. No target artifact contents are copied into reports.
- New report directories only; comparison flags changed contracts or runtimes.
- Jev receives only bounded redacted evidence, with fixed categories, verified TLS,
  disabled redirects, explicit timeouts, no automatic retries, and no execution authority.

## Limits

Trusted code can still access the current user's files, network, and resources,
write outside its working copy, or detach into a new process group. Directory
copying is not OS-level containment, and path checks are not a complete defense
against actively hostile code racing filesystem operations. Redaction cannot
identify every private value, encoding, or transformed credential. Review exported
reports before sharing them.

## Reproducing the security checks

Run the test suite from the project README. It includes path/symlink rejection,
stale-file exclusion, secret/environment boundaries, bounded capture, process
timeouts, and model-response validation. `docs/validation.md` records actual scans
and results. Passing those checks is not a security certification.

Security fixes should include a focused regression. Report a real vulnerability
privately to repository maintainers using their supported security contact; do not
publish credentials or exploitable private data in an issue.
