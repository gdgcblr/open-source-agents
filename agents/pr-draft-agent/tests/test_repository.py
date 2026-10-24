"""Exercise staged evidence and input boundaries against disposable Git repositories."""

from __future__ import annotations

import errno
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pr_draft_agent import repository as capture
from pr_draft_agent.repository import InputError, capture_snapshot, validate_intent


def test_partial_staging_excludes_worktree_and_untracked_content(repo, stage, git):
    stage("app.txt", "baseline\n")
    git("commit", "-qm", "baseline")
    path = stage("app.txt", "STAGED_SENTINEL\n")
    path.write_text("STAGED_SENTINEL\nUNSTAGED_SENTINEL\n")
    (repo / "untracked.txt").write_text("UNTRACKED_SENTINEL\n")
    template = repo / ".github/PULL_REQUEST_TEMPLATE.md"
    template.parent.mkdir()
    template.write_text("## Summary\n\n## Testing\n")
    before_index = git("diff", "--cached", "--raw", "-z").stdout
    before_status = git("status", "--porcelain=v1", "-z").stdout

    snapshot = capture_snapshot(repo)

    assert snapshot.root == repo.resolve()
    assert [(f.path, f.status) for f in snapshot.files] == [("app.txt", "M")]
    assert "STAGED_SENTINEL" in snapshot.diff
    assert "UNSTAGED_SENTINEL" not in snapshot.diff
    assert "UNTRACKED_SENTINEL" not in snapshot.diff
    assert snapshot.template == "## Summary\n\n## Testing\n"
    assert snapshot.template_source == ".github/PULL_REQUEST_TEMPLATE.md"
    assert snapshot.diff_sha256 == hashlib.sha256(snapshot.diff.encode()).hexdigest()
    assert all(not Path(item.path).is_absolute() for item in snapshot.files)
    assert str(repo.resolve()) not in snapshot.diff
    assert git("diff", "--cached", "--raw", "-z").stdout == before_index
    assert git("status", "--porcelain=v1", "-z").stdout == before_status


def test_alternate_case_working_tree_path_is_accepted(repo, stage):
    stage("app.txt", "selected content\n")
    alternate = Path(str(repo).upper())
    try:
        same_directory = os.path.samefile(alternate, repo)
    except OSError:
        same_directory = False
    if not same_directory:
        pytest.skip("The filesystem treats path case as significant")
    snapshot = capture_snapshot(alternate)
    assert snapshot.root == repo.resolve()
    assert snapshot.files[0].path == "app.txt"


def test_unborn_head_and_nested_directory(repo, stage):
    stage("folder with spaces/new file.txt", "first staged content\n")
    snapshot = capture_snapshot(repo / "folder with spaces")
    assert [(f.path, f.status) for f in snapshot.files] == [
        ("folder with spaces/new file.txt", "A")
    ]
    assert "+first staged content" in snapshot.diff
    assert snapshot.template_source is None
    assert snapshot.template == "## Summary\n\n## Why\n\n## Testing\n\n## Suggested checks\n"


def test_deleted_file_and_rename_are_not_lost(repo, stage, git):
    stage("old.txt", "original\n")
    stage("deleted.txt", "delete this\n")
    git("commit", "-qm", "baseline")
    git("mv", "old.txt", "new.txt")
    git("rm", "-q", "deleted.txt")
    snapshot = capture_snapshot(repo)
    assert {(f.path, f.status) for f in snapshot.files} == {
        ("old.txt", "D"),
        ("new.txt", "A"),
        ("deleted.txt", "D"),
    }


def test_linked_worktree(repo, stage, git, tmp_path):
    stage("app.txt", "baseline\n")
    git("commit", "-qm", "baseline")
    worktree = tmp_path / "linked checkout"
    git("worktree", "add", "-qb", "feature", str(worktree))
    (worktree / "app.txt").write_text("linked staged content\n")
    git("add", "app.txt", cwd=worktree)
    snapshot = capture_snapshot(worktree)
    assert snapshot.root == worktree.resolve()
    assert "+linked staged content" in snapshot.diff


