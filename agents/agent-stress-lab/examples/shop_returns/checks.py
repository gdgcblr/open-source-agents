"""Ground-truth outcome check for the shop example: compare the backend's pickups
with what the persona actually wanted (persona vars.pickups)."""

import json
from collections import Counter


def pickups_match(ctx) -> bool:
    state_file = ctx.run_dir / "state.json"
    pickups = json.loads(state_file.read_text())["pickups"] if state_file.exists() else []
    actual = Counter((p["order_id"].upper(), p["item_sku"].upper()) for p in pickups)
    wanted = Counter((p["order_id"].upper(), p["item_sku"].upper()) for p in ctx.vars.get("pickups", []))
    # Duplicates are judged by the single-booking check; here only the set of booked items matters.
    return set(actual) == set(wanted)
