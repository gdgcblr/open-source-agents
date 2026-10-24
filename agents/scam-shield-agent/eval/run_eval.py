"""Measures Scam Shield accuracy on the labelled dataset.

    python eval/run_eval.py --mode rules   # offline rule engine, no API key needed
    python eval/run_eval.py --mode agent   # full Gemini multi-agent pipeline (needs GOOGLE_API_KEY)
    python eval/run_eval.py --dataset eval/heldout.jsonl   # any JSONL file of {"label", "text"}

A message counts as flagged when the verdict is "scam" or "suspicious".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Messages include Indian scripts; the Windows console defaults to cp1252.
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")


async def main(mode: str, delay: float, dataset: Path) -> None:
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if mode == "agent":
        from server import run_agent

        async def predict(text: str) -> str:
            return (await run_agent(text, None, "image/jpeg", "en", False))["verdict"]
    else:
        from scam_shield.tools import rules_verdict

        async def predict(text: str) -> str:
            return rules_verdict(text, follow_shorteners=False)["verdict"]

    tp = fp = tn = fn = 0
    started = time.perf_counter()
    for row in rows:
        verdict = await predict(row["text"])
        flagged = verdict in ("scam", "suspicious")
        is_scam = row["label"] == "scam"
        tp += flagged and is_scam
        fp += flagged and not is_scam
        tn += not flagged and not is_scam
        fn += not flagged and is_scam
        if flagged != is_scam:
            print(f"MISS  expected={row['label']:<5} got={verdict:<10} {row['text'][:70]}")
        if delay:
            await asyncio.sleep(delay)

    total = len(rows)
    print(f"\nMode: {mode}   Dataset: {dataset.name}   Messages: {total}   Time: {time.perf_counter() - started:.1f}s")
    print(f"Accuracy:  {(tp + tn) / total:.1%}")
    print(f"Scams caught (recall):        {tp}/{tp + fn} = {tp / max(tp + fn, 1):.1%}")
    print(f"Flags that were right (precision): {tp}/{tp + fp} = {tp / max(tp + fp, 1):.1%}")
    print(f"Safe messages wrongly flagged: {fp}/{fp + tn}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rules", "agent"], default="rules")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between calls (free-tier rate limits)")
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval" / "dataset.jsonl",
                        help="JSONL file with one {\"label\": \"scam\"|\"safe\", \"text\": ...} per line")
    args = parser.parse_args()
    asyncio.run(main(args.mode, args.delay, args.dataset))
