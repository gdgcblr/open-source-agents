"""Unit tests for Azure DevOps Pipeline YAML generator and validator."""

import yaml

from tools.ado_generator import ADOGenerator, validate_pipeline_yaml
from tools.github_parser import parse_workflow_content

SAMPLE_WORKFLOW = """
name: Generator Test
on:
  push:
    branches: [main, release/*]
  pull_request:
    branches: [main]
jobs:
  build:
    name: Build Job
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pytest
"""


def test_generator_produces_valid_yaml():
    wf = parse_workflow_content(SAMPLE_WORKFLOW)
    gen = ADOGenerator()
    pipeline_yaml = gen.generate_pipeline(wf)

    # Must be valid YAML
    parsed = yaml.safe_load(pipeline_yaml)
    assert isinstance(parsed, dict)
    assert "jobs" in parsed
    assert len(parsed["jobs"]) == 1

    job = parsed["jobs"][0]
    assert job["job"] == "build"
    assert job["pool"]["vmImage"] == "ubuntu-latest"
    assert len(job["steps"]) == 3


def test_validation_passes_on_valid_pipeline():
    wf = parse_workflow_content(SAMPLE_WORKFLOW)
    gen = ADOGenerator()
    pipeline_yaml = gen.generate_pipeline(wf)
    res = validate_pipeline_yaml(pipeline_yaml)

    assert res.is_valid is True
    assert len(res.errors) == 0
    assert res.structural_checks["yaml_syntax"] is True
    assert res.structural_checks["has_jobs_or_steps"] is True


def test_validation_fails_on_syntax_error():
    broken_yaml = "jobs: [unterminated"
    res = validate_pipeline_yaml(broken_yaml)
    assert res.is_valid is False
    assert res.structural_checks["yaml_syntax"] is False
    assert any("Syntax" in e for e in res.errors)


def test_validation_fails_on_empty_job_steps():
    bad_job = "jobs:\n  - job: empty\n    pool:\n      vmImage: ubuntu-latest\n    steps: []"
    res = validate_pipeline_yaml(bad_job)
    assert res.is_valid is False
    assert any("no steps" in e.lower() for e in res.errors)
