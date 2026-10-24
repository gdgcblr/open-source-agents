"""Integration tests for CLI behavior and end-to-end offline execution."""

from pathlib import Path

from agent import run_migration
from config import get_config


def test_cli_end_to_end_offline(tmp_path):
    project_root = Path(__file__).parent.parent
    sample_wf = project_root / "samples" / "github-action-example.yml"
    sample_tf = project_root / "samples" / "terraform-example"

    cfg = get_config(offline_mode=True)
    summary, validation, risk, out_files = run_migration(
        workflow_path=sample_wf,
        output_dir=tmp_path,
        terraform_dir=sample_tf,
        config=cfg,
    )

    assert summary.workflow_name == "CI/CD Production Build and Deploy"
    assert summary.jobs_count == 2
    assert summary.steps_count == 14
    assert validation.is_valid is True
    assert risk.overall_score > 0

    assert len(out_files) == 6
    for key, p in out_files.items():
        assert p.is_file()
        assert p.stat().st_size > 0
