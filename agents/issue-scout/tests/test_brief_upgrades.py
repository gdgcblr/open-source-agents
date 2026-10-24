"""Code pointers, the repo-aware next step, and the legwork receipt."""

import base64

from conftest import NOW, FakeClient, comment, issue_payload, repo_payload, ts
from issue_scout.models import Candidate, IssueSignals, Mention, Profile
from issue_scout.plan import next_step
from issue_scout.pointers import MAX_HITS_PER_FILE, code_pointers, identifiers
from issue_scout.report import render_brief, render_find
from issue_scout.scout import Scout
from test_pipeline import world

ISSUE_BODY = """Bodies are written by `html.escape` in `_storage` and `_export_view`. See `confluence` docs.

```python
import xml.etree.ElementTree
`decoy_in_repro` = 1
```
"""
SOURCE = "\n".join([
    "import html",
    "",
    "def _storage(content: str) -> str:",
    "    return html.escape(content)",
    "",
    "def _export_view(content: str) -> str:",
    "    return html.escape(content)",
])


def encoded(text):
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode(), "size": len(text)}


def test_identifiers_take_prose_names_in_order_and_skip_repro_scripts():
    names = identifiers("Escaping bug", ISSUE_BODY)
    assert names == ["html.escape", "_storage", "_export_view"]  # no plain words, no fenced decoys


def test_identifiers_ignore_hashes_and_common_words():
    assert identifiers("", "At `8584940e` on `main`, `GET` returns `fooBar`") == ["fooBar"]


def code_client(authenticated=True, search_hits=("src/atlassian.py",)):
    def search(params):
        # The underscore name is tried first; dotted names are unreliable in code search.
        return {"items": [{"path": p} for p in search_hits]} if "_storage" in params["q"] else {"items": []}

    return FakeClient(
        {
            "/search/code": search,
            "/repos/o/r/contents/src/atlassian.py": encoded(SOURCE),
            "/repos/o/r/contents/src/huge.py": dict(encoded("x"), size=10_000_000),
        },
        authenticated=authenticated,
    )


def test_code_pointers_find_exact_lines_via_code_search():
    client = code_client()
    result = code_pointers(client, "o/r", "main", "t", ISSUE_BODY, [], ["src/atlassian.py", "src/other.py"])
    lines = [(p["path"], p["line"], p["term"]) for p in result["pointers"]]
    assert lines[0] == ("src/atlassian.py", 3, "_storage")
    assert ("src/atlassian.py", 4, "html.escape") in lines
    assert len(lines) == MAX_HITS_PER_FILE
    assert result["pointers"][0]["url"] == "https://github.com/o/r/blob/main/src/atlassian.py#L3"
    first_query = next(p["q"] for path, p in client.calls if path == "/search/code")
    assert first_query == "repo:o/r _storage"


def test_code_pointers_only_open_files_in_the_repo_tree():
    client = code_client(search_hits=("../../etc/passwd", "src/atlassian.py"))
    result = code_pointers(client, "o/r", "main", "t", ISSUE_BODY, [], ["src/atlassian.py"])
    assert result["searched_files"] == ["src/atlassian.py"]


def test_code_pointers_without_token_fall_back_to_likely_files_and_skip_huge_files():
    client = code_client(authenticated=False)
    result = code_pointers(client, "o/r", "main", "t", ISSUE_BODY, ["src/huge.py", "src/atlassian.py"],
                           ["src/huge.py", "src/atlassian.py"])
    assert not any(path == "/search/code" for path, _ in client.calls)
    assert {p["path"] for p in result["pointers"]} == {"src/atlassian.py"}


def test_code_pointers_need_identifiers():
    result = code_pointers(code_client(), "o/r", "main", "t", "no code names here", ["src/atlassian.py"], [])
    assert result == {"identifiers": [], "pointers": [], "searched_files": []}


# --- next step ------------------------------------------------------------------------


def candidate(flags=(), verdict="ready", **signals):
    c = Candidate(repo="o/r", number=7, title="t", url="u", verdict=verdict, flags=list(flags))
    c.signals = IssueSignals(**signals)
    return c


