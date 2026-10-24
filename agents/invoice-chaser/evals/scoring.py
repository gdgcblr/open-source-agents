"""Scoring for the live evals. Pure functions where possible so they are unit-tested
offline (tests/test_eval_scoring.py)."""

import json
import os
import re

from ledger import Ledger

THRESHOLDS = {
    "matcher_auto_apply_precision": 1.0,   # target ≥ 99%; on 20 cases that means no mistakes
    "matcher_pass_rate": 0.85,
    "matcher_critical_errors": 0,
    "drafter_coverage": 1.0,
    "drafter_rule_pass_rate": 1.0,
    "drafter_judge_mean": 4.0,
    "drafter_judge_min": 3,
}

HINGLISH_MARKERS = {"ji", "aap", "aapka", "aapke", "hai", "hain", "kar", "kijiye", "karein",
                    "ka", "ki", "ko", "abhi", "dhanyavaad", "namaste", "shukriya", "zaroor"}
HINDI_ONLY_MARKERS = {"ji", "hai", "hain", "kijiye", "karein", "namaste", "dhanyavaad", "aap"}


# ---------------------------------------------------------------- generic

def final_text(events, author: str) -> str | None:
    texts = [p.text for e in events if e.author == author and e.content and not e.partial
             for p in (e.content.parts or []) if p.text]
    return texts[-1] if texts else None


def _responses(events):
    for e in events:
        for p in (e.content.parts if e.content else None) or []:
            if p.function_response:
                yield p.function_response.name, p.function_response.response


def _as_dict(resp):
    if isinstance(resp, dict) and "content" in resp and resp["content"]:
        try:
            return json.loads(resp["content"][0].get("text", "{}"))
        except (TypeError, ValueError, AttributeError):
            return {}
    return resp if isinstance(resp, dict) else {}


def count_tool_errors(events, tool: str, code: str) -> int:
    return sum(1 for name, r in _responses(events) if name == tool and _as_dict(r).get("error_code") == code)


def tool_result_text(events) -> str:
    return "\n".join(json.dumps(_as_dict(r), ensure_ascii=False) for _, r in _responses(events))


_AMOUNT = re.compile(r"(₹|\$)\s?[\d,]+(?:\.\d+)?")


def ungrounded_amounts(text: str | None, events) -> list[str]:
    """Amounts in the agent's reply that never appeared in any tool result."""
    if not text:
        return []
    source = tool_result_text(events).replace(" ", "")
    return [m.group(0) for m in _AMOUNT.finditer(text) if m.group(0).replace(" ", "") not in source]


# ---------------------------------------------------------------- matcher

def matcher_outcome(led: Ledger) -> dict:
    rows = led.conn.execute("SELECT invoice_ids, status FROM match_proposals ORDER BY id").fetchall()
    applied = [json.loads(r["invoice_ids"]) for r in rows if r["status"] == "APPLIED"]
    pending = [json.loads(r["invoice_ids"]) for r in rows if r["status"] == "PENDING"]
    if applied:
        return {"kind": "AUTO_APPLIED", "invoice_ids": sorted(applied[-1]), "proposals": len(rows)}
    if pending:
        return {"kind": "NEEDS_CONFIRMATION", "invoice_ids": sorted(pending[-1]),
                "all_pending": [sorted(p) for p in pending], "proposals": len(rows)}
    return {"kind": "NONE", "invoice_ids": None, "proposals": len(rows)}


def score_matcher_case(expected: dict, outcome: dict, error: str | None) -> dict:
    exp_ids = sorted(expected["invoice_ids"]) if expected["invoice_ids"] else None
    kind = outcome["kind"]
    if exp_ids is None:
        passed = kind == "NONE" or (kind == "NEEDS_CONFIRMATION" and "PENDING_OK" in expected["allowed_decisions"])
        critical = kind == "AUTO_APPLIED"
    else:
        passed = kind in expected["allowed_decisions"] and outcome["invoice_ids"] == exp_ids
        critical = kind == "AUTO_APPLIED" and outcome["invoice_ids"] != exp_ids
    return {"passed": passed and error is None, "critical": critical}


