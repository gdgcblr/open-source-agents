"""Load, validate, cache and resolve versioned model and harness profiles.

Profiles are JSON files distilled by hand from official vendor documentation.
Every guideline and capability names its source document, the section it came
from, and an evidence status. Profiles can define *variants* for specific
models, because models from one provider do not all behave the same.

Built-in profiles ship in ``profiles/``. A directory named by
``PROMPT_ENHANCER_PROFILES_DIR`` can add profiles or override built-ins by id.
Nothing here touches the network.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .schema import Capability, Guideline, HarnessProfile, ModelProfile, Resolution, Source, Variant

BUILTIN_DIR = Path(__file__).parent / "profiles"
FALLBACK_PROFILE = "generic"
SCHEMA_VERSION = 2

# Profiles must cite official vendor documentation, not blogs or mirrors.
OFFICIAL_DOC_HOSTS = frozenset(
    {
        "platform.claude.com",
        "docs.claude.com",
        "code.claude.com",
        "developers.openai.com",
        "platform.openai.com",
        "ai.google.dev",
        "cloud.google.com",
    }
)

EVIDENCE = {"documented", "experimentally-verified", "unverified"}
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
_KINDS = {"structure", "advice"}
_SEVERITIES = {"info", "warning", "error"}
_STYLES = {"xml", "markdown"}
_POSITIONS = {"before", "after"}
_WHEN_KEYS = {"flags", "task_types", "intent", "harnesses", "harness_modes"}


class ProfileError(ValueError):
    """Raised when a profile file is malformed or cites an unofficial source."""


def _require(cond: Any, where: str, msg: str) -> None:
    if not cond:
        raise ProfileError(f"{where}: {msg}")


def _parse_sources(raw: Any, where: str) -> dict[str, Source]:
    _require(isinstance(raw, list) and raw, where, "'sources' must be a non-empty list")
    out: dict[str, Source] = {}
    for s in raw:
        _require(isinstance(s, dict), where, "each source must be an object")
        url = str(s.get("url", ""))
        parsed = urlparse(url)
        _require(parsed.scheme == "https", where, f"source must use https: {url!r}")
        _require(parsed.hostname in OFFICIAL_DOC_HOSTS, where, f"source host {parsed.hostname!r} is not an allowed official documentation host")
        sid = str(s.get("id") or url)
        out[sid] = Source(id=sid, title=str(s.get("title", url)), url=url)
    return out


def _patterns(raw: Any, where: str) -> tuple[str, ...]:
    _require(isinstance(raw, list), where, "'match' must be a list")
    for p in raw:
        try:
            re.compile(p)
        except (re.error, TypeError) as e:
            raise ProfileError(f"{where}: bad match pattern {p!r}: {e}") from e
    return tuple(raw)


def _parse_guidelines(raw: Any, sources: dict[str, Source], where: str) -> tuple[Guideline, ...]:
    out = []
    for g in raw or []:
        gid = g.get("id")
        _require(isinstance(gid, str) and gid, where, "guideline without id")
        w = f"{where} guideline {gid!r}"
        _require(g.get("kind") in _KINDS, w, f"kind must be one of {sorted(_KINDS)}")
        _require(g.get("source") in sources, w, f"cites unknown source {g.get('source')!r}")
        _require(g.get("evidence") in EVIDENCE, w, f"evidence must be one of {sorted(EVIDENCE)}")
        _require(g.get("severity", "info") in _SEVERITIES, w, "invalid severity")
        _require(isinstance(g.get("text"), str) and g["text"].strip(), w, "missing text")
        when = g.get("when", {})
        _require(isinstance(when, dict) and set(when) <= _WHEN_KEYS, w, f"unknown 'when' keys {set(when) - _WHEN_KEYS}")
        aug = g.get("augments")
        _require(aug is None or re.match(r"^PE\d{3}$", str(aug)), w, "augments must be a rule id like PE301")
        out.append(Guideline(
            id=gid, kind=g["kind"], text=g["text"], source=sources[g["source"]], section=str(g.get("section", "")),
            evidence=g["evidence"], severity=g.get("severity", "info"), when=when, augments=aug,
        ))
    return tuple(out)


def _parse_capabilities(raw: Any, sources: dict[str, Source], where: str) -> tuple[Capability, ...]:
    out = []
    for c in raw or []:
        w = f"{where} capability {c.get('name')!r}"
        _require(c.get("source") in sources, w, "cites unknown source")
        _require(c.get("evidence") in EVIDENCE, w, "invalid evidence status")
        out.append(Capability(name=c["name"], summary=c["summary"], source=sources[c["source"]], evidence=c["evidence"]))
    return tuple(out)


def parse_model_profile(data: Any, where: str) -> ModelProfile:
    _require(isinstance(data, dict), where, "profile must be a JSON object")
    _require(data.get("schema_version") == SCHEMA_VERSION, where, f"unsupported schema_version (expected {SCHEMA_VERSION})")
    pid = str(data.get("id", ""))
    _require(_ID.match(pid), where, f"invalid id {pid!r}")
    _require(_SEMVER.match(str(data.get("profile_version", ""))), where, "profile_version must be semver (x.y.z)")
    _require(_DATE.match(str(data.get("last_verified", ""))), where, "last_verified must be YYYY-MM-DD")
    st = data.get("structure", {})
    _require(isinstance(st, dict) and st.get("style") in _STYLES, where, "structure.style must be xml or markdown")
    _require(st.get("constraints_position") in _POSITIONS, where, "structure.constraints_position must be before or after")
    sources = _parse_sources(data.get("sources"), where)
    variants = []
    for v in data.get("variants", []) or []:
        vw = f"{where} variant {v.get('id')!r}"
        variants.append(Variant(
            id=str(v.get("id")), match=_patterns(v.get("match", []), vw),
            guidelines=_parse_guidelines(v.get("guidelines"), sources, vw),
            capabilities=_parse_capabilities(v.get("capabilities"), sources, vw),
        ))
    return ModelProfile(
        id=pid,
        provider=str(data.get("provider", "unknown")),
        display_name=str(data.get("display_name", pid)),
        profile_version=data["profile_version"],
        last_verified=data["last_verified"],
        aliases=tuple(a.lower() for a in data.get("aliases", [])),
        match=_patterns(data.get("match", []), where),
        style=st["style"],
        constraints_position=st["constraints_position"],
        long_context_reminder=bool(st.get("long_context_reminder", True)),
        sources=tuple(sources.values()),
        capabilities=_parse_capabilities(data.get("capabilities"), sources, where),
        guidelines=_parse_guidelines(data.get("guidelines"), sources, where),
        variants=tuple(variants),
    )


def _profile_dirs() -> tuple[Path, ...]:
    dirs = [BUILTIN_DIR]
    extra = os.environ.get("PROMPT_ENHANCER_PROFILES_DIR")
    if extra:
        dirs.append(Path(extra).expanduser())
    return tuple(dirs)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ProfileError(f"{path.name}: cannot read profile: {e}") from e


@lru_cache(maxsize=8)
def _load_models_cached(dirs: tuple[Path, ...]) -> dict[str, ModelProfile]:
    profiles: dict[str, ModelProfile] = {}
    for d in dirs:
        for path in sorted((d / "models").glob("*.json")):
            prof = parse_model_profile(_read_json(path), path.name)
            profiles[prof.id] = prof  # later directories override built-ins
    if FALLBACK_PROFILE not in profiles:
        raise ProfileError(f"missing required fallback profile '{FALLBACK_PROFILE}'")
    return profiles


@lru_cache(maxsize=8)
def _load_harnesses_cached(dirs: tuple[Path, ...]) -> dict[str, HarnessProfile]:
    harnesses: dict[str, HarnessProfile] = {}
    for d in dirs:
        path = d / "harnesses" / "harnesses.json"
        if not path.exists():
            continue
        data = _read_json(path)
        _require(isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION, path.name, "unsupported schema_version")
        for h in data.get("harnesses", []):
            _require(h.get("mode") in {"rewrite", "augment"}, path.name, f"harness {h.get('id')!r} has invalid mode")
            if h.get("sources"):
                _parse_sources(h["sources"], path.name)
            harnesses[h["id"]] = HarnessProfile(
                id=h["id"], display_name=h.get("display_name", h["id"]), mode=h["mode"], description=h.get("description", ""),
                default_model_profile=h.get("default_model_profile"), model_env=tuple(h.get("model_env", ())),
                max_context_chars=h.get("max_context_chars"),
            )
    return harnesses


def load_models() -> dict[str, ModelProfile]:
    """All model profiles. Parsed once per profile-directory set, then served from an in-process cache."""
    return _load_models_cached(_profile_dirs())


def load_harnesses() -> dict[str, HarnessProfile]:
    return _load_harnesses_cached(_profile_dirs())


def clear_cache() -> None:
    _load_models_cached.cache_clear()
    _load_harnesses_cached.cache_clear()


def get_harness(harness_id: str) -> HarnessProfile:
    harnesses = load_harnesses()
    if harness_id not in harnesses:
        raise KeyError(f"unknown harness {harness_id!r}; known: {', '.join(sorted(harnesses))}")
    return harnesses[harness_id]


def detect_model(harness: HarnessProfile, explicit: str | None = None) -> str | None:
    """Pick the model id: explicit argument first, then environment variables."""
    if explicit and explicit.strip():
        return explicit.strip()
    for var in ("PROMPT_ENHANCER_MODEL", *harness.model_env):
        val = os.environ.get(var)
        if val and val.strip():
            return val.strip()
    return None


def _with_variant(profile: ModelProfile, model_key: str) -> ModelProfile:
    for v in profile.variants:
        if any(re.search(p, model_key) for p in v.match):
            return replace(
                profile,
                guidelines=profile.guidelines + v.guidelines,
                capabilities=profile.capabilities + v.capabilities,
                variant=v.id,
            )
    return profile


def resolve(model: str | None, harness: HarnessProfile | None = None) -> Resolution:
    """Map a model id to a profile, degrading gracefully.

    Order: exact profile id, alias (e.g. ``gemini``), regex pattern on the
    model id (then a matching model-specific variant is merged in), the
    harness default (e.g. Claude Code always runs a Claude model), and finally
    the generic profile.
    """
    profiles = load_models()
    if model and model.strip():
        key = model.strip().lower()
        if key in profiles:
            return Resolution(profiles[key], model, True, "exact-id")
        for prof in profiles.values():
            if key in prof.aliases:
                return Resolution(prof, model, prof.id != FALLBACK_PROFILE, "alias")
        for prof in profiles.values():
            if any(re.search(p, key) for p in prof.match):
                return Resolution(_with_variant(prof, key), model, True, "pattern")
    if harness and harness.default_model_profile in profiles:
        return Resolution(profiles[harness.default_model_profile], model, not model, "harness-default")
    return Resolution(profiles[FALLBACK_PROFILE], model, False, "fallback")
