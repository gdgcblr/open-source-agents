import argparse
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

COUNT_TOKENS_MODEL = "gemini-3.8-flash"

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
    # Fallback: use the supported model to count tokens (tokenizers are compatible)
    result = client.models.count_tokens(model=COUNT_TOKENS_MODEL, contents=prompt)
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


def print_report(prompt: str, model: str, output_tokens: int):
    print(f"\nModel    : {model}")
    print(f"Prompt   : {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
    print("-" * 50)

    input_tokens = count_tokens(prompt, model)
    costs = estimate_cost(input_tokens, output_tokens, model)

    print(f"Input tokens   : {input_tokens:,}")
    print(f"Output tokens  : {output_tokens:,} (estimated)")
    print(f"Input cost     : ${costs['input_cost']:.6f}")
    print(f"Output cost    : ${costs['output_cost']:.6f}")
    print(f"Total cost     : ${costs['total_cost']:.6f}")
    print("-" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Estimate token count and API cost for a prompt using Gemini models."
    )
    parser.add_argument("prompt", nargs="?", help="The prompt text to estimate")
    parser.add_argument(
        "--file", "-f", help="Path to a file containing the prompt text"
    )
    parser.add_argument(
        "--model",
        "-m",
        default="gemini-3.8-flash",
        choices=list(MODELS.keys()),
        help="Gemini model to use for estimation (default: gemini-3.8-flash)",
    )
    parser.add_argument(
        "--output-tokens",
        "-o",
        type=int,
        default=500,
        help="Estimated number of output tokens (default: 500)",
    )
    parser.add_argument(
        "--all-models",
        "-a",
        action="store_true",
        help="Show cost estimate across all supported models",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all supported models and their pricing",
    )

    args = parser.parse_args()

    if args.list_models:
        print("\nSupported models and pricing (per 1M tokens):\n")
        print(f"{'Model':<30} {'Input':>10} {'Output':>10}  {'Token Count API'}")
        print("-" * 65)
        for name, price in MODELS.items():
            native = "native" if price["supports_count_tokens"] else "via gemini-3.8-flash"
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

    if args.all_models:
        for model in MODELS:
            print_report(prompt, model, args.output_tokens)
    else:
        print_report(prompt, args.model, args.output_tokens)


if __name__ == "__main__":
    main()
