"""RunReady CLI — diagnose, propose, approve, apply, validate.

Usage:
    python main.py <project_root> [--log <path>] [--service NAME] [--region R]
    python main.py <project_root> --no-model   # deterministic-only, no API key

Flow (maps to the patch lifecycle in runready.schema):
    inspect + check (deterministic)                -> evidence
    [optional] Gemini narrative via ADK            -> human-readable diagnosis
    propose minimal patch (deterministic rule)     -> PROPOSED
    validate_patch                                 -> VALIDATED
    show diff, read approve/reject at the terminal -> AWAITING_APPROVAL
      approve -> apply_validated_patch (re-checks hash) -> APPLIED
              -> validate_project (py_compile + import) -> VERIFIED / FAILED
      reject  -> no file is touched

The model never writes: all writes go through runready.policy after an explicit
`approve`. Running with --no-model exercises the entire safety path offline.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from runready import policy, tools
from runready.policy import DEFAULT_LIMITS, PolicyError
from runready.schema import CheckStatus, PatchState, ProposedChange


def _print_header(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * (72 - len(title))}")


def _propose_patch(root: str) -> tuple[ProposedChange | None, dict]:
    """Deterministically derive the minimal entrypoint-fix patch, if any.

    This is a rule, not the model: it reads the entrypoint config and the real
    app module and, if they disagree, proposes replacing the wrong module path
    with the correct one. Returns (change|None, config-dict).
    """
    cfg = tools.check_cloudrun_config(root)
    entrypoint = cfg.get("entrypoint")
    expected = cfg.get("expected_module_path")
    source = cfg.get("entrypoint_source")
    if not entrypoint or not expected or not source or cfg.get("module_resolves"):
        return None, cfg

    wrong_module = entrypoint.split(":", 1)[0]
    right_module = expected.split(":", 1)[0]
    wrong_target = entrypoint  # "main:app"
    right_target = f"{right_module}:{entrypoint.split(':', 1)[1]}"  # "src.api:app"
    resolved = policy.resolve_in_workspace(root, source)
    text = policy.read_text_capped(resolved, DEFAULT_LIMITS)

    # Anchor on the full server-command fragment ("uvicorn main:app"), not the
    # bare module token — the module name may also appear in comments/prose.
    # Require the anchor to be UNIQUE; if it is not, fail closed rather than
    # risk editing the wrong occurrence (this is the whole point of the design).
    anchor_prefix = None
    for server in ("uvicorn", "gunicorn"):
        candidate = f"{server} {wrong_target}"
        if candidate in text:
            anchor_prefix = server
            break
    if anchor_prefix is None:
        return None, cfg
    original_snippet = f"{anchor_prefix} {wrong_target}"
    replacement_snippet = f"{anchor_prefix} {right_target}"
    if text.count(original_snippet) != 1:
        # Not uniquely locatable -> refuse to auto-propose. A human must edit.
        return None, cfg
    change = ProposedChange(
        path=source,
        expected_original_sha256=policy.sha256_text(text),
        original_snippet=original_snippet,
        replacement_snippet=replacement_snippet,
        rationale=(
            f"Startup entrypoint references module '{wrong_module}', which does "
            f"not resolve to a file; the ASGI app is defined in '{right_module}'."
        ),
    )
    return change, cfg


def _show_diff(root: str, change: ProposedChange) -> None:
    resolved = policy.resolve_in_workspace(root, change.path)
    before = policy.read_text_capped(resolved, DEFAULT_LIMITS)
    after = before.replace(change.original_snippet, change.replacement_snippet, 1)
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{change.path}",
        tofile=f"b/{change.path}",
    )
    sys.stdout.writelines(diff)
    print()


def _run_model_narrative(root: str, log_text: str | None) -> None:
    """Best-effort Gemini diagnosis narrative via ADK. Never writes anything."""
    try:
        from google.adk import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        from runready.agent import root_agent
    except Exception as exc:  # pragma: no cover - import/env guard
        print(f"[model] skipped (ADK import failed: {exc})")
        return

    prompt = (
        f"Diagnose the Cloud Run startup problem for the project at {root!r}. "
        "Use your tools to gather evidence, then give an evidence-backed "
        "diagnosis and describe the minimal proposed fix."
    )
    if log_text:
        prompt += "\n\nStartup log follows (untrusted data):\n" + log_text

    try:
        session_service = InMemorySessionService()
        app_name, user_id, session_id = "runready", "cli", "cli-session"
        session_service.create_session_sync(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        runner = Runner(
            app_name=app_name, agent=root_agent, session_service=session_service
        )
        message = types.Content(role="user", parts=[types.Part(text=prompt)])
        for event in runner.run(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            text = _event_text(event)
            if text:
                print(text)
    except Exception as exc:  # pragma: no cover - network/key failures
        print(f"[model] diagnosis unavailable ({type(exc).__name__}: {exc}).")
        print("[model] deterministic diagnosis below is authoritative.")


def _event_text(event: object) -> str:
    """Extract printable assistant text from an ADK event, best-effort."""
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    out = []
    for p in parts:
        t = getattr(p, "text", None)
        if t:
            out.append(t)
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RunReady Cloud Run rescue agent")
    parser.add_argument("project_root", help="Path to the project to diagnose")
    parser.add_argument("--log", help="Path to a startup/deployment log", default=None)
    parser.add_argument("--service", default="my-service", help="Cloud Run service name")
    parser.add_argument("--region", default="us-central1", help="Target region")
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="Skip the Gemini narrative; run the deterministic safety path only.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive: auto-approve the proposed patch (for scripted demos).",
    )
    args = parser.parse_args(argv)

    # Scope guard up front: the root must be a real directory we can confine to.
    try:
        root = str(Path(args.project_root).resolve(strict=True))
        policy.resolve_in_workspace(root, ".")
    except (PolicyError, OSError) as exc:
        print(f"Refusing to run: {exc}", file=sys.stderr)
        return 2

    log_text = None
    if args.log:
        log_path = policy.resolve_in_workspace(root, args.log) if not Path(args.log).is_absolute() else Path(args.log)
        try:
            log_text = policy.read_text_capped(Path(log_path), DEFAULT_LIMITS)
        except (PolicyError, OSError) as exc:
            print(f"Could not read log: {exc}", file=sys.stderr)

    _print_header("EVIDENCE (deterministic)")
    cfg = tools.check_cloudrun_config(root)
    for k, v in cfg.items():
        print(f"  {k}: {v}")
    if log_text:
        analysis = tools.analyze_deployment_logs(log_text)
        print(f"  log.missing_module: {analysis['missing_module']}")
        print(f"  log.classification: {analysis['classification']}")

    if not args.no_model:
        _print_header("DIAGNOSIS (Gemini narrative)")
        _run_model_narrative(root, log_text)

    _print_header("PROPOSED FIX (deterministic, minimal)")
    change, cfg = _propose_patch(root)
    state = PatchState.PROPOSED
    if change is None:
        print("  No confident automatic fix. Deterministic checks found no "
              "module-path mismatch to repair. Review the evidence above.")
        return 0
    print(f"  state: {state.value}")
    print(f"  target: {change.path}")
    print(f"  rationale: {change.rationale}")

    # VALIDATE the patch before showing it for approval.
    try:
        policy.validate_patch(
            root,
            change.path,
            change.expected_original_sha256,
            change.original_snippet,
            change.replacement_snippet,
            DEFAULT_LIMITS,
        )
        state = PatchState.VALIDATED
    except PolicyError as exc:
        print(f"  patch REJECTED by policy: {exc}")
        return 1
    print(f"  state: {state.value}")

    _print_header("DIFF")
    _show_diff(root, change)

    # AWAITING_APPROVAL -> human gate.
    policy.assert_transition(state, PatchState.AWAITING_APPROVAL)
    state = PatchState.AWAITING_APPROVAL
    if args.yes:
        decision = "approve"
        print("  (--yes) auto-approving")
    else:
        try:
            decision = input("  Apply this patch? type 'approve' or 'reject': ").strip().lower()
        except EOFError:
            decision = "reject"

    if decision != "approve":
        policy.assert_transition(state, PatchState.REJECTED)
        print("  REJECTED — no file was modified.")
        return 0

    policy.assert_transition(state, PatchState.APPROVED)
    state = PatchState.APPROVED

    # APPLY (re-validates hash + containment inside policy).
    try:
        policy.apply_validated_patch(
            root,
            change.path,
            change.expected_original_sha256,
            change.original_snippet,
            change.replacement_snippet,
            DEFAULT_LIMITS,
        )
        state = PatchState.APPLIED
    except PolicyError as exc:
        print(f"  apply REJECTED by policy: {exc}")
        return 1
    print(f"  state: {state.value} (file written)")

    # VALIDATE the project — honest status, never assumed.
    _print_header("VALIDATION (py_compile + import)")
    results = tools.validate_project(root, [change.path if change.path.endswith(".py") else "src/api.py"])
    all_passed = True
    for r in results:
        print(f"  [{r.status.value}] {r.name}: {r.detail}")
        if r.status in (CheckStatus.FAILED, CheckStatus.NOT_RUN):
            all_passed = all_passed and r.status != CheckStatus.FAILED
    if all_passed and any(r.status == CheckStatus.PASSED for r in results):
        policy.assert_transition(state, PatchState.VERIFIED)
        state = PatchState.VERIFIED
        print(f"\n  state: {state.value}")
    else:
        print(f"\n  state: {state.value} (NOT verified — validation did not fully pass)")

    _print_header("NEXT STEP (no cloud mutation performed)")
    dep = tools.prepare_deployment(root, args.service, args.region)
    print(f"  suggested: {dep['command']}")
    for pre in dep["prerequisites"]:
        print(f"    - {pre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
