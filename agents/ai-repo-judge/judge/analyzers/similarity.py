"""Cross-submission analysis: duplicate ideas (README TF-IDF cosine) and copied code (shingle Jaccard).

Each submission stores a compact fingerprint, so the cohort can be recomputed cheaply on every run
without re-fetching or re-judging unchanged PRs.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from judge.analyzers.docs import PLACEHOLDER_RE
from judge.workspace import Workspace

STOP = set(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
        "you",
        "your",
        "we",
        "our",
        "can",
        "will",
        "not",
        "use",
        "using",
        "used",
        "uses",
        "which",
        "when",
        "what",
        "who",
        "why",
        "where",
        "all",
        "any",
        "each",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
        "just",
        "also",
        "then",
        "there",
        "these",
        "those",
        "their",
        "them",
        "they",
        "was",
        "were",
        "been",
        "being",
        "do",
        "does",
        "did",
        "get",
        "gets",
        "project",
        "agent",
        "tool",
        "tools",
        "agents",
        "api",
        "key",
        "keys",
        "python",
        "install",
        "run",
        "file",
        "files",
        "example",
        "output",
        "input",
        "readme",
        "env",
        "setup",
        "usage",
        "license",
        "mit",
        "section",
        "step",
        "steps",
        "see",
        "note",
        "e",
        "g",
        "etc",
        "via",
        "e.g",
    ]
)
WORD = re.compile(r"[a-z][a-z0-9+#-]{2,}")
SHINGLE = 5
MAX_HASHES = 3000


def fingerprint(ws: Workspace) -> dict:
    text = PLACEHOLDER_RE.sub(" ", ws.readme.lower())
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"(?m)^#{1,6} .*$", " ", text)  # template headings are shared by everyone
    terms = Counter(w for w in WORD.findall(text) if w not in STOP)
    hashes: set[int] = set()
    for rel in ws.source_files:
        lines = [ln.strip() for ln in (ws.read(rel) or "").splitlines()]
        lines = [ln for ln in lines if ln and not ln.startswith(("#", "//", "import ", "from ", "*", "/*"))]
        for i in range(max(0, len(lines) - SHINGLE + 1)):
            h = int(hashlib.blake2b("\n".join(lines[i : i + SHINGLE]).encode(), digest_size=8).hexdigest(), 16)
            hashes.add(h)
    # Bottom-k sketch keeps the Jaccard estimate unbiased while bounding storage.
    sketch = sorted(hashes)[:MAX_HASHES]
    return {"terms": dict(terms.most_common(400)), "shingles": [str(h) for h in sketch], "n_shingles": len(hashes)}


def _tfidf(docs: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    n = len(docs)
    df: Counter[str] = Counter()
    for terms in docs.values():
        df.update(terms.keys())
    out = {}
    for sid, terms in docs.items():
        # Smoothed IDF (+1) so identical READMEs still score 1.0 in a tiny cohort.
        vec = {t: (1 + math.log(c)) * (math.log((1 + n) / (1 + df[t])) + 1) for t, c in terms.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        out[sid] = {t: v / norm for t, v in vec.items()}
    return out


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


def cohort(fps: dict[str, dict]) -> dict[str, dict]:
    """For each submission id: {'idea': [(other, score)], 'code': [(other, score)]}, sorted descending."""
    ids = list(fps)
    vecs = _tfidf({i: fps[i].get("terms", {}) for i in ids})
    sets = {i: set(fps[i].get("shingles", [])) for i in ids}
    out: dict[str, dict] = {i: {"idea": [], "code": []} for i in ids}
    for x, a in enumerate(ids):
        for b in ids[x + 1 :]:
            idea = round(_cos(vecs[a], vecs[b]), 3)
            sa, sb = sets[a], sets[b]
            code = round(len(sa & sb) / len(sa | sb), 3) if sa and sb else 0.0
            for p, q in ((a, b), (b, a)):
                out[p]["idea"].append((q, idea))
                out[p]["code"].append((q, code))
    for v in out.values():
        v["idea"].sort(key=lambda t: -t[1])
        v["code"].sort(key=lambda t: -t[1])
    return out


def clusters(sim: dict[str, dict], threshold: float = 0.35) -> list[list[str]]:
    parent = {i: i for i in sim}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, v in sim.items():
        for b, s in v["idea"]:
            if s >= threshold:
                parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for i in sim:
        groups.setdefault(find(i), []).append(i)
    return sorted((sorted(g) for g in groups.values() if len(g) > 1), key=len, reverse=True)
