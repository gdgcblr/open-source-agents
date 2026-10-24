"""Orchestration: evaluate new or changed submissions, then publish the whole cohort.

evaluate() is the expensive, cached step (per head commit). publish() is cheap and recomputes
everything that depends on other submissions: similarity, name collisions, medians and insights.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime

from judge import JUDGE_VERSION
from judge.analyzers import run_all, similarity
from judge.llm.client import ChatClient, LLMError
from judge.llm.review import PROMPT_VERSION, LLMReview, mock_review, review
from judge.models import (
    AnalyzerResult,
    Check,
    FileInfo,
    Finding,
    HistoryPoint,
    LLMInfo,
    SimilarRef,
    Submission,
    SubmissionMeta,
    SubmissionSummary,
)
from judge.scoring import (
    MANIPULATION_PENALTY,
    READY_THRESHOLD,
    RUBRIC,
    confidence,
    llm_findings,
    overall_score,
    score_dimensions,
    top_fixes,
    verdict,
)
from judge.sources import body_hash
from judge.store import Store
from judge.workspace import CODE_LANGUAGES, Workspace

log = logging.getLogger(__name__)
LLM_MODES = ("off", "on", "mock")


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# ----- evaluation (expensive, cached by head commit) -------------------------------------------
def cache_keys(meta: SubmissionMeta, llm_mode: str) -> dict:
    return {
        "head_sha": meta.head_sha,
        "judge_version": JUDGE_VERSION,
        "body_hash": body_hash(meta.body),
        "llm_mode": llm_mode,
    }


def is_fresh(prev: dict | None, meta: SubmissionMeta, llm_mode: str) -> bool:
    """True when a stored record can be reused without re-evaluating."""
    if not prev or prev.get("error"):
        return False
    keys = prev.get("keys", {})
    want = cache_keys(meta, llm_mode)
    same_code = all(keys.get(k) == want[k] for k in ("head_sha", "judge_version", "body_hash"))
    if not same_code:
        return False
    if llm_mode == "off":
        return True  # an existing LLM review is extra information, keep it
    llm_ok = (prev.get("review") or {}).get("provider") not in (None, "mock") if llm_mode == "on" else True
    return keys.get("llm_mode") == llm_mode and llm_ok


def evaluate(
    ws: Workspace, *, llm_mode: str, client: ChatClient | None, prev: dict | None, online: bool = True
) -> dict:
    static = run_all(ws, online=online)
    rev: LLMReview | None = None
    info = LLMInfo()
    prev_rev = (prev or {}).get("review")
    # An LLM review is reused for the same commit and prompt even when other analyzers re-run.
    reusable = bool(
        prev_rev
        and (prev or {}).get("keys", {}).get("head_sha") == ws.meta.head_sha
        and prev_rev.get("prompt_version") == PROMPT_VERSION
        and prev_rev.get("provider") != "mock"
    )
    if llm_mode == "off" and reusable:
        rev = LLMReview.model_validate(prev_rev)
        info = LLMInfo(used=True, provider=rev.provider, model=rev.model, tokens=rev.tokens)
    elif llm_mode == "on" and client is not None:
        if reusable:
            rev = LLMReview.model_validate(prev_rev)
            info = LLMInfo(used=True, provider=rev.provider, model=rev.model, tokens=rev.tokens)
        else:
            try:
                rev = review(ws, static, client)
                info = LLMInfo(used=True, provider=rev.provider, model=rev.model, tokens=rev.tokens)
            except LLMError as exc:
                log.warning("LLM review failed for %s: %s", ws.meta.id, exc)
                info = LLMInfo(used=False, error=str(exc)[:300])
    elif llm_mode == "mock":
        rev = mock_review(ws, static)
        info = LLMInfo(used=True, provider="mock", model="mock")

    counts = Counter(f.file for r in static.values() for f in r.findings if f.file)
    files = [
        FileInfo(path=f, lines=ws.line_count(f), language=ws.language(f), findings=counts.get(f, 0)) for f in ws.files
    ]
    langs: Counter[str] = Counter()
    for fi in files:
        if fi.language in CODE_LANGUAGES or fi.language == "HTML":
            langs[fi.language] += fi.lines

    history = list((prev or {}).get("history", []))
    last = (prev or {}).get("last_score")
    if prev and last and prev.get("keys", {}).get("head_sha") != ws.meta.head_sha:
        history.append(last)
    return {
        "id": ws.meta.id,
        "meta": ws.meta.model_dump(),
        "project_path": ws.project_path,
        "extra_projects": ws.extra_projects,
        "category": ws.category,
        "slug": ws.slug,
        "files": [f.model_dump() for f in files],
        "languages": dict(langs.most_common()),
        "loc": sum(f.lines for f in files if f.language in CODE_LANGUAGES),
        "static": {k: v.model_dump() for k, v in static.items()},
        "review": rev.model_dump() if rev else None,
        "llm": info.model_dump(),
        "fingerprint": similarity.fingerprint(ws),
        "keys": cache_keys(ws.meta, llm_mode if info.used or llm_mode != "on" else "off"),
        "history": history[-20:],
        "judged_at": now(),
        "error": None,
    }


def error_record(meta: SubmissionMeta, message: str, prev: dict | None) -> dict:
    return {
        "id": meta.id,
        "meta": meta.model_dump(),
        "error": message,
        "judged_at": now(),
        "keys": cache_keys(meta, "off"),
        "history": (prev or {}).get("history", []),
    }


def evaluate_all(
    source,
    store: Store,
    metas: list[SubmissionMeta],
    *,
    llm_mode: str,
    client: ChatClient | None,
    refresh: bool = False,
    online: bool = True,
    progress: Callable[[str], None] = lambda _: None,
) -> dict[str, dict]:
    from judge.sources import SourceError

    records = store.load_records()
    for i, meta in enumerate(metas, 1):
        prev = records.get(meta.id)
        tag = f"[{i}/{len(metas)}] #{meta.id}"
        if meta.partial and prev and not prev["meta"].get("partial"):
            # API unavailable: keep the stored title/author/description, take only the fresh head commit
            meta = SubmissionMeta.model_validate({**prev["meta"], "head_sha": meta.head_sha, "partial": False})
        if not refresh and is_fresh(prev, meta, llm_mode):
            prev["meta"] = {**prev["meta"], **meta.model_dump(exclude={"head_sha", "base_sha"})}
            store.save_record(prev)
            progress(f"{tag} unchanged since {prev['keys']['head_sha'][:7]}; skipped")
            continue
        try:
            ws = source.workspace(meta) if hasattr(source, "workspace") else source(meta)
        except SourceError as exc:
            records[meta.id] = error_record(meta, str(exc), prev)
            store.save_record(records[meta.id])
            progress(f"{tag} could not be loaded: {exc}")
            continue
        if not ws.project_path:
            records[meta.id] = error_record(meta, "No agents/<slug>/ or tools/<slug>/ folder in this PR", prev)
            store.save_record(records[meta.id])
            progress(f"{tag} has no project folder; recorded as an error")
            continue
        progress(f"{tag} judging {ws.project_path} @ {meta.head_sha[:7]}…")
        rec = evaluate(ws, llm_mode=llm_mode, client=client, prev=prev, online=online)
        records[meta.id] = rec
        store.save_record(rec)
        llm = rec["llm"]
        progress(
            f"{tag} done"
            + (
                f" (LLM {llm['provider']}, {llm['tokens']} tokens)"
                if llm["used"]
                else f" (LLM skipped: {llm['error']})"
                if llm.get("error")
                else " (static only)"
            )
        )
    return records


# ----- publishing (cheap, recomputed every run) -------------------------------------------------
def _cohort_checks(
    rec: dict, sim: dict, records: dict[str, dict]
) -> tuple[list[Check], list[Check], list[Finding], list[SimilarRef]]:
    sid = rec["id"]
    titles = {i: r["meta"].get("title") or r.get("slug", i) for i, r in records.items()}
    slugs = {i: r.get("slug", "") for i, r in records.items()}
    comp, innov, findings, similar = [], [], [], []

    clash = [
        i
        for i, r in records.items()
        if i != sid
        and not r.get("error")
        and r.get("slug") == rec["slug"]
        and r.get("category") == rec["category"]
        and r["meta"].get("state") != "closed"
    ]
    comp.append(
        Check(
            id="unique_name",
            dimension="compliance",
            label="Folder name unique within its category",
            weight=1,
            status="warn" if clash else "pass",
            detail=f"Also used by #{', #'.join(clash)}" if clash else "Unique",
            fix="Pick a more specific name (e.g. add the data source or domain)." if clash else None,
        )
    )
    peers = sim.get(sid)
    if not peers or not peers["idea"]:
        innov.append(
            Check(
                id="novelty",
                dimension="innovation",
                label="Idea differs from other submissions",
                weight=1,
                status="skip",
                detail="No other submissions to compare with",
            )
        )
        return comp, innov, findings, similar
    best_id, best = peers["idea"][0]
    novelty = max(0.2, min(1.0, 1 - (best - 0.15) / 0.5))
    innov.append(
        Check(
            id="novelty",
            dimension="innovation",
            label="Idea differs from other submissions",
            weight=1,
            status="pass" if novelty >= 0.7 else "warn" if novelty >= 0.4 else "fail",
            score=novelty,
            detail=f"Closest: #{best_id} {titles[best_id]!r} (README similarity {best:.0%})",
        )
    )
    code_id, code = peers["code"][0] if peers["code"] else (None, 0.0)
    innov.append(
        Check(
            id="originality",
            dimension="innovation",
            label="Code is not copied from another submission",
            weight=1,
            status="fail" if code >= 0.6 else "warn" if code >= 0.3 else "pass",
            score=max(0.0, 1 - code),
            detail=f"Max code overlap {code:.0%}" + (f" with #{code_id}" if code_id else ""),
        )
    )
    if code >= 0.3 and code_id:
        findings.append(
            Finding(
                dimension="innovation",
                severity="high" if code >= 0.6 else "medium",
                title=f"Large code overlap with #{code_id} ({code:.0%})",
                detail=f"Shares many identical code blocks with {titles[code_id]!r}.",
                fix="If code was adapted, credit the source; otherwise differentiate the implementation.",
            )
        )
    for other, s in peers["idea"][:3]:
        if s >= 0.2:
            similar.append(SimilarRef(id=other, slug=slugs[other], title=titles[other], score=s, kind="idea"))
    for other, s in peers["code"][:2]:
        if s >= 0.15 and other not in {x.id for x in similar}:
            similar.append(SimilarRef(id=other, slug=slugs[other], title=titles[other], score=s, kind="code"))
    return comp, innov, findings, similar


def build_submission(rec: dict, sim: dict, records: dict[str, dict]) -> Submission:
    static = {k: AnalyzerResult.model_validate(v) for k, v in rec["static"].items()}
    comp, innov, extra, similar = _cohort_checks(rec, sim, records)
    static["compliance"].checks.extend(comp)
    static.setdefault("innovation", AnalyzerResult()).checks.extend(innov)
    static["innovation"].findings.extend(extra)
    rev = LLMReview.model_validate(rec["review"]) if rec.get("review") else None

    dims = score_dimensions(static, rev)
    sec = next(d for d in dims if d.key == "security")
    sec.findings.extend(llm_findings(rev))
    manipulated = bool(static["security"].facts.get("manipulation_lines")) or bool(rev and rev.manipulation_attempt)
    overall = max(0, overall_score(dims) - (MANIPULATION_PENALTY if manipulated else 0))
    v, gates = verdict(dims, overall)
    ai = static["ai_native"].facts
    meta = rec["meta"]
    return Submission(
        id=rec["id"],
        number=meta.get("number"),
        title=meta.get("title") or rec["slug"],
        url=meta.get("url"),
        author=meta.get("author"),
        author_avatar=meta.get("author_avatar"),
        state=meta.get("state", "open"),
        created_at=meta.get("created_at"),
        updated_at=meta.get("updated_at"),
        head_sha=meta.get("head_sha", ""),
        category=rec["category"],
        slug=rec["slug"],
        project_path=rec["project_path"],
        extra_projects=rec.get("extra_projects", []),
        files=[FileInfo.model_validate(f) for f in rec["files"]],
        loc=rec["loc"],
        languages=rec["languages"],
        frameworks=ai.get("frameworks", []),
        providers=ai.get("providers", []),
        ai_level=ai.get("ai_level", 0),
        ai_level_label=ai.get("ai_level_label", ""),
        ai_level_evidence=ai.get("ai_evidence", []),
        claims=rev.claims if rev else [],
        summary=rev.summary if rev else None,
        strengths=rev.strengths if rev else [],
        top_fixes=top_fixes(dims, rev),
        dimensions=dims,
        overall=overall,
        verdict=v,
        gates=gates,
        confidence=confidence(dims, bool(rev)),
        manipulation_suspected=manipulated,
        llm=LLMInfo.model_validate(rec.get("llm") or {}),
        similar=similar,
        history=[HistoryPoint.model_validate(h) for h in rec.get("history", [])],
        judged_at=rec["judged_at"],
        judge_version=rec["keys"]["judge_version"],
    )


def summarize(s: Submission) -> SubmissionSummary:
    sev = Counter(f.severity for d in s.dimensions for f in d.findings)
    return SubmissionSummary(
        id=s.id,
        number=s.number,
        title=s.title,
        url=s.url,
        author=s.author,
        author_avatar=s.author_avatar,
        state=s.state,
        category=s.category,
        slug=s.slug,
        overall=s.overall,
        verdict=s.verdict,
        confidence=s.confidence,
        scores={d.key: d.score for d in s.dimensions},
        frameworks=s.frameworks,
        providers=s.providers,
        languages=list(s.languages)[:4],
        ai_level=s.ai_level,
        ai_level_label=s.ai_level_label,
        severity_counts={k: sev.get(k, 0) for k in ("critical", "high", "medium", "low", "info")},
        top_fix=s.top_fixes[0] if s.top_fixes else None,
        head_sha=s.head_sha,
        judged_at=s.judged_at,
        updated_at=s.updated_at,
        llm_used=s.llm.used,
    )


def insights(subs: list[Submission], clusters: list[list[str]]) -> dict:
    n = len(subs)
    by_id = {s.id: s for s in subs}
    overall = [s.overall for s in subs]
    dim_scores: dict[str, list[int]] = {d.key: [] for d in RUBRIC}
    issues: dict[str, dict] = {}
    for s in subs:
        for d in s.dimensions:
            if d.score is not None:
                dim_scores[d.key].append(d.score)
            for c in d.checks:
                if c.status in ("fail", "warn"):
                    item = issues.setdefault(
                        f"{d.key}.{c.id}",
                        {"check_id": c.id, "dimension": d.key, "label": c.label, "fail": 0, "warn": 0},
                    )
                    item[c.status] += 1

    def tally(values) -> list[dict]:
        return [{"name": k, "count": v} for k, v in Counter(values).most_common()]

    hist = Counter(min(9, s.overall // 10) for s in subs)
    return {
        "count": n,
        "by_verdict": dict(Counter(s.verdict for s in subs)),
        "by_category": dict(Counter(s.category for s in subs)),
        "by_state": dict(Counter(s.state for s in subs)),
        "avg_overall": round(statistics.mean(overall)) if overall else 0,
        "median_overall": round(statistics.median(overall)) if overall else 0,
        "dimension_avg": {k: round(statistics.mean(v)) if v else None for k, v in dim_scores.items()},
        "dimension_median": {k: round(statistics.median(v)) if v else None for k, v in dim_scores.items()},
        "histogram": [
            {"bucket": f"{b * 10}-{b * 10 + 9 if b < 9 else 100}", "count": hist.get(b, 0)} for b in range(10)
        ],
        "providers": tally(p for s in subs for p in s.providers),
        "frameworks": tally(f for s in subs for f in s.frameworks),
        "languages": tally(lang for s in subs for lang in list(s.languages)[:2]),
        "ai_levels": [{"level": lvl, "count": sum(1 for s in subs if s.ai_level == lvl)} for lvl in range(6)],
        "common_issues": sorted(
            ({**v, "share": round((v["fail"] + v["warn"]) / n, 2)} for v in issues.values()),
            key=lambda x: (-(x["fail"] + x["warn"]), -x["fail"]),
        )[:12]
        if n
        else [],
        "clusters": [{"members": c, "titles": [by_id[i].title for i in c if i in by_id]} for c in clusters],
        "secrets_found": sum(
            1 for s in subs if any(f.gate and f.dimension == "security" for d in s.dimensions for f in d.findings)
        ),
        "manipulation_attempts": sum(s.manipulation_suspected for s in subs),
        "llm_tokens": sum(s.llm.tokens for s in subs),
    }


def publish(store: Store, records: dict[str, dict], repo: str | None) -> tuple[dict, dict[str, dict]]:
    ok = {i: r for i, r in records.items() if not r.get("error") and r.get("static")}
    sim = similarity.cohort({i: r.get("fingerprint", {}) for i, r in ok.items()})
    subs = [build_submission(r, sim, ok) for r in ok.values()]
    subs.sort(key=lambda s: (s.number is None, -(s.number or 0)))
    for s in subs:  # remember the latest score so the next commit can append it to history
        rec = ok[s.id]
        rec["last_score"] = HistoryPoint(
            sha=s.head_sha, judged_at=s.judged_at, overall=s.overall, verdict=s.verdict
        ).model_dump()
        store.save_record(rec)
    groups = similarity.clusters(sim)
    ins = insights(subs, groups)
    errors = [
        {"id": i, "title": r["meta"].get("title"), "url": r["meta"].get("url"), "error": r["error"]}
        for i, r in records.items()
        if r.get("error")
    ]
    index = {
        "generated_at": now(),
        "repo": repo,
        "judge_version": JUDGE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "rubric": [
            {"key": d.key, "label": d.label, "weight": d.weight, "llm_share": d.llm_share, "purpose": d.purpose}
            for d in RUBRIC
        ],
        "thresholds": {"ready": READY_THRESHOLD, "manipulation_penalty": MANIPULATION_PENALTY},
        "submissions": [summarize(s).model_dump() for s in subs],
        "insights": ins,
        "errors": errors,
    }
    details = {s.id: s.model_dump() for s in subs}
    return index, details
