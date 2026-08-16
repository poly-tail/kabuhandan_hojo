"""Watchlist schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from kabuhandan_hojo.schemas.common import ORMModel
from kabuhandan_hojo.schemas.securities import SecurityRead
from kabuhandan_hojo.schemas.scores import ScoreRead


class WatchlistCreate(BaseModel):
    ticker_code: str
    name: str | None = None
    market: str | None = None
    memo: str | None = None
    thesis_bull: str | None = None
    thesis_bear: str | None = None
    sort_order: int = 100


class WatchlistRead(ORMModel):
    id: int
    ticker_code: str
    memo: str | None = None
    thesis_bull: str | None = None
    thesis_bear: str | None = None
    sort_order: int
    is_active: bool
    last_reviewed_at: datetime | None = None


class WatchlistItemResponse(BaseModel):
    watchlist: WatchlistRead
    security: SecurityRead
    latest_score: ScoreRead | None = None
    latest_event_summary: str | None = None
    updated_at: datetime | None = None