@pytest.mark.parametrize("committed", [False, True])
def test_empty_index_is_actionable(repo, stage, git, committed):
    if committed:
        stage("app.txt", "baseline\n")
        git("commit", "-qm", "baseline")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "NO_STAGED_CHANGES"


def test_invalid_paths_and_bare_repository(tmp_path, repo, git):
    plain = tmp_path / "plain"
    plain.mkdir()
    file = tmp_path / "file"
    file.write_text("text")
    bare = tmp_path / "bare.git"
    git("init", "--bare", "-q", str(bare))
    for path in (tmp_path / "missing", plain, file, bare):
        with pytest.raises(InputError) as error:
            capture_snapshot(path)
        assert error.value.code == "INVALID_REPOSITORY"


@pytest.mark.parametrize("count", [20, 21])
def test_changed_path_count_limit(repo, stage, count):
    for number in range(count):
        stage(f"file-{number}.txt")
    if count == 20:
        assert len(capture_snapshot(repo).files) == 20
    else:
        with pytest.raises(InputError) as error:
            capture_snapshot(repo)
        assert error.value.code == "INPUT_TOO_LARGE"


@pytest.mark.parametrize("size", [65_536, 65_537])
def test_diff_byte_limit_at_boundary(repo, stage, git, size):
    stage("large.txt", "x\n")
    initial = git("diff", "--cached", "--no-renames", "--no-ext-diff", "--no-textconv").stdout
    # Each added ASCII character contributes exactly one byte to this one-line patch.
    stage("large.txt", "x" * (size - len(initial.encode()) + 1) + "\n")
    if size == 65_536:
        assert len(capture_snapshot(repo).diff.encode()) == 65_536
    else:
        with pytest.raises(InputError) as error:
            capture_snapshot(repo)
        assert error.value.code == "INPUT_TOO_LARGE"


@pytest.mark.parametrize("size", [16_384, 16_385])
def test_template_byte_limit_at_boundary(repo, stage, size):
    stage("app.txt")
    (repo / "PULL_REQUEST_TEMPLATE.md").write_bytes(b"x" * size)
    if size == 16_384:
        assert len(capture_snapshot(repo).template.encode()) == size
    else:
        with pytest.raises(InputError) as error:
            capture_snapshot(repo)
        assert error.value.code == "INPUT_TOO_LARGE"


def test_template_limit_counts_utf8_bytes(repo, stage):
    stage("app.txt")
    template = repo / "PULL_REQUEST_TEMPLATE.md"
    template.write_text("é" * 8_192, encoding="utf-8")
    assert len(capture_snapshot(repo).template.encode()) == 16_384
    template.write_text("é" * 8_193, encoding="utf-8")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "INPUT_TOO_LARGE"


def test_diff_limit_counts_utf8_bytes(repo, stage):
    stage("unicode.txt", "é" * 40_000 + "\n")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "INPUT_TOO_LARGE"


def test_multibyte_intent_is_preserved_and_limited_by_bytes():
    assert validate_intent("é" * 1024) == "é" * 1024
    assert validate_intent("  explain this  ") == "  explain this  "
    with pytest.raises(InputError) as error:
        validate_intent("é" * 1024 + "x")
    assert error.value.code == "INPUT_TOO_LARGE"


def test_long_noncredential_line_does_not_stall_input_validation():
    # An ordinary long source line must not trigger quadratic regex backtracking.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pr_draft_agent.repository import _has_sensitive_content; "
                "assert not _has_sensitive_content('x' * 65000)"
            ),
        ],
        capture_output=True,
        timeout=2,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("source", ["diff", "template", "intent"])
