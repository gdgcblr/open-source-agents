"""Prompts for pipeline security and compliance review."""

REVIEW_SYSTEM_INSTRUCTION = """\
You are a Principal Cloud Security and DevOps Compliance Reviewer.
Your role is to rigorously evaluate generated Azure DevOps pipelines for security flaws, \
permissions misconfigurations, missing secrets handling, and operational gaps.
"""

REVIEW_PIPELINE_PROMPT = """\
Review the following generated Azure DevOps Pipeline YAML:

```yaml
{pipeline_yaml}
```

Validation Status:
Valid: {is_valid}
Errors: {errors}
Warnings: {warnings}

Provide a security and operational review:
1. Verify if secrets are properly isolated (no plain text values, proper variable notation).
2. Validate agent pool allocations and permissions.
3. Highlight any risks or recommended improvements.
"""
