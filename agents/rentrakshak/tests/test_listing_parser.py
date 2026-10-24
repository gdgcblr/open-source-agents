from rentrakshak.services.listing_parser import extract_property


def test_extract_koramangala_rent():
    prop = extract_property("1 BHK furnished flat Koramangala rent Rs 28000 deposit 56000")
    assert prop.locality == "Koramangala"
    assert prop.monthly_rent_inr == 28000
    assert prop.deposit_inr == 56000


def test_missing_rent_note():
    prop = extract_property("Nice room somewhere in Bengaluru")
    assert prop.monthly_rent_inr is None
    assert any("rent" in n.lower() for n in prop.raw_notes)
