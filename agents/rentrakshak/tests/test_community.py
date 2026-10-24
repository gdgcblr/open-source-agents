from rentrakshak.models.schemas import AnonymousExperienceInput
from rentrakshak.services.community import (
    create_anonymous_experience,
    delete_experience,
    search_anonymous_experiences,
)


def test_submit_and_search(tmp_db):
    data = AnonymousExperienceInput(
        locality="HSR Layout",
        property_type="apartment",
        category="Maintenance",
        sentiment="negative",
        experience_text="Water leakage took weeks to fix but eventually resolved after follow-ups.",
    )
    out = create_anonymous_experience(data, db_path=tmp_db)
    assert out["success"]
    assert "edit_token" in out

    pub = search_anonymous_experiences(locality="HSR Layout", db_path=tmp_db)
    assert pub["count"] >= 1
    item = pub["items"][0]
    assert "edit_token" not in item
    assert "experience_text" in item


def test_pii_held_or_redacted(tmp_db):
    data = AnonymousExperienceInput(
        locality="Indiranagar",
        property_type="flat",
        category="Communication",
        sentiment="neutral",
        experience_text="Broker was responsive but shared personal email test@example.com in chat often.",
    )
    out = create_anonymous_experience(data, db_path=tmp_db)
    assert out["success"]
    pub = search_anonymous_experiences(locality="Indiranagar", db_path=tmp_db)
    text = pub["items"][0]["experience_text"]
    assert "test@example.com" not in text


def test_unauthorized_delete(tmp_db):
    data = AnonymousExperienceInput(
        locality="Hebbal",
        property_type="pg",
        category="General rental experience",
        sentiment="positive",
        experience_text="PG food was good and housekeeping was regular throughout my stay there.",
    )
    out = create_anonymous_experience(data, db_path=tmp_db)
    bad = delete_experience(out["public_id"], "wrong-token", db_path=tmp_db)
    assert not bad["success"]
