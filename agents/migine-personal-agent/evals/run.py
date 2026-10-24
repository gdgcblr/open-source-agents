"""Live extraction evaluation. Uses synthetic text only; never opens Mac apps."""

import json
import platform
import time
from decimal import Decimal
from pathlib import Path

from migine.config import Settings
from migine.ollama import Ollama


def main():
    settings = Settings.load()
    model = Ollama(settings)
    results = []
    for line in Path(__file__).with_name("cases.jsonl").read_text().splitlines():
        case = json.loads(line)
        start = time.monotonic()
        try:
            actual = [
                r.model_dump(mode="json")
                for r in model.extract(
                    {
                        "title": "Synthetic evaluation",
                        "body": case["body"],
                        "received": "2026-10-24",
                        "id": case["id"],
                    }
                )
            ]
            grounded = all(r["evidence"] in case["body"] for r in actual)
            passed = grounded and len(actual) == len(case["expected"])
            for expected, record in zip(case["expected"], actual):
                for key, value in expected.items():
                    passed &= (
                        Decimal(record[key]) == Decimal(value)
                        if key == "amount"
                        else record[key] == value
                    )
            error = None
        except Exception as exc:  # noqa: BLE001 -- Record a failed case and continue the evaluation.
            actual, passed, error = [], False, type(exc).__name__
        results.append(
            {
                "case": case["id"],
                "passed": bool(passed),
                "actual": actual,
                "seconds": round(time.monotonic() - start, 2),
                "error": error,
            }
        )
    report = {
        "model": settings.chat_model,
        "machine": platform.machine(),
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "results": results,
    }
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
