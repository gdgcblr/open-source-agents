import pytest

from prompt_enhancer import registry, sources


def page(ok=True):
    sections = set()
    for p in registry.load_models().values():
        for g in list(p.guidelines) + [g for v in p.variants for g in v.guidelines]:
            sections.add(g.section.split(">")[-1].strip())
    body = " ".join(sorted(sections)) if ok else "This page was reorganised."
    return f"<html><script>var nonce={id(body)}</script><body><h2>{body}</h2></body></html>"


def test_check_reports_ok_and_detects_changes():
    rows = sources.check(fetcher=lambda url: page())
    assert rows and all(r["status"] == "ok" for r in rows)
    assert all(r["changed_since_last_check"] is None for r in rows)
    assert all(r["changed_since_last_check"] is False for r in sources.check(fetcher=lambda url: page()))
    assert all(r["changed_since_last_check"] is True for r in sources.check(fetcher=lambda url: page() + "<p>new</p>"))


def test_missing_sections_flagged():
    rows = sources.check(fetcher=lambda url: page(False), use_cache=False)
    assert all(r["status"] == "sections-missing" and r["missing_sections"] for r in rows)


def test_fetch_errors_are_reported_not_raised():
    def boom(url):
        raise TimeoutError("slow")
    assert all(r["status"] == "error" for r in sources.check(fetcher=boom, use_cache=False))


@pytest.mark.parametrize("url", ["http://ai.google.dev/x", "https://evil.example.com/x", "file:///etc/passwd"])
def test_fetch_refuses_non_official_or_insecure_urls(url):
    with pytest.raises(ValueError):
        sources.fetch(url)


@pytest.mark.network
def test_live_docs_still_contain_cited_sections():
    rows = sources.check(use_cache=False)
    assert all(r["status"] == "ok" for r in rows), rows