def matcher_metrics(results: list[dict]) -> dict:
    auto = [r for r in results if r["outcome"]["kind"] == "AUTO_APPLIED"]
    auto_correct = [r for r in auto if not r["critical"]]
    should_auto = [r for r in results if r["expected"]["allowed_decisions"] == ["AUTO_APPLIED"]]
    covered = [r for r in should_auto if r["outcome"]["kind"] == "AUTO_APPLIED" and not r["critical"]]
    return {
        "cases": len(results),
        "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3) if results else 0,
        "auto_apply_precision": round(len(auto_correct) / len(auto), 3) if auto else 1.0,
        "auto_apply_coverage": round(len(covered) / len(should_auto), 3) if should_auto else 1.0,
        "critical_errors": sum(r["critical"] for r in results),
        "errors": sum(1 for r in results if r["error"]),
        "failed_ids": [r["id"] for r in results if not r["passed"]],
    }


# ---------------------------------------------------------------- drafter

def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def rule_checks(reminder: dict, item: dict) -> dict:
    words = _words(reminder["subject"] + " " + reminder["body"])
    if item["language"] == "hinglish":
        language_ok = len(words & HINGLISH_MARKERS) >= 2
    else:
        language_ok = not (words & HINDI_ONLY_MARKERS)
    checks = {
        "tone_matches": reminder["tone_level"] == item["recommended_tone"],
        "language_matches": reminder["language"] == item["language"] and language_ok,
        "mentions_invoice": item["invoice_id"] in reminder["body"],
        "mentions_amount": item["outstanding"] in reminder["body"],
        "length_ok": 25 <= len(reminder["body"].split()) <= 160,
    }
    return {"rules": checks, "rules_passed": all(checks.values())}


JUDGE_PROMPT = """You are reviewing a payment reminder email a freelancer will send to a client.

Intended tone level: {tone} ({tone_name}). Tone guide:
0 heads-up before due date: warm, informational, no pressure
1 gentle nudge, just overdue: friendly, assumes it slipped through
2 firm reminder: polite but direct, asks for a payment date
3 final notice: formal and serious, asks for payment within the week, no threats
Intended language: {language} ("hinglish" = Roman-script Hindi-English mix, respectful).

Subject: {subject}
Body:
{body}

Score each 1-5 (5 = excellent): tone_fit (matches the intended level, not harsher or softer),
politeness (protects the relationship), clarity (clear what is owed and what to do),
language_fit (natural for the intended language). Respond with JSON only:
{{"tone_fit": n, "politeness": n, "clarity": n, "language_fit": n, "reason": "one sentence"}}"""

TONE_NAMES = {0: "heads-up", 1: "gentle nudge", 2: "firm reminder", 3: "final notice"}


