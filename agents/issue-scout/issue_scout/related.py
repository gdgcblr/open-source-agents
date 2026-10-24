"""Find issues and merged PRs related to an issue, so contributors see prior work first."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence

STOPWORDS = set(
    """
    a about above add added adding after again all allow allows also an and any are as at be because been before
    being below between both bug but by can cannot could did do does doing don done down during each enable error
    even every example feature few fix fixed fixes for from get gets getting give had has have having how however i
    if implement improve in instead into is issue it its just like make makes many may more most must need needed
    needs new no not now of off on once one only or other our out over own please possible problem request same
    see should so some such support supported than that the their them then there these they this those through to
    too try trying under until up update use used user users uses using very via want was way we were what when
    where which while who why will with without would yet you your
    """.split()
)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")
MIN_SIMILARITY = 0.1
_CODE_RE = re.compile(r"`([^`\n]{2,60})`")


@dataclass
class RelatedItem:
    number: int
    title: str
    url: str
    kind: str  # "issue" or "pr"
    state: str  # "open", "closed" or "merged"
    similarity: float
    possible_duplicate: bool = False


def tokens(text: str) -> List[str]:
    found = []
    for raw in _TOKEN_RE.findall(text or ""):
        word = raw.lower()
        if len(word) >= 3 and word not in STOPWORDS:
            found.append(word)
    return found


def keywords(title: str, body: str = "", limit: int = 5) -> List[str]:
    """Pick search terms: code identifiers first, then title words, then frequent body words."""
    ranked: Dict[str, float] = {}
    for snippet in _CODE_RE.findall(body or "") + _CODE_RE.findall(title or ""):
        for word in tokens(snippet):
            ranked[word] = ranked.get(word, 0) + 3
    for word in tokens(title):
        ranked[word] = ranked.get(word, 0) + 2
    for word in tokens(body)[:400]:
        ranked[word] = ranked.get(word, 0) + 0.2
    ordered = sorted(ranked.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ordered[:limit]]


def similarity(a: str, b: str) -> float:
    left, right = set(tokens(a)), set(tokens(b))
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 2)


def _search(client, query: str, terms: List[str]) -> List[dict]:
    """Precise first (top two terms must all match), broad (any term) only if that finds little."""
    items = client.search_issues("%s %s" % (query, " ".join(terms[:2])), per_page=20)
    if len(items) < 3 and len(terms) > 2:
        seen = {item.get("number") for item in items}
        broad = client.search_issues("%s %s" % (query, " OR ".join(terms)), per_page=20)
        items = items + [item for item in broad if item.get("number") not in seen]
    return items


def find_related(client, repo: str, issue: dict, limit: int = 5) -> Dict[str, List[RelatedItem]]:
    """Similar issues (any state) and merged PRs that touched the same topic: 2-4 search calls."""
    terms = keywords(issue.get("title", ""), issue.get("body") or "", limit=4)
    result: Dict[str, List[RelatedItem]] = {"open_issues": [], "closed_issues": [], "merged_prs": []}
    if not terms:
        return result
    title = issue.get("title", "")
    number = issue.get("number")

    for item in _search(client, "repo:%s is:issue" % repo, terms):
        if item.get("number") == number:
            continue
        score = similarity(title, item.get("title", ""))
        state = item.get("state", "open")
        related = RelatedItem(item["number"], item.get("title", ""), item.get("html_url", ""), "issue", state, score)
        related.possible_duplicate = score >= 0.5
        result["open_issues" if state == "open" else "closed_issues"].append(related)

    for item in _search(client, "repo:%s is:pr is:merged" % repo, terms):
        score = similarity(title, item.get("title", ""))
        result["merged_prs"].append(
            RelatedItem(item["number"], item.get("title", ""), item.get("html_url", ""), "pr", "merged", score)
        )

    for key in result:
        result[key] = _top(result[key], limit)
    return result


def _top(items: Sequence[RelatedItem], limit: int) -> List[RelatedItem]:
    # The OR query casts a wide net; keep only items whose titles actually overlap.
    relevant = [item for item in items if item.similarity >= MIN_SIMILARITY]
    return sorted(relevant, key=lambda item: -item.similarity)[:limit]
