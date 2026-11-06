import logging
from typing import Literal

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Values that must never be used as a JWT signing key in production.
_UNSAFE_SECRET_KEYS = {"", "change-me-in-production"}


class Settings(BaseSettings):
    # Deployment environment
    environment: Literal["development", "test", "production"] = "development"

    # Database & Cache
    database_url: str = ""
    redis_url: str = "redis://localhost:6379"
    secret_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]

    # Authentication / Authorization
    auth_enforcement: bool = True
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""
    dev_admin_password: str = "dev-admin-password"

    # Logging
    log_format: str = "json"

    # Alert Service
    alert_check_interval_minutes: int = 360

    # AI / Agent Engine (Claude API + LangGraph)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    ai_enabled: bool = False
    ai_max_tokens: int = 4096
    ai_temperature: float = 0.2
    ai_cache_enabled: bool = True
    ai_batch_interval_minutes: int = 30
    ai_max_concurrent_agents: int = 3

    # DeepSeek / Multi-LLM
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    llm_primary: str = "deepseek"      # deepseek | anthropic
    llm_fallback: str = "anthropic"    # fallback if primary fails
    ai_embedding_model: str = "text-embedding-3-small"
    ai_embedding_provider: str = "deepseek"  # deepseek | openai

    # RAG Vector Store
    ai_vector_store_type: str = "memory"     # memory | pgvector | qdrant
    ai_rag_top_k: int = 5                    # top-K retrieval results
    ai_rag_similarity_threshold: float = 0.7 # minimum similarity score
    ai_insight_cache_ttl_minutes: int = 5    # cache TTL for pre-computed insights

    # LangGraph workflow config
    langgraph_checkpointer: str = "memory"  # memory, postgres, or sqlite
    langgraph_max_steps: int = 25

    # Audit & Observability
    ai_audit_log_enabled: bool = True
    ai_recommendation_log_retention_days: int = 365

    model_config = {"env_prefix": "FPSO_", "env_file": ".env", "extra": "forbid"}


settings = Settings()


def validate_runtime_config() -> list[str]:
    """Validate security-critical configuration at application startup.

    In production, any problem raises RuntimeError so the process fails closed.
    In development/test, problems are logged as warnings and startup continues.

    Returns the list of problems found (empty when configuration is valid).
    """
    problems: list[str] = []

    secret = settings.secret_key or ""
    if not secret:
        problems.append("FPSO_SECRET_KEY is not set")
    elif secret in _UNSAFE_SECRET_KEYS:
        problems.append("FPSO_SECRET_KEY is still set to an insecure default")
    elif len(secret) < 32:
        problems.append("FPSO_SECRET_KEY is shorter than 32 characters")

    if not settings.database_url:
        problems.append("FPSO_DATABASE_URL is not set")

    if "*" in settings.cors_origins:
        problems.append("FPSO_CORS_ORIGINS must not contain '*' (wildcard)")

    if settings.environment == "production":
        if problems:
            raise RuntimeError(
                "Refusing to start in production with invalid configuration: "
                + "; ".join(problems)
            )
    else:
        for problem in problems:
            logger.warning("Configuration warning (non-fatal in %s): %s",
                           settings.environment, problem)

    return problems