@pytest.mark.parametrize(
    "content",
    [
        "API_KEY=synthetic-value-12345",
        'api_key: "synthetic-value-12345"',
        '"ACCESS_TOKEN": "synthetic-value-12345"',
        "AUTH_TOKEN=synthetic-value-12345",
        "CLIENT_SECRET=synthetic-value-12345",
        "PASSWORD='synthetic-value-12345'",
        "GOOGLE_API_KEY=synthetic-value-12345",
        'config = {"API_KEY": "synthetic-value-12345"}',
        '{"config":{"API_KEY":"synthetic-value-12345"}}',
        "NORMAL=\nAPI_KEY=synthetic-value-12345",
        "-API_KEY=synthetic-value-12345",
        "some-API_KEY=synthetic-value-12345",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "ghp_" + "a" * 24,
    ],
)
def test_sensitive_content_is_blocked_without_disclosure(repo, stage, source, content):
    stage("app.txt", content if source == "diff" else "safe staged content\n")
    if source == "template":
        (repo / "PULL_REQUEST_TEMPLATE.md").write_text(content)
    with pytest.raises(InputError) as error:
        if source == "intent":
            validate_intent(content)
        else:
            capture_snapshot(repo)
    assert error.value.code == "SENSITIVE_INPUT"
    assert "synthetic-value-12345" not in str(error.value)
    assert content not in str(error.value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "your_api_key_here",
        "YOUR_TOKEN_HERE",
        "your_password_here",
        "replace_me",
        "example",
    ],
)
def test_documented_credential_placeholders_are_allowed(repo, stage, value):
    stage(".env.example", f'GOOGLE_API_KEY="{value}"\n')
    assert capture_snapshot(repo).files[0].path == ".env.example"


@pytest.mark.parametrize(("value", "allowed"), [("x" * 7, True), ("x" * 8, False)])
def test_credential_value_minimum_length(value, allowed):
    intent = f"API_KEY={value}"
    if allowed:
        assert validate_intent(intent) == intent
    else:
        with pytest.raises(InputError) as error:
            validate_intent(intent)
        assert error.value.code == "SENSITIVE_INPUT"


def test_env_example_is_still_scanned_for_credentials(repo, stage):
    stage(".env.example", "API_KEY=synthetic-value-12345\n")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "SENSITIVE_INPUT"
    assert "synthetic-value-12345" not in str(error.value)


def test_removed_credential_line_is_blocked(repo, stage, git):
    stage("app.txt", "API_KEY=synthetic-value-12345\n")
    git("commit", "-qm", "baseline")
    stage("app.txt", "ordinary replacement\n")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "SENSITIVE_INPUT"
    assert "synthetic-value-12345" not in str(error.value)


def test_hyphenated_credential_name_is_blocked():
    with pytest.raises(InputError) as error:
        validate_intent("my-API_KEY=synthetic-value-12345")
    assert error.value.code == "SENSITIVE_INPUT"
    assert "synthetic-value-12345" not in str(error.value)


def test_placeholder_lookalike_is_not_a_placeholder():
    with pytest.raises(InputError) as error:
        validate_intent("API_KEY=example123")
    assert error.value.code == "SENSITIVE_INPUT"


def test_short_credential_value_is_allowed():
    assert validate_intent("API_KEY=short") == "API_KEY=short"


@pytest.mark.parametrize(
    "token",
    ["ghp_" + "a" * 20, "github_pat_" + "B" * 20, "sk-" + "c" * 20],
)
def test_all_token_shapes_are_blocked(repo, stage, token):
    stage("notes.txt", f"TOKEN={token}\n")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "SENSITIVE_INPUT"
    assert token not in str(error.value)


@pytest.mark.parametrize("source", ["diff", "template", "intent"])
def test_empty_credential_assignment_does_not_consume_the_next_line(repo, stage, source):
    content = "API_KEY=\nNEXT_SETTING=safe_value\n"
    stage("app.txt", content if source == "diff" else "ordinary text\n")
    if source == "template":
        (repo / "PULL_REQUEST_TEMPLATE.md").write_text(content)
    if source == "intent":
        assert validate_intent(content) == content
    else:
        assert capture_snapshot(repo).files[0].path == "app.txt"


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "nested/.ENV.local",
        "x.PEM",
        "x.KEY",
        ".pem",
        ".key",
        "credentials.json",
        "CREDENTIALS.JSON",
        "service-account-demo.json",
        "SERVICE-ACCOUNT-DEMO.JSON",
    ],
)
def test_sensitive_paths_are_blocked(repo, stage, name):
    stage(name, "safe text\n")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "SENSITIVE_INPUT"


