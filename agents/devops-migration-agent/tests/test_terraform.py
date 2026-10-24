"""Unit tests for Terraform static analysis and service connection validator."""

from pathlib import Path

from tools.terraform_validator import analyze_terraform_directory


def test_analyze_sample_terraform():
    sample_dir = Path(__file__).parent.parent / "samples" / "terraform-example"
    res = analyze_terraform_directory(sample_dir)

    assert res.has_terraform is True
    assert res.file_count >= 1
    assert "azurerm" in res.providers
    assert res.backend_type == "azurerm"
    assert res.resources_count >= 2
    assert "AzureRM Service Connection (ARM)" in res.service_connections_needed


def test_analyze_empty_directory(tmp_path):
    res = analyze_terraform_directory(tmp_path)
    assert res.has_terraform is False
    assert len(res.findings) > 0


def test_detect_hardcoded_credentials(tmp_path):
    tf_file = tmp_path / "bad.tf"
    tf_file.write_text('provider "azurerm" {\n  client_secret = "supersecretpassword"\n}\n')
    res = analyze_terraform_directory(tmp_path)
    assert any("plaintext credential" in f.lower() for f in res.findings)
