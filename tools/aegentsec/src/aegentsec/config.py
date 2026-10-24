from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_ADMIN_KEY_LENGTH = 32
ADMIN_KEY_PLACEHOLDER = "replace-with-a-long-random-value"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AegentSec"
    app_env: str = "development"
    database_path: Path = Path("./data/aegentsec.sqlite3")
    iam_issuer: str = "http://localhost:8000"
    iam_private_key_path: Path = Path("./keys/private.pem")
    iam_key_id: str = "aegentsec-key-001"
    jwt_expiration_minutes: int = 15
    admin_api_key: str = ""
    mcp_resource_uri: str = "http://localhost:8000/mcp"
    inventory_api_audience: str = "http://localhost:8001"

    @property
    def allowed_audiences(self) -> set[str]:
        return {self.mcp_resource_uri, self.inventory_api_audience}

    def validate_admin_api_key(self) -> None:
        key = self.admin_api_key
        if len(key) < MIN_ADMIN_KEY_LENGTH or key == ADMIN_KEY_PLACEHOLDER:
            raise ValueError(
                f"ADMIN_API_KEY must be a random value of at least {MIN_ADMIN_KEY_LENGTH} "
                "characters; generate one with: python -c 'import secrets; "
                "print(secrets.token_urlsafe(48))'"
            )
