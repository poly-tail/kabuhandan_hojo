"""Watchlist request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WatchlistCreate(BaseModel):
    ticker_code: str = Field(min_length=4, max_length=10)
    name: str | None = None
    market: str | None = None
    memo: str | None = None
    thesis_bull: str | None = None
    thesis_bear: str | None = None
    sort_order: int = 100


class WatchlistItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker_code: str
    name: str
    market: str | None = None
    memo: str | None = None
    thesis_bull: str | None = None
    thesis_bear: str | None = None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SecuritySearchResult(BaseModel):
    ticker_code: str
    name: str
    market: str | None = None
    in_watchlist: bool = False
