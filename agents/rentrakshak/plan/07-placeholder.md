# 07 — Vacating / availability board

**Implement:**
- DB table: `vacating_posts` with statuses draft|pending_review|active|filled|withdrawn|expired
- Contact stored encrypted-at-rest as private field; public search hides phone/email by default
- `create_vacating_post`, `search_available_rooms`, `update_vacating_post_status`
- Auto-expire past availability dates on search

**Tests:** `tests/test_vacating.py`