def test_template_precedence_and_worktree_content(repo, stage):
    stage("app.txt")
    stage(".github/PULL_REQUEST_TEMPLATE.md", "staged template\n")
    (repo / ".github/PULL_REQUEST_TEMPLATE.md").write_text("current local template\n")
    (repo / "PULL_REQUEST_TEMPLATE.md").write_text("lower priority\n")
    snapshot = capture_snapshot(repo)
    assert snapshot.template == "current local template\n"
    assert snapshot.template_source == ".github/PULL_REQUEST_TEMPLATE.md"


@pytest.mark.parametrize("source", [".github/pull_request_template.md", "pull_request_template.md"])
def test_lowercase_template_candidates(repo, stage, source):
    stage("app.txt")
    path = repo / source
    path.parent.mkdir(exist_ok=True)
    path.write_text("## Custom\n")
    snapshot = capture_snapshot(repo)
    assert snapshot.template == "## Custom\n"
    # On a case-insensitive filesystem, the earlier uppercase candidate is
    # the same physical file; its declared precedence remains correct.
    assert (repo / snapshot.template_source).samefile(path)


@pytest.mark.parametrize("parent_symlink", [False, True])
def test_template_symlink_escape_is_blocked(repo, stage, tmp_path, parent_symlink):
    stage("app.txt")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "PULL_REQUEST_TEMPLATE.md").write_text("private external content\n")
    if parent_symlink:
        (repo / ".github").symlink_to(outside, target_is_directory=True)
    else:
        (repo / "PULL_REQUEST_TEMPLATE.md").symlink_to(outside / "PULL_REQUEST_TEMPLATE.md")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "TEMPLATE_UNSAFE"
    assert "private external content" not in str(error.value)


@pytest.mark.parametrize(
    "kind", ["directory", "invalid_utf8", "controls", "c1_controls"]
)
def test_invalid_present_template_does_not_fall_back(repo, stage, kind):
    stage("app.txt")
    path = repo / "PULL_REQUEST_TEMPLATE.md"
    if kind == "directory":
        path.mkdir()
    elif kind == "invalid_utf8":
        path.write_bytes(b"\xff")
    elif kind == "controls":
        path.write_bytes(b"unsafe\x1b[31m")
    else:
        path.write_bytes(b"unsafe\xc2\x85text")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "TEMPLATE_INVALID"


def test_unreadable_selected_template_does_not_fall_back(repo, stage, monkeypatch):
    stage("app.txt")
    (repo / "PULL_REQUEST_TEMPLATE.md").write_text("## Template\n")
    original = os.open

    def denied(path, *args, **kwargs):
        if Path(path).name == "PULL_REQUEST_TEMPLATE.md":
            raise PermissionError("synthetic private details")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(capture.os, "open", denied)
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "TEMPLATE_INVALID"
    assert "synthetic private details" not in str(error.value)


def test_mixed_binary_and_text_changes_are_rejected(repo, stage):
    stage("good.txt", "normal text\n")
    stage("image.bin", b"\x00\xff\x00")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "UNSUPPORTED_CHANGE"


def test_symlink_change_is_rejected(repo, git):
    (repo / "link").symlink_to("nonexistent-target")
    git("add", "link")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "UNSUPPORTED_CHANGE"


@pytest.mark.parametrize("ignore_submodules", [False, True])
def test_submodule_change_is_rejected_even_with_diff_config(repo, stage, git, ignore_submodules):
    stage("app.txt", "baseline\n")
    git("commit", "-qm", "baseline")
    oid = git("rev-parse", "HEAD").stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{oid},dependency")
    if ignore_submodules:
        git("config", "diff.ignoreSubmodules", "all")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "UNSUPPORTED_CHANGE"


