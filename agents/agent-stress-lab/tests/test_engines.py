from pydantic import TypeAdapter

from murphy.config.schema import FaultSpec, Rule
from murphy.proxy.faults import FaultEngine
from murphy.proxy.policy import PolicyEngine

BOOK = {"order_id": "a12 ", "item_sku": "SNK-42"}


def faults(*specs):
    return [FaultSpec.model_validate(s) for s in specs]


def rules(*specs):
    return TypeAdapter(list[Rule]).validate_python(list(specs))


# --- FaultEngine ---------------------------------------------------------

def test_fault_glob_and_call_index():
    engine = FaultEngine(faults({"tool": "get_*", "type": "error_500", "on_call": 2}))
    assert engine.pick("get_order", 1) is None
    assert engine.pick("get_order", 2).type == "error_500"
    assert engine.pick("book_pickup", 2) is None


def test_fault_default_trigger_is_first_call():
    assert FaultSpec(tool="x", type="slow").on_call == 1


def test_fault_rate_is_deterministic_per_seed():
    spec = faults({"tool": "*", "type": "error_500", "rate": 0.5})
    e1, e2 = FaultEngine(spec, seed=3), FaultEngine(spec, seed=3)
    a = [e1.pick("t", i) is not None for i in range(1, 50)]
    b = [e2.pick("t", i) is not None for i in range(1, 50)]
    assert a == b and 0 < sum(a) < 49


def test_fault_first_match_wins():
    engine = FaultEngine(faults({"tool": "book_*", "type": "slow"}, {"tool": "*", "type": "error_500"}))
    assert engine.pick("book_pickup", 1).type == "slow"


# --- PolicyEngine --------------------------------------------------------

def test_idempotent_uses_ground_truth_and_normalized_keys():
    p = PolicyEngine(rules({"id": "idem", "type": "idempotent", "tool": "book_pickup", "key": ["order_id", "item_sku"]}))
    assert p.check("book_pickup", BOOK) == []
    p.observe("book_pickup", BOOK, {"pickup_id": "PU-1"}, upstream_ok=True)
    assert p.check("book_pickup", {"order_id": "A12", "item_sku": "snk-42"}) == ["idem"]


def test_idempotent_ignores_failed_upstream_calls():
    p = PolicyEngine(rules({"id": "idem", "type": "idempotent", "tool": "book_pickup", "key": ["order_id"]}))
    p.check("book_pickup", BOOK)
    p.observe("book_pickup", BOOK, None, upstream_ok=False)
    assert p.check("book_pickup", BOOK) == []


def test_requires_before_with_prior_result():
    p = PolicyEngine(rules({"id": "elig", "type": "requires_before", "tool": "book_pickup",
                            "prior": "check_return_eligibility", "match": ["order_id"], "prior_result": {"eligible": True}}))
    assert p.check("book_pickup", BOOK) == ["elig"]
    p.observe("check_return_eligibility", BOOK, {"eligible": False}, upstream_ok=True)
    assert p.check("book_pickup", BOOK) == ["elig"]
    p.observe("check_return_eligibility", BOOK, {"eligible": True}, upstream_ok=True)
    assert p.check("book_pickup", BOOK) == []


def test_max_calls_and_budget():
    p = PolicyEngine(rules({"id": "lim", "type": "max_calls", "tool": "find_*", "max": 2},
                           {"id": "budget", "type": "budget", "max_tool_calls": 3}))
    assert [p.check("find_orders", {}) for _ in range(3)] == [[], [], ["lim"]]
    assert p.check("get_order", {}) == ["budget"]


def test_mode_off_never_violates():
    p = PolicyEngine(rules({"id": "b", "type": "budget", "max_tool_calls": 0}), mode="off")
    assert p.check("anything", {}) == []