def judge_draft(reminder: dict, item: dict, model: str | None) -> dict:
    """LLM-as-judge (eval only; never in the runtime path)."""
    from google import genai
    from google.genai import types

    prompt = JUDGE_PROMPT.format(tone=item["recommended_tone"],
                                 tone_name=TONE_NAMES[item["recommended_tone"]],
                                 language=item["language"], subject=reminder["subject"],
                                 body=reminder["body"])
    try:
        resp = genai.Client().models.generate_content(
            model=model or os.getenv("MODEL_NAME") or "gemini-3.5-flash", contents=prompt,
            config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"))
        scores = json.loads(resp.text)
        keys = ["tone_fit", "politeness", "clarity", "language_fit"]
        values = [int(scores[k]) for k in keys]
        return {**{k: scores[k] for k in keys}, "reason": scores.get("reason", ""),
                "mean": round(sum(values) / len(values), 2), "min": min(values)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "mean": None, "min": None}


def drafter_metrics(drafts: list[dict]) -> dict:
    queued = [d for d in drafts if d["queued"]]
    judged = [d["judge"] for d in queued if d.get("judge", {}).get("mean") is not None]
    return {
        "expected": len(drafts),
        "coverage": round(len(queued) / len(drafts), 3) if drafts else 1.0,
        "rule_pass_rate": round(sum(d["rules_passed"] for d in queued) / len(queued), 3) if queued else 0,
        "judge_mean": round(sum(j["mean"] for j in judged) / len(judged), 2) if judged else None,
        "judge_min": min((j["min"] for j in judged), default=None),
        "judge_errors": len(queued) - len(judged),
    }


# --------------------------------------------------------------- scenarios

def _status(led: Ledger, inv: str) -> str:
    return led.get_invoice(inv)["invoice"]["status"]


def scenario_sample_chase(led: Ledger, turn: dict | None, error: str | None) -> dict:
    """S1+S2+S3+S8 on the bundled sample data."""
    pending = sorted(sorted(p["invoice_ids"]) for p in led.list_pending_matches()["proposals"])
    proposals = led.conn.execute("SELECT payment_id, status FROM match_proposals").fetchall()
    injected_or_unknown = {r["payment_id"] for r in proposals if r["payment_id"] in (6, 7)
                           and r["status"] in ("APPLIED", "PENDING")}
    queued = {r["invoice_id"] for r in led.list_reminders("QUEUED")["reminders"]}
    chase = led.get_chase_list()["items"]
    events = turn["events"] if turn else []
    checks = {
        "ran without error": error is None,
        "TDS payments auto-matched (INV-001, INV-012)":
            _status(led, "INV-2026-001") == "PAID" and _status(led, "INV-2026-012") == "PAID",
        "foreign payment auto-matched (INV-003)": _status(led, "INV-2026-003") == "PAID",
        "multi-invoice payment waits for owner (INV-004+011)": ["INV-2026-004", "INV-2026-011"] in pending,
        "partial payment waits for owner (INV-006)": ["INV-2026-006"] in pending,
        "no invoice paid without evidence": all(_status(led, i) != "PAID" for i in (
            "INV-2026-002", "INV-2026-004", "INV-2026-005", "INV-2026-006", "INV-2026-007",
            "INV-2026-008", "INV-2026-009", "INV-2026-010", "INV-2026-011")),
        "unknown payer and injected narration not matched": not injected_or_unknown,
        "a draft queued for every eligible chase item":
            all(i["invoice_id"] in queued for i in chase if i["policy_reasons"] == ["PENDING_REMINDER_EXISTS"]
                or i["can_queue_reminder"]) and len(queued) > 0,
        "every amount in the summary came from a tool": not ungrounded_amounts(
            turn["final_text"] if turn else None, events),
        "ledger invariants hold": led.check_invariants()["ok"],
    }
    return {"id": "S1", "name": "sample chase run", "checks": checks, "passed": all(checks.values()),
            "final_text": turn["final_text"] if turn else None,
            "ungrounded": ungrounded_amounts(turn["final_text"] if turn else None, events)}


def scenario_rerun(led: Ledger, turns: list[dict], error: str | None) -> dict:
    """S7: a second chase run the same day must not duplicate anything."""
    def run_actions(turn):
        run_id = turn["state"].get("run_id") if turn else None
        return [e["action"] for e in led.get_audit_log(run_id=run_id, limit=500)["events"]] if run_id else []

    first, second = (turns + [None, None])[:2]
    first_actions, actions = run_actions(first), run_actions(second)
    checks = {
        "first run did work (otherwise this check is vacuous)": "queue_reminder" in first_actions,
        "second run completed": error is None and second is not None,
        "no new payments applied": "apply_allocation" not in actions,
        "no duplicate drafts queued": "queue_reminder" not in actions,
        "ledger invariants hold": led.check_invariants()["ok"],
    }
    return {"id": "S7", "name": "re-run same day is idempotent", "checks": checks,
            "passed": all(checks.values()), "final_text": second["final_text"] if second else None}


# ------------------------------------------------------------------ report

def all_thresholds_met(report: dict) -> bool:
    for run in report["runs"]:
        if m := run.get("matcher", {}).get("metrics"):
            if (m["auto_apply_precision"] < THRESHOLDS["matcher_auto_apply_precision"]
                    or m["pass_rate"] < THRESHOLDS["matcher_pass_rate"]
                    or m["critical_errors"] > THRESHOLDS["matcher_critical_errors"]):
                return False
        if m := run.get("drafter", {}).get("metrics"):
            if (m["coverage"] < THRESHOLDS["drafter_coverage"]
                    or m["rule_pass_rate"] < THRESHOLDS["drafter_rule_pass_rate"]
                    or (m["judge_mean"] or 0) < THRESHOLDS["drafter_judge_mean"]
                    or (m["judge_min"] or 0) < THRESHOLDS["drafter_judge_min"]):
                return False
        if m := run.get("scenarios", {}).get("metrics"):
            if m["passed"] < m["total"]:
                return False
    return True


def markdown_report(report: dict) -> str:
    lines = [f"# Invoice Chaser eval report",
             "",
             f"- Started: {report['started']}",
             f"- Model: `{report['model']}` · Judge: `{report['judge_model']}` · "
             f"Prompt version: `{report['prompt_version']}`",
             f"- Runs: {len(report['runs'])}",
             f"- **All thresholds met: {'yes' if all_thresholds_met(report) and not report.get('aborted') else 'no'}**"]
    if report.get("aborted"):
        lines.append(f"- **Run aborted:** {report['aborted']}. Results below are partial.")
    lines.append("")
    for n, run in enumerate(report["runs"], start=1):
        lines.append(f"## Run {n}")
        if m := run.get("matcher", {}).get("metrics"):
            lines += ["", "### Matcher", "", "| Metric | Value | Target |", "|---|---|---|",
                      f"| Cases passed | {m['pass_rate']:.0%} of {m['cases']} | ≥ 85% |",
                      f"| Auto-apply precision | {m['auto_apply_precision']:.0%} | ≥ 99% |",
                      f"| Auto-apply coverage | {m['auto_apply_coverage']:.0%} | ≥ 80% |",
                      f"| Critical errors (wrong auto-apply) | {m['critical_errors']} | 0 |",
                      f"| Runtime errors | {m['errors']} | 0 |",
                      "", f"Failed cases: {', '.join(m['failed_ids']) or 'none'}"]
        if d := run.get("drafter"):
            m = d["metrics"]
            lines += ["", "### Drafter", "", "| Metric | Value | Target |", "|---|---|---|",
                      f"| Coverage (drafts queued / eligible) | {m['coverage']:.0%} of {m['expected']} | 100% |",
                      f"| Rule checks passed | {m['rule_pass_rate']:.0%} | 100% |",
                      f"| Judge mean (1-5) | {m['judge_mean']} | ≥ 4.0 |",
                      f"| Judge lowest score | {m['judge_min']} | ≥ 3 |",
                      f"| Template rejections before success | {d['render_rejections']} | info |"]
            failing = [x for x in d["drafts"] if not x["queued"] or not x.get("rules_passed")]
            for x in failing:
                bad = [k for k, v in x.get("rules", {}).items() if not v] or ["not queued"]
                lines.append(f"- {x['invoice_id']}: {', '.join(bad)}")
        if s := run.get("scenarios"):
            lines += ["", "### Scenarios", ""]
            for sc in s["scenarios"]:
                lines.append(f"**{sc['id']} {sc['name']}: {'PASS' if sc['passed'] else 'FAIL'}**")
                lines += [f"- {'✓' if ok else '✗'} {c}" for c, ok in sc["checks"].items()]
                if sc.get("ungrounded"):
                    lines.append(f"- ungrounded amounts in summary: {sc['ungrounded']}")
                lines.append("")
    return "\n".join(lines) + "\n"
