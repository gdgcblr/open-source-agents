"""Run the PR Agent: `python -m pr_agent` (monitor + worker + dashboard)."""
from __future__ import annotations

import argparse
import sys

import uvicorn

from .config import load_config


def main() -> int:
    ap = argparse.ArgumentParser(prog="pr_agent")
    ap.add_argument("--config", help="Path to config.yaml")
    ap.add_argument("--check", action="store_true", help="Check config, GitHub access and the local model, then exit")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.check:
        return doctor(cfg)

    from .pipeline import Engine
    from .web import create_app
    engine = Engine(cfg)
    engine.start()
    print(f"PR Agent dashboard: http://{cfg.host}:{cfg.port}  (model: {cfg.model}, strict_local={cfg.strict_local})")
    uvicorn.run(create_app(engine), host=cfg.host, port=cfg.port, log_level="warning")
    engine.stop()
    return 0


def doctor(cfg) -> int:
    import httpx
    from .github import GitHub
    ok = True
    print(f"Repos: {[r.name for r in cfg.repos] or 'NONE - add some to config.yaml'}")
    print(f"GitHub token: {'set' if cfg.github_token else 'MISSING (only public repos, 60 req/h)'}")
    gh = GitHub(cfg.github_token)
    for r in cfg.repos:
        try:
            print(f"  {r.name}: {len(gh.open_pulls(r.name))} open PR(s)")
        except Exception as e:
            ok = False
            print(f"  {r.name}: ERROR {e}")
    try:
        tags = httpx.get(f"{cfg.api_base}/api/tags", timeout=5).json()
        names = [m["name"] for m in tags.get("models", [])]
        want = cfg.model.split("/", 1)[1]
        print(f"Ollama: running; models {names}")
        if not any(n == want or n == f"{want}:latest" for n in names):
            ok = False
            print(f"  Model '{want}' not pulled. Run: ollama pull {want}")
    except Exception as e:
        ok = False
        print(f"Ollama: NOT reachable at {cfg.api_base} ({e})")
    print("All good." if ok else "Fix the items above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
