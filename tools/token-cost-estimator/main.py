import argparse
import json
import sys
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

MODELS = {
    "gemini-3.8-flash": {
        "input": 0.10,
        "output": 0.40,
        "supports_count_tokens": True,
    },
    "gemini-3.8-flash-lite": {
        "input": 0.075,
        "output": 0.30,
        "supports_count_tokens": False,
    },
}

PRICE_PER_MILLION = 1_000_000


def count_tokens(prompt: str, model: str) -> int:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)
    client = genai.Client(api_key=api_key)
    if MODELS[model]["supports_count_tokens"]:
        result = client.models.count_tokens(model=model, contents=prompt)
        return result.total_tokens
    fallback = next(m for m, v in MODELS.items() if v["supports_count_tokens"])
    result = client.models.count_tokens(model=fallback, contents=prompt)
    return result.total_tokens


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> dict:
    pricing = MODELS[model]
    input_cost = (input_tokens / PRICE_PER_MILLION) * pricing["input"]
    output_cost = (output_tokens / PRICE_PER_MILLION) * pricing["output"]
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
    }


def build_result(prompt: str, model: str, output_tokens: int) -> dict:
    input_tokens = count_tokens(prompt, model)
    costs = estimate_cost(input_tokens, output_tokens, model)
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": round(costs["input_cost"], 6),
        "output_cost": round(costs["output_cost"], 6),
        "total_cost": round(costs["total_cost"], 6),
    }


def print_report(result: dict, budget: float | None = None):
    print(f"\nModel    : {result['model']}")
    print("-" * 50)
    print(f"Input tokens   : {result['input_tokens']:,}")
    print(f"Output tokens  : {result['output_tokens']:,} (estimated)")
    print(f"Input cost     : ${result['input_cost']:.6f}")
    print(f"Output cost    : ${result['output_cost']:.6f}")
    print(f"Total cost     : ${result['total_cost']:.6f}")
    if budget is not None:
        if result["total_cost"] > budget:
            print(f"WARNING: Estimated cost ${result['total_cost']:.6f} exceeds budget of ${budget:.6f}")
        else:
            print(f"OK: Estimated cost is within budget of ${budget:.6f}")
    print("-" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Estimate token count and API cost for a prompt using Gemini models."
    )
    parser.add_argument("prompt", nargs="?", help="The prompt text to estimate")
    parser.add_argument("--file", "-f", help="Path to a file containing the prompt text")
    parser.add_argument(
        "--model", "-m",
        default="gemini-3.8-flash",
        choices=list(MODELS.keys()),
        help="Gemini model to use for estimation (default: gemini-3.8-flash)",
    )
    parser.add_argument(
        "--output-tokens", "-o",
        type=int,
        default=500,
        help="Estimated number of output tokens (default: 500)",
    )
    parser.add_argument("--all-models", "-a", action="store_true", help="Show cost estimate across all supported models")
    parser.add_argument("--list-models", action="store_true", help="List all supported models and their pricing")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--budget", "-b", type=float, help="Warn if estimated total cost exceeds this amount in USD")

    args = parser.parse_args()

    if args.list_models:
        print("\nSupported models and pricing (per 1M tokens):\n")
        print(f"{'Model':<30} {'Input':>10} {'Output':>10}  {'Token Count API'}")
        print("-" * 65)
        for name, price in MODELS.items():
            fallback = next(m for m, v in MODELS.items() if v["supports_count_tokens"])
            native = "native" if price["supports_count_tokens"] else f"via {fallback}"
            print(f"{name:<30} ${price['input']:>8.3f} ${price['output']:>8.3f}  {native}")
        print()
        sys.exit(0)

    if args.file:
        try:
            with open(args.file, "r") as f:
                prompt = f.read()
        except FileNotFoundError:
            print(f"Error: File '{args.file}' not found.")
            sys.exit(1)
    elif args.prompt:
        prompt = args.prompt
    else:
        print("Reading prompt from stdin (Ctrl+D to finish):")
        prompt = sys.stdin.read()

    if not prompt.strip():
        print("Error: Prompt is empty.")
        sys.exit(1)

    budget_exceeded = False

    if args.all_models:
        results = [build_result(prompt, model, args.output_tokens) for model in MODELS]
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for result in results:
                print_report(result, args.budget)
            if args.budget:
                budget_exceeded = any(r["total_cost"] > args.budget for r in results)
    else:
        result = build_result(prompt, args.model, args.output_tokens)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_report(result, args.budget)
            if args.budget:
                budget_exceeded = result["total_cost"] > args.budget

    if budget_exceeded:
        sys.exit(1)


if __name__ == "__main__":
    main()
