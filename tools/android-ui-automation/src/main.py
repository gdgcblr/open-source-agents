"""Command-line entry point.

Examples (run from the project root)::

    python -m src.main tools
    python -m src.main call list_devices
    python -m src.main call click_element --args '{"text": "Login"}'
    python -m src.main run workflow.json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from .automation import TOOL_NAMES, AndroidAutomation
from .config import Config
from .models.responses import ActionResponse


def _load_args(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("--args must be a JSON object")
    return value


def _build(args: argparse.Namespace) -> AndroidAutomation:
    config = Config.from_env()
    if args.device:
        config = Config(config.adb_path, args.device, config.command_timeout, config.ui_wait_timeout)
    return AndroidAutomation(config)


def _cmd_call(args: argparse.Namespace) -> int:
    try:
        kwargs = _load_args(args.args)
    except (ValueError, json.JSONDecodeError) as exc:
        print(ActionResponse.fail(args.tool, "INVALID_ARGUMENT", "Bad --args", str(exc)).to_json())
        return 2
    resp = _build(args).call(args.tool, **kwargs)
    print(resp.to_json())
    return 0 if resp.success else 1


def _cmd_run(args: argparse.Namespace) -> int:
    """Run a JSON workflow; stop at the first failed step."""
    try:
        with open(args.file, encoding="utf-8") as fh:
            steps: List[Dict[str, Any]] = json.load(fh)
        if not isinstance(steps, list):
            raise ValueError("workflow must be a JSON list of steps")
    except (OSError, ValueError) as exc:
        print(f"Could not read workflow: {exc}", file=sys.stderr)
        return 2

    auto = _build(args)
    results: List[Dict[str, Any]] = []
    exit_code = 0
    for i, step in enumerate(steps, 1):
        tool = step.get("action", "") if isinstance(step, dict) else ""
        kwargs = step.get("args", {}) if isinstance(step, dict) else {}
        resp = auto.call(tool, **kwargs)
        results.append(resp.to_dict())
        print(f"[{i}/{len(steps)}] {resp.summary()}", file=sys.stderr)
        if not resp.success and not step.get("continue_on_failure", False):
            exit_code = 1
            break
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    return exit_code


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="android-ui-automation", description=__doc__.split("\n")[0])
    parser.add_argument("--device", help="Device serial (overrides ANDROID_DEVICE_ID)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tools", help="List available tools")

    p_call = sub.add_parser("call", help="Call one tool and print the JSON response")
    p_call.add_argument("tool", choices=TOOL_NAMES)
    p_call.add_argument("--args", help="Tool arguments as a JSON object")

    p_run = sub.add_parser("run", help="Run a JSON workflow file step by step")
    p_run.add_argument("file")

    args = parser.parse_args(argv)
    if args.command == "tools":
        print("\n".join(TOOL_NAMES))
        return 0
    if args.command == "call":
        return _cmd_call(args)
    return _cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
