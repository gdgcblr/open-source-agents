# 2. The report never writes the patch; apply re-runs the tests

Date: 2026-10-24
Status: Accepted

## Context

Human review happens in a static HTML report. The page could assemble a patch itself
from the ticked removals, which would save a step. But tests in `run` were passed by
the full set of removals, not by whatever subset the developer ticks, and dropping
one removal can break another (a kept function may call a helper that is still ticked).

## Decision

The report only builds a command, such as `dead-code-reaper apply --keep 5`, which the
developer copies into a terminal. `apply` adds any removals that the kept ones depend
on to the keep list, runs the project's tests once on the final selection, and writes
the patch only if they pass. The report itself never produces a patch.

## Consequences

- Every patch the tool writes has passed the project's tests, whatever was unticked.
- Human review costs one extra step (paste a command) and one extra test run.
- The report stays a plain file with no server, so it can be shared, attached to a
  pull request, or kept as a CI build artifact.
- `apply` needs the state saved by `run` (what was verified, and against which version
  of each file), and must refuse to apply if those files have changed since.
