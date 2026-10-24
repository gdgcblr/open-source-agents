"""Small, reproducible synthetic retrieval evaluation; no server or cloud calls."""
import argparse
import json
from pathlib import Path
import statistics
import time

from agent import run_agent
from importer import read_xlsx
from nlp import LocalEncoder

CASES = [
    ("I want to know how I can start contributing to open source", {"P011", "P012"}),
    ("I need help with my first pull request", {"P011", "P012"}),
    ("I want to put my app online", {"P003"}),
    ("I want to run AI offline", {"P006"}),
    ("Docker", {"P003"}),
    ("I am working on a campus map", {"P016"}),
    ("I need help with documentation", {"P011"}),
    ("I need help with a screen reader", {"P002", "P005"}),
    ("I want to build a mobile app", {"P002", "P015"}),
    ("quantum spectroscopy", set()),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", help="Optional installed MiniLM directory")
    args = parser.parse_args()
    encoder = LocalEncoder(args.model_dir)
    profiles, _ = read_xlsx((Path(__file__).parent / "sample/form-responses.xlsx").read_bytes())
    profiles = [{**p, "spot": "", "until_ts": 0, "checked_at": 0} for p in profiles]
    me = profiles[0]
    rows = []
    for query, expected in CASES:
        result = run_agent(me, profiles, query, "", set(), False, time.time(), encoder)
        returned = [p["id"] for p in result["matches"]]
        passed = expected.issubset(returned) if expected else not returned
        rows.append({"query": query, "expected_ids": sorted(expected), "returned_ids": returned,
                     "passed": passed, "latency_ms": result["latency_ms"]})
    large = [{**profiles[i % len(profiles)], "id": f"E{i:03}", "name": f"Synthetic {i}"}
             for i in range(200)]
    durations = []
    for _ in range(10):
        start = time.perf_counter()
        run_agent(large[0], large, CASES[0][0], "", set(), False, time.time(), encoder)
        durations.append((time.perf_counter() - start) * 1000)
    report = {
        "engine": "local semantic NLP" if encoder.available else "local lexical NLP",
        "warning": encoder.error,
        "passed": sum(row["passed"] for row in rows), "cases": len(rows), "results": rows,
        "200_profiles_10_sequential_searches": {
            "median_ms": round(statistics.median(durations), 2), "max_ms": round(max(durations), 2)},
        "limitations": "Curated synthetic checks, not a held-out benchmark or 200 concurrent users. No live Gemini test."
    }
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all(row["passed"] for row in rows) else 1)


if __name__ == "__main__":
    main()
