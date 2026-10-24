"""Guardrails shared by the CLI, the MCP server and the ADK agent.

Three jobs, all deterministic and model-free:
1. Validate every value that ends up inside a GitHub search query, so user or model input
   cannot smuggle in extra qualifiers (e.g. a "language" of `python repo:evil/x`).
2. Treat issue text as untrusted: spot text that tries to instruct AI tools, and mask
   secrets (leaked tokens and keys) before anything reaches a model or a terminal.
3. Help check that a model's answer only links to GitHub pages the tools actually returned.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Set

from .models import Profile


class GuardrailError(ValueError):
    """Raised when input fails validation. The message is safe to show to users and models."""


# --- 1. Input validation ----------------------------------------------------

MAX_LANGUAGES = 5
MAX_TOPICS = 3
MAX_LABELS = 5
HOURS_RANGE = (0.5, 40.0)
STARS_RANGE = (0, 1_000_000)

_LANGUAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+#.\- ]{0,29}$")  # c++, c#, objective-c, jupyter notebook
_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")  # GitHub's own topic rules
_LABEL_RE = re.compile(r"^[^\"\\\n\r\t]{1,50}$")  # labels are quoted in queries, so no quotes/escapes
_REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def _check_all(values: Iterable[str], pattern: re.Pattern, kind: str, limit: int) -> List[str]:
    cleaned = []
    for value in values:
        item = " ".join(str(value).split()).strip().lower() if kind != "label" else str(value).strip()
        if not item:
            continue
        if not pattern.match(item):
            raise GuardrailError("Invalid %s %r." % (kind, value))
        if item not in cleaned:
            cleaned.append(item)
    if len(cleaned) > limit:
        raise GuardrailError("Too many %ss (max %d)." % (kind, limit))
    return cleaned


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clean_profile(profile: Profile) -> Profile:
    """Validate a profile in place before it is turned into search queries."""
    profile.languages = _check_all(profile.languages, _LANGUAGE_RE, "language", MAX_LANGUAGES)
    profile.topics = _check_all(profile.topics, _TOPIC_RE, "topic", MAX_TOPICS)
    profile.labels = _check_all(profile.labels, _LABEL_RE, "label", MAX_LABELS)
    if not profile.labels:
        raise GuardrailError("At least one issue label is required.")
    profile.hours = clamp(float(profile.hours), *HOURS_RANGE)
    profile.min_stars = int(clamp(int(profile.min_stars), *STARS_RANGE))
    if profile.max_stars is not None:
        profile.max_stars = int(clamp(int(profile.max_stars), profile.min_stars, STARS_RANGE[1]))
    return profile


def check_repo(repo: str) -> str:
    repo = (repo or "").strip()
    if not _REPO_RE.match(repo) or ".." in repo:
        raise GuardrailError("Invalid repository %r (expected owner/name)." % repo)
    return repo


def check_user(user: str) -> str:
    user = (user or "").strip()
    if not _USER_RE.match(user):
        raise GuardrailError("Invalid GitHub username %r." % user)
    return user


# --- 2. Untrusted content -------------------------------------------------------

_INJECTION_PATTERNS = [
    r"\bignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?|rules)\b",
    r"\bdisregard (all |any )?(the )?(previous|prior|above|your) (instructions|rules|guidelines)\b",
    r"\bforget (everything |all |what )?(you were told|you know|your (previous |prior )?(instructions|rules)|(previous|prior) instructions)\b",
    r"\b(you are|act as|pretend to be) (now )?(an? )?(ai|assistant|chatbot|language model|llm)\b",
    # Not plain "system prompt": AI repos discuss system prompts in ordinary bug reports.
    r"\b(ai|llm|bot|assistant|agent)s? (reading|processing|summari[sz]ing) this\b",
    r"\bnew instructions?:",
    r"<\s*/?\s*(system|instructions?)\s*>",
    r"\b(reveal|print|output|leak) (your|the) (system prompt|instructions|api key|token)",
    r"\bmark (this|the) issue as (ready|available|safe)\b",
]
_injection_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Common credential formats. Matches are masked, never logged.
_SECRET_PATTERNS = [
    r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",  # GitHub classic / OAuth / app tokens
    r"\bgithub_pat_[A-Za-z0-9_]{30,}\b",  # GitHub fine-grained tokens
    r"\bAIza[0-9A-Za-z_-]{35}\b",  # Google API keys
    r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}\b",  # OpenAI / Anthropic style keys
    r"\bAKIA[0-9A-Z]{16}\b",  # AWS access key ids
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",  # Slack tokens
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
]
_secret_re = re.compile("|".join("(?:%s)" % p for p in _SECRET_PATTERNS))
REDACTED = "[redacted secret]"


def detect_injection(text: str) -> Optional[str]:
    """Return a short snippet if the text looks like it is trying to instruct an AI tool."""
    for pattern in _injection_re:
        match = pattern.search(text or "")
        if match:
            start, end = max(0, match.start() - 30), min(len(text), match.end() + 30)
            return " ".join(text[start:end].split())
    return None


def redact_secrets(text: str) -> str:
    return _secret_re.sub(REDACTED, text) if text else text


def redact_tree(value: Any) -> Any:
    """Mask secrets in every string of a JSON-like structure."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_tree(item) for key, item in value.items()}
    return value


# --- 3. Grounding ---------------------------------------------------------------

_GITHUB_URL_RE = re.compile(r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.\-/#?=&%]+")


def _normalise_url(url: str) -> str:
    url = url.rstrip(").,;:!?'\"]>*_`")
    url = url.split("#")[0].split("?")[0].rstrip("/")
    return url.lower().replace("://www.", "://")


def github_urls(value: Any) -> Set[str]:
    """Every GitHub web URL inside a string or JSON-like structure, normalised."""
    found: Set[str] = set()
    if isinstance(value, str):
        found.update(_normalise_url(url) for url in _GITHUB_URL_RE.findall(value))
    elif isinstance(value, list):
        for item in value:
            found |= github_urls(item)
    elif isinstance(value, dict):
        for item in value.values():
            found |= github_urls(item)
    return found


def ungrounded_urls(text: str, allowed: Iterable[str]) -> List[str]:
    """GitHub URLs in `text` that neither a tool result nor the user supplied."""
    allowed_set = {_normalise_url(url) for url in allowed}
    # A repo root is grounded if any URL inside that repo was returned.
    repo_roots = {"/".join(url.split("/")[:5]) for url in allowed_set}
    return sorted(
        url for url in github_urls(text) if url not in allowed_set and url not in repo_roots
    )
