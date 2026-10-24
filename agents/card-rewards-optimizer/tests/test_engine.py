from datetime import date
from pathlib import Path

from engine import expiring_points, format_expiry, format_table, rank_routes
from portfolio import Holding, Portfolio, load_portfolio, load_rates

BASE = Path(__file__).resolve().parent.parent
RATES = load_rates(str(BASE / "data" / "transfer_rates.yaml"))
EXAMPLE = load_portfolio(str(BASE / "examples" / "portfolio.yaml"), RATES)


def test_rank_routes_sorted_by_value_desc():
    vals = rank_routes(EXAMPLE, RATES)
    rates_seq = [v.inr_per_point for v in vals]
    assert rates_seq == sorted(rates_seq, reverse=True)
    assert vals[0].inr_per_point == 1.0          # Infinia SmartBuy tops the sample


def test_category_filter_cash():
    vals = rank_routes(EXAMPLE, RATES, category="cash")
    assert all(v.route.category == "cash" for v in vals)
    top = vals[0]
    assert (top.card_id, top.route.id) == ("amex-mr", "gold-collection")
    assert top.total_value_inr == 15000.0        # 30000 * 0.5


def test_min_points_excludes_small_balances():
    tiny = Portfolio(holdings=[Holding(card_id="axis-magnus", points=1000)])
    vals = rank_routes(tiny, RATES)
    assert all(v.route.id != "krisflyer" for v in vals)   # min_points 5000


def test_format_table_mentions_as_of_and_disclaimer():
    out = format_table(rank_routes(EXAMPLE, RATES, category="cash"), RATES.as_of)
    assert "2026-10-24" in out
    assert "not financial advice" in out


def test_expiring_within_horizon_listed_with_days_left():
    alerts = expiring_points(EXAMPLE, RATES, today=date(2026, 10, 24))
    assert [(a.card_id, a.days_left) for a in alerts] == [
        ("hdfc-infinia", 37), ("amex-mr", 83)]
    assert alerts[0].best is not None
    assert alerts[0].best.inr_per_point == 1.0      # 20k pts clear SmartBuy min


def test_far_expiry_excluded():
    alerts = expiring_points(EXAMPLE, RATES, today=date(2026, 10, 24), horizon_days=30)
    assert alerts == []


def test_format_expiry_mentions_disclaimer():
    out = format_expiry(expiring_points(EXAMPLE, RATES, today=date(2026, 10, 24)), RATES.as_of)
    assert "not financial advice" in out
