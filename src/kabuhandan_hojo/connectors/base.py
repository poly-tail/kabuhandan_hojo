"""Connector interfaces and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


class ConnectorError(RuntimeError):
    """Base connector exception."""


class MissingCredentialsError(ConnectorError):
    """Raised when an API key is required but missing."""


@dataclass(slots=True)
class DailyBarRecord:
    ticker_code: str
    target_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    adjusted_close: Decimal | None
    volume: int
    turnover_value: Decimal | None
    source_name: str


@dataclass(slots=True)
class ListedIssueRecord:
    ticker_code: str
    local_code: str | None
    name: str
    name_english: str | None
    market: str | None
    industry_17: str | None
    industry_33: str | None
    listed_date: date | None
    source_as_of: date | None = None
    is_active: bool = True


@dataclass(slots=True)
class MarginSnapshotRecord:
    ticker_code: str
    target_date: date
    margin_buy_balance: Decimal | None
    margin_sell_balance: Decimal | None
    source_name: str


@dataclass(slots=True)
class DocumentRecord:
    source_name: str
    external_id: str
    document_type: str
    title: str
    ticker_code: str | None
    published_at: datetime
    storage_uri: str | None
    raw_payload: dict[str, Any]
    content_text: str | None
    hash_digest: str | None


class MarketDataConnector(ABC):
    """Connector for market and issuer data."""

    @abstractmethod
    async def fetch_daily_bars(
        self,
        ticker_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyBarRecord]:
        """Fetch OHLCV bars from an allowed source."""

    @abstractmethod
    async def fetch_listed_issues(self, as_of: date | None = None) -> list[ListedIssueRecord]:
        """Fetch listed-issue master records from an allowed source."""

    @abstractmethod
    async def fetch_margin_snapshot(
        self,
        ticker_code: str,
        as_of: date | None = None,
    ) -> MarginSnapshotRecord | None:
        """Fetch margin trading data for a single issue from an allowed source."""


class DocumentConnector(ABC):
    """Connector for documents and filings."""

    @abstractmethod
    async def fetch_documents(self, target_date: date) -> list[DocumentRecord]:
        """Fetch document metadata for a date."""
