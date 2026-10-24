import argparse, json, sys
from dataclasses import asdict
from pathlib import Path
from .rules import run_all

def main():
    ap = argparse.ArgumentParser(description="Check a contribution folder")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    results = run_all(Path(args.path).resolve())
    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        for r in results:
            print(f"[{'PASS' if r.passed else 'FAIL'}] {r.rule}: {r.message}")
            if not r.passed and r.fix:
                print(f"        fix: {r.fix}")
        print(f"\n{sum(r.passed for r in results)}/{len(results)} checks passed")
    sys.exit(0 if all(r.passed for r in results) else 1)

if __name__ == "__main__":
    main()