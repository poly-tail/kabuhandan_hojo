"""Watchlist request and response schemas."""

from __future__ import annotations

from datetime import datetime

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_collection_name(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value).strip()
    if not cleaned:
        raise ValueError("Watchlist name must not be blank.")
    return cleaned


class WatchlistCollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = 100

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return _clean_collection_name(value) if isinstance(value, str) else value


class WatchlistCollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    sort_order: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return _clean_collection_name(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> "WatchlistCollectionUpdate":
        if self.name is None and self.sort_order is None:
            raise ValueError("At least one watchlist field must be supplied.")
        return self


class WatchlistCollectionRead(BaseModel):
    id: int
    name: str
    is_default: bool
    sort_order: int
    item_count: int
    created_at: datetime
    updated_at: datetime


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
    collection_id: int | None = None
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
