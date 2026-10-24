# Mutation Auditor

Mutation score: 66.7%

Total mutants: 3

- KILLED: 2
- SURVIVED: 1

Score uses PIT's detected flag, which can include timeouts and error outcomes, not only failing assertions. Inspect status counts before drawing conclusions. Empty/incomplete reports have no score. Scope is the supplied PIT report; this is not a guarantee of safe changes.

## Findings

- SURVIVED `example.DiscountService.eligible` line 6: changed conditional boundary
