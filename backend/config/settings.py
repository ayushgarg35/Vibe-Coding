"""
Centralised application settings — loaded from environment / .env
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_SECRET_KEY: str = "change-me"
    APP_BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://pmuser:pmpassword@localhost:5432/agenticpm"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Vector Store
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # LLM Providers
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    LITELLM_MASTER_KEY: str = "change-me"

    # Auth
    CLERK_SECRET_KEY: str = ""
    CLERK_WEBHOOK_SECRET: str = ""

    # Storage
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "agentic-pm"
    S3_REGION: str = "us-east-1"

    # Observability
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "agentic-pm-system"
    LANGSMITH_TRACING: bool = True

    # Compliance
    DEFAULT_DATA_REGION: Literal["US", "EU", "IN"] = "US"
    PII_DETECTION_ENABLED: bool = True
    AUDIT_LOG_ENABLED: bool = True

    # Session
    SESSION_INACTIVITY_TIMEOUT_HOURS: int = 24
    MAX_CLARIFICATION_ROUNDS: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
