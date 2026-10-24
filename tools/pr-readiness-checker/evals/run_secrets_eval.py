"""Secret-scanner eval: generated keys of every supported type plus look-alike decoys.

    python -m evals.run_secrets_eval [--per-type 50] [--seed 7] [--json out.json]

Targets (exit code 1 if missed):
  * recall 1.00 for every provider pattern - a missed key is the worst failure;
  * 0 error-level false positives on decoys;
  * generic heuristic: recall >= 0.90 and at most 2% warn-level false positives.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import uuid
from pathlib import Path

from prcheck.models import Severity
from prcheck.secret_patterns import scan

from . import fixtures as fx

GENERATORS = {
    "google_api_key": fx.fake_google_key,
    "openai_key": fx.fake_openai_key,
    "anthropic_key": fx.fake_anthropic_key,
    "github_token": fx.fake_github_token,
    "github_pat": fx.fake_github_pat,
    "aws_access_key": fx.fake_aws_key,
    "slack_token": fx.fake_slack_token,
    "huggingface_token": fx.fake_hf_token,
    "private_key": fx.fake_private_key,
}
# github_pat is reported under the github_token pattern id.
EXPECTED_ID = {"github_pat": "github_token"}

# Ways a key shows up in real files.
CONTEXTS = [
    'API_KEY = "{v}"',
    "export TOKEN={v}",
    "key: {v}",
    "client = Client(api_key='{v}')",
    "{v}",
    "| `KEY` | {v} |",
]

PLACEHOLDERS = ["your_api_key_here", "<your-key>", "changeme", "sk-...", "AIza...", "xxxxxxxxxxxxxxxxxxxx",
                "${GEMINI_API_KEY}", "os.getenv('API_KEY')", "process.env.OPENAI_API_KEY", "REPLACE_ME_WITH_KEY"]


def decoys(rng: random.Random, n: int) -> list[str]:
    items: list[str] = []
    for _ in range(n):
        items += [
            f'commit = "{"".join(rng.choice("0123456789abcdef") for _ in range(40))}"',
            f'run_id = "{uuid.UUID(int=rng.getrandbits(128))}"',
            f"sha256 = {''.join(rng.choice('0123456789abcdef') for _ in range(64))}",
            f'image = "data:image/png;base64,{"".join(rng.choice(fx.ALNUM + "+/") for _ in range(60))}"',
            f"token_count = {rng.randint(10**15, 10**18)}",
            f"risk-{''.join(rng.choice(string.ascii_lowercase) for _ in range(30))}-report",
            f"api_key = {rng.choice(PLACEHOLDERS)!r}",
            f"password_hint = 'use the {rng.choice(['blue', 'red'])} notebook'",
            # Clearly-not-real values seen in PRs #17, #33, #42, #43, #48: info at most, never error/warn.
            'AWS_ACCESS_KEY_ID = "' + "AKIA" + 'IOSFODNN7EXAMPLE"',
            'TOKEN = "' + "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123456789" + '"',
            'SLACK = "' + "xo" + "xb-" + "123456789012-abcdefghijklmnop" + '"',
            'HEADER = "' + "-----BEGIN " + "RSA PRIVATE KEY-----" + '"',
            'const API_KEY = "super-secret-api-key-' + str(rng.randint(100, 999)) + '";',
        ]
    return items


def generic_positives(rng: random.Random, n: int) -> list[str]:
    names = ["db_password", "SECRET", "auth_token", "client_secret", "ACCESS_KEY", "stripeApiKey"]
    return [f'{rng.choice(names)} = "{fx.fake_generic_secret(rng)}"' for _ in range(n)]


def evaluate(per_type: int = 50, seed: int = 7) -> dict:
    rng = random.Random(seed)
    results: dict[str, dict] = {}
    for kind, make in GENERATORS.items():
        expected_id = EXPECTED_ID.get(kind, kind)
        hits = 0
        misses: list[str] = []
        for i in range(per_type):
            value = make(rng)
            line = CONTEXTS[i % len(CONTEXTS)].format(v=value)
            ids = {m.pattern_id for m in scan(line)}
            if expected_id in ids:
                hits += 1
            else:
                misses.append(line[:40] + "...")
        results[kind] = {"total": per_type, "detected": hits, "recall": hits / per_type, "misses": misses[:3]}

    generic = generic_positives(rng, per_type)
    generic_hits = sum(any(m.pattern_id == "generic_secret" for m in scan(line)) for line in generic)

    decoy_lines = decoys(rng, per_type)
    error_fps, warn_fps = [], []
    for line in decoy_lines:
        for m in scan(line):
            if m.severity is Severity.ERROR:
                error_fps.append(line[:60])
            elif m.severity is Severity.WARN:
                warn_fps.append(line[:60])

    return {
        "providers": results,
        "generic": {"total": len(generic), "detected": generic_hits, "recall": generic_hits / len(generic)},
        "decoys": {"total": len(decoy_lines), "error_false_positives": len(error_fps),
                   "warn_false_positives": len(warn_fps), "examples": (error_fps + warn_fps)[:5]},
    }


def passes(result: dict) -> bool:
    providers_ok = all(r["recall"] == 1.0 for r in result["providers"].values())
    decoys = result["decoys"]
    return (providers_ok and decoys["error_false_positives"] == 0
            and result["generic"]["recall"] >= 0.90
            and decoys["warn_false_positives"] <= 0.02 * decoys["total"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-type", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    result = evaluate(args.per_type, args.seed)
    print("Secret-scanner eval\n")
    print(f"  {'pattern':<20} detected  recall")
    for kind, r in result["providers"].items():
        print(f"  {kind:<20} {r['detected']:>4}/{r['total']:<4} {r['recall']:5.2f}")
        for miss in r["misses"]:
            print(f"      missed: {miss}")
    g = result["generic"]
    print(f"  {'generic (warn)':<20} {g['detected']:>4}/{g['total']:<4} {g['recall']:5.2f}")
    d = result["decoys"]
    print(f"\n  decoys: {d['total']} lines, {d['error_false_positives']} error FP, {d['warn_false_positives']} warn FP")
    for example in d["examples"]:
        print(f"      flagged: {example}")
    ok = passes(result)
    print(f"\nResult: {'PASS' if ok else 'FAIL'}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
