from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from claimcheck import sandbox
from claimcheck.cli import main
from claimcheck.demo import fixture_root
from claimcheck.ollama import json_schema
from claimcheck.sandbox import Execution
from claimcheck.tools import Audit, dockerfile, openapi


def test_snapshot_excludes_secrets_and_symlinks(tmp_path: Path) -> None:
    root, destination = tmp_path / "project", tmp_path / "snapshot"
    root.mkdir()
    destination.mkdir()
    (root / "app.py").write_text("print('ok')")
    (root / ".env").write_text("not a real credential")
    (root / "credentials.json").write_text("{}")
    (root / "key.pem").write_text("excluded placeholder")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("excluded")
    (root / "escape").symlink_to(tmp_path)
    sandbox.snapshot(root, destination)
    assert [path.name for path in destination.iterdir()] == ["app.py"]


def test_snapshot_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, destination = tmp_path / "project", tmp_path / "snapshot"
    root.mkdir()
    destination.mkdir()
    (root / "app.py").write_text("too large")
    monkeypatch.setattr(sandbox, "SNAPSHOT_LIMIT", 1)
    with pytest.raises(ValueError, match="snapshot exceeds"):
        sandbox.snapshot(root, destination)


def test_process_timeout_and_output_limit() -> None:
    execution = sandbox.execute([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.1)
    assert execution.timed_out
    assert execution.returncode != 0
    execution = sandbox.execute([sys.executable, "-c", "print('x' * 20000)"])
    assert execution.returncode == 125
    assert "limit" in execution.stderr.lower()


def test_sandbox_flags_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "script.py").write_text("print('ok')")
    commands: list[list[str]] = []

    def fake(argv: list[str], **kwargs: object) -> Execution:
        commands.append(argv)
        if argv[1] == "run":
            return Execution(-9, "", "", timed_out=True)
        return Execution(0, "", "")

    monkeypatch.setattr(sandbox, "execute", fake)
    result = sandbox.run_command(tmp_path, ["python", "script.py"])
    assert result.timed_out
    assert "--network=none" in commands[0]
    assert "--read-only" in commands[0]
    assert "--security-opt=no-new-privileges" in commands[0]
    assert "--user=65534:65534" in commands[0]
    assert commands[1][:3] == ["docker", "rm", "--force"]
    assert str(tmp_path.resolve()) not in " ".join(commands[0])


def test_openapi_alias_and_structure_limits() -> None:
    with pytest.raises(ValueError, match="aliases"):
        openapi.discover("x: &self [*self]")
    with pytest.raises(ValueError, match="Responses"):
        openapi.discover("openapi: 3.1.0\npaths:\n  /a:\n    get:\n      responses: []")
    with pytest.raises(ValueError, match="parameters"):
        openapi.discover(
            "openapi: 3.1.0\npaths:\n  /a:\n    parameters: wrong\n    get:\n      responses: {}"
        )


@pytest.mark.parametrize(
    ("status", "content", "headers", "expected"),
    [
        (302, b"", {"location": "http://evil.test"}, "failed"),
        (200, b"not json", {"content-type": "application/json"}, "failed"),
        (200, b"{}", {"content-type": "text/html"}, "failed"),
        (200, b'{"status":"ok"}', {"content-type": "application/json"}, "passed"),
    ],
)
def test_http_contract_checks(
    status: int,
    content: bytes,
    headers: dict[str, str],
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, content=content, headers=headers)

    monkeypatch.setattr(
        openapi,
        "http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False),
    )
    claim = openapi.discover((fixture_root() / "openapi.yaml").read_text())[0]
    assert openapi.check(claim, "http://localhost").status == expected
    assert len(requests) == 1


def test_schema_conversion_does_not_change_enum_values() -> None:
    assert json_schema({"type": "STRING", "enum": ["READY"]}) == {
        "type": "string",
        "enum": ["READY"],
    }


def test_legacy_env_is_not_empty_pass() -> None:
    claims = dockerfile.discover("FROM base\nENV MODE production\n")
    assert len(claims) == 1
    assert claims[0].kind == "unsupported"


def test_cli_partial_agent_failure_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from claimcheck import agent

    async def fail(audit: Audit, settings: object) -> dict:
        audit.verify_claim(next(iter(audit.ledger.claims)))
        raise RuntimeError("synthetic model failure")

    monkeypatch.setattr(agent, "run_agent", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "claimcheck",
            "audit",
            str(fixture_root()),
            "--agent",
            "--output",
            str(tmp_path),
        ],
    )
    assert main() == 2
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["agent"]["error"] is True
    assert report["coverage"]["executed"] == 1
    assert report["summary"]["not_verified"] == 13


def test_cli_unverified_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "README.md").write_text("```sh\npython missing.py\n```")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "claimcheck",
            "audit",
            str(tmp_path),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert main() == 3
