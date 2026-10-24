# Buggy Service Incident Demo

This directory contains a self-contained buggy e-commerce service designed for quick verification of the **Incident Analyzer**.

## Files
- `service.py`: An order processing service with an intentional `AttributeError` when `discount` is `None`.
- `incident.log`: The captured runtime stack trace, including sensitive JWT tokens in headers (to demonstrate automatic secret scrubbing).

## 30-Second Reproducible Walkthrough

From the `agents/incident-analyzer` root:

```bash
# 1. One-time Setup: Index the service and export human-readable Markdown spec
python main.py index examples/buggy_service --markdown

# 2. Run Incident Diagnosis in Mock Mode (zero API keys needed)
python main.py analyze \
    --spec examples/buggy_service/.incident-spec.json \
    --log-file examples/buggy_service/incident.log \
    --expected '{"status": "confirmed", "final_amount": 45.0}' \
    --actual 'AttributeError: NoneType object has no attribute get' \
    --mock
```

Notice in the output:
1. The sensitive JWT bearer token in `incident.log` is automatically sanitized.
2. The failure is correlated to `apply_discount_code` in `service.py`.
3. A unified git diff patch is generated and validated against Python AST syntax.