def test_unmerged_index_is_rejected(repo, stage, git):
    stage("app.txt", "base\n")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "other")
    stage("app.txt", "other\n")
    git("commit", "-qm", "other")
    git("checkout", "-q", "main")
    stage("app.txt", "main\n")
    git("commit", "-qm", "main")
    assert git("merge", "other", check=False).returncode != 0
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "INDEX_UNMERGED"


@pytest.mark.parametrize(
    "name", ["bad\nname.txt", "bad\x1bname.txt", "bad\u0085name.txt"]
)
def test_control_character_paths_are_rejected(repo, stage, name):
    stage(name)
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "UNSUPPORTED_CHANGE"


def test_command_like_path_is_treated_as_data(repo, stage):
    name = "$(touch pwned).txt"
    stage(name, "shell metacharacters\n")
    snapshot = capture_snapshot(repo)
    assert snapshot.files[0].path == name
    assert not (repo / "pwned").exists()


def test_non_utf8_diff_is_rejected(repo, stage):
    stage("bad.txt", b"text\xff\n")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "INVALID_ENCODING"


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose arbitrary byte filenames")
def test_non_utf8_filename_is_rejected(repo, git):
    try:
        descriptor = os.open(os.fsencode(repo) + b"/bad-\xff.txt", os.O_WRONLY | os.O_CREAT, 0o600)
    except OSError as error:
        if error.errno == errno.EILSEQ:
            pytest.skip("The filesystem rejects non-UTF-8 filenames at creation")
        raise
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"ordinary text\n")
    git("add", "--all")
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "INVALID_ENCODING"


def test_non_utf8_path_in_git_metadata_is_rejected():
    raw = b":000000 100644 " + b"0" * 40 + b" " + b"1" * 40 + b" A\0bad-\xff.txt\0"
    with pytest.raises(InputError) as error:
        capture._parse_raw_metadata(raw)
    assert error.value.code == "INVALID_ENCODING"


@pytest.mark.parametrize(
    "name",
    ["/absolute.txt", "../escape.txt", "nested/../../escape.txt", "./relative.txt", ""],
)
def test_unsafe_metadata_paths_are_rejected(name):
    raw = (
        b":000000 100644 "
        + b"0" * 40
        + b" "
        + b"1" * 40
        + b" A\0"
        + name.encode()
        + b"\0"
    )
    with pytest.raises(InputError) as error:
        capture._parse_raw_metadata(raw)
    assert error.value.code == "UNSUPPORTED_CHANGE"


def test_unreadable_repository_is_rejected(repo, stage):
    if os.name == "nt" or getattr(os, "geteuid", lambda: -1)() == 0:
        pytest.skip("Permission checks are not portable to this platform")
    stage("app.txt")
    repo.chmod(0o000)
    try:
        with pytest.raises(InputError) as error:
            capture_snapshot(repo)
    finally:
        repo.chmod(0o700)
    assert error.value.code == "INVALID_REPOSITORY"


def test_git_redirecting_environment_is_ignored(repo, stage, monkeypatch, tmp_path):
    stage("app.txt", "selected repository\n")
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_EXTERNAL_DIFF"):
        monkeypatch.setenv(variable, str(tmp_path / "wrong-target"))
    assert "+selected repository" in capture_snapshot(repo).diff


def test_external_diff_and_textconv_are_not_executed(repo, stage, git, tmp_path):
    marker = tmp_path / "executed"
    helper = tmp_path / "helper.sh"
    helper.write_text(f'#!/bin/sh\ntouch "{marker}"\necho unexpected\n')
    helper.chmod(0o755)
    stage("app.txt", "baseline\n")
    git("commit", "-qm", "baseline")
    stage("app.txt", "selected change\n")
    (repo / ".gitattributes").write_text("app.txt diff=custom\n")
    git("config", "diff.external", str(helper))
    git("config", "diff.custom.textconv", str(helper))
    snapshot = capture_snapshot(repo)
    assert "+selected change" in snapshot.diff
    assert not marker.exists()


