from conftest import backend_client, read_state



async def test_find_orders_lists_customer_orders(run_dir):
    async with backend_client(run_dir) as c:
        res = await c.call_tool("find_orders", {"email": "Priya@Example.com"})
    assert {o["order_id"] for o in res.data["orders"]} == {"A12", "A07"}


async def test_eligibility_rules(run_dir):
    async with backend_client(run_dir) as c:
        ok = await c.call_tool("check_return_eligibility", {"order_id": "A12", "item_sku": "SNK-42"})
        old = await c.call_tool("check_return_eligibility", {"order_id": "B33", "item_sku": "HPH-09"})
        final = await c.call_tool("check_return_eligibility", {"order_id": "C51", "item_sku": "SWM-03"})
    assert ok.data["eligible"] is True
    assert old.data["eligible"] is False and "window" in old.data["reason"]
    assert final.data["eligible"] is False and "final sale" in final.data["reason"]


async def test_book_pickup_is_not_idempotent_and_persists_state(run_dir):
    args = {"order_id": "A12", "item_sku": "SNK-42", "reason": "size"}
    async with backend_client(run_dir) as c:
        first = await c.call_tool("book_pickup", args)
        second = await c.call_tool("book_pickup", args)
        status = await c.call_tool("get_pickup_status", {"order_id": "A12"})
    assert first.data["pickup_id"] != second.data["pickup_id"]
    assert len(status.data["pickups"]) == 2
    assert len(read_state(run_dir)["pickups"]) == 2


async def test_unknown_order_is_tool_error(run_dir):
    async with backend_client(run_dir) as c:
        res = await c.call_tool("get_order", {"order_id": "ZZ9"}, raise_on_error=False)
    assert res.is_error
