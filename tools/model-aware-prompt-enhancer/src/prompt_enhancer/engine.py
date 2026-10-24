"""Enhancement pipeline: analysis -> patch selection -> apply -> requirement lock -> result.

Selection policy
----------------
* ``auto`` patches apply unless rejected. Currently no patch is automatic:
  structural patches (S.*) became opt-in after live A/B runs showed no gain.
* Other patches apply only when accepted by patch id or rule id (``accept``).
* Patches that need information only the user has (``needs_input``) apply only
  when an answer is supplied in ``answers``; they are never filled by guessing.
* ``force`` applies every *additive* patch that does not need input, and
  proposes structure even for short or already-structured prompts. Patches
  that replace or delete user text always require an explicit ``accept``.

Requirement lock
----------------
Every explicit requirement extracted from the original must appear verbatim in
the result. If an automatic step would drop one, the original is returned
unchanged with status ``blocked``. Requirements inside text the user explicitly
chose to replace (e.g. redacting a secret) are exempt and reported as such.
"""

from __future__ import annotations

import copy
from typing import Any
from collections.abc import Iterable, Mapping

from . import requirements as req
from .analyzer import Options, run
from .patches import PatchConflict, apply, unified_diff
from .rules import RuleContext
from .schema import AnalysisReport, EnhancementResult, LockCheck, Patch


def _augment_context(report: AnalysisReport, ctx: RuleContext, limit: int | None) -> str | None:
    constraints = [r.text for r in report.requirements if r.kind == "constraint"]
    if not constraints:
        return None
    lines = [f"[prompt-enhancer: {report.model_profile} profile v{report.profile_version}]",
             "The user's explicit constraints, quoted verbatim from their prompt. Follow every one of them:"]
    lines += [f"- {c}" for c in constraints]
    text = "\n".join(lines)
    if limit and len(text) > limit:
        text = text[: limit - 15].rstrip() + "\n[truncated]"
    return text


def _select(patches: list[Patch], accept: set[str], reject: set[str], answers: Mapping[str, str], force: bool) -> tuple[list[Patch], list[str], list[str], set[str]]:
    selected: list[Patch] = []
    pending: list[str] = []
    rejected: list[str] = []
    explicit: set[str] = set()
    for p in patches:
        keys = {p.id, p.rule_id}
        if keys & reject:
            rejected.append(p.id)
            continue
        wanted = bool(keys & accept) or "all" in accept
        if p.needs_input:
            answer = (answers.get(p.id) or answers.get(p.rule_id) or "").strip()
            if answer and (wanted or p.id in answers or p.rule_id in answers):
                q = copy.copy(p)
                q.new = p.new.replace("{answer}", answer)
                selected.append(q)
                explicit.add(p.id)
            else:
                pending.append(p.id)
        elif p.auto or wanted or (force and p.op != "replace"):
            selected.append(p)
            if wanted and not p.auto:
                explicit.add(p.id)
        else:
            pending.append(p.id)
    return selected, pending, rejected, explicit


def enhance(
    prompt: str,
    model: str | None = None,
    harness: str = "api",
    options: Options | None = None,
    accept: Iterable[str] = (),
    reject: Iterable[str] = (),
    answers: Mapping[str, str] | None = None,
) -> EnhancementResult:
    """Diagnose ``prompt`` and apply the selected minimal patches.

    ``accept``/``reject`` take patch ids (``PE301.1``, ``S.wrap``) or rule ids
    (``PE301``, ``profile:claude.structure-xml``); ``accept`` may contain ``"all"``.
    ``answers`` maps a patch id or rule id to the user's text for ``needs_input`` patches.
    """
    opts = options or Options.from_env()
    report, ctx = run(prompt, model, harness, opts)
    answers = dict(answers or {})

    def result(status: str, reason: str | None, enhanced: str = prompt, applied: list[str] | None = None,
               pending: list[str] | None = None, rejected: list[str] | None = None,
               additional: str | None = None, lock: LockCheck | None = None) -> EnhancementResult:
        return EnhancementResult(
            original=prompt, enhanced=enhanced, changed=enhanced != prompt or additional is not None, status=status, reason=reason,
            harness=ctx.harness.id, mode=ctx.harness.mode, additional_context=additional, applied=applied or [],
            pending=pending if pending is not None else [p.id for p in report.patches], rejected=rejected or [],
            diff=unified_diff(prompt, enhanced), lock=lock or req.check(report.requirements, enhanced), analysis=report,
        )

    if not prompt.strip():
        return result("skipped", "empty prompt")
    if "slash_command" in report.flags:
        return result("skipped", "slash command; passed through untouched")

    if ctx.harness.mode == "augment":
        extra = _augment_context(report, ctx, ctx.harness.max_context_chars)
        return result("enhanced" if extra else "no-change", None if extra else "no constraints to restate",
                      additional=extra, pending=[p.id for p in report.patches if not p.id.startswith("S.")])

    selected, pending, rejected, explicit = _select(report.patches, set(accept), set(reject), answers, opts.force)
    if not selected:
        if pending:
            reason = f"no automatic changes; {len(pending)} suggestion(s) await review or answers"
        elif report.diagnostics:
            reason = "no safe automatic changes; see diagnostics"
        else:
            reason = "no issues found; the prompt is fine as written"
        return result("no-change", reason, pending=pending, rejected=rejected)

    # A restated constraint must reflect replacements the user accepted inside it (e.g. a redacted key).
    replaced_now = [p for p in selected if p.op == "replace"]
    for i, p in enumerate(selected):
        if p.id == "S.constraints" and replaced_now:
            q = copy.copy(p)
            for r in report.requirements:
                inner = [x for x in replaced_now if r.start <= x.start and x.end <= r.end]
                if r.kind == "constraint" and inner:
                    shifted = [copy.copy(x) for x in inner]
                    for x in shifted:
                        x.start -= r.start
                        x.end -= r.start
                    q.new = q.new.replace(r.text, apply(r.text, shifted))
            selected[i] = q

    try:
        enhanced = apply(prompt, selected)
    except PatchConflict as e:
        return result("blocked", str(e), pending=pending, rejected=rejected)

    # Requirement lock (exempt requirements the user explicitly chose to replace).
    replaced = [p for p in selected if p.id in explicit and p.op == "replace"]
    locked = [r for r in report.requirements if not any(p.start < r.end and r.start < p.end for p in replaced)]
    lock = req.check(locked, enhanced)
    if not lock.ok:
        missing = ", ".join(lock.missing)
        return result("blocked", f"requirement lock failed ({missing} would be lost); original returned unchanged",
                      pending=pending, rejected=rejected, lock=lock)
    exempt = [r.id for r in report.requirements if r not in locked]
    if exempt:
        report.warnings.append(f"requirements {', '.join(exempt)} were modified by patches you accepted")
    return result("enhanced", None, enhanced=enhanced, applied=[p.id for p in selected], pending=pending, rejected=rejected, lock=lock)


def enhance_messages(
    messages: list[dict[str, Any]],
    model: str | None = None,
    harness: str = "api",
    options: Options | None = None,
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], EnhancementResult | None]:
    """Enhance only the latest user message of a chat transcript.

    System/developer messages, tool calls and results, earlier turns and any
    non-text content are returned unchanged (deep-copied; input is not mutated).
    """
    out = copy.deepcopy(messages)
    for msg in reversed(out):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            r = enhance(msg["content"], model=model, harness=harness, options=options, **kwargs)
            if r.status == "enhanced" and r.mode == "rewrite":
                msg["content"] = r.enhanced
            return out, r
    return out, None
