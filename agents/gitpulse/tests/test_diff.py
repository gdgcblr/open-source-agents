from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from agents.gitpulse.core import (
    DiffError,
    GitPulseError,
    fetch_pull_request_head,
    get_branch_diff,
    get_changed_python_files,
    run_ruff_linter,
)


def _git_response(stdout: str = "", returncode: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


def _successful_git_call(command: list[str], **_: object) -> CompletedProcess[str]:
    arguments = command[3:]
    if arguments == ["rev-parse", "--show-toplevel"]:
        return _git_response("C:/repo\n")
    if arguments == ["rev-parse", "--verify", "--end-of-options", "upstream/main^{commit}"]:
        return _git_response("a" * 40 + "\n")
    if arguments == ["rev-parse", "--verify", "--end-of-options", "HEAD^{commit}"]:
        return _git_response("c" * 40 + "\n")
    if arguments == ["rev-parse", "--verify", "--end-of-options", "feature/other^{commit}"]:
        return _git_response("d" * 40 + "\n")
    if arguments == ["merge-base", "a" * 40, "c" * 40]:
        return _git_response("b" * 40 + "\n")
    if arguments == ["merge-base", "a" * 40, "d" * 40]:
        return _git_response("e" * 40 + "\n")
    diff_prefix = ["diff", "--no-ext-diff", "--no-color", "--unified=3"]
    if arguments in (
        diff_prefix + ["b" * 40, "c" * 40, "--"],
        diff_prefix + ["b" * 40, "--"],
        diff_prefix + ["e" * 40, "d" * 40, "--"],
    ):
        return _git_response("diff --git a/file.py b/file.py\n")
    raise AssertionError(f"Unexpected git command: {arguments!r}")


def test_get_branch_diff_uses_merge_base_and_no_shell(tmp_path: Path) -> None:
    with patch("agents.gitpulse.core.subprocess.run", side_effect=_successful_git_call) as run:
        result = get_branch_diff("upstream/main", tmp_path)

    assert result.startswith("diff --git")
    assert all(call.kwargs["shell"] is False for call in run.call_args_list)


def test_get_branch_diff_includes_tracked_worktree_when_requested(tmp_path: Path) -> None:
    with patch("agents.gitpulse.core.subprocess.run", side_effect=_successful_git_call) as run:
        get_branch_diff("upstream/main", tmp_path, include_worktree=True)

    diff_arguments = run.call_args_list[-1].args[0][3:]
    assert diff_arguments == [
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--unified=3",
        "b" * 40,
        "--",
    ]


def test_get_branch_diff_accepts_an_alternate_local_head_ref(tmp_path: Path) -> None:
    with patch("agents.gitpulse.core.subprocess.run", side_effect=_successful_git_call) as run:
        result = get_branch_diff("upstream/main", tmp_path, head_ref="feature/other")

    assert result.startswith("diff --git")
    assert run.call_args_list[-1].args[0][3:] == [
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--unified=3",
        "e" * 40,
        "d" * 40,
        "--",
    ]


def test_get_branch_diff_rejects_invalid_base_ref(tmp_path: Path) -> None:
    def invalid_ref_call(command: list[str], **_: object) -> CompletedProcess[str]:
        if command[3:] == ["rev-parse", "--show-toplevel"]:
            return _git_response("C:/repo\n")
        return _git_response(returncode=128)

    with patch("agents.gitpulse.core.subprocess.run", side_effect=invalid_ref_call), pytest.raises(
        DiffError,
        match="does not resolve",
    ):
        get_branch_diff("missing-ref", tmp_path)


def test_get_branch_diff_rejects_empty_diff(tmp_path: Path) -> None:
    def empty_diff_call(command: list[str], **_: object) -> CompletedProcess[str]:
        result = _successful_git_call(command)
        if command[3:5] == ["diff", "--no-ext-diff"]:
            return _git_response()
        return result

    with patch("agents.gitpulse.core.subprocess.run", side_effect=empty_diff_call), pytest.raises(
        DiffError,
        match="No changes were found",
    ):
        get_branch_diff("upstream/main", tmp_path)


def test_get_branch_diff_rejects_oversized_diff(tmp_path: Path) -> None:
    def large_diff_call(command: list[str], **_: object) -> CompletedProcess[str]:
        result = _successful_git_call(command)
        if command[3:5] == ["diff", "--no-ext-diff"]:
            return _git_response("x" * 20)
        return result

    with patch("agents.gitpulse.core.subprocess.run", side_effect=large_diff_call), pytest.raises(
        DiffError,
        match="exceeds the 10-byte limit",
    ):
        get_branch_diff("upstream/main", tmp_path, max_bytes=10)


def test_get_changed_python_files_returns_existing_in_repo_files(tmp_path: Path) -> None:
    python_file = tmp_path / "src" / "main.py"
    python_file.parent.mkdir()
    python_file.write_text("value = 1\n", encoding="utf-8")

    def changed_files_call(command: list[str], **_: object) -> CompletedProcess[str]:
        arguments = command[3:]
        if arguments == ["rev-parse", "--show-toplevel"]:
            return _git_response(f"{tmp_path}\n")
        if arguments == ["rev-parse", "--verify", "--end-of-options", "upstream/main^{commit}"]:
            return _git_response("a" * 40 + "\n")
        if arguments == ["rev-parse", "--verify", "--end-of-options", "HEAD^{commit}"]:
            return _git_response("c" * 40 + "\n")
        if arguments == ["merge-base", "a" * 40, "c" * 40]:
            return _git_response("b" * 40 + "\n")
        if arguments == [
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
            "b" * 40,
            "c" * 40,
            "--",
        ]:
            return _git_response("src/main.py\0README.md\0missing.py\0")
        raise AssertionError(f"Unexpected git command: {arguments!r}")

    with patch("agents.gitpulse.core.subprocess.run", side_effect=changed_files_call) as run:
        changed_files = get_changed_python_files("upstream/main", tmp_path)

    assert changed_files == (Path("src/main.py"),)
    assert all(call.kwargs["shell"] is False for call in run.call_args_list)


def test_fetch_pull_request_head_uses_private_ref_without_checkout(tmp_path: Path) -> None:
    def fetch_call(command: list[str], **_: object) -> CompletedProcess[str]:
        arguments = command[3:]
        if arguments == ["remote", "get-url", "upstream"]:
            return _git_response("https://github.com/example/project.git\n")
        if arguments == [
            "fetch",
            "--no-tags",
            "upstream",
            "+refs/pull/42/head:refs/gitpulse/pull/42/head",
        ]:
            return _git_response()
        if arguments == [
            "rev-parse",
            "--verify",
            "--end-of-options",
            "refs/gitpulse/pull/42/head^{commit}",
        ]:
            return _git_response("f" * 40 + "\n")
        raise AssertionError(f"Unexpected git command: {arguments!r}")

    with patch("agents.gitpulse.core.subprocess.run", side_effect=fetch_call) as run:
        head_ref = fetch_pull_request_head(42, "upstream", tmp_path)

    assert head_ref == "refs/gitpulse/pull/42/head"
    assert all(call.kwargs["shell"] is False for call in run.call_args_list)
    assert all("checkout" not in call.args[0] for call in run.call_args_list)


def test_fetch_pull_request_head_rejects_invalid_remote_and_number(tmp_path: Path) -> None:
    with pytest.raises(DiffError, match="positive integer"):
        fetch_pull_request_head(0, "upstream", tmp_path)
    with pytest.raises(DiffError, match="configured Git remote"):
        fetch_pull_request_head(42, "--upload-pack=unsafe", tmp_path)


def test_run_ruff_linter_parses_json_diagnostics(tmp_path: Path) -> None:
    python_file = tmp_path / "main.py"
    python_file.write_text("import unused\n", encoding="utf-8")
    diagnostic = (
        '[{"filename":"main.py","code":"F401",'
        '"message":"unused import","location":{"row":1,"column":1}}]'
    )
    result = CompletedProcess(args=["ruff"], returncode=1, stdout=diagnostic, stderr="")

    with patch("agents.gitpulse.core.subprocess.run", return_value=result) as run:
        findings = run_ruff_linter(
            [Path("main.py")],
            tmp_path,
            python_executable="python.exe",
        )

    assert len(findings) == 1
    assert findings[0].file_path == "main.py"
    assert findings[0].line_number == 1
    assert findings[0].code == "F401"
    assert run.call_args.kwargs["shell"] is False


def test_run_ruff_linter_rejects_paths_outside_repository(tmp_path: Path) -> None:
    with pytest.raises(GitPulseError, match="relative to the repository root"):
        run_ruff_linter(
            [Path("../outside.py")],
            tmp_path,
            python_executable="python.exe",
        )