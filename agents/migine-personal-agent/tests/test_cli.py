from argparse import Namespace

from test_agent import settings_at

from migine.cli import execute
from migine.demo import load_demo
from migine.storage import Store


def test_brief_reuses_preference_and_keeps_overdue(tmp_path):
    from datetime import date

    settings = settings_at(tmp_path)
    store = Store(tmp_path)
    load_demo(store, "2026-09")
    load_demo(store, "2026-10")
    with store.connect() as db:
        # Remove payment evidence to simulate unpaid bills.
        db.execute("DELETE FROM records WHERE json_extract(payload,'$.kind')='payment'")
    store.remember("bill_notice_days", "3")
    result = execute(Namespace(command="brief", date=date(2026, 10, 16), calendar=False), settings)
    assert len(result["attention"]) == 1  # September is overdue; October is four days away.
    store.remember("bill_notice_days", "5")
    result = execute(Namespace(command="brief", date=date(2026, 10, 16), calendar=False), settings)
    assert len(result["attention"]) == 2
