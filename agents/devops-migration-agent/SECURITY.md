# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability or secret leakage within the DevOps Migration Agent, please do not disclose it publicly on GitHub issues.

Instead, please report security vulnerabilities directly to the maintainers or via GitHub Security Advisories.

## Security Controls

- **No Workflow Script Execution:** All workflows are analyzed statically. Shell code is never executed.
- **Safe Deserialization:** Only PyYAML `safe_load` is utilized.
- **Zero Secrets Policy:** Secrets and credentials are never stored, logged, or printed.
- **Local / Offline Operation:** The agent can operate 100% offline without communicating with any external network service.
