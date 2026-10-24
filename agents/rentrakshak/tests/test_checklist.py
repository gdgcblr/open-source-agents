from rentrakshak.services.checklist import build_rental_checklist, get_karnataka_rental_guidance


def test_checklist_items_present():
    items = build_rental_checklist()
    assert len(items) >= 10
    ids = {i.item_id for i in items}
    assert "CHK-03" in ids


def test_legal_sources_have_urls():
    refs = get_karnataka_rental_guidance()
    assert refs
    assert all(r.url.startswith("http") for r in refs)
    assert all(r.date_checked for r in refs)
