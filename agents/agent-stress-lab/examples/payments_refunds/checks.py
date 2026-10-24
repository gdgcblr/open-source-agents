"""Ground-truth outcome check: money refunded per payment equals what the customer asked for."""

import json
from collections import defaultdict


def refunds_match(ctx) -> bool:
    state_file = ctx.run_dir / "state.json"
    refunds = json.loads(state_file.read_text())["refunds"] if state_file.exists() else []
    actual: dict[str, int] = defaultdict(int)
    for r in refunds:
        actual[r["payment_id"]] += r["amount"]
    wanted = {r["payment_id"]: r["amount"] for r in ctx.vars.get("refunds", [])}
    return dict(actual) == wanted
