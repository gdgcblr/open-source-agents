def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(email: str) -> dict:
    normalized = normalize_email(email)
    if "@" not in normalized:
        raise ValueError("email must contain @")
    return {"id": 123, "email": normalized}
