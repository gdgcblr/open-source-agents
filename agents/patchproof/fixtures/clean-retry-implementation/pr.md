# PR #44: Correctly bound retry loop and add boundary exhaustion tests

Fixes #42.

## Summary
- Validates `max_retries < 0` and raises `ValueError`.
- Propagates `FatalClientError` immediately without retrying.
- Uses `while retries < max_retries:` after the initial attempt so at most `max_retries` retries are executed.
- Includes boundary unit tests asserting exact `call_count` on exhaustion for `max_retries=3` and `max_retries=0`.

