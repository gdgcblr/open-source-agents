"""Unit tests for GitHub Actions workflow parser."""

import pytest

from tools.github_parser import (
    WorkflowParseError,
    detect_hardcoded_credentials,
    parse_workflow_content,
)

SAMPLE_WORKFLOW_BOOLEAN_ON = """
name: Boolean On Test
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run test
        run: echo "Hello world"
"""

SAMPLE_STRING_ON = """
name: String On Test
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Build"
"""

SAMPLE_LIST_ON = """
name: List On Test
on: [push, pull_request, workflow_dispatch]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Build"
"""

SAMPLE_SCHEDULE_ON = """
name: Schedule Test
on:
  schedule:
    - cron: '0 2 * * *'
jobs:
  nightly:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Nightly"
"""

SAMPLE_SECRETS_WORKFLOW = """
name: Secrets Test
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy
        run: echo "Deploying"
        env:
          API_KEY: ${{ secrets.DEPLOY_API_KEY }}
          DB_PASS: ${{ secrets.DATABASE_PASSWORD }}
"""


def test_parse_boolean_on_trigger():
    """Confirms parser correctly handles PyYAML's parsing of 'on' as boolean True."""
    wf = parse_workflow_content(SAMPLE_WORKFLOW_BOOLEAN_ON)
    assert wf.name == "Boolean On Test"
    assert wf.triggers.push is not None
    assert wf.triggers.push.branches == ["main"]
    assert wf.triggers.pull_request is not None
    assert wf.triggers.pull_request.branches == ["main"]
    assert len(wf.jobs) == 1
    assert "test" in wf.jobs
    job = wf.jobs["test"]
    assert len(job.steps) == 2
    assert job.steps[0].uses == "actions/checkout@v4"
    assert job.steps[0].action_name == "actions/checkout"
    assert job.steps[0].action_version == "v4"


def test_parse_string_on_trigger():
    wf = parse_workflow_content(SAMPLE_STRING_ON)
    assert wf.triggers.push is not None
    assert wf.triggers.pull_request is None


def test_parse_list_on_trigger():
    wf = parse_workflow_content(SAMPLE_LIST_ON)
    assert wf.triggers.push is not None
    assert wf.triggers.pull_request is not None
    assert wf.triggers.workflow_dispatch is True


def test_parse_schedule_trigger():
    wf = parse_workflow_content(SAMPLE_SCHEDULE_ON)
    assert wf.triggers.schedule is not None
    assert wf.triggers.schedule.cron == ["0 2 * * *"]


def test_detect_secrets_references():
    wf = parse_workflow_content(SAMPLE_SECRETS_WORKFLOW)
    assert "DEPLOY_API_KEY" in wf.detected_secrets
    assert "DATABASE_PASSWORD" in wf.detected_secrets
    assert len(wf.detected_secrets) == 2


def test_detect_hardcoded_credentials():
    clean_text = "echo 'No secrets here'"
    assert len(detect_hardcoded_credentials(clean_text)) == 0

    token_text = "token: ghp_123456789012345678901234567890123456"
    findings = detect_hardcoded_credentials(token_text)
    assert len(findings) == 1

    aws_text = "key: AKIAIOSFODNN7EXAMPLE"
    assert len(detect_hardcoded_credentials(aws_text)) == 1


def test_invalid_yaml_raises_error():
    bad_yaml = "name: Broken\njobs: [unterminated"
    with pytest.raises(WorkflowParseError):
        parse_workflow_content(bad_yaml)


def test_non_dict_yaml_raises_error():
    with pytest.raises(WorkflowParseError):
        parse_workflow_content("- just\n- a\n- list")
