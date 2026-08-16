"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Environment-driven application settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="Kabuhandan Hojo API")
    app_env: Literal["local", "dev", "test", "prod"] = Field(default="local")
    app_version: str = Field(default="0.1.0")
    log_level: str = Field(default="INFO")
    sql_echo: bool = Field(default=False)
    database_url: str = Field(default="sqlite:///./kabuhandan_hojo.db")

    jquants_api_key: str | None = Field(default=None)
    jquants_base_url: str = Field(default="https://api.jquants.com")
    edinet_api_key: str | None = Field(default=None)
    edinet_base_url: str = Field(default="https://api.edinet-fsa.go.jp/api/v2")
    tdnet_api_key: str | None = Field(default=None)
    tdnet_base_url: str = Field(default="https://api.arrowfront.jp")
    youtube_api_key: str | None = Field(default=None)
    youtube_base_url: str = Field(default="https://www.googleapis.com/youtube/v3")
    youtube_monitored_channels: dict[str, list[str]] = Field(default_factory=dict)
    ir_allowlist_domains: list[str] = Field(default_factory=list)

    scoring_event_weight: float = Field(default=0.30)
    scoring_fundamental_weight: float = Field(default=0.25)
    scoring_technical_weight: float = Field(default=0.20)
    scoring_flow_weight: float = Field(default=0.15)
    scoring_risk_weight: float = Field(default=0.10)

    score_change_alert_threshold: float = Field(default=12.0)
    high_priority_threshold: float = Field(default=65.0)
    low_liquidity_daily_volume: int = Field(default=100_000)
    recent_event_lookback_days: int = Field(default=30)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once for the default application factory."""

    return Settings()
