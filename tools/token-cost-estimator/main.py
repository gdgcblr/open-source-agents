import argparse
import json
import sys
import os
import glob
from dotenv import load_dotenv

load_dotenv()

PRICE_PER_MILLION = 1_000_000
TOKEN_BREAKDOWN_THRESHOLD = 1000

GEMINI_MODELS = {
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

OPENAI_MODELS = {
    "gpt-4o": {
        "input": 2.50,
        "output": 10.00,
        "encoding": "o200k_base",
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60,
        "encoding": "o200k_base",
    },
    "gpt-4-turbo": {
        "input": 10.00,
        "output": 30.00,
        "encoding": "cl100k_base",
    },
    "gpt-3.5-turbo": {
        "input": 0.50,
        "output": 1.50,
        "encoding": "cl100k_base",
    },
}

ALL_MODELS = {
    **{f"gemini/{k}": v for k, v in GEMINI_MODELS.items()},
    **{f"openai/{k}": v for k, v in OPENAI_MODELS.items()},
}


def count_tokens_gemini(prompt: str, model_key: str) -> int:
    from google import genai
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)
    client = genai.Client(api_key=api_key)
    model_info = GEMINI_MODELS[model_key]
    if model_info["supports_count_tokens"]:
        result = client.models.count_tokens(model=model_key, contents=prompt)
        return result.total_tokens
    fallback = next(m for m, v in GEMINI_MODELS.items() if v["supports_count_tokens"])
    result = client.models.count_tokens(model=fallback, contents=prompt)
    return result.total_tokens


def count_tokens_openai(prompt: str, model_key: str) -> int:
    try:
        import tiktoken
    except ImportError:
        print("Error: tiktoken not installed. Run: pip install tiktoken")
        sys.exit(1)
    encoding_name = OPENAI_MODELS[model_key]["encoding"]
    enc = tiktoken.get_encoding(encoding_name)
    return len(enc.encode(prompt))


def count_tokens(prompt: str, provider: str, model_key: str) -> int:
    if provider == "gemini":
        return count_tokens_gemini(prompt, model_key)
    if provider == "openai":
        return count_tokens_openai(prompt, model_key)
    print(f"Error: Unknown provider '{provider}'.")
    sys.exit(1)


def estimate_cost(input_tokens: int, output_tokens: int, provider: str, model_key: str) -> dict:
    models = GEMINI_MODELS if provider == "gemini" else OPENAI_MODELS
    pricing = models[model_key]
    input_cost = (input_tokens / PRICE_PER_MILLION) * pricing["input"]
    output_cost = (output_tokens / PRICE_PER_MILLION) * pricing["output"]
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
    }


def build_result(prompt: str, provider: str, model_key: str, output_tokens: int) -> dict:
    input_tokens = count_tokens(prompt, provider, model_key)
    costs = estimate_cost(input_tokens, output_tokens, provider, model_key)
    result = {
        "provider": provider,
        "model": model_key,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": round(costs["input_cost"], 6),
        "output_cost": round(costs["output_cost"], 6),
        "total_cost": round(costs["total_cost"], 6),
    }
    if input_tokens >= TOKEN_BREAKDOWN_THRESHOLD:
        result["breakdown"] = {
            "characters": len(prompt),
            "words": len(prompt.split()),
            "tokens": input_tokens,
        }
    return result


def print_breakdown(result: dict):
    if "breakdown" in result:
        b = result["breakdown"]
        print(f"  Prompt breakdown (large prompt detected):")
        print(f"    Characters : {b['characters']:,}")
        print(f"    Words      : {b['words']:,}")
        print(f"    Tokens     : {b['tokens']:,}")


def print_report(result: dict, budget: float | None = None):
    print(f"\nProvider : {result['provider']}")
    print(f"Model    : {result['model']}")
    print("-" * 50)
    print_breakdown(result)
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


