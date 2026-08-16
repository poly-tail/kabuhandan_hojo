"""Application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Environment-backed settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Kabuhandan Hojo API", alias="APP_NAME")
    app_env: Literal["local", "dev", "test", "prod"] = Field(default="local", alias="APP_ENV")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    app_use_mock: bool = Field(default=False, alias="APP_USE_MOCK")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    database_url: str = Field(default="sqlite:///./data/kabuhandan_hojo.db", alias="DATABASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    openai_reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = Field(
        default="high",
        alias="OPENAI_REASONING_EFFORT",
    )
    openai_model_scanner: str = Field(default="gpt-5.4", alias="OPENAI_MODEL_SCANNER")
    openai_model_analyst: str = Field(default="gpt-5.4", alias="OPENAI_MODEL_ANALYST")
    openai_model_judge: str = Field(default="gpt-5.5", alias="OPENAI_MODEL_JUDGE")
    openai_model_critical: str = Field(default="gpt-5.5", alias="OPENAI_MODEL_CRITICAL")
    openai_reasoning_scanner: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = Field(
        default="low",
        alias="OPENAI_REASONING_SCANNER",
    )
    openai_reasoning_analyst: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = Field(
        default="medium",
        alias="OPENAI_REASONING_ANALYST",
    )
    openai_reasoning_judge: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = Field(
        default="high",
        alias="OPENAI_REASONING_JUDGE",
    )
    openai_reasoning_critical: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = Field(
        default="xhigh",
        alias="OPENAI_REASONING_CRITICAL",
    )
    openai_enable_web_search: bool = Field(default=True, alias="OPENAI_ENABLE_WEB_SEARCH")
    openai_max_web_search_calls: int = Field(default=5, ge=0, alias="OPENAI_MAX_WEB_SEARCH_CALLS")
    openai_max_stocks_per_request: int = Field(default=20, ge=1, alias="OPENAI_MAX_STOCKS_PER_REQUEST")
    openai_daily_request_limit: int = Field(default=50, ge=1, alias="OPENAI_DAILY_REQUEST_LIMIT")
    openai_default_verbosity: str = Field(default="medium", alias="OPENAI_DEFAULT_VERBOSITY")
    openai_critical_confirmation_required: bool = Field(default=True, alias="OPENAI_CRITICAL_CONFIRMATION_REQUIRED")

    postgres_user: str = Field(default="kabuhandan", alias="POSTGRES_USER")
    postgres_password: str = Field(default="kabuhandan", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="kabuhandan", alias="POSTGRES_DB")
    postgres_host: str = Field(default="db", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings."""

    return Settings()
