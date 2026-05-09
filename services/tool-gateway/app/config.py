from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://platform:platform@postgres:5432/platform",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="devsecret", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256")
    platform_secrets_key: str = Field(default="", alias="PLATFORM_SECRETS_KEY")
    sample_db_url: str = Field(default="", alias="SAMPLE_DB_URL")
    mailhog_host: str = Field(default="mailhog", alias="MAILHOG_HOST")
    mailhog_port: int = Field(default=1025, alias="MAILHOG_PORT")
    mock_crm_url: str = Field(default="http://mock-crm:8080", alias="MOCK_CRM_URL")


settings = Settings()
