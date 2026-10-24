# Example issue: explicit zero timeout is discarded

Calling `parse_timeout(0)` returns the default timeout instead of preserving the
explicit value. Expected behavior: zero is a valid value and must remain zero.
The report does not include a test case; the agent should inspect the source and
then, only after authorization, run the repository tests to capture the failure.

Environment: Python 3.11+.
