"""Portfolio request and response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PortfolioHoldingUpsert(BaseModel):
    ticker_code: str = Field(min_length=4, max_length=10)
    quantity: Decimal = Field(gt=Decimal("0"))
    average_cost: Decimal | None = Field(default=None, gt=Decimal("0"))
    note: str | None = None
    sort_order: int = 100


class PortfolioHoldingRead(BaseModel):
    id: int
    ticker_code: str
    name: str
    market: str | None = None
    quantity: Decimal
    average_cost: Decimal | None = None
    last_price: Decimal | None = None
    market_value: Decimal | None = None
    cost_basis: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_return_pct: Decimal | None = None
    note: str | None = None
    sort_order: int
    updated_at: datetime


class PortfolioImportCsvRequest(BaseModel):
    csv_text: str = Field(min_length=1)
    replace_existing: bool = False


class PortfolioImportCsvResponse(BaseModel):
    imported_count: int
    archived_count: int = 0
