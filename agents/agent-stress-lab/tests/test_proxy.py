import time

from conftest import SHOP_UPSTREAM, proxy_client, read_jsonl, read_state

BOOK = {"order_id": "A12", "item_sku": "SNK-42", "reason": "size"}
ELIG = {"order_id": "A12", "item_sku": "SNK-42"}
RULES = [
    {"id": "no-double-booking", "type": "idempotent", "tool": "book_pickup", "key": ["order_id", "item_sku"]},
    {"id": "eligibility-first", "type": "requires_before", "tool": "book_pickup",
     "prior": "check_return_eligibility", "match": ["order_id", "item_sku"], "prior_result": {"eligible": True}},
]
TIMEOUT = [{"tool": "book_pickup", "type": "timeout_after_commit", "on_call": 1}]


async def test_proxy_forwards_all_upstream_tools(run_dir):
    async with proxy_client(run_dir) as c:
        names = {t.name for t in await c.list_tools()}
    assert names == {"find_orders", "get_order", "check_return_eligibility", "book_pickup", "get_pickup_status"}


async def test_upstream_state_persists_across_calls_in_one_run(run_dir):
    async with proxy_client(run_dir) as c:
        await c.call_tool("book_pickup", BOOK)
        status = await c.call_tool("get_pickup_status", {"order_id": "A12"})
    assert len(status.data["pickups"]) == 1


async def test_timeout_after_commit_creates_pickup_but_reports_error(run_dir):
    async with proxy_client(run_dir, TIMEOUT) as c:
        first = await c.call_tool("book_pickup", BOOK, raise_on_error=False)
        second = await c.call_tool("book_pickup", BOOK, raise_on_error=False)
    assert first.is_error and "timeout" in first.content[0].text
    assert not second.is_error
    assert len(read_state(run_dir)["pickups"]) == 2
    events = read_jsonl(run_dir / "tools.jsonl")
    assert events[0]["v"] == 1 and events[0]["fault"] == "timeout_after_commit" and events[0]["upstream_called"]
    assert events[1]["fault"] is None and events[1]["ok"]


async def test_error_500_does_not_reach_upstream(run_dir):
    async with proxy_client(run_dir, [{"tool": "book_*", "type": "error_500"}]) as c:
        res = await c.call_tool("book_pickup", BOOK, raise_on_error=False)
    assert res.is_error and "500" in res.content[0].text
    assert read_state(run_dir)["pickups"] == []
    assert read_jsonl(run_dir / "tools.jsonl")[0]["upstream_called"] is False


async def test_slow_delays_then_succeeds(run_dir):
    async with proxy_client(run_dir, [{"tool": "get_order", "type": "slow", "delay_s": 0.5}]) as c:
        start = time.monotonic()
        res = await c.call_tool("get_order", {"order_id": "A12"})
        elapsed = time.monotonic() - start
    assert res.data["order_id"] == "A12" and elapsed >= 0.5


async def test_malformed_drops_a_field(run_dir):
    async with proxy_client(run_dir, [{"tool": "get_order", "type": "malformed"}]) as c:
        res = await c.call_tool("get_order", {"order_id": "A12"})
    assert "order_id" not in res.structured_content and "items" in res.structured_content


async def test_fault_only_hits_configured_call_index(run_dir):
    async with proxy_client(run_dir, [{"tool": "get_order", "type": "error_500", "on_call": 2}]) as c:
        first = await c.call_tool("get_order", {"order_id": "A12"}, raise_on_error=False)
        second = await c.call_tool("get_order", {"order_id": "A12"}, raise_on_error=False)
    assert not first.is_error and second.is_error


async def test_policy_monitor_records_without_blocking(run_dir):
    async with proxy_client(run_dir, policy={"mode": "monitor", "rules": RULES}) as c:
        res = await c.call_tool("book_pickup", BOOK, raise_on_error=False)
    assert not res.is_error
    event = read_jsonl(run_dir / "tools.jsonl")[0]
    assert event["policy"] == {"violations": ["eligibility-first"], "blocked": False}


async def test_policy_enforce_blocks_duplicate_after_committed_timeout(run_dir):
    async with proxy_client(run_dir, TIMEOUT, policy={"mode": "enforce", "rules": RULES}) as c:
        await c.call_tool("check_return_eligibility", ELIG)
        first = await c.call_tool("book_pickup", BOOK, raise_on_error=False)
        retry = await c.call_tool("book_pickup", BOOK, raise_on_error=False)
    assert first.is_error and retry.is_error
    assert "no-double-booking" in retry.content[0].text
    assert len(read_state(run_dir)["pickups"]) == 1


async def test_policy_enforce_blocks_booking_without_eligibility(run_dir):
    async with proxy_client(run_dir, policy={"mode": "enforce", "rules": RULES}) as c:
        res = await c.call_tool("book_pickup", BOOK, raise_on_error=False)
    assert res.is_error and "eligibility-first" in res.content[0].text
    assert read_state(run_dir)["pickups"] == []


async def test_multiple_upstreams_are_namespaced(run_dir):
    upstreams = [SHOP_UPSTREAM, {**SHOP_UPSTREAM, "name": "shop2"}]
    async with proxy_client(run_dir, upstreams=upstreams) as c:
        names = {t.name for t in await c.list_tools()}
        res = await c.call_tool(next(n for n in names if "shop2" in n and n.endswith("get_order")), {"order_id": "A12"})
    assert len(names) == 10
    assert res.data["order_id"] == "A12"
