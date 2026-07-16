"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings with safe development defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EXPEDIENTE_CERO_",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_docs_enabled: bool = True
    database_url: str = "sqlite:///./data/expediente-cero.db"
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = "gpt-5.6"
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    follow_up_attempt_lease_seconds: int = Field(default=300, gt=0)

    @model_validator(mode="after")
    def validate_follow_up_lease(self) -> "Settings":
        if self.follow_up_attempt_lease_seconds <= self.openai_timeout_seconds:
            raise ValueError("follow-up attempt lease must exceed the OpenAI timeout")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""
    return Settings()
