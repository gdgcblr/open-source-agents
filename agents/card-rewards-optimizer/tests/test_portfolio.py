from pathlib import Path

import pytest

from portfolio import PortfolioError, load_portfolio, load_rates

BASE = Path(__file__).resolve().parent.parent
RATES = str(BASE / "data" / "transfer_rates.yaml")
EXAMPLE = str(BASE / "examples" / "portfolio.yaml")


def test_load_rates_parses_cards():
    rates = load_rates(RATES)
    assert rates.as_of == "2026-10-24"
    assert "hdfc-infinia" in rates.cards
    card = rates.cards["hdfc-infinia"]
    assert card.name == "HDFC Infinia"
    assert any(r.id == "krisflyer" and r.min_points == 5000 for r in card.routes)


def test_load_portfolio_happy_path():
    rates = load_rates(RATES)
    p = load_portfolio(EXAMPLE, rates)
    assert p.holdings[0].card_id == "hdfc-infinia"
    assert p.holdings[0].points == 82000
    assert p.holdings[0].batches[0].points == 20000


def test_unknown_card_id_suggests_closest(tmp_path):
    rates = load_rates(RATES)
    bad = tmp_path / "p.yaml"
    bad.write_text("cards:\n  - card_id: hdfc-infiniaa\n    points: 100\n")
    with pytest.raises(PortfolioError, match="hdfc-infinia"):
        load_portfolio(str(bad), rates)


def test_bad_expiry_date_is_clear_error(tmp_path):
    rates = load_rates(RATES)
    bad = tmp_path / "p.yaml"
    bad.write_text(
        "cards:\n  - card_id: sbi-elite\n    points: 100\n"
        "    batches:\n      - points: 50\n        expires_on: soon\n")
    with pytest.raises(PortfolioError, match="expires_on"):
        load_portfolio(str(bad), rates)


def test_rates_cards_not_a_mapping_is_clear_error(tmp_path):
    bad = tmp_path / "rates.yaml"
    bad.write_text('as_of: "2026-10-24"\ncards:\n  - just-a-list-item\n')
    with pytest.raises(PortfolioError, match="must be a mapping"):
        load_rates(str(bad))


def test_cards_not_a_list_is_clear_error(tmp_path):      # fix 2A
    rates = load_rates(RATES)
    bad = tmp_path / "p.yaml"
    bad.write_text("cards:\n")           # 'cards:' with no list -> None
    with pytest.raises(PortfolioError, match="must be a list"):
        load_portfolio(str(bad), rates)


def test_batch_missing_required_field_is_clear_error(tmp_path):   # fix 2A
    rates = load_rates(RATES)
    bad = tmp_path / "p.yaml"
    bad.write_text(
        "cards:\n  - card_id: sbi-elite\n    points: 100\n"
        "    batches:\n      - points: 50\n")        # no expires_on
    with pytest.raises(PortfolioError, match="expires_on"):
        load_portfolio(str(bad), rates)