def run_batch(folder: str, provider: str, model_key: str, output_tokens: int, budget: float | None, as_json: bool):
    pattern = os.path.join(folder, "*.txt")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"Error: No .txt files found in '{folder}'.")
        sys.exit(1)

    print(f"\nBatch mode — processing {len(files)} file(s) from '{folder}'\n")

    batch_results = []
    total_input_tokens = 0
    total_cost = 0.0

    for filepath in files:
        with open(filepath, "r") as f:
            prompt = f.read()
        if not prompt.strip():
            print(f"  Skipping empty file: {os.path.basename(filepath)}")
            continue
        result = build_result(prompt, provider, model_key, output_tokens)
        result["file"] = os.path.basename(filepath)
        batch_results.append(result)
        total_input_tokens += result["input_tokens"]
        total_cost += result["total_cost"]

    if as_json:
        summary = {
            "provider": provider,
            "model": model_key,
            "files_processed": len(batch_results),
            "total_input_tokens": total_input_tokens,
            "total_estimated_cost": round(total_cost, 6),
            "results": batch_results,
        }
        print(json.dumps(summary, indent=2))
    else:
        for result in batch_results:
            print(f"File: {result['file']}")
            print_report(result, budget)
        print(f"\n{'=' * 50}")
        print(f"BATCH SUMMARY")
        print(f"{'=' * 50}")
        print(f"Files processed   : {len(batch_results)}")
        print(f"Total input tokens: {total_input_tokens:,}")
        print(f"Total est. cost   : ${total_cost:.6f}")
        if budget is not None:
            if total_cost > budget:
                print(f"WARNING: Total batch cost ${total_cost:.6f} exceeds budget of ${budget:.6f}")
            else:
                print(f"OK: Total batch cost is within budget of ${budget:.6f}")
        print(f"{'=' * 50}\n")

    if budget and total_cost > budget:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Estimate token count and API cost for a prompt. Supports Gemini and OpenAI models."
    )
    parser.add_argument("prompt", nargs="?", help="The prompt text to estimate")
    parser.add_argument("--file", "-f", help="Path to a file containing the prompt text")
    parser.add_argument("--batch", help="Path to a folder of .txt files to estimate in bulk")
    parser.add_argument(
        "--provider", "-p",
        default="gemini",
        choices=["gemini", "openai"],
        help="LLM provider to use (default: gemini)",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="Model name (default: gemini-3.8-flash for Gemini, gpt-4o-mini for OpenAI)",
    )
    parser.add_argument(
        "--output-tokens", "-o",
        type=int,
        default=500,
        help="Estimated number of output tokens per prompt (default: 500)",
    )
    parser.add_argument("--all-models", "-a", action="store_true", help="Show cost estimate across all models for the selected provider")
    parser.add_argument("--list-models", action="store_true", help="List all supported models and their pricing")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--budget", "-b", type=float, help="Warn if estimated total cost exceeds this amount in USD")

    args = parser.parse_args()

    # set default model per provider
    if args.model is None:
        args.model = "gemini-3.8-flash" if args.provider == "gemini" else "gpt-4o-mini"

    # validate model for provider
    models_for_provider = GEMINI_MODELS if args.provider == "gemini" else OPENAI_MODELS
    if args.model not in models_for_provider:
        valid = ", ".join(models_for_provider.keys())
        print(f"Error: Model '{args.model}' not available for provider '{args.provider}'. Valid: {valid}")
        sys.exit(1)

    if args.list_models:
        print("\n--- Gemini models (requires GEMINI_API_KEY) ---\n")
        print(f"{'Model':<25} {'Input':>10} {'Output':>10}  {'Token Count'}")
        print("-" * 60)
        for name, price in GEMINI_MODELS.items():
            fallback = next(m for m, v in GEMINI_MODELS.items() if v["supports_count_tokens"])
            native = "API (native)" if price["supports_count_tokens"] else f"API (via {fallback})"
            print(f"{name:<25} ${price['input']:>8.3f} ${price['output']:>8.3f}  {native}")

        print("\n--- OpenAI models (no API key needed — local tiktoken) ---\n")
        print(f"{'Model':<25} {'Input':>10} {'Output':>10}  {'Token Count'}")
        print("-" * 60)
        for name, price in OPENAI_MODELS.items():
            print(f"{name:<25} ${price['input']:>8.3f} ${price['output']:>8.3f}  local (tiktoken)")
        print()
        sys.exit(0)

    if args.batch:
        run_batch(args.batch, args.provider, args.model, args.output_tokens, args.budget, args.json)
        return

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
        results = [
            build_result(prompt, args.provider, m, args.output_tokens)
            for m in models_for_provider
        ]
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for result in results:
                print_report(result, args.budget)
            if args.budget:
                budget_exceeded = any(r["total_cost"] > args.budget for r in results)
    else:
        result = build_result(prompt, args.provider, args.model, args.output_tokens)
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
