# Advisory provenance and updates

`advisories.json` is a hand-reviewed, partial snapshot checked on 2026-10-24. The tool does not download advisories at runtime.

The two PHP records use the PHP project's [OOM advisory](https://github.com/php/php-src/security/advisories/GHSA-w8hw-w9fx-j79w) and [stale-state advisory](https://github.com/php/php-src/security/advisories/GHSA-6wmf-4rv5-p3rp), published October 21. The publisher lists the four branch fixes and critical severity. Coverage here deliberately starts at 8.2.0; older branches, source backports, and prereleases are outside the matcher.

The Node record uses the project's [October 21 bulletin](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases). It identifies CVE-2026-111497 as high severity, affected 22.x/24.x/26.x release lines, and security releases 22.23.4/24.22.1/26.12.1. Other CVEs and dependency updates in that bulletin are not included.

For each branch, `introduced` is the inclusive lower bound of this curated coverage, `fixed` is both the exclusive affected upper bound and inclusive fixed lower bound, and `branch_end` is the exclusive end of the fixed range. These bounds encode the publisher's branch-level statements; they do not establish the exact introducing commit. Severity remains null if a future publisher record does not establish it. Do not invent a score from a descriptive title.

The [October 23 PHP follow-up](https://www.php.net/archive/2026.php) is recorded as an unresolved notice. Its ranges are deliberately not guessed. PHP reports HOLD for manual verification even when the two October 21 CVEs are fixed, unless another condition already requires ESCALATE.

To update:

1. Read the primary publisher advisory and release details. Confirm CVE identity, publication date, severity, affected branches, fixes, prerequisites, and later corrections.
2. Update only verified fields and explicit ranges. Keep unknown coverage as a notice. Never refresh `verified_on` merely to silence staleness.
3. Review the whole snapshot before updating its verification date. Schema validation and URL allowlisting do not prove authenticity.
4. Add independent below-fix/at-fix/other-branch expectations and any new escalation fixture. Keep old regression cases where still applicable.
5. Run the complete suite and evaluator. Record intentional fixture-date changes and reviewer rationale.

An operator-supplied `TRIAGE_ADVISORY_PATH` has the same trust requirements. Malformed or unverified data fails closed to UNKNOWN. Missing/severely corrupted data cannot preserve knowledge it no longer contains; urgent log indicators still escalate independently.
