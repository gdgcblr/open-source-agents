# Issue #42: Enforce bounded retry limit in `retry_request`

When `retry_request(operation, max_retries=3)` encounters transient errors, it must bound retry attempts strictly.

## Acceptance Criteria

- R-001: `retry_request` must retry transient failures at most `max_retries` times (at most `1 + max_retries` total attempts, and zero retries when `max_retries == 0`).
- R-002: `retry_request` must raise `ValueError` immediately if `max_retries < 0`.
- R-003: `retry_request` must not retry on `FatalClientError` and must re-raise it immediately.

