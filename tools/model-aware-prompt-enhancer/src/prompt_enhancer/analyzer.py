"""Analysis orchestration: parse -> classify -> extract requirements -> run rules -> model guidance -> patches.

Everything here is deterministic and offline, cheap enough to run on every
prompt, and the result is a plain JSON-serializable :class:`AnalysisReport`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date

from . import classifier, registry, requirements
from .document import parse
from .rules import RuleContext, all_rules
from .schema import AnalysisReport, Diagnostic, Guideline, HarnessProfile, ModelProfile, Patch, SEVERITY_ORDER
from .tokens import count as count_tokens

STALE_AFTER_DAYS = 180

# Structural patches (S.wrap, S.constraints, S.reminder) are opt-in. Live A/B runs on Claude Haiku
# (see README "Benchmarks") showed no gain from restructuring alone (0 wins, 17 ties, 3 losses over
# 2 runs), while answering the toolkit's questions won every case. Enable with accept=["S.wrap", ...] or force.
STRUCTURE_AUTO = False

# Delimiters the enhancer adds. If the prompt already contains one, the other style (or none) is used.
_XML_MARKERS = ("<user_request", "</user_request", "<constraints", "</constraints", "<request_reminder", "</request_reminder")
_MD_MARKERS = ("## Request", "## Constraints", "## Request reminder")
_STRUCTURED = re.compile(r"<([A-Za-z_][\w-]*)\b[^>]*>.*?</\1>", re.S)
_MD_HEADING = re.compile(r"^#{1,4}\s+\S", re.M)
_EXAMPLES = re.compile(r"(\bfor example\b|\be\.g\.|\bexample\s*:|<example\b|\binput\s*:.*\boutput\s*:)", re.I | re.S)
_REASON = re.compile(r"\b(because|so that|since|as it|as they|in order to|otherwise)\b", re.I)
_NEGATIVE = re.compile(r"\b(don't|do not|never|avoid|without|must not|should not|shouldn't|no)\b", re.I)
_STEPS = re.compile(r"\b(step[- ]by[- ]step|think carefully|first,? .{0,80}\bthen\b)", re.I | re.S)
_NUMBERED = re.compile(r"^[ \t]*\d+[.)][ \t]+\S", re.M)
_CAPS = re.compile(r"\b(CRITICAL|IMPORTANT|MUST|NEVER|ALWAYS|MANDATORY|STRICTLY)\b")


@dataclass
class Options:
    min_words: int = 8  # below this, structural changes are not proposed (diagnostics still run)
    long_context_tokens: int = 4000
    force: bool = False  # propose structure even for short/structured prompts, and apply all non-input patches
    disabled_rules: frozenset[str] = field(default_factory=frozenset)
    min_confidence: float = 0.0

    @classmethod
    def from_env(cls) -> Options:
        o = cls()
        if v := os.environ.get("PROMPT_ENHANCER_MIN_WORDS"):
            o.min_words = int(v)
        if v := os.environ.get("PROMPT_ENHANCER_LONG_CONTEXT_TOKENS"):
            o.long_context_tokens = int(v)
        if v := os.environ.get("PROMPT_ENHANCER_DISABLE_RULES"):
            o.disabled_rules = frozenset(x.strip() for x in v.split(",") if x.strip())
        return o


def _flags(ctx_doc, reqs, tokens: int, opts: Options, intent: str) -> set[str]:
    doc = ctx_doc
    f: set[str] = set()
    constraints = [r for r in reqs if r.kind == "constraint"]
    if doc.blocks:
        f.add("has_context_blocks")
        if doc.text[: doc.blocks[0].start].strip():
            f.add("request_before_context")
    if tokens >= opts.long_context_tokens:
        f.add("long_context")
    has_length = bool(doc.find_all(requirements.LENGTH))
    if not has_length and not doc.find_all(requirements.FORMAT):
        f.add("no_output_format")
    if not has_length:
        f.add("no_length_limit")
    if not _EXAMPLES.search(doc.text):
        f.add("no_examples")
    if constraints:
        f.add("has_constraints")
        if not any(_REASON.search(r.text) for r in constraints):
            f.add("constraints_without_reason")
        if any(_NEGATIVE.search(r.text) for r in constraints):
            f.add("negative_phrasing")
    if _STEPS.search(doc.request) or len(_NUMBERED.findall(doc.request)) >= 3:
        f.add("prescribes_steps")
    if doc.word_count < 12 and not constraints and not doc.blocks and intent != "question":
        f.add("vague_scope")
    if sum(1 for s in doc.sentences if re.match(r"^(also\s+)?(write|create|add|fix|update|remove|rename|summari[sz]e|extract|list|compare|translate|generate|draft|review|implement|document|design)\b", s.text, re.I)) >= 3:
        f.add("multiple_requests")
    if _STRUCTURED.search(doc.request) or len(_MD_HEADING.findall(doc.request)) >= 2:
        f.add("already_structured")
    if doc.text.lstrip().startswith("/"):
        f.add("slash_command")
    if len(_CAPS.findall(doc.request)) >= 2:
        f.add("emphatic_caps")
    if doc.template_vars:
        f.add("has_template_vars")
    return f


def guideline_applies(g: Guideline, task_type: str, intent: str, flags: set[str], harness: HarnessProfile) -> bool:
    w = g.when
    if not set(w.get("flags", [])) <= flags:
        return False
    if "task_types" in w and task_type not in w["task_types"]:
        return False
    if "intent" in w and intent != w["intent"]:
        return False
    if "harnesses" in w and harness.id not in w["harnesses"]:
        return False
    if "harness_modes" in w and harness.mode not in w["harness_modes"]:
        return False
    return True


def _pick_style(profile: ModelProfile, text: str) -> str | None:
    def collides(style: str) -> bool:
        return any(m in text for m in (_XML_MARKERS if style == "xml" else _MD_MARKERS))

    other = "markdown" if profile.style == "xml" else "xml"
    for style in (profile.style, other):
        if not collides(style):
            return style
    return None


def structure_patches(ctx: RuleContext, opts: Options, warnings: list[str]) -> list[Patch]:
    """Profile-driven structural patches: delimiters, restated constraints, long-context reminder.

    They only add delimiters and the user's own sentences, never new requirements.
    """
    doc, prof, flags = ctx.doc, ctx.profile, ctx.flags
    if ctx.harness.mode != "rewrite" or not doc.text.strip() or "slash_command" in flags:
        return []
    if not opts.force and ("already_structured" in flags or doc.word_count < opts.min_words):
        return []
    constraints = [r.text for r in ctx.requirements if r.kind == "constraint"]
    reminder = doc.sentences[0].text if (
        prof.long_context_reminder and {"long_context", "request_before_context"} <= flags and doc.sentences
    ) else None
    if not constraints and not reminder and not opts.force:
        return []
    style = _pick_style(prof, doc.text)
    if style is None:
        warnings.append("prompt already contains the enhancer's delimiters in both styles; no structural changes proposed")
        return []
    if style != prof.style:
        warnings.append(f"prompt contains the {prof.style} delimiters the enhancer would add; using {style} instead")

    structural = [g for g in prof.guidelines if g.kind == "structure" and guideline_applies(g, ctx.task_type, ctx.intent, flags, ctx.harness)]
    style_g = next((g for g in structural if not g.when), structural[0] if structural else None)
    constraints_g = next((g for g in structural if "has_constraints" in g.when.get("flags", [])), style_g)
    reminder_g = next((g for g in structural if "long_context" in g.when.get("flags", [])), style_g)

    def rid(g: Guideline | None) -> str:
        return f"profile:{g.id}" if g else "profile:structure"

    n = len(doc.text)
    out: list[Patch] = []
    # Wrap only the user's instructions. Supplied content (emails, documents, code) must stay outside
    # <user_request>: labelling it as the request makes injected text look like the user's own words.
    # Found by the live A/B run (auto-injection case). If instructions and content interleave, don't wrap.
    if doc.sentences:
        w_start, w_end = doc.sentences[0].start, doc.sentences[-1].end
    else:
        w_start, w_end = 0, n
    interleaved = any(w_start < b.start < w_end for b in doc.blocks)
    block_after = any(b.start >= w_end for b in doc.blocks)
    where = "below" if prof.constraints_position == "before" else "above"
    bullets = "\n".join(f"- {c}" for c in constraints)
    wrap_rationale = (style_g.text if style_g else "Delimit the request.") + " Supplied content stays outside the request tag."
    if style == "xml":
        if not interleaved:
            out.append(Patch(id="S.wrap", rule_id=rid(style_g), op="wrap", start=w_start, end=w_end, new="<user_request>\n",
                             suffix="\n</user_request>", rationale=wrap_rationale, auto=STRUCTURE_AUTO))
        cons = f"<constraints>\nRestated verbatim from the request {where}. Follow every one of them.\n{bullets}\n</constraints>"
        rem = f"<request_reminder>\n{reminder}\n</request_reminder>" if reminder else ""
    else:
        if not interleaved:
            out.append(Patch(id="S.wrap", rule_id=rid(style_g), op="wrap", start=w_start, end=w_end, new="## Request\n\n",
                             suffix="\n\n## Supplied content" if block_after else "", rationale=wrap_rationale, auto=STRUCTURE_AUTO))
        cons = f"## Constraints\n\nRestated verbatim from the request {where}. Follow every one of them.\n\n{bullets}"
        rem = f"## Request reminder\n\n{reminder}" if reminder else ""
    if constraints:
        before = prof.constraints_position == "before"
        out.append(Patch(id="S.constraints", rule_id=rid(constraints_g), op="insert", start=0 if before else n, end=0 if before else n,
                         new=(cons + "\n\n") if before else ("\n\n" + cons), order=-10 if before else 5,
                         rationale="Restate the user's own constraints in one place (verbatim).", auto=STRUCTURE_AUTO))
    if reminder:
        out.append(Patch(id="S.reminder", rule_id=rid(reminder_g), op="insert", start=n, end=n, new="\n\n" + rem, order=9,
                         rationale=reminder_g.text if reminder_g else "Repeat the request after long context.", auto=STRUCTURE_AUTO))
    return out


def run(prompt: str, model: str | None = None, harness: str = "api", options: Options | None = None) -> tuple[AnalysisReport, RuleContext]:
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    opts = options or Options.from_env()
    h = registry.get_harness(harness)
    model_id = registry.detect_model(h, model)
    res = registry.resolve(model_id, h)
    profile = res.profile

    doc = parse(prompt)
    task_type, scores = classifier.classify(doc)
    intent = classifier.intent(doc)
    reqs = requirements.extract(doc)
    tokens, method = count_tokens(prompt)
    flags = _flags(doc, reqs, tokens, opts, intent)
    ctx = RuleContext(doc=doc, task_type=task_type, intent=intent, requirements=reqs, flags=flags, profile=profile, harness=h)

    warnings: list[str] = []
    if model_id and not res.matched:
        warnings.append(f"unknown model {model_id!r}; using the '{profile.id}' fallback profile (generic guidance only)")
    elif not model_id and profile.id == registry.FALLBACK_PROFILE:
        warnings.append("no model given; using the generic profile (pass --model for model-specific guidance)")
    age = (date.today() - date.fromisoformat(profile.last_verified)).days
    if age > STALE_AFTER_DAYS:
        warnings.append(f"profile '{profile.id}' was last verified {age} days ago; run `prompt-enhancer sources check`")

    diagnostics: list[Diagnostic] = []
    patches: list[Patch] = []
    for r in all_rules():
        if r.id in opts.disabled_rules or (r.tasks is not None and task_type not in r.tasks):
            continue
        for i, f in enumerate(r.func(ctx), 1):
            if f.confidence < opts.min_confidence:
                continue
            ids = []
            for j, p in enumerate(f.patches, 1):
                p.id = f"{r.id}.{i}" if len(f.patches) == 1 else f"{r.id}.{i}.{j}"
                p.rule_id = r.id
                patches.append(p)
                ids.append(p.id)
            diagnostics.append(Diagnostic(
                rule_id=r.id, category=r.category, severity=f.severity or r.severity, message=f.message,
                remediation=f.remediation, confidence=round(f.confidence, 2), evidence=f.evidence, patch_ids=ids,
            ))

    # Model guidance: attach to a generic diagnostic ("augments") or report on its own.
    fired = {d.rule_id: d for d in diagnostics}
    for g in profile.guidelines:
        if g.kind != "advice" or not guideline_applies(g, task_type, intent, flags, h):
            continue
        if g.augments:
            d = fired.get(g.augments)
            if d:
                d.remediation += f" [{profile.display_name}] {g.text}"
                d.source_url = d.source_url or g.source.url
                d.evidence_status = d.evidence_status or g.evidence
            continue
        diagnostics.append(Diagnostic(
            rule_id=f"profile:{g.id}", category="model-guidance", severity=g.severity, message=g.text,
            remediation=f"See '{g.section}' in {g.source.title}.", confidence=0.8, source_url=g.source.url, evidence_status=g.evidence,
        ))

    patches += structure_patches(ctx, opts, warnings)
    diagnostics.sort(key=lambda d: (-SEVERITY_ORDER[d.severity], d.evidence[0].start if d.evidence else 10**9, d.rule_id))

    report = AnalysisReport(
        prompt_chars=len(prompt), word_count=doc.word_count, tokens=tokens, token_method=method,
        task_type=task_type, task_scores=scores, intent=intent, model=model_id, model_profile=profile.id,
        profile_version=profile.profile_version, variant=profile.variant, requirements=reqs, diagnostics=diagnostics,
        patches=patches, flags=sorted(flags), warnings=warnings,
    )
    return report, ctx


def analyze(prompt: str, model: str | None = None, harness: str = "api", options: Options | None = None) -> AnalysisReport:
    """Diagnose a prompt without changing it."""
    return run(prompt, model, harness, options)[0]
