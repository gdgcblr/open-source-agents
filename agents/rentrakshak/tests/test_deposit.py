from rentrakshak.services.deposit import assess_deposit_terms
from rentrakshak.services.listing_parser import extract_property


def test_no_legal_cap_claim():
    prop = extract_property("", monthly_rent_inr=20000, deposit_inr=120000)
    out = assess_deposit_terms(prop)
    assert out["legal_cap_claimed"] is False
    assert any("universal" in n.lower() for n in out["limitations"])
