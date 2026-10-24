"""Content-addressed result cache keys.

key = hash(code context + rules version + CVE db version + prompt version + task).
The model id is deliberately absent, so a model swap in models.yaml keeps every entry.
"""

from __future__ import annotations

import hashlib


def result_key(context_hash: str, versions: dict[str, str], task: str = "judge") -> str:
    raw = "|".join([task, context_hash, versions["rules"], versions["cve_db"],
                    versions["prompt"]])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
