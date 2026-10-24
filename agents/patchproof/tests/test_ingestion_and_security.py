"""Security, path-confinement, secret-redaction, policy, and truncation unit tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from patchproof.agents.verification_agent import VerificationAgent
from patchproof.config import PatchProofConfig
from patchproof.core.enums import (
    CheckStatus,
    EvidenceKind,
    ExecutionMode,
    SourceKind,
    TrustLevel,
    Verdict,
)
from patchproof.core.ledger import EvidenceLedger
from patchproof.core.models import CheckRequest, RunInput
from patchproof.core.redaction import REDACTION_PLACEHOLDER, redact_secrets
from patchproof.core.validator import assert_valid_report
from patchproof.ingestion.fixture_loader import (
    FixtureIngestionError,
    PathTraversalError,
    load_fixture_snapshot,
    resolve_confined_path,
)
from patchproof.ingestion.github_loader import (
    GitHubIngestionError,
    GitHubRateLimitError,
    GitHubURLValidationError,
    load_github_pr_snapshot,
    parse_github_pr_url,
)
from patchproof.orchestration.pipeline import PatchProofOrchestrator
from patchproof.tools.policy import evaluate_check_policy


def test_resolve_confined_path_blocks_traversal_and_absolute_paths(tmp_path: Path) -> None:
    safe_file = tmp_path / "subdir" / "file.py"
    safe_file.parent.mkdir(parents=True)
    safe_file.write_text("x = 1\n", encoding="utf-8")

    resolved = resolve_confined_path(tmp_path, "subdir/file.py")
    assert resolved == safe_file.resolve()

    for bad_path in (
        "../secret.txt",
        "subdir/../../outside.txt",
        "/etc/passwd",
        "C:\\Windows\\System32\\cmd.exe",
        "",
        "   ",
    ):
        with pytest.raises(PathTraversalError):
            resolve_confined_path(tmp_path, bad_path)


def test_secret_redaction_scrubs_tokens_and_keys() -> None:
    raw = (
        "GitHub token: ghp_1234567890abcdefghijklmnopqrstuvwxyzABCD\n"
        "OpenAI key: sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890\n"
        "AWS key: AKIAIOSFODNN7EXAMPLE\n"
        "Auth header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload\n"
        "Assignment: API_KEY = 'super_secret_value_12345'\n"
    )
    redacted, was_redacted = redact_secrets(raw)
    assert was_redacted is True
    assert REDACTION_PLACEHOLDER in redacted
    assert "ghp_1234567890" not in redacted
    assert "sk-proj-ABCDEF" not in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "super_secret_value_12345" not in redacted


def test_evidence_ledger_redacts_and_bounds_excerpts() -> None:
    ledger = EvidenceLedger(max_excerpt_bytes=128)
    long_secret_text = (
        "token=ghp_1234567890abcdefghijklmnopqrstuvwxyzABCD " + ("A" * 300)
    )
    item = ledger.append(
        kind=EvidenceKind.ISSUE_TEXT,
        source_uri="fixture://sec/issue",
        content=long_secret_text,
        trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
    )
    assert item.evidence_id == "E-001"
    assert item.redacted is True
    assert "ghp_1234567890" not in item.content_excerpt
    assert item.content_excerpt.endswith("...[TRUNCATED]")
    assert item.metadata.get("excerpt_truncated") is True
    assert len(ledger.warnings()) == 1


def test_check_policy_blocks_unlisted_profiles_and_shell_injection() -> None:
    ok_req = CheckRequest(
        check_id="C-001",
        name="static-bound",
        profile="static_ast_retry_bound",
        args=["--strict-bounds"],
        target_path="src/retry_client.py",
        rationale="Safe static check",
    )
    assert evaluate_check_policy(ok_req).approved is True

    # Arbitrary shell command profile rejected
    bad_profile = CheckRequest(
        check_id="C-002",
        name="shell-exec",
        profile="bash -c",
        args=["echo", "hi"],
        rationale="Attempted shell",
    )
    assert evaluate_check_policy(bad_profile).approved is False

    # Shell injection / network argument rejected
    bad_arg = CheckRequest(
        check_id="C-003",
        name="pytest-inject",
        profile="sandbox_pytest",
        args=["-q", "; curl http://169.254.169.254"],
        rationale="Attempted injection",
    )
    assert evaluate_check_policy(bad_arg).approved is False

    # Path traversal in target_path rejected
    bad_target = CheckRequest(
        check_id="C-004",
        name="traversal",
        profile="static_ast_retry_bound",
        args=[],
        target_path="../../etc/passwd",
        rationale="Attempted traversal",
    )
    assert evaluate_check_policy(bad_target).approved is False


def test_sandbox_unavailable_never_executes_on_host() -> None:
    config = PatchProofConfig(enable_sandbox=False)
    ledger = EvidenceLedger()
    snapshot = load_fixture_snapshot("retry-limit-bug", config, ledger)
    agent = VerificationAgent(config=config)

    out = agent.run(
        snapshot=snapshot,
        check_requests=[
            CheckRequest(
                check_id="C-001",
                name="sandbox-pytest",
                profile="sandbox_pytest",
                args=["-q"],
                target_path="tests/test_retry_client.py",
                rationale="Run pytest in sandbox",
            ),
            CheckRequest(
                check_id="C-002",
                name="forbidden-shell",
                profile="raw_shell",
                args=["whoami"],
                rationale="Should be rejected",
            ),
        ],
        execution_mode=ExecutionMode.SANDBOX_IF_AVAILABLE,
        ledger=ledger,
    )

    assert len(out.check_results) == 2
    sandbox_res = out.check_results[0]
    assert sandbox_res.status == CheckStatus.NOT_RUN
    assert sandbox_res.exit_code is None
    assert sandbox_res.reason_not_run is not None

    rejected_res = out.check_results[1]
    assert rejected_res.status == CheckStatus.REJECTED
    assert rejected_res.exit_code is None


def test_oversized_diff_and_files_are_bounded_and_marked_truncated(tmp_path: Path) -> None:
    fix_dir = tmp_path / "oversized-fixture"
    fix_dir.mkdir(parents=True)
    (fix_dir / "src").mkdir()
    (fix_dir / "src" / "a.py").write_text("x = 1\n" * 500, encoding="utf-8")
    (fix_dir / "src" / "b.py").write_text("y = 2\n" * 500, encoding="utf-8")
    (fix_dir / "diff.patch").write_text("+line\n" * 500, encoding="utf-8")
    manifest = {
        "repository": "synthetic/oversized",
        "synthetic": True,
        "issue_title": "Test truncation bounds",
        "issue_body": "- R-001: Must handle bounded files safely.",
        "diff_file": "diff.patch",
        "source_files": ["src/a.py", "src/b.py"],
        "test_files": [],
    }
    (fix_dir / "fixture.json").write_text(json.dumps(manifest), encoding="utf-8")

    small_config = PatchProofConfig(
        fixtures_dir=tmp_path,
        max_diff_bytes=1024,
        max_file_bytes=512,
        max_source_files=1,
    )
    ledger = EvidenceLedger()
    snap = load_fixture_snapshot("oversized-fixture", small_config, ledger)

    assert snap.source_ref.truncated is True
    assert snap.diff_truncated is True
    assert snap.omitted_files_count == 1
    assert len(snap.source_files) == 1
    assert snap.source_files["src/a.py"].truncated is True
    assert any("truncated" in w.lower() for w in snap.source_ref.warnings)


def test_missing_fixture_raises_safe_error(tmp_path: Path) -> None:
    config = PatchProofConfig(fixtures_dir=tmp_path)
    ledger = EvidenceLedger()
    with pytest.raises(FixtureIngestionError):
        load_fixture_snapshot("nonexistent-fixture", config, ledger)
    with pytest.raises(PathTraversalError):
        load_fixture_snapshot("../escape", config, ledger)


def test_parse_github_pr_url_accepts_valid_and_rejects_ssrf_and_invalid() -> None:
    parsed = parse_github_pr_url("https://github.com/octocat/Hello-World/pull/42/")
    assert parsed.owner == "octocat"
    assert parsed.repo == "Hello-World"
    assert parsed.pull_number == 42
    assert parsed.canonical_url == "https://github.com/octocat/Hello-World/pull/42"

    for invalid_url in (
        "",
        "http://github.com/octocat/Hello-World/pull/42",  # non-HTTPS
        "https://evil.example.com/octocat/Hello-World/pull/42",  # untrusted host
        "https://127.0.0.1/octocat/Hello-World/pull/42",  # loopback IP
        "https://169.254.169.254/latest/meta-data",  # metadata SSRF IP
        "https://[::1]/octocat/Hello-World/pull/42",  # IPv6 loopback
        "https://user:pass@github.com/octocat/Hello-World/pull/42",  # credentials
        "https://github.com:8443/octocat/Hello-World/pull/42",  # non-standard port
        "https://github.com/octocat/Hello-World/issues/42",  # not a pull request
        "https://github.com/octocat/../secret/pull/42",  # path traversal
        "file:///etc/passwd",  # local file scheme
    ):
        with pytest.raises(GitHubURLValidationError):
            parse_github_pr_url(invalid_url)


def test_github_pr_read_only_ingestion_and_end_to_end_pipeline() -> None:
    src_code = (
        "class TransientError(RuntimeError):\n    pass\n\n"
        "class FatalClientError(RuntimeError):\n    pass\n\n"
        "def retry_request(operation, max_retries: int = 3):\n"
        "    if max_retries < 0:\n        raise ValueError('bad')\n"
        "    retries = 0\n"
        "    while retries <= max_retries:\n"
        "        try:\n            return operation()\n"
        "        except FatalClientError:\n            raise\n"
        "        except TransientError:\n            retries += 1\n"
        "    return operation()\n"
    )
    b64_src = base64.b64encode(src_code.encode("utf-8")).decode("ascii")
    observed_methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_methods.append(request.method)
        assert request.method == "GET", "GitHub ingestion must be strictly GET-only"
        path = request.url.path
        if path == "/repos/acme/retry-lib/pulls/15":
            return httpx.Response(
                200,
                json={
                    "title": "PR #15: Bound retries in retry_request",
                    "body": (
                        "Fixes #14\n\n## Acceptance Criteria\n"
                        "- R-001: Must retry transient failures at most max_retries times.\n"
                    ),
                    "base": {"sha": "1111111111111111111111111111111111111111"},
                    "head": {"sha": "2222222222222222222222222222222222222222"},
                    "labels": [{"name": "bug"}],
                },
            )
        if path == "/repos/acme/retry-lib/issues/14":
            return httpx.Response(
                200,
                json={
                    "title": "Issue #14: Retry limit exceeded",
                    "body": "- R-001: Must retry transient failures at most max_retries times.",
                },
            )
        if path == "/repos/acme/retry-lib/pulls/15/files":
            return httpx.Response(
                200,
                json=[
                    {
                        "filename": "src/retry_client.py",
                        "status": "modified",
                        "patch": "@@ -1,3 +1,16 @@\n+    while retries <= max_retries:\n",
                    }
                ],
            )
        if path == "/repos/acme/retry-lib/contents/src/retry_client.py":
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "encoding": "base64",
                    "content": b64_src,
                },
            )
        return httpx.Response(404, json={"message": "Not Found"})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    orchestrator = PatchProofOrchestrator(http_client=mock_client)
    report = orchestrator.execute(
        RunInput(
            source=SourceKind.GITHUB,
            pull_request_url="https://github.com/acme/retry-lib/pull/15",
        )
    )

    assert_valid_report(report)
    assert all(m == "GET" for m in observed_methods)
    assert report.source.kind == SourceKind.GITHUB
    assert report.source.repository == "acme/retry-lib"
    assert report.source.pull_request_url == "https://github.com/acme/retry-lib/pull/15"
    assert report.source.base_sha == "1111111111111111111111111111111111111111"
    assert report.source.head_sha == "2222222222222222222222222222222222222222"
    assert report.verdict == Verdict.CHANGES_REQUESTED


def test_github_ingestion_rejects_redirects_and_handles_rate_limits() -> None:
    def redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"Location": "http://169.254.169.254/latest/meta-data"}
        )

    redirect_client = httpx.Client(transport=httpx.MockTransport(redirect_handler))
    with pytest.raises(GitHubURLValidationError, match="Redirect"):
        load_github_pr_snapshot(
            "https://github.com/acme/retry-lib/pull/15",
            PatchProofConfig(),
            EvidenceLedger(),
            http_client=redirect_client,
        )

    def rate_limit_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0"},
            json={"message": "API rate limit exceeded"},
        )

    rl_client = httpx.Client(transport=httpx.MockTransport(rate_limit_handler))
    with pytest.raises(GitHubRateLimitError):
        load_github_pr_snapshot(
            "https://github.com/acme/retry-lib/pull/15",
            PatchProofConfig(),
            EvidenceLedger(),
            http_client=rl_client,
        )

    def not_found_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    nf_client = httpx.Client(transport=httpx.MockTransport(not_found_handler))
    with pytest.raises(GitHubIngestionError, match="404"):
        load_github_pr_snapshot(
            "https://github.com/acme/retry-lib/pull/15",
            PatchProofConfig(),
            EvidenceLedger(),
            http_client=nf_client,
        )