def test_configured_fsmonitor_is_not_executed(repo, stage, git, tmp_path):
    marker = tmp_path / "fsmonitor-executed"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f'#!/bin/sh\ntouch "{marker}"\nprintf "1\\n"\n')
    hook.chmod(0o755)
    stage("app.txt", "selected change\n")
    git("config", "core.fsmonitor", str(hook))

    snapshot = capture_snapshot(repo)

    assert "+selected change" in snapshot.diff
    assert not marker.exists()


def test_repository_diff_prefix_configuration_cannot_leak_local_paths(repo, stage, git):
    stage("app.txt", "baseline\n")
    git("commit", "-qm", "baseline")
    stage("app.txt", "selected change\n")
    local_path = str(repo.resolve())
    git("config", "diff.srcPrefix", f"{local_path}/private/")
    git("config", "diff.dstPrefix", f"{local_path}/private/")
    snapshot = capture_snapshot(repo)
    assert local_path not in snapshot.diff
    assert "a/app.txt" in snapshot.diff
    assert "b/app.txt" in snapshot.diff


def test_concurrent_index_change_rejects_entire_snapshot(repo, stage, monkeypatch):
    stage("app.txt")
    original = capture._run_git
    reads = 0

    def changing_index(args, *other):
        nonlocal reads
        result = original(args, *other)
        if "--raw" in args:
            reads += 1
            if reads == 2:
                return result.replace(b"app.txt", b"other.txt")
        return result

    monkeypatch.setattr(capture, "_run_git", changing_index)
    with pytest.raises(InputError) as error:
        capture_snapshot(repo)
    assert error.value.code == "INDEX_CHANGED"


@pytest.mark.parametrize("size", [32_768, 32_769])
def test_git_output_capture_enforces_exact_byte_limit(repo, size):
    args = [sys.executable, "-c", f"import sys; sys.stdout.buffer.write(b'x' * {size})"]
    if size == 32_768:
        assert capture._run_git(args, repo, 32_768, "reading metadata") == b"x" * size
    else:
        with pytest.raises(InputError) as error:
            capture._run_git(args, repo, 32_768, "reading metadata")
        assert error.value.code == "INPUT_TOO_LARGE"


def test_capped_reader_never_reads_more_than_limit_plus_one(repo, monkeypatch):
    bytes_read = 0
    original = os.read

    def observed_read(fd, size):
        nonlocal bytes_read
        value = original(fd, size)
        bytes_read += len(value)
        return value

    monkeypatch.setattr(capture.os, "read", observed_read)
    # Keep Popen's own startup/error-pipe reads outside the data counter.
    original_popen = subprocess.Popen

    def observed_popen(*args, **kwargs):
        nonlocal bytes_read
        process = original_popen(*args, **kwargs)
        bytes_read = 0
        return process

    monkeypatch.setattr(capture.subprocess, "Popen", observed_popen)
    with pytest.raises(InputError) as error:
        capture._run_git(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 1000000)"],
            repo,
            1024,
            "reading metadata",
        )
    assert error.value.code == "INPUT_TOO_LARGE"
    assert bytes_read == 1025


def test_timeout_kills_and_reaps_child_without_leaking_output(repo, monkeypatch):
    children = []
    original = subprocess.Popen

    def observed_popen(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(capture.subprocess, "Popen", observed_popen)
    monkeypatch.setattr(capture, "GIT_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(InputError) as error:
        capture._run_git(
            [
                sys.executable,
                "-c",
                "import time; print('PRIVATE_SENTINEL', flush=True); time.sleep(10)",
            ],
            repo,
            32_768,
            "reading metadata",
        )
    assert error.value.code == "GIT_TIMEOUT"
    assert "PRIVATE_SENTINEL" not in str(error.value)
    assert children[0].poll() is not None
    assert children[0].stdout.closed
