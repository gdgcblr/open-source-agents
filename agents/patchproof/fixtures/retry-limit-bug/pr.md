# PR #43: Add retry loop and validation to `retry_request`

Fixes #42.

## Summary
- Validates `max_retries < 0` and raises `ValueError`.
- Propagates `FatalClientError` without retrying.
- Retries `TransientError` up to `max_retries` using a `while` loop.
- Adds unit tests for recovery on retry, negative `max_retries`, and `FatalClientError`.

