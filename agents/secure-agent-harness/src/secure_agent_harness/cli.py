"""Small interactive command-line interface."""
from .agent import SecureAgent
from .config import Settings
from .guardrails import GuardrailViolation


def main() -> None:
    settings = Settings.from_env()
    try:
        agent = SecureAgent(settings)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print("Secure Agent Harness (type 'exit' to quit; do not enter secrets)")
    while True:
        try:
            request = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if request.casefold() in {"exit", "quit"}:
            print("Bye.")
            break
        try:
            result = agent.run(request)
            print(f"\nAgent> {result.answer}")
            print(
                f"[steps={result.steps}, tools={result.tool_calls}, "
                f"estimated_cost=${result.estimated_cost_usd:.6f}]"
            )
            for warning in result.warnings:
                print(f"Warning: {warning}")
        except (GuardrailViolation, RuntimeError, ValueError) as exc:
            print(f"Request stopped: {exc}")
