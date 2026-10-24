import subprocess

import pytest

from firstrun import source
from firstrun.cli import build_parser, parse_env_file
from firstrun.models import Edit
from firstrun.repair import EditError, apply_edits, copy_project, unified_diff, validate_edits


def test_parse_env_file(tmp_path):
    f = tmp_path / "secrets.env"
    f.write_text('# comment\nGEMINI_API_KEY="abc"\nexport TOKEN=xyz\n\nEMPTY=\nbroken line\n')
    assert parse_env_file(f) == {"GEMINI_API_KEY": "abc", "TOKEN": "xyz", "EMPTY": ""}


def test_parser_defaults():
    args = build_parser().parse_args(["examples/quote-of-the-day"])
    assert args.sandbox == "docker" and args.max_rounds == 2 and not args.ci


@pytest.mark.parametrize("url,owner,repo,rest", [
    ("https://github.com/gdgcblr/open-source-agents", "gdgcblr", "open-source-agents", None),
    ("github.com/gdgcblr/open-source-agents.git", "gdgcblr", "open-source-agents", None),
    ("https://github.com/a/b/tree/feat/x/agents/foo", "a", "b", "feat/x/agents/foo"),
])
def test_github_url_parsing(url, owner, repo, rest):
    m = source.GITHUB_RE.match(url)
    assert m and m["owner"] == owner and m["repo"] == repo and m["rest"] == rest


def test_tree_url_ref_split(monkeypatch):
    def fake_git(*args, timeout=180):
        ref = args[-1]
        ok = ref == "feat/x"
        return subprocess.CompletedProcess(args, 0, stdout="abc\trefs/heads/feat/x\n" if ok else "", stderr="")

    monkeypatch.setattr(source, "_git", fake_git)
    assert source._split_ref("u", "feat/x/agents/foo") == ("feat/x", "agents/foo")


def test_local_target_with_subdir(tmp_path):
    (tmp_path / "agents" / "demo").mkdir(parents=True)
    project, label = source.resolve_target(str(tmp_path), "agents/demo", tmp_path / "work")
    assert project == (tmp_path / "agents" / "demo").resolve()
    assert label.endswith("(agents/demo)")
    with pytest.raises(source.SourceError):
        source.resolve_target(str(tmp_path), "agents/missing", tmp_path / "work")


def test_edits_append_replace_create_and_diff(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "requirements.txt").write_text("colorama")
    (src / "README.md").write_text("Run `python summarize.py`\n")
    (src / ".venv").mkdir()
    (src / ".venv" / "junk").write_text("x")
    dst = copy_project(src, tmp_path / "dst")
    assert not (dst / ".venv").exists()

    apply_edits(dst, [
        Edit("requirements.txt", "", "python-dotenv\n"),
        Edit("README.md", "python summarize.py", "python src/summarize.py"),
        Edit(".env.example", "", "GEMINI_API_KEY=your_key_here\n"),
    ])
    assert (dst / "requirements.txt").read_text() == "colorama\npython-dotenv\n"
    diff = unified_diff(src, dst)
    assert "+Run `python src/summarize.py`" in diff
    assert "new file mode" in diff and "+GEMINI_API_KEY=your_key_here" in diff
    # the patch applies to the original with git
    (tmp_path / "fix.patch").write_text(diff)
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "apply", str(tmp_path / "fix.patch")], cwd=src, check=True)
    assert "python-dotenv" in (src / "requirements.txt").read_text()


def test_bad_edits_are_rejected(tmp_path):
    (tmp_path / "README.md").write_text("pip install x\npip install x\n")
    problems = validate_edits(tmp_path, [
        Edit("../outside.txt", "", "x"),
        Edit("README.md", "pip install x", "pip install y"),
        Edit("README.md", "not there", "y"),
        Edit("missing.txt", "a", "b"),
        Edit(".git/config", "", "x"),
    ])
    assert len(problems) == 5
    with pytest.raises(EditError):
        apply_edits(tmp_path, [Edit("README.md", "not there", "y")])
