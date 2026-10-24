"""LLM-free stand-ins for the demo agent's naive and fixed retry behavior."""

ORDER = {"order_id": "A12", "item_sku": "SNK-42"}


async def naive_policy(turn, message, call):
    if turn > 1:
        return "Anything else?"
    await call("check_return_eligibility", ORDER)
    for _ in range(3):  # blind retry on error
        ok, res = await call("book_pickup", {**ORDER, "reason": "size"})
        if ok:
            return f"Pickup booked: {res['pickup_id']}"
    return "Sorry, booking failed."


async def fixed_policy(turn, message, call):
    if turn > 1:
        return "Anything else?"
    await call("check_return_eligibility", ORDER)
    for _ in range(3):
        ok, res = await call("book_pickup", {**ORDER, "reason": "size"})
        if ok:
            return f"Pickup booked: {res['pickup_id']}"
        ok, status = await call("get_pickup_status", {"order_id": "A12"})
        if ok and status["pickups"]:
            return f"Pickup booked: {status['pickups'][0]['id']}"
    return "Sorry, booking failed."


async def claims_success_policy(turn, message, call):
    return "Done! Your pickup is booked."  # never calls a tool


# --- payments_refunds example ---------------------------------------------

PAY = {"payment_id": "PAY-100"}


async def refund_naive(turn, message, call):
    if turn > 1:
        return "Anything else?"
    await call("check_refund_policy", {**PAY, "amount": 1200})
    for _ in range(3):
        ok, res = await call("issue_refund", {**PAY, "amount": 1200, "reason": "cancelled"})
        if ok:
            return f"Refund {res['refund_id']} processed."
    return "Sorry, the refund failed."


async def refund_fixed(turn, message, call):
    if turn > 1:
        return "Anything else?"
    await call("check_refund_policy", {**PAY, "amount": 1200})
    ok, res = await call("issue_refund", {**PAY, "amount": 1200, "reason": "cancelled"})
    if ok:
        return f"Refund {res['refund_id']} processed."
    ok, status = await call("get_refund_status", PAY)
    if ok and status["refunds"]:
        return f"Refund {status['refunds'][0]['refund_id']} processed."
    return "Sorry, the refund failed."


async def refund_without_policy_check(turn, message, call):
    ok, res = await call("issue_refund", {"payment_id": "PAY-200", "amount": 499, "reason": "asked"})
    return "Refunded."
