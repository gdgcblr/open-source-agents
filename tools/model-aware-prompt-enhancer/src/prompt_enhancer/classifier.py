"""Deterministic task classification and intent detection.

Five task types drive task-specific rules: coding, research, extraction,
writing, general. Scores are keyword hit counts so the result is explainable;
`scores` is returned with every analysis.
"""

from __future__ import annotations

import re

from .document import PromptDoc

TASK_TYPES = ("coding", "research", "extraction", "writing", "general")

_KEYWORDS: dict[str, re.Pattern[str]] = {
    "coding": re.compile(
        r"\b(function|bug|refactor|unit tests?|compile|stack ?trace|exception|python|javascript|typescript|"
        r"java|golang|rust|c\+\+|sql|regex|endpoint|api|class|method|script|implement|debug|repo(sitory)?|"
        r"pull request|lint|module|library|cli|codebase|deploy|dockerfile|migration)\b",
        re.I,
    ),
    "research": re.compile(
        r"\b(research|investigate|analy[sz]e|compare|evaluate|assess|pros and cons|trade-?offs?|"
        r"summari[sz]e|summary|literature|sources|evidence|explain why|market|study|studies|report on|recap|key points)\b",
        re.I,
    ),
    "extraction": re.compile(
        r"\b(extract|pull out|parse|list all|find all|identify all|get all|classify|categori[sz]e|label each|"
        r"tag each|sentiment|fields?|schema|structured data|normali[sz]e)\b",
        re.I,
    ),
    "writing": re.compile(
        r"\b(write|draft|compose|email|blog|essay|post|letter|rewrite|copy ?edit|tweet|announcement|"
        r"article|newsletter|speech|story|poem|haiku|cover letter|translate|proofread|tone)\b",
        re.I,
    ),
}

_ADVISORY = re.compile(
    r"\b((can|could|would) you (suggest|recommend|advise|propose)|suggest|recommendations?|"
    r"any (ideas|suggestions)|how (should|would|could|can) i|what would you)\b",
    re.I,
)


def classify(doc: PromptDoc) -> tuple[str, dict[str, int]]:
    scores = {k: len(p.findall(doc.request)) for k, p in _KEYWORDS.items()}
    # coding vocabulary is specific ("function", "endpoint"); generic verbs like "write" are not
    scores["coding"] *= 2
    if any(b.text.startswith("```") for b in doc.blocks):
        scores["coding"] += 2
    # "write a function" is coding, not writing: a coding hit outranks a bare "write"
    best = max(scores, key=lambda k: (scores[k], k == "coding"))
    return (best if scores[best] > 0 else "general"), scores


def intent(doc: PromptDoc) -> str:
    if _ADVISORY.search(doc.request):
        return "advisory"
    if doc.request.rstrip().endswith("?"):
        return "question"
    return "action"
