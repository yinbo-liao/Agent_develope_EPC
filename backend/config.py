from pydantic_settings import BaseSettings
from pydantic import ValidationError
import sys


class Settings(BaseSettings):
    # Database & Cache
    database_url: str = ""
    redis_url: str = "redis://localhost:6379"
    secret_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

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

# Validate critical secrets on startup
if not settings.secret_key:
    print("WARNING: FPSO_SECRET_KEY is not set. Authentication will be insecure.")
if not settings.database_url:
    print("WARNING: FPSO_DATABASE_URL is not set. Database connections will fail.")
