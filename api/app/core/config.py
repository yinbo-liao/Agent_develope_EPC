from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Workflow Platform"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"
    DEBUG: bool = True

    API_PREFIX: str = "/api/v1"
    SECRET_KEY: str = Field(
        default="dev-secret-change-me-in-prod-override",
        min_length=16,
    )
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://aiwf:changeme_in_production@localhost:5432/aiwf_dev",
    )
    REDIS_URL: str = Field(default="redis://:changeme@localhost:6379/0")
    OPA_URL: str = "http://opa:8181"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    LOG_LEVEL: str = "INFO"
    ENABLE_METRICS: bool = True
    ENABLE_TRACING: bool = True
    REQUESTS_PER_MINUTE: int = 120

    METRICS_TOKEN: str | None = None
    SEED_DEMO_USERS: bool = False
    DEMO_USER_PASSWORD: str = "demo-pass-1234"
    DEMO_REVIEWER_PASSWORD: str = "reviewer-pass-1234"

    MCP_POSTGRES_ENABLED: bool = True
    MCP_GITHUB_ENABLED: bool = False
    MCP_PUPPETEER_ENABLED: bool = False
    MCP_SLACK_ENABLED: bool = False
    GITHUB_TOKEN: str | None = None
    SLACK_BOT_TOKEN: str | None = None
    SLACK_DEFAULT_CHANNEL: str = "#alerts"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @computed_field  # type: ignore[misc]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def validate_production_secrets(self) -> list[str]:
        """Validate that no insecure default secrets are used in production.

        Returns a list of validation error messages (empty = all clear).
        """
        errors: list[str] = []
        if not self.is_production:
            return errors

        insecure_markers = (
            "changeme",
            "change_me",
            "<change",
            "dev-secret",
            "test-secret",
            "replace-me",
            "placeholder",
        )
        for field_name in ("SECRET_KEY", "DATABASE_URL", "REDIS_URL"):
            value = str(getattr(self, field_name, "")).lower()
            if any(marker in value for marker in insecure_markers):
                errors.append(
                    f"{field_name} contains a placeholder or insecure default. "
                    f"Set {field_name} to a production-safe value."
                )

        if self.SECRET_KEY and len(self.SECRET_KEY) < 32:
            errors.append("SECRET_KEY must be at least 32 characters in production.")
        if self.SEED_DEMO_USERS:
            errors.append("SEED_DEMO_USERS must be false in production.")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