CONVENTIONS = {"rules": [{"rule": "dco"}, {"rule": "cla"}], "test_commands": ["pytest -q"]}


def test_next_step_for_a_clean_issue_drafts_a_comment_and_checklist():
    step = next_step(candidate(), CONVENTIONS, "src/atlassian.py", NOW)
    assert "Leave a short comment" in step["action"]
    assert "`src/atlassian.py`" in step["comment_draft"]
    assert step["checklist"] == [
        "Sign the project's CLA before opening the PR.",
        "Sign off every commit: git commit -s",
        "Run the tests before pushing: `pytest -q`",
        "Write `Fixes #7` in the PR description so the issue closes when it merges.",
    ]


def test_next_step_respects_a_no_assignment_policy():
    policy = Mention("maint", ts(1), "https://github.com/o/r/issues/7#c1", "just open a PR", True)
    step = next_step(candidate(open_policy=policy), {}, None, NOW)
    assert step["action"].startswith("Start now")
    assert step["comment_draft"] is None and "@maint" in step["why"]


def test_next_step_asks_an_active_claimant_first():
    claim = Mention("alice", ts(3), "https://github.com/o/r/issues/7#c2", "can I work on this")
    step = next_step(candidate(["recently-claimed"], "caution", active_claims=[claim]), {}, None, NOW)
    assert "Ask whether" in step["action"] and "3 days ago" in step["why"]
    assert step["comment_draft"].startswith("Hi @alice")


def test_next_step_confirms_possible_fix_first():
    hint = Mention("bob", ts(1), "https://github.com/o/r/issues/7#c3", "already exists")
    step = next_step(candidate(["possibly-resolved"], "caution", resolved_hints=[hint]), {}, None, NOW)
    assert step["action"].startswith("Confirm") and "@bob" in step["comment_draft"]


def test_next_step_for_dead_end_says_skip():
    step = next_step(candidate(["open-pr"], "skip"), {}, None, NOW)
    assert step["action"].startswith("Don't start") and "open PR" in step["why"]


# --- brief and find integration -------------------------------------------------------


def test_brief_puts_code_pointer_files_first_and_renders_new_sections():
    client = world()
    client.token = "t"  # code search needs a token
    client.routes["/search/code"] = lambda params: {"items": [{"path": "src/atlassian.py"}]}
    client.routes["/repos/acme/app/issues/1"] = issue_payload(1, "acme/app", title="Escaping bug", body=ISSUE_BODY)
    client.routes["/repos/acme/app"] = repo_payload("acme/app")
    client.routes["/repos/acme/app/git/trees/main"] = {"tree": [
        {"path": "src/atlassian.py", "type": "blob"},
        {"path": "docs/escaping_bug.md", "type": "blob"},
    ]}
    client.routes["/repos/acme/app/contents/src/atlassian.py"] = encoded(SOURCE)
    client.routes["/search/issues"] = {"items": []}

    facts = Scout(client, now=NOW).brief_facts("acme/app#1")
    assert facts["likely_files"][0]["path"] == "src/atlassian.py"
    assert "contains" in facts["likely_files"][0]["why"]
    assert facts["next_step"]["action"].startswith("Leave a short comment")

    text = render_brief(facts, NOW)
    assert "### Next step" in text and "### Code pointers" in text
    assert "[`src/atlassian.py:3`](https://github.com/acme/app/blob/main/src/atlassian.py#L3)" in text


def test_find_reports_legwork():
    client = world()
    for number, events in ((1, [comment("a"), comment("b")]), (2, [])):
        client.routes["/repos/acme/app/issues/%d/timeline" % number] = events
    result = Scout(client, now=NOW).find(Profile(languages=["python"]), limit=5)
    work = result.legwork
    assert work["issues_checked"] == 4
    assert work["comments_read"] == 2 + 1 + 1  # acme/app#1 (2), lib#3 (1), lib#4 (1)
    assert work["cross_references_followed"] == 0
    assert work["repos_merge_history_checked"] == 2 and work["closed_prs_reviewed"] == 7
    assert "**Legwork done for you:** checked 4 issues, read 4 comments" in render_find(result, NOW)
