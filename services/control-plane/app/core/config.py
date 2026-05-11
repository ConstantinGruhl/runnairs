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
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    jwt_secret: str = Field(default="devsecret", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256")
    jwt_ttl_minutes: int = Field(default=60 * 8)
    app_env: str = Field(default="development", alias="APP_ENV")
    platform_secrets_key: str = Field(default="", alias="PLATFORM_SECRETS_KEY")
    tool_gateway_url: str = Field(default="http://tool-gateway:8001", alias="TOOL_GATEWAY_URL")

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
