"""Security and market-data schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from kabuhandan_hojo.schemas.common import ORMModel


class SecurityCreate(BaseModel):
    ticker_code: str = Field(min_length=4, max_length=10)
    name: str
    name_english: str | None = None
    market: str | None = None
    industry_17: str | None = None
    industry_33: str | None = None


class SecurityRead(ORMModel):
    ticker_code: str
    local_code: str | None = None
    name: str
    name_english: str | None = None
    market: str | None = None
    industry_17: str | None = None
    industry_33: str | None = None
    is_active: bool
    listed_date: date | None = None


class PriceBarCreate(BaseModel):
    target_date: date
    open_price: Decimal = Field(alias="open")
    high_price: Decimal = Field(alias="high")
    low_price: Decimal = Field(alias="low")
    close_price: Decimal = Field(alias="close")
    adjusted_close: Decimal | None = None
    volume: int
    turnover_value: Decimal | None = None
    source_name: str = "manual"

    model_config = ConfigDict(populate_by_name=True)


class PriceBarRead(ORMModel):
    id: int
    ticker_code: str
    target_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    adjusted_close: Decimal | None = None
    volume: int
    turnover_value: Decimal | None = None
    source_name: str


class FinancialSnapshotCreate(BaseModel):
    target_date: date
    revenue: Decimal | None = None
    operating_profit: Decimal | None = None
    ordinary_profit: Decimal | None = None
    net_income: Decimal | None = None
    revenue_growth_yoy: Decimal | None = None
    operating_profit_growth_yoy: Decimal | None = None
    operating_margin: Decimal | None = None
    roe: Decimal | None = None
    equity_ratio: Decimal | None = None
    source_name: str = "manual"


class FinancialSnapshotRead(ORMModel):
    id: int
    ticker_code: str
    target_date: date
    revenue: Decimal | None = None
    operating_profit: Decimal | None = None
    ordinary_profit: Decimal | None = None
    net_income: Decimal | None = None
    revenue_growth_yoy: Decimal | None = None
    operating_profit_growth_yoy: Decimal | None = None
    operating_margin: Decimal | None = None
    roe: Decimal | None = None
    equity_ratio: Decimal | None = None
    source_name: str


class FlowSnapshotCreate(BaseModel):
    target_date: date
    average_daily_volume_20: int | None = None
    volume_ratio_20: Decimal | None = None
    margin_buy_ratio: Decimal | None = None
    margin_buy_balance: Decimal | None = None
    margin_sell_balance: Decimal | None = None
    credit_ratio: Decimal | None = None
    buy_balance_change_wow: Decimal | None = None
    sell_balance_change_wow: Decimal | None = None
    buy_balance_to_volume: Decimal | None = None
    sell_balance_to_volume: Decimal | None = None
    squeeze_potential_subscore: Decimal | None = None
    short_interest_ratio: Decimal | None = None
    float_turnover_ratio: Decimal | None = None
    large_holder_activity_score: Decimal | None = None
    source_name: str = "manual"


class FlowSnapshotRead(ORMModel):
    id: int
    ticker_code: str
    target_date: date
    average_daily_volume_20: int | None = None
    volume_ratio_20: Decimal | None = None
    margin_buy_ratio: Decimal | None = None
    margin_buy_balance: Decimal | None = None
    margin_sell_balance: Decimal | None = None
    credit_ratio: Decimal | None = None
    buy_balance_change_wow: Decimal | None = None
    sell_balance_change_wow: Decimal | None = None
    buy_balance_to_volume: Decimal | None = None
    sell_balance_to_volume: Decimal | None = None
    squeeze_potential_subscore: Decimal | None = None
    short_interest_ratio: Decimal | None = None
    float_turnover_ratio: Decimal | None = None
    large_holder_activity_score: Decimal | None = None
    source_name: str


class TechnicalFeatureRead(ORMModel):
    id: int
    ticker_code: str
    target_date: date
    sma_5: Decimal | None = None
    sma_25: Decimal | None = None
    sma_75: Decimal | None = None
    sma_200: Decimal | None = None
    sma_5_slope_pct: Decimal | None = None
    sma_25_slope_pct: Decimal | None = None
    sma_75_slope_pct: Decimal | None = None
    deviation_from_sma_25_pct: Decimal | None = None
    deviation_from_sma_75_pct: Decimal | None = None
    ma_gap_5_25_pct: Decimal | None = None
    ma_gap_25_75_pct: Decimal | None = None
    golden_cross_flag: bool = False
    dead_cross_flag: bool = False
    breakout_20d: bool = False
    breakout_60d: bool = False
    volume_ratio_20: Decimal | None = None
    volume_surge_ratio: Decimal | None = None
    atr_14: Decimal | None = None
    atr_pct_14: Decimal | None = None
    rsi_14: Decimal | None = None
    roc_20: Decimal | None = None
    macd_line: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None
    macd_bullish_cross_flag: bool = False
    macd_bearish_cross_flag: bool = False
    bollinger_mid_20: Decimal | None = None
    bollinger_upper_20: Decimal | None = None
    bollinger_lower_20: Decimal | None = None
    bollinger_width_20: Decimal | None = None
    upper_wick_ratio: Decimal | None = None
    lower_wick_ratio: Decimal | None = None
    body_ratio: Decimal | None = None
    close_position_ratio: Decimal | None = None
    gap_pct: Decimal | None = None
    gap_up_flag: bool = False
    gap_down_flag: bool = False
    consecutive_up_candles: int = 0
    consecutive_down_candles: int = 0
    range_compression_20: Decimal | None = None

    @computed_field(return_type=Decimal | None)
    @property
    def ma_5(self) -> Decimal | None:
        return self.sma_5

    @computed_field(return_type=Decimal | None)
    @property
    def ma_25(self) -> Decimal | None:
        return self.sma_25

    @computed_field(return_type=Decimal | None)
    @property
    def ma_75(self) -> Decimal | None:
        return self.sma_75

    @computed_field(return_type=Decimal | None)
    @property
    def ma_200(self) -> Decimal | None:
        return self.sma_200

    @computed_field(return_type=Decimal | None)
    @property
    def ma_5_slope(self) -> Decimal | None:
        return self.sma_5_slope_pct

    @computed_field(return_type=Decimal | None)
    @property
    def ma_25_slope(self) -> Decimal | None:
        return self.sma_25_slope_pct

    @computed_field(return_type=Decimal | None)
    @property
    def ma_75_slope(self) -> Decimal | None:
        return self.sma_75_slope_pct

    @computed_field(return_type=Decimal | None)
    @property
    def price_vs_ma_25(self) -> Decimal | None:
        return self.deviation_from_sma_25_pct

    @computed_field(return_type=Decimal | None)
    @property
    def price_vs_ma_75(self) -> Decimal | None:
        return self.deviation_from_sma_75_pct

    @computed_field(return_type=Decimal | None)
    @property
    def ma_gap_5_25(self) -> Decimal | None:
        return self.ma_gap_5_25_pct

    @computed_field(return_type=Decimal | None)
    @property
    def ma_gap_25_75(self) -> Decimal | None:
        return self.ma_gap_25_75_pct


class InterpretedMetricRead(BaseModel):
    key: str
    label: str
    value: str
    interpretation: str


class TechnicalContextRead(BaseModel):
    trend_subscore: Decimal
    momentum_subscore: Decimal
    volatility_subscore: Decimal
    price_action_subscore: Decimal
    volume_confirmation_subscore: Decimal
    moving_average_state: str
    momentum_state: str
    volatility_state: str
    price_action_state: str
    volume_confirmation_state: str
    interpretations: list[str]
    metrics: list[InterpretedMetricRead]


class FlowContextRead(BaseModel):
    liquidity_subscore: Decimal
    positioning_subscore: Decimal
    squeeze_potential_subscore: Decimal
    state_summary: str
    interpretations: list[str]
    metrics: list[InterpretedMetricRead]


class SecurityDetailResponse(BaseModel):
    security: SecurityRead
    latest_score: "ScoreRead | None" = None
    latest_features: TechnicalFeatureRead | None = None
    technical_context: TechnicalContextRead | None = None
    recent_events: list["EventRead"]
    latest_financials: FinancialSnapshotRead | None = None
    latest_flow: FlowSnapshotRead | None = None
    flow_context: FlowContextRead | None = None
    latest_prices: list[PriceBarRead]
    updated_at: datetime | None = None


from kabuhandan_hojo.schemas.events import EventRead  # noqa: E402
from kabuhandan_hojo.schemas.scores import ScoreRead  # noqa: E402

SecurityDetailResponse.model_rebuild()
