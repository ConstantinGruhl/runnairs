from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://platform:platform@postgres:5432/platform",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    jwt_secret: str = Field(default="devsecret", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256")
    jwt_ttl_minutes: int = Field(default=60 * 8)
    platform_secrets_key: str = Field(default="", alias="PLATFORM_SECRETS_KEY")
    tool_gateway_url: str = Field(default="http://tool-gateway:8001", alias="TOOL_GATEWAY_URL")


settings = Settings()
