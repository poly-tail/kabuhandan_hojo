"""Screening filter schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class TechnicalScreeningFilters(BaseModel):
    min_rsi_14: Decimal | None = None
    max_rsi_14: Decimal | None = None
    macd_cross: Literal["bullish", "bearish"] | None = None
    macd_histogram_positive: bool | None = None
    price_above_ma_25: bool | None = None
    price_above_ma_75: bool | None = None
    golden_cross_only: bool = False
    dead_cross_exclude: bool = False
    min_volume_surge_ratio: Decimal | None = None
    min_upper_wick_ratio: Decimal | None = None
    max_upper_wick_ratio: Decimal | None = None
    min_lower_wick_ratio: Decimal | None = None
    gap_up_only: bool = False
    gap_down_exclude: bool = False


class FlowScreeningFilters(BaseModel):
    min_credit_ratio: Decimal | None = None
    max_credit_ratio: Decimal | None = None
    min_buy_balance_change_wow: Decimal | None = None
    max_buy_balance_change_wow: Decimal | None = None
    min_sell_balance_change_wow: Decimal | None = None
    min_buy_balance_to_volume: Decimal | None = None
    max_buy_balance_to_volume: Decimal | None = None
    min_sell_balance_to_volume: Decimal | None = None
    min_squeeze_potential_subscore: Decimal | None = None


class ScreeningFilterRequest(BaseModel):
    min_total_score: Decimal = Field(default=Decimal("60"), ge=Decimal("0"), le=Decimal("100"))
    limit: int = Field(default=20, ge=1, le=100)
    technical: TechnicalScreeningFilters | None = None
    flow: FlowScreeningFilters | None = None
