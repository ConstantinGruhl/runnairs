from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_SECRETS = {"", "devsecret", "changeme-dev-only"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://platform:platform@postgres:5432/platform",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="devsecret", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256")
    app_env: str = Field(default="development", alias="APP_ENV")
    platform_secrets_key: str = Field(default="", alias="PLATFORM_SECRETS_KEY")
    sample_db_url: str = Field(default="", alias="SAMPLE_DB_URL")
    mailhog_host: str = Field(default="mailhog", alias="MAILHOG_HOST")
    mailhog_port: int = Field(default=1025, alias="MAILHOG_PORT")
    mock_crm_url: str = Field(default="http://mock-crm:8080", alias="MOCK_CRM_URL")

    @model_validator(mode="after")
    def validate_runtime_security(self) -> "Settings":
        if self.app_env.lower() == "production":
            secret = self.jwt_secret.strip()
            if secret in _INSECURE_JWT_SECRETS or len(secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to a strong, non-default value when APP_ENV=production"
                )
        return self


settings = Settings()
