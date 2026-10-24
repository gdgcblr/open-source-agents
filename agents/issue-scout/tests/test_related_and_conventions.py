import base64

from conftest import FakeClient
from issue_scout.conventions import fetch_contributing, likely_files, mentioned_paths, parse_conventions
from issue_scout.related import find_related, keywords, similarity

CONTRIBUTING = """# Contributing

We use [Conventional Commits](https://www.conventionalcommits.org). All commits must be
signed off (`git commit -s`) to satisfy the DCO. Please add a changelog entry.

```bash
$ pip install -e ".[dev]"
pre-commit install
pytest tests/
ruff check .
```
"""


def test_keywords_prefer_code_identifiers():
    words = keywords("Crash when loading config", "Calling `parse_config` on an empty file raises")
    assert words[0] == "parse_config"
    assert "crash" in words and "when" not in words


def test_similarity():
    assert similarity("Crash in config parser", "config parser crash on empty file") >= 0.5
    assert similarity("Add dark mode", "Fix typo in README") == 0.0


def test_find_related_groups_and_flags_duplicates():
    def issues(params):
        if "is:pr" in params["q"]:
            return {"items": [{"number": 40, "title": "Fix config parser crash", "html_url": "u40", "state": "closed"}]}
        return {
            "items": [
                {"number": 1, "title": "Crash in config parser", "html_url": "u1", "state": "open"},  # itself
                {"number": 2, "title": "Config parser crash", "html_url": "u2", "state": "open"},
                {"number": 3, "title": "Config parser crashes on Windows", "html_url": "u3", "state": "closed"},
                {"number": 4, "title": "Docs for plugins", "html_url": "u4", "state": "closed"},  # unrelated
            ]
        }

    client = FakeClient({"/search/issues": issues})
    related = find_related(client, "o/r", {"number": 1, "title": "Crash in config parser", "body": ""})
    assert [i.number for i in related["open_issues"]] == [2]
    assert related["open_issues"][0].possible_duplicate
    assert [i.number for i in related["closed_issues"]] == [3]
    assert [i.number for i in related["merged_prs"]] == [40]
    assert all("repo:o/r" in params["q"] for _, params in client.calls)


def test_parse_conventions():
    parsed = parse_conventions(CONTRIBUTING)
    rules = {rule["rule"] for rule in parsed["rules"]}
    assert {"dco", "conventional_commits", "changelog"} <= rules
    assert "cla" not in rules
    assert parsed["setup_commands"] == ['pip install -e ".[dev]"']
    assert parsed["test_commands"] == ["pytest tests/"]
    assert parsed["lint_commands"] == ["pre-commit install", "ruff check ."]


def test_fetch_contributing_via_community_profile():
    encoded = base64.b64encode(CONTRIBUTING.encode()).decode()
    client = FakeClient(
        {
            "/repos/o/r/community/profile": {"files": {"contributing": {"url": "https://api.github.com/repos/o/r/contents/CONTRIBUTING.md", "html_url": "h"}}},
            "https://api.github.com/repos/o/r/contents/CONTRIBUTING.md": {"encoding": "base64", "content": encoded, "path": "CONTRIBUTING.md"},
        }
    )
    guide = fetch_contributing(client, "o/r")
    assert guide["url"] == "h" and "DCO" in guide["text"]
    assert fetch_contributing(FakeClient({}), "o/r") is None


def test_likely_files_ranks_named_and_matching_paths():
    tree = [
        {"path": "src/config/parser.py", "type": "blob"},
        {"path": "src/config/loader.py", "type": "blob"},
        {"path": "tests/test_parser.py", "type": "blob"},
        {"path": "node_modules/parser/index.js", "type": "blob"},
        {"path": "docs", "type": "tree"},
    ]
    files = likely_files(tree, "Parser crash", "See src/config/loader.py when the config parser fails")
    paths = [f["path"] for f in files]
    assert paths[0] == "src/config/loader.py"
    assert "src/config/parser.py" in paths
    assert not any("node_modules" in p for p in paths)


def test_likely_files_ignores_words_common_to_most_paths():
    tree = [{"path": "acme/module%d/file%d.py" % (i, i), "type": "blob"} for i in range(20)]
    tree.append({"path": "acme/confluence/storage.py", "type": "blob"})
    files = likely_files(tree, "acme confluence storage escapes quotes", "")
    assert [f["path"] for f in files] == ["acme/confluence/storage.py"]
    assert "acme" not in files[0]["why"]


def test_inline_comments_are_stripped_from_commands():
    parsed = parse_conventions("```\npytest -rs    # names skipped tests\n```")
    assert parsed["test_commands"] == ["pytest -rs"]


def test_mentioned_paths():
    assert mentioned_paths("Edit docs/setup.md and utils.py") == ["docs/setup.md", "utils.py"]
