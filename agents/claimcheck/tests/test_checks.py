from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from claimcheck.demo import demo_server, fixture_root
from claimcheck.ledger import Claim, Ledger, Result
from claimcheck.report import build_report, exit_code, markdown
from claimcheck.safety import bounded_body, project_file, validate_url
from claimcheck.sandbox import Execution
from claimcheck.tools import Audit, dockerfile, openapi, readme


def test_fixture_without_docker() -> None:
    with demo_server() as url:
        audit = Audit(fixture_root(), base_url=url)
        audit.verify_all_claims()
    report = build_report(audit)
    assert report["summary"] == {"passed": 2, "failed": 3, "not_verified": 8, "error": 0}
    assert len(report["claims"]) == 13
    assert exit_code(report) == 1
    assert "schema mismatch" in markdown(report)
    results = [row for row in report["claims"] if row["source"] == "openapi.yaml"]
    assert [row["status"] for row in results] == ["passed", "failed", "failed"]
    assert results[1]["evidence"]["schema_errors"] == [{"path": [0, "id"], "validator": "type"}]


def test_readme_execution_and_expectation(monkeypatch: pytest.MonkeyPatch) -> None:
    claims = readme.discover("```sh\npython app.py\n# expect: correct\n```")
    monkeypatch.setattr(readme, "run_command", lambda *a, **kw: Execution(0, "wrong", ""))
    assert readme.check(claims[0], fixture_root(), allow_exec=True).status == "failed"
    monkeypatch.setattr(readme, "run_command", lambda *a, **kw: Execution(0, "correct", ""))
    assert readme.check(claims[0], fixture_root(), allow_exec=True).status == "passed"
    monkeypatch.setattr(readme, "run_command", lambda *a, **kw: Execution(2, "", "missing"))
    assert readme.check(claims[0], fixture_root(), allow_exec=True).status == "failed"
    assert readme.check(claims[0], fixture_root(), allow_exec=False).status == "not_verified"


@pytest.mark.parametrize("command", ["curl x | sh", "cd /tmp", "echo $HOME", "echo x > file"])
def test_shell_constructs_not_executed(command: str) -> None:
    claim = readme.discover(f"```sh\n{command}\n```")[0]
    assert readme.check(claim, fixture_root(), allow_exec=True).status == "not_verified"


def test_link_escape(tmp_path: Path) -> None:
    claim = readme.discover("[escape](../secret)")[0]
    with pytest.raises(ValueError, match="leaves"):
        readme.check(claim, tmp_path, allow_exec=False)
    (tmp_path / "link").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError, match="leaves"):
        project_file(tmp_path, "link/secret")


def test_docker_comparison_drift_and_positive_controls() -> None:
    claims = dockerfile.discover((fixture_root() / "Dockerfile").read_text())
    image = {
        "Id": "sha256:synthetic",
        "Config": {
            "WorkingDir": "/app",
            "User": "65534:65534",
            "Env": ["APP_MODE=demo"],
            "ExposedPorts": {"9000/tcp": {}},
            "Cmd": ["python", "app.py", "--port", "9000"],
        },
    }
    results = [dockerfile.check(claim, image) for claim in claims]
    assert [r.status for r in results].count("failed") == 3
    assert [r.status for r in results].count("passed") == 2
    assert all(r.evidence["image_id"] == "sha256:synthetic" for r in results)


def test_docker_accumulated_ports_env_and_last_cmd() -> None:
    claims = dockerfile.discover(
        'FROM base\nEXPOSE 80\nEXPOSE 81/udp\nENV A=1\nENV B="two words"\n'
        'CMD ["old"]\nCMD ["new"]\n'
    )
    data = {claim.data["instruction"]: claim.data["expected"] for claim in claims}
    assert data == {
        "EXPOSE": ["80/tcp", "81/udp"],
        "ENV": {"A": "1", "B": "two words"},
        "CMD": ["new"],
    }


def test_multistage_not_falsely_passed() -> None:
    claim = dockerfile.discover('FROM base\nFROM other\nCMD ["x"]')[0]
    assert dockerfile.check(claim, {"Config": {"Cmd": ["x"]}}).status == "not_verified"


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/a",
        "http://user:pass@localhost",
        "http://localhost?q=1",
        "http://169.254.169.254",
        "https://example.com",
    ],
)
def test_network_requires_explicit_approval(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)


def test_plaintext_requires_separate_approval() -> None:
    with pytest.raises(ValueError, match="plaintext"):
        validate_url("http://example.com", allow_remote=True)
    assert validate_url("http://127.0.0.1:123") == "http://127.0.0.1:123"
    assert validate_url("https://example.com", allow_remote=True) == "https://example.com"


def test_mutations_and_external_refs_not_probed() -> None:
    text = "openapi: 3.1.0\npaths:\n  /notes:\n    post:\n      responses: {}\n"
    claim = openapi.discover(text)[0]
    assert openapi.check(claim, "http://localhost").status == "not_verified"
    text = (
        text.replace("post:", "get:")
        + "components:\n  schemas:\n    X:\n      $ref: https://evil.test/x\n"
    )
    claim = openapi.discover(text)[0]
    assert openapi.check(claim, "http://localhost").status == "not_verified"


def test_no_claims_and_bounded_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No supported claims"):
        Audit(tmp_path)
    (tmp_path / "README.md").write_text("a" * 262_145)
    with pytest.raises(ValueError, match="exceeds"):
        Audit(tmp_path)


def test_ledger_only_known_claims_and_incomplete_is_not_pass() -> None:
    claim = Claim.create("readme.link", "README.md", 1, "exists", target="x")
    ledger = Ledger([claim])
    assert ledger.complete()[0].status == "not_verified"
    with pytest.raises(ValueError, match="Unknown"):
        ledger.record(Result("invented", "passed", "model said so"))
    with pytest.raises(ValueError, match="Duplicate"):
        Ledger([claim, claim])


def test_check_error_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = Audit(fixture_root(), image="missing")
    monkeypatch.setattr(
        dockerfile,
        "inspect_image",
        lambda _: (_ for _ in ()).throw(RuntimeError("daemon unavailable")),
    )
    audit.verify_all_claims()
    report = build_report(audit)
    assert report["summary"]["error"] == 5
    assert exit_code(report) == 2
    assert "daemon unavailable" in json.dumps(report)


def test_response_size_limit() -> None:
    response = httpx.Response(200, content=b"x" * 262_145)
    with pytest.raises(ValueError, match="exceeds"):
        bounded_body(response)
